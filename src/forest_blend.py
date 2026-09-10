"""Random forest as a third blend component -- walk-forward gate + ship.

Question: does adding a per-league random forest (forest_train.py) to the
deployed league+global logistic blend lower log loss on the 5-fold
walk-forward mean? Same rule as every other candidate: judged on the MEAN
across test seasons 2021-2025; single-fold wins do not count.

Per fold T (train 2017..T-3, validate T-2, calibrate T-1, test T):
  league logistic  -- deployed feature set + decay (global_train spec)
  global logistic  -- GLOBAL_FEATS on the pooled fit (+feeders), vec
                      scaling where the deployed decision uses it
  forest           -- league features, forest_train protocol
  blend2 = w*league + (1-w)*global with the deployed fixed w
  blend3(v) = (1-v)*blend2 + v*forest for v on a fixed grid

Decision per league: v* minimises the 5-fold mean; endorsed only if v* > 0
and mean(blend2) - mean(blend3) >= MIN_GAIN (0.001 -- smaller gains are
inside fold noise and not worth the artifact).

    python3 src/forest_blend.py            # harness only, ships nothing
    python3 src/forest_blend.py --ship     # also writes evaluation-track
                                           # artifacts for endorsed leagues

Shipping mirrors global_train.py: outcome_model_{code}.json becomes a
3-component blend fit on the default split (2025 held out), registered as
deployed, plus a harness-style rolling_backtest_{code}_*.json so the web
export resolves the new version's 5-fold mean. refold_live.py reads this
script's latest report to carry v into the *_live track.
"""

import argparse
import glob
import json
from datetime import datetime, timezone

import backtest_common
import config
import forest_train
import global_train
import leagues
import metrics
import outcome_baselines
import outcome_train
from global_train import GLOBAL_DECAY, GLOBAL_FEATS, blend_probs, fit_vector_scaling, log_loss_of, metrics_of, score_probs

FOLD_TEST_SEASONS = [2021, 2022, 2023, 2024, 2025]
V_GRID = [round(0.05 * i, 2) for i in range(21)]  # 0.00 .. 1.00 (1.0 = forest replaces the logistic blend)
MIN_GAIN = 0.001  # mean log-loss improvement below this is noise: not worth a 1 MB tree artifact


def latest_decisions() -> dict:
    reports = sorted(glob.glob(str(config.REPORTS_DIR / "global_train_*.json")))
    if not reports:
        raise SystemExit("no global_train report found -- run global_train.py first")
    return json.loads(open(reports[-1]).read())["decisions"]


def latest_forest_decisions() -> dict:
    reports = sorted(glob.glob(str(config.REPORTS_DIR / "forest_blend_*.json")))
    return json.loads(open(reports[-1]).read())["decisions"] if reports else {}


def three_way(blend2: list, forest: list, v: float) -> list:
    return [tuple((1 - v) * b[k] + v * f[k] for k in range(3)) for b, f in zip(blend2, forest)]


