import json
import sys
from datetime import datetime, timezone

import backtest_common
import config
import db
import goals_model
import leagues
import matches as matches_module
import metrics
import outcome_baselines
import outcome_model
import promotion
import richer_features


def build_outcome_section(buckets: dict, all_samples: list, league_cfg: dict) -> dict:
    freq = outcome_baselines.frequency_baseline(buckets["train"])
    elo_params = outcome_baselines.calibrate_elo(buckets["train"])

    outcome_model_path = config.MODELS_DIR / league_cfg["outcome_artifact"]
    model = outcome_model.load_model(outcome_model_path)

    # Optional GBM candidate -- narrow except so a fresh checkout (no
    # outcome_train_gbm.py run yet) skips the row instead of crashing, while
    # the required logistic artifact above stays fatal-if-missing.
    gbm_model = None
    gbm_path = config.MODELS_DIR / "outcome_model_pl_gbm.json" if league_cfg["code"] == "pl" else config.MODELS_DIR / "___absent___.json"
    try:
        gbm_model = outcome_model.load_model(gbm_path)
    except FileNotFoundError:
        print(
            f"[evaluate_report] no GBM candidate at {gbm_path} -- skipping gbm baseline row "
            f"(run outcome_train_gbm.py to produce it)",
            file=sys.stderr,
        )

    def uniform_probs(s):
        return (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)

    def freq_probs(s):
        return outcome_baselines.frequency_probs(freq, s)

    def elo_only_probs(s):
        return outcome_baselines.elo_probs(s["elo_diff"], *elo_params)

    def logistic_probs(s):
        return outcome_model.predict_proba(s, model)

    baselines = {
        "uniform": uniform_probs,
        "frequency": freq_probs,
        "elo_only": elo_only_probs,
        "logistic": logistic_probs,
    }
    if gbm_model is not None:
        baselines["gbm"] = lambda s: outcome_model.predict_proba(s, gbm_model)

    # DC-derived 1X2 from the (always-present) goals artifact.
    goals = goals_model.load_model(config.MODELS_DIR / league_cfg["goals_artifact"])
    dc_wrapper = {"type": "dc_outcome", "max_goals": 6, "goals": goals}
    baselines["dc_outcome"] = lambda s: outcome_model.predict_proba(s, dc_wrapper)

    # Optional blend artifact (only exists if blend_train.py ran and won).
    blend_path = config.MODELS_DIR / "outcome_blend_pl.json"
    try:
        blend_model = outcome_model.load_model(blend_path)
        baselines["blend"] = lambda s: outcome_model.predict_proba(s, blend_model)
    except FileNotFoundError:
        print(f"[evaluate_report] no blend artifact at {blend_path} -- skipping blend row", file=sys.stderr)

    test_scored = {name: outcome_baselines.score_samples(buckets["test"], fn) for name, fn in baselines.items()}
    global_section = {name: metrics.all_outcome_metrics(scored) for name, scored in test_scored.items()}

    all_scored_logistic = outcome_baselines.score_samples(all_samples, logistic_probs)
    per_season = metrics.group_metrics(all_scored_logistic, key_fn=lambda s: s["season"])

    logistic_test = test_scored["logistic"]
    by_outcome_class = metrics.group_metrics(logistic_test, key_fn=lambda s: s["cls"])
    by_confidence_band = metrics.calibration_error(logistic_test)
    by_outcome_class_per_baseline = {
        name: metrics.group_metrics(scored, key_fn=lambda s: s["cls"]) for name, scored in test_scored.items()
    }

    # Majority-class row: predicts the train-majority outcome deterministically.
    # An accuracy-only baseline -- as a degenerate 0/1 "probability" forecast
    # its log loss is unbounded, so probability metrics are null by design.
    majority_cls = max(range(3), key=lambda c: (freq["home"], freq["draw"], freq["away"])[c])
    majority_accuracy = sum(1 for s in buckets["test"] if s["cls"] == majority_cls) / max(len(buckets["test"]), 1)
    global_section["majority"] = {
        "log_loss": None,
        "brier": None,
        "rps": None,
        "accuracy": majority_accuracy,
        "balanced_accuracy": None,
        "n": len(buckets["test"]),
        "note": f"always predicts {['home', 'draw', 'away'][majority_cls]} (train majority); accuracy-only baseline",
    }

    # Calibration slope/intercept for the shipped model (target: slope 1, intercept 0).
    slope_intercept = metrics.calibration_slope_intercept(logistic_test)

    # Paired bootstrap 95% CIs on the log-loss delta vs each serious baseline
    # -- tells us whether a small gap (e.g. vs elo-only) is real or noise.
    bootstrap = {
        f"logistic_minus_{name}": metrics.paired_bootstrap_log_loss_delta(logistic_test, test_scored[name])
        for name in ("frequency", "elo_only")
    }

    return {
        "confusion_matrix": metrics.confusion_matrix(logistic_test),
        "calibration_slope_intercept": slope_intercept,
        "bootstrap_log_loss_deltas": bootstrap,
        "global": global_section,
        "per_season": per_season,
        "by_outcome_class": by_outcome_class,
        "by_outcome_class_per_baseline": by_outcome_class_per_baseline,
        "by_confidence_band": by_confidence_band,
        "elo_calibration_params": {"scale": elo_params[0], "d0": elo_params[1], "tau": elo_params[2]},
        "frequency_baseline": freq,
    }, test_scored


