"""Walk-forward evaluation harness. SHIPS NOTHING.

Compares fixed candidates across multiple test seasons; the production
artifact still comes exclusively from outcome_train.py / blend_train.py. A
candidate is "real" only if it beats the incumbent (logistic9, no decay) on
MEAN log-loss across folds -- single-fold wins do not count.

GBM excluded: it lost decisively on the single split and each fold would cost
a 12-combo grid.
"""

import json
import math
from datetime import datetime, timezone

import backtest_common
import blend_train
import config
import leagues
import goals_train
import metrics
import outcome_baselines
import outcome_model
import outcome_train

DEFAULT_FOLD_TEST_SEASONS = [2021, 2022, 2023, 2024, 2025]
THIN_TRAIN_FOLDS = [2021]  # 2 train seasons; validate/calibrate are COVID-era
DECAY = 0.8  # PRD 8.3 target; outcome_train.py picks the exact shipping decay

B_DRAWS = [round(-0.5 + 0.05 * i, 2) for i in range(21)]

ALLSCHED = {"rest_diff": "rest_all_diff", "congestion_diff": "congestion_all_diff",
            "short_rest_diff": "short_rest_all_diff", "long_rest_diff": "long_rest_all_diff"}


def with_allsched(feats: list) -> list:
    """Swap league-only schedule features for their all-competition twins."""
    return [ALLSCHED.get(f, f) for f in feats]


def deployed_rows(code: str) -> list:
    """The league's deployed feature set as a candidate, plus the same set
    with all-competition rest/congestion -- the paired test for
    ingest_team_fixtures.py. Empty if no logistic release is registered."""
    try:
        import global_train
        spec = global_train.deployed_league_spec(code)
    except Exception:
        return []
    feats, decay = spec["features"], spec["decay"]
    rows = [{"name": "deployed", "kind": "logistic", "feats": feats, "decay": decay}]
    if any(f in ALLSCHED for f in feats):
        rows.append({"name": "deployed_allsched", "kind": "logistic", "feats": with_allsched(feats), "decay": decay})
    # Transfermarkt squad value (ingest_squad_values.py): log ratio of squad values.
    rows.append({"name": "deployed_value", "kind": "logistic", "feats": feats + ["value_diff"], "decay": decay})
    # API-Football xG (2022/23+): rolling xG for/against. Fair only on folds
    # where the data exists: run with --folds 2024-2025.
    # Player-based strength (player_ratings.py): expected-XI plus-minus sum.
    rows.append({"name": "deployed_xi", "kind": "logistic", "feats": feats + ["xi_strength_diff"], "decay": decay})
    xg = [f for f in ("xg_diff", "xga_diff") if f not in feats]
    if xg:
        rows.append({"name": "deployed_xg", "kind": "logistic", "feats": feats + xg, "decay": decay})
    return rows


