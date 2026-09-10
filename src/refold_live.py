"""PRD 12.2 production refold: refit the frozen methodology through 2025/26
for the live 2026/27 season.

Methodology is FROZEN -- per-league feature sets, decay, and blend weights
are exactly the harness-selected ones; only the data window rolls forward:

    train 2017-2023 · validate 2024 · calibrate (temperature) 2025

Artifacts are written to a parallel *_live deployment track
(outcome_model_{code}_live.json, goals_model_{code}_live.json,
outcome_model_global_live.json) and registered under their own roles.
predict.py serves the _live artifacts when they exist; the evaluation
artifacts (fit through 2024, held-out 2025) are untouched so the
performance page's backtest stays honestly out-of-sample. The live locked
ledger is the refold's true forward test -- there is no held-out season
here by design, and the registry entry says so.

    python3 src/refold_live.py
"""

import glob
import json
from datetime import datetime, timezone

import backtest_common
import config
import forest_blend
import forest_train
import goals_train
import leagues
import metrics
import model_registry
import outcome_train
from global_train import GLOBAL_FEATS, GLOBAL_DECAY, deployed_league_spec

# Fit = train+validate+calibrate buckets. The current season's PLAYED
# matches ride in the train list (--include-current, default on): with decay
# anchored at the newest fit season they carry full weight, while temperature
# still calibrates on the last COMPLETE season -- a few dozen live matches is
# far too small a calibration set.
def refold_splits(include_current: bool) -> dict:
    train = list(range(2017, 2024)) + ([2026] if include_current else [])
    return {
        "train_seasons": train,
        "validate_season": 2024,
        "calibrate_season": 2025,
        "test_season": 2027,  # nothing lands here; the live ledger is the test
    }


def latest_blend_ws() -> dict:
    reports = sorted(glob.glob(str(config.REPORTS_DIR / "global_train_*.json")))
    if not reports:
        raise SystemExit("no global_train report found -- run global_train.py first")
    decisions = json.loads(open(reports[-1]).read()).get("decisions", {})
    return {code: d["fixed_w"] for code, d in decisions.items() if d.get("blend_endorsed")}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PRD 12.2 production refold onto the *_live serving track.")
    parser.add_argument("--tag", type=str, default="r26", help='Release generation tag, e.g. "r26w1"')
    parser.add_argument("--no-current", action="store_true", help="Exclude current-season played matches from the fit")
    args = parser.parse_args()
    tag = args.tag

    started = datetime.now(timezone.utc)
    blend_ws = latest_blend_ws()
    forest_decisions = {c: d for c, d in forest_blend.latest_forest_decisions().items() if d.get("forest_endorsed")}
    splits = refold_splits(not args.no_current)

    league_buckets = {}
    league_feeders = {}
    league_specs = {}
    for code in leagues.TARGETS:
        _, samples = outcome_train.load_enriched_buckets(leagues.target_config(code), score_feeders=True)
        targets_only = [s for s in samples if not s.get("tier2")]
        league_feeders[code] = [s for s in samples if s.get("tier2") and s["season"] in splits["train_seasons"]]
        league_buckets[code] = backtest_common.split_by_season(targets_only, **splits)
        league_specs[code] = deployed_league_spec(code)
        b = league_buckets[code]
        print(
            f"{code}: fit {len(b['train']) + len(b['validate']) + len(b['calibrate'])} rows "
            f"· spec {league_specs[code]['version']} · blend w={blend_ws.get(code, '—')}"
        )

    pooled = {
        k: [s for code in leagues.TARGETS for s in league_buckets[code][k]]
        for k in ("train", "validate", "calibrate", "test")
    }
    pooled["train"] = pooled["train"] + [f for code in leagues.TARGETS for f in league_feeders[code]]
    global_live = outcome_train.build_artifact(GLOBAL_FEATS, pooled, decay=GLOBAL_DECAY)
    global_live["label"] = (
        f"global15_{tag} [{', '.join(GLOBAL_FEATS)}] pooled 5-league logistic, decay={GLOBAL_DECAY}, "
        f"refold {tag}: temperature on pooled 2025"
    )
    global_live["trained_on"] = f"pooled 5 leagues through current played matches (PRD 12.2 refold {tag}; live ledger is the test)"
    global_path = config.MODELS_DIR / "outcome_model_global_live.json"
    global_path.write_text(json.dumps(global_live, indent=2))
    model_registry.register(global_path, deployed=True, notes="PRD 12.2 refold, live 2026/27 track")
    print(f"wrote {global_path}")

    for code in leagues.TARGETS:
        cfg = leagues.target_config(code)
        spec = league_specs[code]
        buckets = league_buckets[code]
        league_artifact = outcome_train.build_artifact(spec["features"], buckets, decay=spec["decay"])

        w = blend_ws.get(code)
        forest_dec = forest_decisions.get(code)
        if w is not None and forest_dec is not None:
            # Forest endorsed by forest_blend.py's 5-fold harness: carry its
            # fixed v into the live track. Same refold buckets; the forest
            # never sees the calibrate season (forest_train protocol).
            v = forest_dec["fixed_v"]
            forest_live = forest_train.build_forest_artifact(spec["features"], buckets, decay=spec["decay"])
            artifact = forest_blend.blend3_artifact(
                league_artifact, global_live, forest_live, w, v,
                f"blend{int(w * 100)}_global_rf{int(v * 100)}_{tag} "
                f"[{round((1 - v) * w, 3)} x {spec['version']} + {round((1 - v) * (1 - w), 3)} x global15_{tag} + {v} x forest]",
            )
        elif w is not None:
            artifact = {
                "type": "blend",
                "label": f"blend{int(w * 100)}_global_{tag} [w={w} x {spec['version']} + {round(1 - w, 2)} x global15_{tag}]",
                "components": [
                    {"weight": w, "model": league_artifact},
                    {"weight": round(1.0 - w, 4), "model": global_live},
                ],
            }
        else:
            artifact = {**league_artifact, "label": f"{spec['version']}_{tag} (league-only refold)"}
        artifact["trained_on"] = f"2017-2025 + current played (PRD 12.2 refold {tag}; temperature on 2025)"
        artifact["selected_on"] = (
            "methodology frozen from the 2025-held-out harness (features/decay/blend w unchanged); "
            "no held-out test season -- the live locked ledger is the evaluation"
        )

        out_path = config.MODELS_DIR / cfg["outcome_artifact"].replace(".json", "_live.json")
        out_path.write_text(json.dumps(artifact, indent=2))
        entry = model_registry.register(out_path, deployed=True, notes="PRD 12.2 refold, live 2026/27 track")

        goals_live = goals_train.fit_goals_artifact(buckets)
        goals_live["trained_on"] = f"2017-2025 + current played (PRD 12.2 refold {tag})"
        goals_path = config.MODELS_DIR / cfg["goals_artifact"].replace(".json", "_live.json")
        goals_path.write_text(json.dumps(goals_live, indent=2))
        model_registry.register(goals_path, deployed=True, notes="PRD 12.2 refold, live 2026/27 track")
        print(f"shipped {code} live: {entry['version']} + goals (alpha={goals_live['alpha']}, decay={goals_live['decay']})")

    print(f"refold complete in {(datetime.now(timezone.utc) - started).total_seconds():.0f}s")


if __name__ == "__main__":
    main()