def build_goals_section(buckets: dict, league_cfg: dict) -> dict:
    model = goals_model.load_model(config.MODELS_DIR / league_cfg["goals_artifact"])
    test_scored = []
    for s in buckets["test"]:
        mu_home, mu_away = goals_model.expected_goals(s["home_team_id"], s["away_team_id"], model, s.get("elo_diff", 0.0))
        test_scored.append({**s, "mu_home": mu_home, "mu_away": mu_away})

    rho = model.get("rho", 0.0)
    return {
        "poisson_deviance": metrics.poisson_deviance(test_scored),
        "mean_abs_goal_error": metrics.mean_abs_goal_error(test_scored),
        "exact_score_accuracy": metrics.exact_score_accuracy(test_scored, rho=rho),
        "ou_calibration": metrics.ou_calibration(test_scored, rho=rho),
        "btts_calibration": metrics.btts_calibration(test_scored, rho=rho),
        "rho": rho,
    }


def build_baseline_comparison_table(global_section: dict) -> list:
    order = ["uniform", "frequency", "majority", "elo_only", "logistic"]
    for optional in ("gbm", "dc_outcome", "blend"):
        if optional in global_section:
            order.append(optional)
    rows = []
    for name in order:
        row = {
            "baseline": name,
            "log_loss": global_section[name]["log_loss"],
            "brier": global_section[name]["brier"],
            "rps": global_section[name]["rps"],
            "accuracy": global_section[name]["accuracy"],
            "balanced_accuracy": global_section[name].get("balanced_accuracy"),
        }
        rows.append(row)

    freq_ll = global_section["frequency"]["log_loss"]
    elo_ll = global_section["elo_only"]["log_loss"]
    for row in rows:
        if row["log_loss"] is None:
            continue
        if row["baseline"] not in ("frequency", "uniform"):
            row["beats_frequency"] = row["log_loss"] < freq_ll
        if row["baseline"] in ("logistic", "gbm", "dc_outcome", "blend"):
            row["beats_elo_only"] = row["log_loss"] < elo_ll
    return rows


def _fmt(v, width: int = 6) -> str:
    return f"{v:.4f}" if v is not None else "—".center(6)