def rows_for(enriched: bool) -> list:
    """Candidate rows for one league's harness run. Enriched leagues (shot
    stats + lineups ingested) get the full historical ladder plus the new
    venue/trend/schedule-strength candidates; the rest get the
    fixtures+injuries ladder plus the same new candidates."""
    if enriched:
        return [
            {"name": "logistic9", "kind": "logistic", "feats": outcome_train.NINE, "decay": None},
            {"name": "logistic9_decay", "kind": "logistic", "feats": outcome_train.NINE, "decay": DECAY},
            {"name": "logistic11_sched", "kind": "logistic", "feats": outcome_train.ELEVEN_SCHED, "decay": DECAY},
            {"name": "logistic11_ew", "kind": "logistic", "feats": outcome_train.ELEVEN_EW, "decay": DECAY},
            {"name": "logistic12_corn", "kind": "logistic", "feats": outcome_train.TWELVE_CORN, "decay": DECAY},
            {"name": "logistic13_xg", "kind": "logistic", "feats": outcome_train.THIRTEEN_XG, "decay": DECAY},
            {"name": "logistic14_ks", "kind": "logistic", "feats": outcome_train.FOURTEEN_KS, "decay": DECAY},
            {"name": "logistic12_close", "kind": "logistic", "feats": outcome_train.TWELVE_CLOSE, "decay": DECAY},
            {"name": "logistic14_draw", "kind": "logistic", "feats": outcome_train.FOURTEEN_DRAW, "decay": DECAY},
            {"name": "logistic12_venue", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + ["venue_form_diff"], "decay": DECAY},
            {"name": "logistic12_trend", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + ["elo_trend_diff"], "decay": DECAY},
            {"name": "logistic12_schedstr", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + ["sched_strength_diff"], "decay": DECAY},
            {"name": "logistic14_new3", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + outcome_train.NEW3, "decay": DECAY},
            {"name": "full_ratings", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + outcome_train.RATING3, "decay": DECAY},
            {"name": "full_minus_h2h", "kind": "logistic", "feats": outcome_train._minus(outcome_train.ELEVEN_EW, "h2h_signal"), "decay": DECAY},
            {"name": "full_ghost", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + outcome_train.GHOST, "decay": DECAY},
            {"name": "full_restbins", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + outcome_train.RESTBINS, "decay": DECAY},
            {"name": "full_ew10", "kind": "logistic", "feats": outcome_train._swap(outcome_train.ELEVEN_EW, outcome_train.EW_TRIO, outcome_train.EW10_TRIO), "decay": DECAY},
            {"name": "ratings_core", "kind": "logistic", "feats": outcome_train.RATINGS_CORE, "decay": DECAY},
            {"name": "full_kitchen", "kind": "logistic", "feats": outcome_train.ELEVEN_EW + outcome_train.NEW3 + outcome_train.RATING3 + outcome_train.GHOST, "decay": DECAY},
            {"name": "ordered_elo", "kind": "ordered", "feat": "elo_diff", "decay": DECAY},
            {"name": "ordered_pi", "kind": "ordered", "feat": "pi_pred_gd", "decay": DECAY},
            {"name": "davidson_elo", "kind": "davidson", "feat": "elo_diff", "decay": DECAY},
            {"name": "dc_outcome", "kind": "dc", "decay": DECAY},
            {"name": "dc_outcome_nodecay", "kind": "dc", "decay": None},
            {"name": "blend_draw_dc", "kind": "blend", "feats": outcome_train.FOURTEEN_DRAW, "decay": DECAY},
            {"name": "logistic14_draw_bias", "kind": "logistic_bias", "feats": outcome_train.FOURTEEN_DRAW, "decay": DECAY},
        ]
    return [
        {"name": "logistic7_base", "kind": "logistic", "feats": outcome_train.BASE_SEVEN, "decay": None},
        {"name": "logistic8_inj", "kind": "logistic", "feats": outcome_train.BASE_EIGHT, "decay": None},
        {"name": "logistic8_inj_decay", "kind": "logistic", "feats": outcome_train.BASE_EIGHT, "decay": DECAY},
        {"name": "logistic9_venue", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + ["venue_form_diff"], "decay": None},
        {"name": "logistic9_trend", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + ["elo_trend_diff"], "decay": None},
        {"name": "logistic9_schedstr", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + ["sched_strength_diff"], "decay": None},
        {"name": "logistic11_new3", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + outcome_train.NEW3, "decay": None},
        {"name": "base_ratings", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + outcome_train.RATING3, "decay": None},
        {"name": "base_minus_h2h", "kind": "logistic", "feats": outcome_train._minus(outcome_train.BASE_EIGHT, "h2h_signal"), "decay": None},
        {"name": "base_ghost", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + outcome_train.GHOST, "decay": None},
        {"name": "base_restbins", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + outcome_train.RESTBINS, "decay": None},
        {"name": "base_ew10", "kind": "logistic", "feats": outcome_train._swap(outcome_train.BASE_EIGHT, outcome_train.EW_TRIO, outcome_train.EW10_TRIO), "decay": None},
        {"name": "ratings_core", "kind": "logistic", "feats": outcome_train.RATINGS_CORE, "decay": None},
        {"name": "base_kitchen", "kind": "logistic", "feats": outcome_train.BASE_EIGHT + outcome_train.NEW3 + outcome_train.RATING3 + outcome_train.GHOST, "decay": None},
        {"name": "ordered_elo", "kind": "ordered", "feat": "elo_diff", "decay": None},
        {"name": "ordered_pi", "kind": "ordered", "feat": "pi_pred_gd", "decay": None},
        {"name": "davidson_elo", "kind": "davidson", "feat": "elo_diff", "decay": None},
        {"name": "dc_outcome", "kind": "dc", "decay": None},
    ]


# Incumbent per ladder: the control the mean-log-loss rule is judged against.
INCUMBENT = "logistic9"
BASE_INCUMBENT = "logistic8_inj"


def select_temperature_bias(artifact: dict, cal_samples: list) -> dict:
    """(T, b_draw) joint grid on calibrate by log-loss -- the one calibration
    variant evaluated (full vector scaling rejected: 4 params on ~380 rows)."""
    logits = [blend_train._logistic_logits(s, artifact) for s in cal_samples]
    cls = [s["cls"] for s in cal_samples]
    eps = 1e-15
    n = len(cls)
    best = None
    for T in outcome_train.TEMPERATURES:
        for b in B_DRAWS:
            total = 0.0
            for i in range(n):
                z = logits[i]
                p = blend_train._softmax([z[0] / T, z[1] / T + b, z[2] / T])
                total += -math.log(max(p[cls[i]], eps))
            ll = total / n
            if best is None or ll < best[2]:
                best = (T, b, ll)
    T, b, _ = best
    return {**artifact, "temperature": T, "class_bias": [0.0, b, 0.0]}


