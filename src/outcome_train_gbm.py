import json

import lightgbm as lgb
import numpy as np

import backtest_common
import config
import db
import matches as matches_module
import metrics
import model_registry
import outcome_model
import promotion
import richer_features
from outcome_train import NINE, TEMPERATURES, labels, matrix

CLASS_NAMES = ["home", "draw", "away"]
NUM_CLASS = 3

FIXED_PARAMS = {
    # "multiclass" (softmax) deliberately, NOT "multiclassova" -- the pure-
    # Python reconstruction applies a joint 3-way softmax to the raw margins,
    # which is only correct for the softmax objective.
    "objective": "multiclass",
    "num_class": NUM_CLASS,
    "metric": "multi_logloss",
    "verbosity": -1,
    "seed": 42,
    "deterministic": True,
    "force_row_wise": True,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
}

# Conservative grid for a small dataset (2,220 train rows) -- shallow trees,
# high min_data_in_leaf, nonzero L2.
GRID = [
    {"num_leaves": 7, "learning_rate": 0.05, "min_data_in_leaf": 40, "lambda_l2": 1.0},
    {"num_leaves": 7, "learning_rate": 0.05, "min_data_in_leaf": 80, "lambda_l2": 1.0},
    {"num_leaves": 7, "learning_rate": 0.10, "min_data_in_leaf": 40, "lambda_l2": 1.0},
    {"num_leaves": 15, "learning_rate": 0.03, "min_data_in_leaf": 40, "lambda_l2": 1.0},
    {"num_leaves": 15, "learning_rate": 0.05, "min_data_in_leaf": 40, "lambda_l2": 1.0},
    {"num_leaves": 15, "learning_rate": 0.05, "min_data_in_leaf": 80, "lambda_l2": 2.0},
    {"num_leaves": 15, "learning_rate": 0.05, "min_data_in_leaf": 40, "lambda_l2": 5.0},
    {"num_leaves": 15, "learning_rate": 0.10, "min_data_in_leaf": 80, "lambda_l2": 1.0},
    {"num_leaves": 31, "learning_rate": 0.03, "min_data_in_leaf": 80, "lambda_l2": 2.0},
    {"num_leaves": 31, "learning_rate": 0.05, "min_data_in_leaf": 80, "lambda_l2": 2.0},
    {"num_leaves": 31, "learning_rate": 0.05, "min_data_in_leaf": 40, "lambda_l2": 5.0},
    {"num_leaves": 31, "learning_rate": 0.10, "min_data_in_leaf": 80, "lambda_l2": 5.0},
]

VERIFY_TOLERANCE = 1e-9


# --- Tree export: LightGBM dump_model() -> simplified, version-proof schema ---

def export_node(node: dict) -> dict:
    if "leaf_value" in node and "split_feature" not in node:
        return {"leaf": True, "value": node["leaf_value"]}
    decision_type = node.get("decision_type")
    if decision_type != "<=":
        raise ValueError(
            f"unsupported decision_type {decision_type!r} -- categorical split? "
            "The pure-python evaluator only supports numeric '<=' splits."
        )
    return {
        "leaf": False,
        "split_feature": node["split_feature"],
        "threshold": node["threshold"],
        "default_left": bool(node.get("default_left", True)),
        "left": export_node(node["left_child"]),
        "right": export_node(node["right_child"]),
    }


def _walk_raw(node: dict, row) -> float:
    """Walk a RAW dump_model() tree node (used only during recipe derivation,
    before re-encoding)."""
    while "leaf_value" not in node or "split_feature" in node:
        fval = row[node["split_feature"]]
        if fval != fval:
            go_left = node.get("default_left", True)
        else:
            go_left = fval <= node["threshold"]
        node = node["left_child"] if go_left else node["right_child"]
    return node["leaf_value"]


