"""Classifier bake-off on the deployed feature sets. SHIPS NOTHING.

Compares the production learner (multinomial logistic) against SVM (linear
and RBF kernels), random forest and XGBoost on identical inputs:

  * same point-in-time features as the deployed league model
    (global_train.deployed_league_spec), plus the pooled GLOBAL_FEATS set
  * same season split as the evaluation track (train 2017-2022, validate
    2023, calibrate 2024, held-out test 2025)
  * same season-decay sample weights
  * hyper-parameters picked on the validate season by log loss, then the
    model is refit on train+validate
  * one scalar temperature per model fitted on the calibrate season, so the
    SVM/forest probabilities get the same calibration help the logistic
    model does in production

Reported on the test season: log loss, Brier, RPS, accuracy, and macro
precision / recall / F1 (the accuracy-family numbers papers usually quote).
Log loss is the decision metric -- accuracy ignores confidence.

    python3 src/model_comparison.py [--leagues pl,lal] [--quick]
"""

import argparse
import json
import math
import sys
import time
import warnings
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from xgboost import XGBClassifier

import backtest_common
import config
import global_train
import leagues
import metrics
import outcome_train

warnings.filterwarnings("ignore")
SEED = 7
TEMPERATURES = outcome_train.TEMPERATURES


# ---------------------------------------------------------------- data
def league_data(code: str) -> tuple[dict, list, float | None]:
    _, samples = outcome_train.load_enriched_buckets(leagues.target_config(code), score_feeders=True)
    targets_only = [s for s in samples if not s.get("tier2")]
    buckets = backtest_common.split_by_season(targets_only)
    spec = global_train.deployed_league_spec(code)
    return buckets, spec["features"], spec["decay"]


def xy(samples: list, feats: list) -> tuple[np.ndarray, np.ndarray]:
    return outcome_train.matrix(samples, feats), outcome_train.labels(samples)


def weights(samples: list, decay) -> np.ndarray | None:
    return outcome_train.season_weights(samples, decay)


# ---------------------------------------------------------------- models
def candidates(quick: bool) -> dict:
    """name -> list of (label, factory). Each factory returns an unfitted
    sklearn-style classifier with predict_proba."""
    c_lin = [0.01, 0.1, 1.0] if not quick else [0.1]
    c_rbf = [0.3, 1.0, 3.0] if not quick else [1.0]
    leaf = [5, 20, 50] if not quick else [20]
    depth = [2, 3, 4] if not quick else [3]
    return {
        "logistic": [("lrcv", lambda: outcome_train.LogisticRegressionCV(Cs=12, cv=5, max_iter=2000, scoring="neg_log_loss"))],
        "svm_linear": [(f"C={c}", (lambda c=c: SVC(kernel="linear", C=c, probability=True, random_state=SEED))) for c in c_lin],
        "svm_rbf": [(f"C={c}", (lambda c=c: SVC(kernel="rbf", C=c, gamma="scale", probability=True, random_state=SEED))) for c in c_rbf],
        "random_forest": [
            (f"leaf={l}", (lambda l=l: RandomForestClassifier(n_estimators=500, min_samples_leaf=l, max_features="sqrt", n_jobs=-1, random_state=SEED)))
            for l in leaf
        ],
        "xgboost": [
            (f"depth={d}", (lambda d=d: XGBClassifier(
                objective="multi:softprob", num_class=3, n_estimators=400, learning_rate=0.03, max_depth=d,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=5, reg_lambda=1.0,
                random_state=SEED, n_jobs=-1, verbosity=0,
            )))
            for d in depth
        ],
    }


def fit(model, X, y, w, Xval=None, yval=None):
    if isinstance(model, XGBClassifier) and Xval is not None:
        model.set_params(early_stopping_rounds=50)
        model.fit(X, y, sample_weight=w, eval_set=[(Xval, yval)], verbose=False)
    else:
        model.fit(X, y, sample_weight=w)
    return model


def scored(samples: list, probs: np.ndarray, temperature: float = 1.0) -> list:
    out = []
    for s, p in zip(samples, probs):
        p = np.clip(p, 1e-9, 1.0)
        if temperature != 1.0:
            p = p ** (1.0 / temperature)
        p = p / p.sum()
        out.append({**s, "p_home": float(p[0]), "p_draw": float(p[1]), "p_away": float(p[2])})
    return out


def best_temperature(samples: list, probs: np.ndarray) -> float:
    return min(TEMPERATURES, key=lambda t: metrics.log_loss(scored(samples, probs, t)))


def prf_macro(samples: list) -> dict:
    """Macro precision / recall / F1 over home, draw, away."""
    tp = [0] * 3
    fp = [0] * 3
    fn = [0] * 3
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        pred = max(range(3), key=lambda i: p[i])
        if pred == s["cls"]:
            tp[pred] += 1
        else:
            fp[pred] += 1
            fn[s["cls"]] += 1
    precs, recs, f1s = [], [], []
    for k in range(3):
        prec = tp[k] / (tp[k] + fp[k]) if tp[k] + fp[k] else 0.0
        rec = tp[k] / (tp[k] + fn[k]) if tp[k] + fn[k] else 0.0
        precs.append(prec)
        recs.append(rec)
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return {"precision": sum(precs) / 3, "recall": sum(recs) / 3, "f1": sum(f1s) / 3}


