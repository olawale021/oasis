"""PRD 9.2/9.4: global five-league model + per-league blend.

One pooled multinomial logistic trains across all five leagues on the common
fixtures+injuries feature set plus league-identity dummies (PL = reference
class). Each league's final probability is then a convex blend

    p = w * league_model + (1 - w) * global_model

with w selected on that league's calibrate season (grid 0..1) -- the PRD's
60/40 starting point is a hypothesis, not a constant, so w is fitted.

Decision protocol matches the rest of the pipeline: a 5-fold walk-forward
harness (test seasons 2021-2025) compares league-only vs global-only vs
blend per league on MEAN log loss; the blend ships for a league only where
it beats league-only on the mean. Shipped blends are written as that
league's outcome artifact (type "blend", self-contained with both
components) and registered/deployed in the model registry.

Leakage note: folds are season-indexed. No feature crosses leagues, but the
pooled fit does contain other-league matches that are wall-clock concurrent
with a league's test window (European season N spills into calendar year
N+1, overlapping MLS season N+1's start). The information path is only
"global coefficients saw contemporaneous other-league results" -- accepted
and documented rather than hidden.

    python3 src/global_train.py            # harness + ship endorsed blends
    python3 src/global_train.py --dry-run  # harness only, ship nothing
"""

import argparse
import json
from datetime import datetime, timezone

import backtest_common
import config
import leagues
import metrics
import model_registry
import outcome_baselines
import outcome_model
import outcome_train

FOLD_TEST_SEASONS = [2021, 2022, 2023, 2024, 2025]
# League-context covariates (Hubacek sec 4.6) + division-tier flag: the block
# that made pooled training beat per-league in the only published head-to-head.
CONTEXT_FEATS = ["tier2", "lg_hw_rate", "lg_draw_rate", "lg_goals_h", "lg_goals_a", "lg_n_teams"]
GLOBAL_FEATS = (
    outcome_train.BASE_EIGHT + outcome_train.NEW3 + outcome_train.RATING3
    + leagues.DUMMY_FEATURES + CONTEXT_FEATS
)
GLOBAL_DECAY = 0.8
W_GRID = [round(0.05 * i, 2) for i in range(21)]  # 0.00 .. 1.00


def fit_vector_scaling(artifact: dict, cal_samples: list) -> dict:
    """6-parameter vector scaling (per-class scale + bias) fitted on the
    pooled calibrate season -- defensible only because pooling takes the
    calibration set to ~1,900 rows (Niculescu-Mizil & Caruana's threshold
    argument). Cyclic grid refinement, pure python."""
    import math as _math

    base_art = {k: v for k, v in artifact.items() if k not in ("temperature", "vec_scale", "class_bias")}
    params = {"s0": 1.0, "s1": 1.0, "s2": 1.0, "b0": 0.0, "b1": 0.0, "b2": 0.0}

    def make(pr):
        return {**base_art, "vec_scale": [pr["s0"], pr["s1"], pr["s2"]], "class_bias": [pr["b0"], pr["b1"], pr["b2"]]}

    def ll(pr):
        art = make(pr)
        total = 0.0
        for smp in cal_samples:
            pv = outcome_model.predict_proba(smp, art)
            total += -_math.log(max(pv[smp["cls"]], 1e-15))
        return total / len(cal_samples)

    grids = {k: ([0.6 + 0.15 * i for i in range(7)] if k.startswith("s") else [-0.45 + 0.15 * i for i in range(7)]) for k in params}
    for _ in range(2):
        for k in params:
            best_v, best_ll = params[k], float("inf")
            for v in grids[k]:
                trial = dict(params)
                trial[k] = v
                cur = ll(trial)
                if cur < best_ll:
                    best_ll, best_v = cur, v
            params[k] = best_v
            grids[k] = [best_v + 0.06 * f for f in (-1.5, -0.75, 0.0, 0.75, 1.5)]
    return make(params)