def print_summary(table: list, outcome_section: dict) -> None:
    print("\n--- baseline comparison (test season) ---")
    for row in table:
        print(
            f"  {row['baseline']:10s} log_loss={_fmt(row['log_loss'])} brier={_fmt(row['brier'])} "
            f"rps={_fmt(row['rps'])} accuracy={_fmt(row['accuracy'])} bal_acc={_fmt(row['balanced_accuracy'])}"
        )

    si = outcome_section["calibration_slope_intercept"]
    print(f"\n  calibration: slope={si['slope']:.3f} (target 1.0) intercept={si['intercept']:+.3f} (target 0.0)")

    for name, ci in outcome_section["bootstrap_log_loss_deltas"].items():
        verdict = "SIGNIFICANT" if ci["significant"] else "not significant (CI includes 0)"
        print(
            f"  {name}: Δlog_loss={ci['delta']:+.4f} "
            f"[95% CI {ci['ci_lo']:+.4f}, {ci['ci_hi']:+.4f}] -> {verdict}"
        )

    cm = outcome_section["confusion_matrix"]
    print("\n  confusion matrix (rows=actual, cols=predicted home/draw/away):")
    for label, counts in zip(cm["labels"], cm["rows_actual_cols_predicted"]):
        print(f"    {label:5s} {counts}")

    logistic = next(r for r in table if r["baseline"] == "logistic")
    if not logistic.get("beats_frequency") or not logistic.get("beats_elo_only"):
        print(
            "\n  WARNING: logistic does not beat one or more baselines on held-out test season "
            f"(beats_frequency={logistic.get('beats_frequency')}, beats_elo_only={logistic.get('beats_elo_only')})"
        )
    else:
        print("\n  OK: logistic beats both frequency and elo-only baselines on held-out test season")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate a league model against baselines.")
    parser.add_argument("--league", type=str, default="pl", help=f"League code: {list(leagues.TARGETS)}")
    args = parser.parse_args()
    league_cfg = leagues.target_config(args.league)
    target_id, feeder_id = league_cfg["league_id"], league_cfg["feeder_id"]

    started = datetime.now(timezone.utc)
    conn = db.get_connection()
    db.init_db(conn)

    league_ids = [target_id] + ([feeder_id] if feeder_id else [])
    matches = matches_module.load_matches(conn, league_ids)
    transitions = (
        promotion.compute_transitions(conn, target_id, feeder_id, backtest_common.ALL_SEASONS)
        if feeder_id
        else {}
    )
    samples = backtest_common.collect_samples(matches, transitions, use_mov=True, target_league_id=target_id)
    samples = richer_features.enrich_samples(samples, conn, league_id=target_id)
    buckets = backtest_common.split_by_season(samples)
    backtest_common.verify_no_leakage(buckets)

    try:
        outcome_section, test_scored_by_baseline = build_outcome_section(buckets, samples, league_cfg)
        goals_section = build_goals_section(buckets, league_cfg)
    except FileNotFoundError as exc:
        print(f"[evaluate_report] {exc}", file=sys.stderr)
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "evaluate_report_status.json").write_text(
            json.dumps(
                {"success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)},
                indent=2,
            )
        )
        raise SystemExit(1)

    baseline_comparison_table = build_baseline_comparison_table(outcome_section["global"])
    print_summary(baseline_comparison_table, outcome_section)

    finished = datetime.now(timezone.utc)

    report = {
        "meta": {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "seasons": {
                "train": backtest_common.TRAIN_SEASONS,
                "validate": backtest_common.VALIDATE_SEASON,
                "calibrate": backtest_common.CALIBRATE_SEASON,
                "test": backtest_common.TEST_SEASON,
            },
            "min_games": backtest_common.MIN_GAMES,
            "selection_policy": (
                "Models are selected on out-of-sample log loss (single-split validate for the ladder, "
                "walk-forward mean across folds as the final arbiter) with calibration required. "
                "Accuracy and balanced accuracy are reported for context only and are never a "
                "selection criterion."
            ),
            "home_advantage": 60.0,
        },
        "outcome": outcome_section,
        "goals": goals_section,
        "baseline_comparison_table": baseline_comparison_table,
    }

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)

    report_path = config.REPORTS_DIR / f"evaluate_report_{league_cfg['code']}_{backtest_common.TEST_SEASON}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    logistic_row = next(r for r in baseline_comparison_table if r["baseline"] == "logistic")
    status = {
        "success": True,
        "refreshed_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "headline": {
            "logistic_test_log_loss": logistic_row["log_loss"],
            "beats_frequency": logistic_row.get("beats_frequency"),
            "beats_elo_only": logistic_row.get("beats_elo_only"),
        },
    }
    (config.STATUS_DIR / "evaluate_report_status.json").write_text(json.dumps(status, indent=2))

    print(f"\nwrote {report_path}")


if __name__ == "__main__":
    main()