def evaluate_family(name: str, grid: list, buckets: dict, feats: list, decay) -> dict:
    """Pick hyper-params on validate, refit on train+validate, temperature on
    calibrate, report on test."""
    Xtr, ytr = xy(buckets["train"], feats)
    Xva, yva = xy(buckets["validate"], feats)
    Xtr_s, mean, std = outcome_train.standardize(Xtr, Xtr)
    Xva_s = (Xva - mean) / std
    wtr = weights(buckets["train"], decay)

    best = None
    for label, factory in grid:
        m = fit(factory(), Xtr_s, ytr, wtr, Xva_s, yva)
        ll = metrics.log_loss(scored(buckets["validate"], m.predict_proba(Xva_s)))
        if best is None or ll < best[0]:
            best = (ll, label, factory)
    val_ll, label, factory = best

    fit_samples = buckets["train"] + buckets["validate"]
    Xfit, yfit = xy(fit_samples, feats)
    Xfit_s, mean, std = outcome_train.standardize(Xfit, Xfit)
    wfit = weights(fit_samples, decay)
    Xcal_s = (xy(buckets["calibrate"], feats)[0] - mean) / std
    Xte_s = (xy(buckets["test"], feats)[0] - mean) / std
    # Refit uses the validate season as the early-stopping set again for
    # xgboost (it is inside the fit set, so this only bounds tree count).
    model = fit(factory(), Xfit_s, yfit, wfit, (Xva - mean) / std, yva)

    temp = best_temperature(buckets["calibrate"], model.predict_proba(Xcal_s))
    test_raw = scored(buckets["test"], model.predict_proba(Xte_s))
    test = scored(buckets["test"], model.predict_proba(Xte_s), temp)
    return {
        "model": name,
        "chosen": label,
        "validate_log_loss": round(val_ll, 4),
        "temperature": temp,
        "test_log_loss_raw": round(metrics.log_loss(test_raw), 4),
        "test_log_loss": round(metrics.log_loss(test), 4),
        "brier": round(metrics.brier_score(test), 4),
        "rps": round(metrics.rps(test), 4),
        "accuracy": round(metrics.accuracy(test), 4),
        **{k: round(v, 4) for k, v in prf_macro(test).items()},
        "scored": test,
    }


def run_block(title: str, buckets: dict, feats: list, decay, quick: bool) -> list:
    n = {k: len(v) for k, v in buckets.items()}
    print(f"\n== {title}: features={len(feats)} decay={decay} "
          f"train={n['train']} val={n['validate']} cal={n['calibrate']} test={n['test']}", file=sys.stderr)
    rows = []
    for name, grid in candidates(quick).items():
        t0 = time.time()
        r = evaluate_family(name, grid, buckets, feats, decay)
        print(f"   {name:<14} {r['chosen']:<9} val {r['validate_log_loss']:.4f}  test {r['test_log_loss']:.4f} "
              f"(raw {r['test_log_loss_raw']:.4f}, T={r['temperature']})  acc {r['accuracy']:.3f}  [{time.time()-t0:.0f}s]",
              file=sys.stderr)
        rows.append(r)
    base = next(r for r in rows if r["model"] == "logistic")
    for r in rows:
        if r is base:
            r["vs_logistic"] = None
            continue
        boot = metrics.paired_bootstrap_log_loss_delta(r["scored"], base["scored"])
        r["vs_logistic"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in boot.items()}
    for r in rows:
        del r["scored"]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Classifier bake-off vs the deployed logistic models.")
    parser.add_argument("--leagues", default=",".join(leagues.TARGETS), help="comma list of league codes")
    parser.add_argument("--quick", action="store_true", help="single hyper-parameter per family")
    parser.add_argument("--no-pooled", action="store_true")
    args = parser.parse_args()
    codes = [c.strip() for c in args.leagues.split(",") if c.strip()]

    started = datetime.now(timezone.utc)
    report = {"generated_at": started.isoformat(), "splits": {
        "train": backtest_common.TRAIN_SEASONS, "validate": backtest_common.VALIDATE_SEASON,
        "calibrate": backtest_common.CALIBRATE_SEASON, "test": backtest_common.TEST_SEASON}, "leagues": {}}

    all_buckets = {"train": [], "validate": [], "calibrate": [], "test": []}
    for code in codes:
        buckets, feats, decay = league_data(code)
        report["leagues"][code] = {"features": feats, "decay": decay, "n_test": len(buckets["test"]),
                                   "results": run_block(code.upper(), buckets, feats, decay, args.quick)}
        for k in all_buckets:
            all_buckets[k].extend(buckets[k])

    if not args.no_pooled and len(codes) > 1:
        feats = list(global_train.GLOBAL_FEATS)
        report["pooled"] = {"features": feats, "decay": global_train.GLOBAL_DECAY, "n_test": len(all_buckets["test"]),
                            "results": run_block("POOLED", all_buckets, feats, global_train.GLOBAL_DECAY, args.quick)}

    out = config.REPORTS_DIR / f"model_comparison_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))

    # Summary table: test log loss per block, plus accuracy-family for pooled.
    blocks = [(c.upper(), report["leagues"][c]) for c in codes] + ([("POOLED", report["pooled"])] if "pooled" in report else [])
    names = list(candidates(True).keys())
    print("\ntest log loss (lower is better)")
    print(f"{'block':<8}" + "".join(f"{n:>14}" for n in names))
    for title, blk in blocks:
        by = {r["model"]: r for r in blk["results"]}
        print(f"{title:<8}" + "".join(f"{by[n]['test_log_loss']:>14.4f}" for n in names))
    print("\nwrote", out)


if __name__ == "__main__":
    main()