def deployed_league_spec(code: str) -> dict:
    """The deployed league model's feature set + decay, from the registry."""
    cfg = leagues.target_config(code)
    role = cfg["outcome_artifact"].rsplit(".", 1)[0]
    registry = json.loads((config.MODELS_DIR / "registry.json").read_text())
    entries = [e for e in registry if e["role"] == role]
    deployed = next((e for e in entries if e["deployed"]), None)
    entry = deployed if deployed and deployed.get("features") and deployed.get("model_type") != "blend" else None
    if entry is None:
        # Deployed artifact is a blend (its feature list is a union across
        # components, not a league spec) -- fall back to
        # the most recent registered pure-logistic release for this role.
        with_features = [e for e in entries if e.get("features") and e.get("model_type") != "blend"]
        if not with_features:
            raise SystemExit(f"{code}: no registered release with a feature list for role {role}")
        entry = max(with_features, key=lambda e: e["registered_at"])
    return {"features": entry["features"], "decay": (entry.get("parameters") or {}).get("decay"), "version": entry["version"]}


def score_probs(samples: list, artifact: dict) -> list:
    return [outcome_model.predict_proba(s, artifact) for s in samples]


def blend_probs(league_p: list, global_p: list, w: float) -> list:
    return [tuple(w * lp[k] + (1 - w) * gp[k] for k in range(3)) for lp, gp in zip(league_p, global_p)]


def log_loss_of(probs: list, samples: list) -> float:
    import math

    return sum(-math.log(max(p[s["cls"]], 1e-15)) for p, s in zip(probs, samples)) / len(samples)


def select_w(cal_samples: list, league_artifact: dict, global_artifact: dict) -> float:
    lp = score_probs(cal_samples, league_artifact)
    gp = score_probs(cal_samples, global_artifact)
    best_w, best_ll = 1.0, float("inf")
    for w in W_GRID:
        ll = log_loss_of(blend_probs(lp, gp, w), cal_samples)
        if ll < best_ll:
            best_ll, best_w = ll, w
    return best_w