def blend3_artifact(league_artifact: dict, global_artifact: dict, forest_artifact: dict, w: float, v: float, label: str) -> dict:
    return {
        "type": "blend",
        "label": label,
        "components": [
            {"weight": round((1 - v) * w, 4), "model": league_artifact},
            {"weight": round((1 - v) * (1 - w), 4), "model": global_artifact},
            {"weight": round(v, 4), "model": forest_artifact},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Forest-as-third-component blend harness.")
    parser.add_argument("--ship", action="store_true", help="write + register evaluation-track artifacts for endorsed leagues")
    parser.add_argument("--leagues", default=",".join(leagues.TARGETS))
    args = parser.parse_args()
    codes = [c.strip() for c in args.leagues.split(",") if c.strip()]
    started = datetime.now(timezone.utc)
    decisions_in = latest_decisions()

    league_samples, league_feeders, league_specs = {}, {}, {}
    for code in leagues.TARGETS:  # the pooled global fit always uses all five
        _, samples = outcome_train.load_enriched_buckets(leagues.target_config(code), score_feeders=True)
        league_samples[code] = [s for s in samples if not s.get("tier2")]
        league_feeders[code] = [s for s in samples if s.get("tier2")]
        league_specs[code] = global_train.deployed_league_spec(code)
        print(f"loaded {code}: {len(league_samples[code])} samples · spec {league_specs[code]['version']} "
              f"· w={decisions_in[code]['fixed_w']} vec={decisions_in[code].get('use_vec', False)}")

    per_league_folds = {code: [] for code in codes}
    for T in FOLD_TEST_SEASONS:
        split_args = {"train_seasons": list(range(2017, T - 2)), "validate_season": T - 2,
                      "calibrate_season": T - 1, "test_season": T}
        league_buckets = {code: backtest_common.split_by_season(league_samples[code], **split_args) for code in leagues.TARGETS}
        pooled = {k: [s for code in leagues.TARGETS for s in league_buckets[code][k]] for k in ("train", "validate", "calibrate", "test")}
        pooled["train"] += [f for code in leagues.TARGETS for f in league_feeders[code] if f["season"] in split_args["train_seasons"]]
        global_artifact = outcome_train.build_artifact(GLOBAL_FEATS, pooled, decay=GLOBAL_DECAY)
        global_vec = fit_vector_scaling(global_artifact, pooled["calibrate"]) if any(decisions_in[c].get("use_vec") for c in codes) else None

        for code in codes:
            buckets = league_buckets[code]
            test = buckets["test"]
            if not test:
                continue
            backtest_common.verify_no_leakage(buckets)
            spec, dec = league_specs[code], decisions_in[code]
            league_artifact = outcome_train.build_artifact(spec["features"], buckets, decay=spec["decay"])
            forest_artifact = forest_train.build_forest_artifact(spec["features"], buckets, decay=spec["decay"])
            g = global_vec if dec.get("use_vec") else global_artifact
            lp, gp, fp = score_probs(test, league_artifact), score_probs(test, g), score_probs(test, forest_artifact)
            w = dec["fixed_w"]
            b2 = blend_probs(lp, gp, w)
            fit_set = buckets["train"] + buckets["validate"] + buckets["calibrate"]
            freq = outcome_baselines.frequency_baseline(fit_set)
            elo_params = outcome_baselines.calibrate_elo(fit_set)
            fold = {
                "fold": T,
                "frequency": metrics_of([outcome_baselines.frequency_probs(freq, s) for s in test], test),
                "elo_only": metrics_of([outcome_baselines.elo_probs(s["elo_diff"], *elo_params) for s in test], test),
                "league_only": metrics_of(lp, test),
                "global_only": metrics_of(gp, test),
                "forest_only": metrics_of(fp, test),
                "blend2": metrics_of(b2, test),
                "forest_leaf": forest_artifact["min_samples_leaf"],
                "forest_T": forest_artifact["temperature"],
                "blend3_ll_by_v": {str(v): log_loss_of(three_way(b2, fp, v), test) for v in V_GRID},
            }
            per_league_folds[code].append(fold)
            print(f"  fold {T} {code}: league {fold['league_only']['log_loss']:.4f} global {fold['global_only']['log_loss']:.4f} "
                  f"forest {fold['forest_only']['log_loss']:.4f} (leaf={fold['forest_leaf']}, T={fold['forest_T']}) "
                  f"blend2 {fold['blend2']['log_loss']:.4f} best blend3 {min(fold['blend3_ll_by_v'].values()):.4f}")

    decisions = {}
    for code in codes:
        folds = per_league_folds[code]
        rows = ("frequency", "elo_only", "league_only", "global_only", "forest_only", "blend2")
        means = {r: sum(f[r]["log_loss"] for f in folds) / len(folds) for r in rows}
        v_means = {v: sum(f["blend3_ll_by_v"][str(v)] for f in folds) / len(folds) for v in V_GRID}
        best_v = min(v_means, key=v_means.get)
        means["blend3"] = v_means[best_v]
        endorsed = best_v > 0 and means["blend2"] - means["blend3"] >= MIN_GAIN
        decisions[code] = {"means": means, "v_means": {str(k): v for k, v in v_means.items()}, "fixed_v": best_v,
                           "fixed_w": decisions_in[code]["fixed_w"], "use_vec": decisions_in[code].get("use_vec", False),
                           "forest_endorsed": endorsed}
        print(f"{code}: blend2={means['blend2']:.4f} forest={means['forest_only']:.4f} "
              f"blend3(v={best_v})={means['blend3']:.4f} delta={means['blend3'] - means['blend2']:+.4f} "
              f"-> {'FOREST ENDORSED' if endorsed else 'blend2 stands'}")

    shipped = {}
    if args.ship and any(d["forest_endorsed"] for d in decisions.values()):
        import model_registry
        final_buckets = {code: backtest_common.split_by_season(league_samples[code]) for code in leagues.TARGETS}
        pooled_final = {k: [s for code in leagues.TARGETS for s in final_buckets[code][k]] for k in ("train", "validate", "calibrate", "test")}
        pooled_final["train"] += [f for code in leagues.TARGETS for f in league_feeders[code] if f["season"] in backtest_common.TRAIN_SEASONS]
        global_final = outcome_train.build_artifact(GLOBAL_FEATS, pooled_final, decay=GLOBAL_DECAY)
        global_final_vec = fit_vector_scaling(global_final, pooled_final["calibrate"])
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        for code, dec in decisions.items():
            if not dec["forest_endorsed"]:
                continue
            cfg, spec, buckets = leagues.target_config(code), league_specs[code], final_buckets[code]
            w, v = dec["fixed_w"], dec["fixed_v"]
            league_artifact = outcome_train.build_artifact(spec["features"], buckets, decay=spec["decay"])
            forest_artifact = forest_train.build_forest_artifact(spec["features"], buckets, decay=spec["decay"])
            g = global_final_vec if dec["use_vec"] else global_final
            label = (f"blend{int(w * 100)}_global_rf{int(v * 100)} "
                     f"[{round((1 - v) * w, 3)} x {spec['version']} + {round((1 - v) * (1 - w), 3)} x global15 + {v} x forest]")
            artifact = blend3_artifact(league_artifact, g, forest_artifact, w, v, label)
            test = buckets["test"]
            p3 = three_way(blend_probs(score_probs(test, league_artifact), score_probs(test, g), w), score_probs(test, forest_artifact), v)
            m3 = metrics_of(p3, test)
            by_class = metrics.group_metrics([{**s, "p_home": p[0], "p_draw": p[1], "p_away": p[2]} for s, p in zip(test, p3)], key_fn=lambda s: s["cls"])
            artifact.update({
                "test_log_loss": m3["log_loss"], "test_accuracy": m3["accuracy"], "test_rps": m3["rps"],
                "test_draw_log_loss": by_class.get("1", {}).get("log_loss"),
                "selected_on": "forest weight v selected on 5-fold harness mean (fixed-v grid); endorsed vs league+global blend on the same mean",
                "trained_on": f"{backtest_common.TRAIN_SEASONS[0]}-{backtest_common.CALIBRATE_SEASON} (league + forest) + pooled global",
            })
            out_path = config.MODELS_DIR / cfg["outcome_artifact"]
            out_path.write_text(json.dumps(artifact, indent=1))
            entry = model_registry.register(out_path, deployed=True, notes="league + global + random forest blend (forest_blend.py)")
            shipped[code] = {"w": w, "v": v, "version": entry["version"], "test_log_loss": m3["log_loss"]}
            print(f"shipped {code}: {entry['version']} test_log_loss={m3['log_loss']:.4f}")
            report = {
                "meta": {"started_at": started.isoformat(), "folds": FOLD_TEST_SEASONS, "league": code, "instrument": "forest_blend harness"},
                "mean": {
                    "frequency": {"log_loss": dec["means"]["frequency"]},
                    "elo_only": {"log_loss": dec["means"]["elo_only"]},
                    "league_only": {"log_loss": dec["means"]["league_only"]},
                    "global_only": {"log_loss": dec["means"]["global_only"]},
                    "forest_only": {"log_loss": dec["means"]["forest_only"]},
                    "blend2": {"log_loss": dec["means"]["blend2"]},
                    entry["version"]: {"log_loss": dec["means"]["blend3"]},
                },
                "per_fold": per_league_folds[code],
            }
            (config.REPORTS_DIR / f"rolling_backtest_{code}_{stamp}.json").write_text(json.dumps(report, indent=2))

    out = {"meta": {"started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(), "folds": FOLD_TEST_SEASONS},
           "decisions": decisions, "per_league_folds": per_league_folds, "shipped": shipped}
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORTS_DIR / f"forest_blend_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
