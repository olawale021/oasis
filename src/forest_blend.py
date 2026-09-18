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
  global forest    -- GLOBAL_FEATS on the same pooled fit (+feeders), same
                      forest_train protocol: the tree analogue of the global
                      logistic, so pooled data can steady a noisy league forest
  blend2 = w*league + (1-w)*global with the deployed fixed w
  blend4(v,u) = (1-v-u)*blend2 + v*forest + u*global_forest, (v,u) on a
                fixed grid with v+u <= V_MAX

Decision per league: (v*,u*) minimises the 5-fold mean; endorsed only if
v*+u* > 0 and mean(blend2) - mean(blend4) >= MIN_GAIN (0.001 -- smaller
gains are inside fold noise and not worth the artifact).

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
V_MAX = 0.6  # cap: the logistic components must keep >=40% so the match-page factor panel describes a model that matters


def latest_decisions() -> dict:
    reports = sorted(glob.glob(str(config.REPORTS_DIR / "global_train_*.json")))
    if not reports:
        raise SystemExit("no global_train report found -- run global_train.py first")
    return json.loads(open(reports[-1]).read())["decisions"]


def latest_forest_decisions() -> dict:
    reports = sorted(glob.glob(str(config.REPORTS_DIR / "forest_blend_*.json")))
    return json.loads(open(reports[-1]).read())["decisions"] if reports else {}


VU_GRID = [(v, u) for v in V_GRID for u in V_GRID if round(v + u, 2) <= V_MAX]


def vu_key(v: float, u: float) -> str:
    return f"{v},{u}"


def four_way(blend2: list, forest: list, gforest: list, v: float, u: float) -> list:
    r = 1 - v - u
    return [tuple(r * b[k] + v * f[k] + u * g[k] for k in range(3)) for b, f, g in zip(blend2, forest, gforest)]


def blend_artifact(league_artifact: dict, global_artifact: dict, forest_artifact: dict, gforest_artifact: dict,
                   w: float, v: float, u: float, label: str) -> dict:
    """League + global logistic, plus whichever forests carry weight."""
    r = 1 - v - u
    components = [
        {"weight": round(r * w, 4), "model": league_artifact},
        {"weight": round(r * (1 - w), 4), "model": global_artifact},
    ]
    if v > 0:
        components.append({"weight": round(v, 4), "model": forest_artifact})
    if u > 0:
        components.append({"weight": round(u, 4), "model": gforest_artifact})
    return {"type": "blend", "label": label, "components": components}


def blend_label(spec_version: str, w: float, v: float, u: float, tag: str = "") -> str:
    r = 1 - v - u
    head = f"blend{int(w * 100)}_global" + (f"_rf{int(v * 100)}" if v > 0 else "") + (f"_grf{int(u * 100)}" if u > 0 else "") + (f"_{tag}" if tag else "")
    parts = [f"{round(r * w, 3)} x {spec_version}", f"{round(r * (1 - w), 3)} x global15{'_' + tag if tag else ''}"]
    if v > 0:
        parts.append(f"{v} x forest")
    if u > 0:
        parts.append(f"{u} x global_forest")
    return f"{head} [{' + '.join(parts)}]"