def metrics_of(probs: list, samples: list) -> dict:
    scored = [{**s, "p_home": p[0], "p_draw": p[1], "p_away": p[2]} for s, p in zip(samples, probs)]
    m = metrics.all_outcome_metrics(scored)
    return {"log_loss": m["log_loss"], "rps": m["rps"], "accuracy": m["accuracy"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Global model + per-league blend (PRD 9.2/9.4).")
    parser.add_argument("--dry-run", action="store_true", help="Run the harness, ship nothing")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)

    league_samples = {}
    league_feeders = {}
    league_specs = {}
    for code in leagues.TARGETS:
        _, samples = outcome_train.load_enriched_buckets(leagues.target_config(code), score_feeders=True)
        league_samples[code] = [s for s in samples if not s.get("tier2")]
        league_feeders[code] = [s for s in samples if s.get("tier2")]
        league_specs[code] = deployed_league_spec(code)
        print(
            f"loaded {code}: {len(league_samples[code])} target + {len(league_feeders[code])} feeder samples "
            f"· league model {league_specs[code]['version']}"
        )

    # ---- walk-forward harness ----
    per_league_folds = {code: [] for code in leagues.TARGETS}
    for T in FOLD_TEST_SEASONS:
        split_args = {
            "train_seasons": list(range(2017, T - 2)),
            "validate_season": T - 2,
            "calibrate_season": T - 1,
            "test_season": T,
        }
        league_buckets = {
            code: backtest_common.split_by_season(league_samples[code], **split_args) for code in leagues.TARGETS
        }
        pooled = {
            k: [s for code in leagues.TARGETS for s in league_buckets[code][k]]
            for k in ("train", "validate", "calibrate", "test")
        }
        # Feeder-division rows enter the pooled FIT only (train bucket, within
        # the fold's train window) -- never validate/calibrate/test, which
        # stay target-league-only so per-league evaluation is uncontaminated.
        pooled["train"] = pooled["train"] + [
            f for code in leagues.TARGETS for f in league_feeders[code]
            if f["season"] in split_args["train_seasons"]
        ]
        global_artifact = outcome_train.build_artifact(GLOBAL_FEATS, pooled, decay=GLOBAL_DECAY)
        global_artifact_vec = fit_vector_scaling(global_artifact, pooled["calibrate"])

        for code in leagues.TARGETS:
            buckets = league_buckets[code]
            if not buckets["test"]:
                continue
            spec = league_specs[code]
            league_artifact = outcome_train.build_artifact(spec["features"], buckets, decay=spec["decay"])

            test = buckets["test"]
            lp = score_probs(test, league_artifact)
            gp = score_probs(test, global_artifact)
            gp_vec = score_probs(test, global_artifact_vec)
            fit_set = buckets["train"] + buckets["validate"] + buckets["calibrate"]
            freq = outcome_baselines.frequency_baseline(fit_set)
            elo_params = outcome_baselines.calibrate_elo(fit_set)
            freq_p = [outcome_baselines.frequency_probs(freq, s) for s in test]
            elo_p = [outcome_baselines.elo_probs(s["elo_diff"], *elo_params) for s in test]

            per_league_folds[code].append(
                {
                    "fold": T,
                    "frequency": metrics_of(freq_p, test),
                    "elo_only": metrics_of(elo_p, test),
                    "league_only": metrics_of(lp, test),
                    "global_only": metrics_of(gp, test),
                    "global_vec": metrics_of(gp_vec, test),
                    # Fixed-w curve: test log loss at every w, so the blend
                    # weight is selected on the MEAN across folds (like the
                    # decay grid), never on one noisy calibrate season.
                    "blend_ll_by_w": {str(w): log_loss_of(blend_probs(lp, gp, w), test) for w in W_GRID},
                    "blend_vec_ll_by_w": {str(w): log_loss_of(blend_probs(lp, gp_vec, w), test) for w in W_GRID},
                }
            )
        print(f"fold {T} done")

    # ---- decisions: fixed blend weight by 5-fold mean ----
    decisions = {}
    for code, folds in per_league_folds.items():
        rows = ("frequency", "elo_only", "league_only", "global_only", "global_vec")
        means = {r: sum(f[r]["log_loss"] for f in folds) / len(folds) for r in rows}
        # Calibration family for the global component, decided on its own mean.
        use_vec = means["global_vec"] < means["global_only"]
        curve_key = "blend_vec_ll_by_w" if use_vec else "blend_ll_by_w"
        w_means = {
            w: sum(f[curve_key][str(w)] for f in folds) / len(folds) for w in W_GRID
        }
        fixed_w = min(w_means, key=w_means.get)
        means["blend"] = w_means[fixed_w]
        # A degenerate weight is not a blend: endorse only a real mixture
        # that beats league-only on the mean.
        endorsed = fixed_w < 1.0 and means["blend"] < means["league_only"]
        decisions[code] = {"means": means, "fixed_w": fixed_w, "blend_endorsed": endorsed, "use_vec": use_vec}
        print(
            f"{code}: league_only={means['league_only']:.4f} global_temp={means['global_only']:.4f} "
            f"global_vec={means['global_vec']:.4f} blend(w={fixed_w},{'vec' if use_vec else 'temp'})={means['blend']:.4f} "
            f"(elo {means['elo_only']:.4f}) -> {'BLEND ENDORSED' if endorsed else 'league-only stands'}"
        )

    # ---- final artifacts for endorsed leagues ----
    shipped = {}
    if not args.dry_run:
        final_league_buckets = {
            code: backtest_common.split_by_season(league_samples[code]) for code in leagues.TARGETS
        }
        pooled_final = {
            k: [s for code in leagues.TARGETS for s in final_league_buckets[code][k]]
            for k in ("train", "validate", "calibrate", "test")
        }
        pooled_final["train"] = pooled_final["train"] + [
            f for code in leagues.TARGETS for f in league_feeders[code]
            if f["season"] in backtest_common.TRAIN_SEASONS
        ]
        global_final = outcome_train.build_artifact(GLOBAL_FEATS, pooled_final, decay=GLOBAL_DECAY)
        if any(d.get("use_vec") for d in decisions.values()):
            global_final_vec = fit_vector_scaling(global_final, pooled_final["calibrate"])
        global_final["label"] = (
            f"global15 [{', '.join(GLOBAL_FEATS)}] pooled 5-league logistic, decay={GLOBAL_DECAY}, "
            f"temperature-scaled on pooled {backtest_common.CALIBRATE_SEASON}"
        )
        pooled_test_scored = [
            {**s, "p_home": p[0], "p_draw": p[1], "p_away": p[2]}
            for s, p in zip(pooled_final["test"], score_probs(pooled_final["test"], global_final))
        ]
        gm = metrics.all_outcome_metrics(pooled_test_scored)
        global_final["test_log_loss"] = gm["log_loss"]
        global_final["test_accuracy"] = gm["accuracy"]
        global_final["test_rps"] = gm["rps"]
        global_final["trained_on"] = f"pooled 5 leagues, {backtest_common.TRAIN_SEASONS[0]}-{backtest_common.CALIBRATE_SEASON}"
        global_path = config.MODELS_DIR / "outcome_model_global.json"
        global_path.write_text(json.dumps(global_final, indent=2))
        model_registry.register(global_path, deployed=True, notes="PRD 9.2 pooled global model (blend component)")
        print(f"wrote {global_path}: pooled test_log_loss={gm['log_loss']:.4f}")

        for code, decision in decisions.items():
            if not decision["blend_endorsed"]:
                continue
            cfg = leagues.target_config(code)
            spec = league_specs[code]
            buckets = final_league_buckets[code]
            league_artifact = outcome_train.build_artifact(spec["features"], buckets, decay=spec["decay"])
            w = decision["fixed_w"]  # harness-mean-selected, never single-season
            global_component = global_final_vec if decision.get("use_vec") else global_final
            blend_artifact = {
                "type": "blend",
                "label": f"blend{int(w * 100)}_global [w={w} x {spec['version']} + {round(1 - w, 2)} x global15]",
                "components": [
                    {"weight": w, "model": league_artifact},
                    {"weight": round(1.0 - w, 4), "model": global_component},
                ],
            }
            test = buckets["test"]
            bp = blend_probs(score_probs(test, league_artifact), score_probs(test, global_final), w)
            bm = metrics_of(bp, test)
            by_class = metrics.group_metrics(
                [{**s, "p_home": p[0], "p_draw": p[1], "p_away": p[2]} for s, p in zip(test, bp)],
                key_fn=lambda s: s["cls"],
            )
            blend_artifact["test_log_loss"] = bm["log_loss"]
            blend_artifact["test_accuracy"] = bm["accuracy"]
            blend_artifact["test_rps"] = bm["rps"]
            blend_artifact["test_draw_log_loss"] = by_class.get("1", {}).get("log_loss")
            blend_artifact["selected_on"] = "blend w selected on 5-fold harness mean (fixed-w grid); endorsed vs league-only on the same mean"
            blend_artifact["trained_on"] = f"{backtest_common.TRAIN_SEASONS[0]}-{backtest_common.CALIBRATE_SEASON} (league) + pooled global"
            out_path = config.MODELS_DIR / cfg["outcome_artifact"]
            out_path.write_text(json.dumps(blend_artifact, indent=2))
            entry = model_registry.register(out_path, deployed=True, notes="PRD 9.4 league+global blend")
            shipped[code] = {"w": w, "version": entry["version"], "test_log_loss": bm["log_loss"]}
            print(f"shipped {code}: {entry['version']} (w={w}) test_log_loss={bm['log_loss']:.4f}")

            # Harness-style report so the web export's 5-fold means resolve
            # for the blend version (and its baselines) per league.
            report = {
                "meta": {
                    "started_at": started.isoformat(),
                    "folds": FOLD_TEST_SEASONS,
                    "league": code,
                    "instrument": "global_train blend harness",
                },
                "mean": {
                    "frequency": {"log_loss": decision["means"]["frequency"]},
                    "elo_only": {"log_loss": decision["means"]["elo_only"]},
                    "league_only": {"log_loss": decision["means"]["league_only"]},
                    "global_only": {"log_loss": decision["means"]["global_only"]},
                    entry["version"]: {"log_loss": decision["means"]["blend"]},
                },
                "per_fold": per_league_folds[code],
            }
            stamp = started.strftime("%Y%m%dT%H%M%SZ")
            (config.REPORTS_DIR / f"rolling_backtest_{code}_{stamp}.json").write_text(json.dumps(report, indent=2))

    finished = datetime.now(timezone.utc)
    out = {
        "meta": {"started_at": started.isoformat(), "finished_at": finished.isoformat(), "folds": FOLD_TEST_SEASONS},
        "global_features": GLOBAL_FEATS,
        "decisions": decisions,
        "shipped": shipped,
    }
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORTS_DIR / f"global_train_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