def derive_and_verify(raw_dump: dict, X: np.ndarray, margins_true: np.ndarray) -> dict:
    """Empirically derive the reconstruction recipe (class mapping, shrinkage
    handling, base_score) and verify it reproduces booster.predict(raw_score=
    True) to VERIFY_TOLERANCE on EVERY row. Raises if nothing passes -- the
    artifact must never be written from an unverified recipe."""
    tree_info = raw_dump["tree_info"]
    n_rounds = len(tree_info) // NUM_CLASS
    if len(tree_info) != n_rounds * NUM_CLASS:
        raise RuntimeError("tree count not divisible by num_class -- mapping assumption invalid")

    mapping_hypotheses = {
        "interleaved (tree_index % num_class)": lambda c: [t for t in tree_info if t["tree_index"] % NUM_CLASS == c],
        "blocked (tree_index // n_rounds)": lambda c: [t for t in tree_info if t["tree_index"] // n_rounds == c],
    }

    rows = [tuple(r) for r in X]

    for map_name, mapper in mapping_hypotheses.items():
        trees_by_class = [[(t["tree_structure"], t.get("shrinkage", 1.0)) for t in mapper(c)] for c in range(NUM_CLASS)]
        for shrink_baked_in in (True, False):

            def margins_for(row):
                out = []
                for c in range(NUM_CLASS):
                    total = 0.0
                    for root, shrinkage in trees_by_class[c]:
                        total += _walk_raw(root, row) * (1.0 if shrink_baked_in else shrinkage)
                    out.append(total)
                return out

            naive0 = margins_for(rows[0])
            base_score = [float(margins_true[0][c] - naive0[c]) for c in range(NUM_CLASS)]

            max_diff = 0.0
            ok = True
            for i, row in enumerate(rows):
                m = margins_for(row)
                for c in range(NUM_CLASS):
                    diff = abs(m[c] + base_score[c] - margins_true[i][c])
                    if diff > max_diff:
                        max_diff = diff
                    if diff >= VERIFY_TOLERANCE:
                        ok = False
                        break
                if not ok:
                    break

            if ok:
                return {
                    "class_mapping": map_name,
                    "leaf_value_includes_shrinkage": shrink_baked_in,
                    "base_score": base_score,
                    "mapper": mapper,
                    "verification": {
                        "n_rows_checked": len(rows),
                        "n_classes": NUM_CLASS,
                        "max_abs_margin_diff": max_diff,
                        "tolerance": VERIFY_TOLERANCE,
                    },
                }

    raise RuntimeError(
        "FATAL: no (class-mapping, shrinkage) hypothesis reproduced "
        "booster.predict(raw_score=True) within tolerance. Refusing to write "
        "an artifact -- inspect tree_info/shrinkage/base manually."
    )


def _score(samples: list, artifact: dict) -> list:
    scored = []
    for s in samples:
        ph, pd, pa = outcome_model.predict_proba(s, artifact)
        scored.append({**s, "p_home": ph, "p_draw": pd, "p_away": pa})
    return scored


def main() -> None:
    conn = db.get_connection()
    matches = matches_module.load_matches(conn, [backtest_common.PL_ID, backtest_common.CHAMP_ID])
    transitions = promotion.compute_transitions(
        conn, backtest_common.PL_ID, backtest_common.CHAMP_ID, backtest_common.ALL_SEASONS
    )
    samples = backtest_common.collect_samples(matches, transitions, use_mov=True)
    samples = richer_features.enrich_samples(samples, conn)
    buckets = backtest_common.split_by_season(samples)
    backtest_common.verify_no_leakage(buckets)

    X_train, y_train = matrix(buckets["train"], NINE), labels(buckets["train"])
    X_validate, y_validate = matrix(buckets["validate"], NINE), labels(buckets["validate"])

    train_set = lgb.Dataset(X_train, label=y_train, params={"verbosity": -1})

    # --- Search phase: grid + early stopping, both driven by validate ---
    best = None
    for combo in GRID:
        params = {**FIXED_PARAMS, **combo}
        valid_set = lgb.Dataset(X_validate, label=y_validate, reference=train_set, params={"verbosity": -1})
        booster = lgb.train(
            params,
            train_set,
            num_boost_round=2000,
            valid_sets=[valid_set],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
        )
        val_ll = booster.best_score["valid_0"]["multi_logloss"]
        print(f"validate multi_logloss: {val_ll:.4f} best_iter={booster.best_iteration} {combo}")
        if best is None or val_ll < best["val_ll"]:
            best = {"val_ll": val_ll, "combo": combo, "best_iteration": booster.best_iteration}

    print(f"\nwinning combo: {best['combo']} best_iteration={best['best_iteration']} validate_ll={best['val_ll']:.4f}")

    # --- Final refit on train+validate+calibrate, fixed iteration count ---
    fit_samples = buckets["train"] + buckets["validate"] + buckets["calibrate"]
    X_fit, y_fit = matrix(fit_samples, NINE), labels(fit_samples)
    final_params = {**FIXED_PARAMS, **best["combo"]}
    final_booster = lgb.train(
        final_params,
        lgb.Dataset(X_fit, label=y_fit, params={"verbosity": -1}),
        num_boost_round=best["best_iteration"],
    )
    raw_dump = final_booster.dump_model()
    assert len(raw_dump["tree_info"]) == best["best_iteration"] * NUM_CLASS, (
        f"expected {best['best_iteration'] * NUM_CLASS} trees, got {len(raw_dump['tree_info'])}"
    )

    # --- Derive + verify the reconstruction recipe over ALL feature rows ---
    all_samples = buckets["train"] + buckets["validate"] + buckets["calibrate"] + buckets["test"]
    X_all = matrix(all_samples, NINE)
    margins_true = final_booster.predict(X_all, raw_score=True)
    recipe = derive_and_verify(raw_dump, X_all, margins_true)
    print(
        f"reconstruction verified: {recipe['class_mapping']}, "
        f"shrinkage_baked_in={recipe['leaf_value_includes_shrinkage']}, "
        f"base_score={recipe['base_score']}, "
        f"max_abs_margin_diff={recipe['verification']['max_abs_margin_diff']:.2e} "
        f"over {recipe['verification']['n_rows_checked']} rows"
    )

    # --- Export trees in the simplified, version-proof schema ---
    trees = [[export_node(t["tree_structure"]) for t in recipe["mapper"](c)] for c in range(NUM_CLASS)]

    artifact = {
        "type": "lightgbm_trees",
        "features": NINE,
        "classes": CLASS_NAMES,
        "num_class": NUM_CLASS,
        "base_score": recipe["base_score"],
        "class_mapping": recipe["class_mapping"],
        "leaf_value_includes_shrinkage": recipe["leaf_value_includes_shrinkage"],
        "trees": trees,
        "temperature": 1.0,
        "hyperparameters": {**best["combo"], "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "best_iteration": best["best_iteration"]},
        "verification": recipe["verification"],
    }

    # --- Temperature calibration on calibrate, via the exported artifact ---
    best_T, best_cal_ll = 1.0, float("inf")
    for T in TEMPERATURES:
        candidate = {**artifact, "temperature": T}
        ll = metrics.log_loss(_score(buckets["calibrate"], candidate))
        if ll < best_cal_ll:
            best_cal_ll, best_T = ll, T
    artifact["temperature"] = best_T
    print(f"temperature={best_T} calibrate_log_loss={best_cal_ll:.4f}")

    # --- Write artifact, then score test ONCE through the shipped file ---
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MODELS_DIR / "outcome_model_pl_gbm.json"

    artifact.update(
        {
            "label": f"gbm9 [{', '.join(NINE)}] LightGBM multiclass, temperature-scaled on {backtest_common.CALIBRATE_SEASON}",
            "selected_on": f"validate={backtest_common.VALIDATE_SEASON} (grid+early-stopping); calibrated on {backtest_common.CALIBRATE_SEASON} (temperature); test={backtest_common.TEST_SEASON} scored once",
            "trained_on": f"{backtest_common.TRAIN_SEASONS[0]}-{backtest_common.CALIBRATE_SEASON} (train+validate+calibrate), min_games={backtest_common.MIN_GAMES}",
        }
    )
    out_path.write_text(json.dumps(artifact, indent=2))

    shipped = outcome_model.load_model(out_path)
    test_scored = _score(buckets["test"], shipped)
    test_metrics = metrics.all_outcome_metrics(test_scored)
    test_rps = metrics.rps(test_scored)

    artifact.update(
        {
            "test_log_loss": test_metrics["log_loss"],
            "test_accuracy": test_metrics["accuracy"],
            "test_rps": test_rps,
        }
    )
    out_path.write_text(json.dumps(artifact, indent=2))
    # Candidate only -- the logistic remains the shipped artifact.
    model_registry.register(out_path, deployed=False, notes="GBM candidate, not shipped (loses to logistic)")
    print(
        f"wrote {out_path}: test_log_loss={test_metrics['log_loss']:.4f} "
        f"test_accuracy={test_metrics['accuracy']:.4f} test_rps={test_rps:.4f}"
    )


if __name__ == "__main__":
    main()