def main() -> None:
    parser = argparse.ArgumentParser(description="Forest-as-third-component blend harness.")
    parser.add_argument("--ship", action="store_true", help="write + register evaluation-track artifacts for endorsed leagues")
    parser.add_argument("--leagues", default=",".join(leagues.TARGETS))
    args = parser.parse_args()
    codes = [c.strip() for c in args.leagues.split(",") if c.strip()]
    started = datetime.now(timezone.utc)
    decisions_in = latest_decisions()

    league_samples, league_feeders, league_specs = {}, {}, {}
    for code in leagues.pooled_targets():  # the pooled global fit always uses all five
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
        league_buckets = {code: backtest_common.split_by_season(league_samples[code], **split_args) for code in leagues.pooled_targets()}
        pooled = {k: [s for code in leagues.pooled_targets() for s in league_buckets[code][k]] for k in ("train", "validate", "calibrate", "test")}
        pooled["train"] += [f for code in leagues.pooled_targets() for f in league_feeders[code] if f["season"] in split_args["train_seasons"]]
        global_artifact = outcome_train.build_artifact(GLOBAL_FEATS, pooled, decay=GLOBAL_DECAY)
        global_vec = fit_vector_scaling(global_artifact, pooled["calibrate"]) if any(decisions_in[c].get("use_vec") for c in codes) else None
        gforest_artifact = forest_train.build_forest_artifact(list(GLOBAL_FEATS), pooled, decay=GLOBAL_DECAY)

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
            gfp = score_probs(test, gforest_artifact)
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
                "global_forest_only": metrics_of(gfp, test),
                "blend2": metrics_of(b2, test),
                "forest_leaf": forest_artifact["min_samples_leaf"],
                "forest_T": forest_artifact["temperature"],
                "global_forest_leaf": gforest_artifact["min_samples_leaf"],
                "blend4_ll_by_vu": {vu_key(v, u): log_loss_of(four_way(b2, fp, gfp, v, u), test) for v, u in VU_GRID},
            }
            per_league_folds[code].append(fold)
            print(f"  fold {T} {code}: league {fold['league_only']['log_loss']:.4f} global {fold['global_only']['log_loss']:.4f} "
                  f"forest {fold['forest_only']['log_loss']:.4f} gforest {fold['global_forest_only']['log_loss']:.4f} "
                  f"blend2 {fold['blend2']['log_loss']:.4f} best blend4 {min(fold['blend4_ll_by_vu'].values()):.4f}")

    decisions = {}
    for code in codes:
        folds = per_league_folds[code]
        rows = ("frequency", "elo_only", "league_only", "global_only", "forest_only", "global_forest_only", "blend2")
        means = {r: sum(f[r]["log_loss"] for f in folds) / len(folds) for r in rows}
        vu_means = {(v, u): sum(f["blend4_ll_by_vu"][vu_key(v, u)] for f in folds) / len(folds) for v, u in VU_GRID}
        best_v, best_u = min(vu_means, key=vu_means.get)
        means["blend4"] = vu_means[(best_v, best_u)]
        # Diagnostics: best single-forest mixes, for the record.
        means["blend3_league_forest"] = min(vu_means[(v, 0.0)] for v in V_GRID if v <= V_MAX)
        means["blend3_global_forest"] = min(vu_means[(0.0, u)] for u in V_GRID if u <= V_MAX)
        endorsed = (best_v + best_u) > 0 and means["blend2"] - means["blend4"] >= MIN_GAIN
        decisions[code] = {"means": means, "vu_means": {vu_key(v, u): ll for (v, u), ll in vu_means.items()},
                           "fixed_v": best_v, "fixed_u": best_u, "v_max": V_MAX,
                           "fixed_w": decisions_in[code]["fixed_w"], "use_vec": decisions_in[code].get("use_vec", False),
                           "forest_endorsed": endorsed}
        print(f"{code}: blend2={means['blend2']:.4f} forest={means['forest_only']:.4f} gforest={means['global_forest_only']:.4f} "
              f"blend4(v={best_v},u={best_u})={means['blend4']:.4f} delta={means['blend4'] - means['blend2']:+.4f} "
              f"[league-forest-only best {means['blend3_league_forest']:.4f}, global-forest-only best {means['blend3_global_forest']:.4f}] "
              f"-> {'FOREST ENDORSED' if endorsed else 'blend2 stands'}")

    shipped = {}
    if args.ship and any(d["forest_endorsed"] for d in decisions.values()):
        import model_registry
        final_buckets = {code: backtest_common.split_by_season(league_samples[code]) for code in leagues.pooled_targets()}
        pooled_final = {k: [s for code in leagues.pooled_targets() for s in final_buckets[code][k]] for k in ("train", "validate", "calibrate", "test")}
        pooled_final["train"] += [f for code in leagues.pooled_targets() for f in league_feeders[code] if f["season"] in backtest_common.TRAIN_SEASONS]
        global_final = outcome_train.build_artifact(GLOBAL_FEATS, pooled_final, decay=GLOBAL_DECAY)
        global_final_vec = fit_vector_scaling(global_final, pooled_final["calibrate"])
        gforest_final = forest_train.build_forest_artifact(list(GLOBAL_FEATS), pooled_final, decay=GLOBAL_DECAY)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        for code, dec in decisions.items():
            if not dec["forest_endorsed"]:
                continue
            cfg, spec, buckets = leagues.target_config(code), league_specs[code], final_buckets[code]
            w, v, u = dec["fixed_w"], dec["fixed_v"], dec["fixed_u"]
            league_artifact = outcome_train.build_artifact(spec["features"], buckets, decay=spec["decay"])
            forest_artifact = forest_train.build_forest_artifact(spec["features"], buckets, decay=spec["decay"]) if v > 0 else None
            g = global_final_vec if dec["use_vec"] else global_final
            artifact = blend_artifact(league_artifact, g, forest_artifact, gforest_final, w, v, u, blend_label(spec["version"], w, v, u))
            test = buckets["test"]
            fp = score_probs(test, forest_artifact) if v > 0 else [(0.0, 0.0, 0.0)] * len(test)
            p3 = four_way(blend_probs(score_probs(test, league_artifact), score_probs(test, g), w), fp, score_probs(test, gforest_final), v, u)
            m3 = metrics_of(p3, test)
            by_class = metrics.group_metrics([{**s, "p_home": p[0], "p_draw": p[1], "p_away": p[2]} for s, p in zip(test, p3)], key_fn=lambda s: s["cls"])
            artifact.update({
                "test_log_loss": m3["log_loss"], "test_accuracy": m3["accuracy"], "test_rps": m3["rps"],
                "test_draw_log_loss": by_class.get("1", {}).get("log_loss"),
                "selected_on": "forest weights (v league, u global) selected on 5-fold harness mean (fixed grid, v+u<=0.6); endorsed vs league+global blend on the same mean",
                "trained_on": f"{backtest_common.TRAIN_SEASONS[0]}-{backtest_common.CALIBRATE_SEASON} (league + forest) + pooled global logistic + pooled global forest",
            })
            out_path = config.MODELS_DIR / cfg["outcome_artifact"]
            out_path.write_text(json.dumps(artifact, indent=1))
            entry = model_registry.register(out_path, deployed=True, notes="league + global + random forest blend (forest_blend.py)")
            shipped[code] = {"w": w, "v": v, "u": u, "version": entry["version"], "test_log_loss": m3["log_loss"]}
            print(f"shipped {code}: {entry['version']} test_log_loss={m3['log_loss']:.4f}")
            report = {
                "meta": {"started_at": started.isoformat(), "folds": FOLD_TEST_SEASONS, "league": code, "instrument": "forest_blend harness"},
                "mean": {
                    "frequency": {"log_loss": dec["means"]["frequency"]},
                    "elo_only": {"log_loss": dec["means"]["elo_only"]},
                    "league_only": {"log_loss": dec["means"]["league_only"]},
                    "global_only": {"log_loss": dec["means"]["global_only"]},
                    "forest_only": {"log_loss": dec["means"]["forest_only"]},
                    "global_forest_only": {"log_loss": dec["means"]["global_forest_only"]},
                    "blend2": {"log_loss": dec["means"]["blend2"]},
                    entry["version"]: {"log_loss": dec["means"]["blend4"]},
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
