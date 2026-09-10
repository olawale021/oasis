"""Random-forest outcome component: fit, export to a stdlib-walkable JSON
artifact, and prove the export is exact.

Protocol (mirrors the classifier bake-off in model_comparison.py, which is
where the forest earned a look):
  * min_samples_leaf chosen on the validate season from a train-only fit
  * refit on train+validate with the league's season-decay weights
  * one scalar temperature fitted on the calibrate season -- the forest
    never sees calibrate rows, so the temperature is honest (the logistic
    protocol fits through calibrate; trees would memorise it)
  * export refuses to return an artifact until the pure-Python walker in
    outcome_model.py reproduces sklearn's predict_proba to <1e-9 on every
    fit row (same exactness bar the LightGBM export met)

Training-only module: sklearn imported here, never at serving time.
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier

import metrics
import outcome_model
import outcome_train

N_ESTIMATORS = 300
LEAF_GRID = [20, 50, 100]
SEED = 7
EXACTNESS = 1e-9


def _forest(leaf: int) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=N_ESTIMATORS, min_samples_leaf=leaf, max_features="sqrt",
        n_jobs=-1, random_state=SEED,
    )


def _scored(samples: list, probs: np.ndarray, temperature: float = 1.0) -> list:
    out = []
    for s, p in zip(samples, probs):
        p = np.clip(p, 1e-9, 1.0)
        if temperature != 1.0:
            p = p ** (1.0 / temperature)
        p = p / p.sum()
        out.append({**s, "p_home": float(p[0]), "p_draw": float(p[1]), "p_away": float(p[2])})
    return out


def export(model: RandomForestClassifier, feats: list, temperature: float, leaf: int, decay) -> dict:
    trees = []
    for est in model.estimators_:
        t = est.tree_
        trees.append({
            "left": t.children_left.tolist(),
            "right": t.children_right.tolist(),
            "feature": t.feature.tolist(),
            "threshold": t.threshold.tolist(),
            # sklearn >= 1.4 stores class fractions per node; the walker
            # averages leaf fractions over trees exactly as predict_proba does.
            "value": [row[0].tolist() for row in t.value],
        })
    return {
        "type": "random_forest",
        "features": feats,
        "classes": outcome_train.CLASS_NAMES,
        "n_estimators": N_ESTIMATORS,
        "min_samples_leaf": leaf,
        "max_features": "sqrt",
        "decay": decay,
        "temperature": temperature,
        "trees": trees,
    }


def verify_export(model: RandomForestClassifier, artifact: dict, samples: list) -> float:
    """Max abs difference between sklearn predict_proba and the stdlib walker
    (temperature 1) over `samples`. Raises if above EXACTNESS."""
    raw = {**artifact, "temperature": 1.0}
    X = outcome_train.matrix(samples, artifact["features"])
    ref = model.predict_proba(X)
    worst = 0.0
    for s, r in zip(samples, ref):
        p = outcome_model.predict_proba(s, raw)
        worst = max(worst, max(abs(p[k] - r[k]) for k in range(3)))
    if worst > EXACTNESS:
        raise RuntimeError(f"forest export inexact: max abs diff {worst:.3e} > {EXACTNESS}")
    return worst


def build_forest_artifact(feats: list, buckets: dict, decay=None) -> dict:
    """Select leaf on validate, refit on train+validate, temperature on
    calibrate, export, verify. Returns the artifact (with a `verification`
    block) -- never the sklearn object."""
    Xtr, ytr = outcome_train.matrix(buckets["train"], feats), outcome_train.labels(buckets["train"])
    Xva = outcome_train.matrix(buckets["validate"], feats)
    wtr = outcome_train.season_weights(buckets["train"], decay)
    best = None
    for leaf in LEAF_GRID:
        m = _forest(leaf).fit(Xtr, ytr, sample_weight=wtr)
        ll = metrics.log_loss(_scored(buckets["validate"], m.predict_proba(Xva)))
        if best is None or ll < best[0]:
            best = (ll, leaf)
    val_ll, leaf = best

    fit_samples = buckets["train"] + buckets["validate"]
    Xfit, yfit = outcome_train.matrix(fit_samples, feats), outcome_train.labels(fit_samples)
    model = _forest(leaf).fit(Xfit, yfit, sample_weight=outcome_train.season_weights(fit_samples, decay))

    Xcal = outcome_train.matrix(buckets["calibrate"], feats)
    cal_probs = model.predict_proba(Xcal)
    temperature = min(
        outcome_train.TEMPERATURES,
        key=lambda t: metrics.log_loss(_scored(buckets["calibrate"], cal_probs, t)),
    )
    artifact = export(model, feats, temperature, leaf, decay)
    worst = verify_export(model, artifact, fit_samples + buckets["calibrate"])
    artifact["verification"] = {
        "rows_checked": len(fit_samples) + len(buckets["calibrate"]),
        "max_abs_diff_vs_sklearn": float(worst),
        "validate_log_loss": round(val_ll, 4),
    }
    return artifact