def _row_metrics(scored: list) -> dict:
    m = metrics.all_outcome_metrics(scored)
    by_class = metrics.group_metrics(scored, key_fn=lambda s: s["cls"])
    return {
        "log_loss": m["log_loss"],
        "rps": m["rps"],
        "accuracy": m["accuracy"],
        "draw_log_loss": by_class.get("1", {}).get("log_loss"),
        "ece": metrics.calibration_error(scored)["ece"],
        "n": m["n"],
    }


def run_fold(samples: list, T: int, rows: list) -> dict:
    buckets = backtest_common.split_by_season(
        samples,
        train_seasons=list(range(2017, T - 2)),
        validate_season=T - 2,
        calibrate_season=T - 1,
        test_season=T,
    )
    backtest_common.verify_no_leakage(buckets)
    test = buckets["test"]
    fit_set = buckets["train"] + buckets["validate"] + buckets["calibrate"]

    fold = {}
    freq = outcome_baselines.frequency_baseline(fit_set)
    elo_params = outcome_baselines.calibrate_elo(fit_set)
    fold["frequency"] = _row_metrics(
        outcome_baselines.score_samples(test, lambda s: outcome_baselines.frequency_probs(freq, s))
    )
    fold["elo_only"] = _row_metrics(
        outcome_baselines.score_samples(test, lambda s: outcome_baselines.elo_probs(s["elo_diff"], *elo_params))
    )

    cache = {}  # (tuple(feats), decay) -> logistic artifact; decay -> goals artifact

    def logistic_artifact(feats, decay):
        key = ("logistic", tuple(feats), decay)
        if key not in cache:
            cache[key] = outcome_train.build_artifact(feats, buckets, decay=decay)
        return cache[key]

    def goals_artifact(decay):
        key = ("goals", decay)
        if key not in cache:
            cache[key] = goals_train.fit_goals_artifact(buckets, decay=decay)
        return cache[key]

    for row in rows:
        kind = row["kind"]
        if kind == "logistic":
            artifact = logistic_artifact(row["feats"], row["decay"])
        elif kind == "ordered":
            artifact = outcome_train.build_ordered_artifact(row["feat"], buckets, decay=row["decay"])
        elif kind == "davidson":
            artifact = outcome_train.build_davidson_artifact(row["feat"], buckets, decay=row["decay"])
        elif kind == "dc":
            artifact = {"type": "dc_outcome", "max_goals": 6, "goals": goals_artifact(row["decay"])}
        elif kind == "blend":
            logistic = dict(logistic_artifact(row["feats"], row["decay"]))
            goals = goals_artifact(row["decay"])
            logits, dc_probs, cls = blend_train.cache_calibrate_inputs(buckets["calibrate"], logistic, goals)
            Tsel, w, _ = blend_train.select_blend(logits, dc_probs, cls)
            logistic["temperature"] = Tsel
            artifact = {
                "type": "blend",
                "components": [
                    {"weight": w, "model": logistic},
                    {"weight": round(1.0 - w, 4), "model": {"type": "dc_outcome", "max_goals": 6, "goals": goals}},
                ],
            }
            fold.setdefault("_blend_params", {})[row["name"]] = {"T": Tsel, "w": w}
        elif kind == "logistic_bias":
            base = logistic_artifact(row["feats"], row["decay"])
            artifact = select_temperature_bias(base, buckets["calibrate"])
            fold.setdefault("_bias_params", {})[row["name"]] = {
                "T": artifact["temperature"],
                "b_draw": artifact["class_bias"][1],
            }
        else:
            raise ValueError(f"unknown row kind {kind!r}")

        scored = outcome_train._score(test, artifact)
        fold[row["name"]] = _row_metrics(scored)

    return fold


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Walk-forward harness for one league. Ships nothing.")
    parser.add_argument("--league", type=str, default="pl", help=f"League code: {list(leagues.TARGETS)}")
    parser.add_argument(
        "--folds",
        type=str,
        default=None,
        help='Test seasons for the folds, e.g. "2023-2025" or "2021,2023,2025" (default: 2021-2025)',
    )
    parser.add_argument("--only", type=str, default=None, help="comma list of candidate names to run (others skipped)")
    args = parser.parse_args()

    if args.folds:
        FOLD_TEST_SEASONS = []
        for part in args.folds.split(","):
            if "-" in part:
                lo, hi = part.split("-")
                FOLD_TEST_SEASONS.extend(range(int(lo), int(hi) + 1))
            else:
                FOLD_TEST_SEASONS.append(int(part))
    else:
        FOLD_TEST_SEASONS = DEFAULT_FOLD_TEST_SEASONS
    league_cfg = leagues.target_config(args.league)

    started = datetime.now(timezone.utc)
    conn, samples = outcome_train.load_enriched_buckets(league_cfg)

    n_stats = conn.execute(
        "SELECT COUNT(*) FROM fixture_statistics fs JOIN fixtures f ON f.fixture_id = fs.fixture_id"
        " WHERE f.league_id = ?",
        (league_cfg["league_id"],),
    ).fetchone()[0]
    enriched = n_stats > 1000
    rows = rows_for(enriched) + deployed_rows(args.league)
    if args.only:
        keep = {n.strip() for n in args.only.split(",")}
        rows = [r for r in rows if r["name"] in keep]
    incumbent = INCUMBENT if enriched else BASE_INCUMBENT
    if args.only and incumbent not in {r["name"] for r in rows}:
        incumbent = rows[0]["name"]  # paired subset run: first listed row is the control
    print(f"league={args.league} enriched={enriched} incumbent={incumbent} rows={len(rows)}")

    per_fold = {}
    for T in FOLD_TEST_SEASONS:
        print(f"\n=== fold: test={T} (train=2017-{T - 3}, validate={T - 2}, calibrate={T - 1}) ===")
        per_fold[str(T)] = run_fold(samples, T, rows)

    row_names = ["frequency", "elo_only"] + [r["name"] for r in rows]
    metric_keys = ["log_loss", "rps", "accuracy", "draw_log_loss", "ece"]

    def mean_over(folds):
        out = {}
        for name in row_names:
            out[name] = {
                k: sum(per_fold[str(T)][name][k] for T in folds) / len(folds) for k in metric_keys
            }
        return out

    mean_all = mean_over(FOLD_TEST_SEASONS)
    non_thin = [T for T in FOLD_TEST_SEASONS if T not in THIN_TRAIN_FOLDS]
    mean_excl = mean_over(non_thin)

    incumbent_ll = mean_all[incumbent]["log_loss"]
    best_name = min(row_names, key=lambda n: mean_all[n]["log_loss"])
    decision = {
        "incumbent": incumbent,
        "incumbent_mean_log_loss": incumbent_ll,
        "best_by_mean_log_loss": best_name,
        "best_mean_log_loss": mean_all[best_name]["log_loss"],
        "beats_incumbent": mean_all[best_name]["log_loss"] < incumbent_ll,
        "rule": "a candidate is real only if it beats the incumbent on MEAN log-loss across ALL folds; "
        "single-fold wins do not count; the shipped artifact comes only from outcome_train.py/blend_train.py",
    }

    print(f"\n{'row':24s} " + " ".join(f"{T:>7d}" for T in FOLD_TEST_SEASONS) + f" {'mean':>7s} {'drawLL':>7s}")
    for name in row_names:
        cells = " ".join(f"{per_fold[str(T)][name]['log_loss']:7.4f}" for T in FOLD_TEST_SEASONS)
        print(f"{name:24s} {cells} {mean_all[name]['log_loss']:7.4f} {mean_all[name]['draw_log_loss']:7.4f}")
    print(f"\ndecision: best={best_name} ({mean_all[best_name]['log_loss']:.4f}) "
          f"vs incumbent {incumbent} ({incumbent_ll:.4f}) -> beats_incumbent={decision['beats_incumbent']}")

    finished = datetime.now(timezone.utc)
    report = {
        "meta": {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "folds": FOLD_TEST_SEASONS,
            "thin_train_folds": THIN_TRAIN_FOLDS,
            "decay": DECAY,
            "league": args.league,
            "rows": [{k: (list(v) if isinstance(v, list) else v) for k, v in r.items()} for r in rows],
            "decision_rule": decision["rule"],
        },
        "per_fold": per_fold,
        "mean": mean_all,
        "mean_excl_thin": mean_excl,
        "decision": decision,
    }

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = config.REPORTS_DIR / f"rolling_backtest_{args.league}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps(report, indent=2))
    (config.STATUS_DIR / "rolling_backtest_status.json").write_text(
        json.dumps(
            {
                "success": True,
                "refreshed_at": finished.isoformat(),
                "duration_ms": int((finished - started).total_seconds() * 1000),
                "decision": decision,
            },
            indent=2,
        )
    )
    print(f"\nwrote {report_path}")


if __name__ == "__main__":
    main()
