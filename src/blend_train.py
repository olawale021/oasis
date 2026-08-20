"""Train the logistic+Dixon-Coles blend: p = w * p_logistic + (1-w) * p_dc.

Linear opinion pool (on-simplex, one parameter, graceful w->1 fallback to the
logistic). Stacking (DC prob as a logistic FEATURE) is deliberately rejected:
train rows' DC outputs come from a model fit on those same rows, leaking
target information into the refit. Post-hoc blending touches neither
component's training; (T, w) are fit jointly on the calibrate bucket only --
the same protocol as the existing temperature scaling.
"""

import json
import math

import backtest_common
import config
import goals_train
import metrics
import outcome_model
import outcome_train

WEIGHTS = [round(0.05 * i, 2) for i in range(21)]  # 0.00..1.00


def _logistic_logits(sample: dict, artifact: dict) -> list:
    feats = tuple(sample[name] for name in artifact["features"])
    x = [(f - mean) / std for f, mean, std in zip(feats, artifact["means"], artifact["stds"])]
    return [
        inter + sum(c * xi for c, xi in zip(coef, x))
        for coef, inter in zip(artifact["coef"], artifact["intercept"])
    ]


def _softmax(logits: list) -> tuple:
    top = max(logits)
    exps = [math.exp(z - top) for z in logits]
    total = sum(exps)
    return tuple(e / total for e in exps)


def cache_calibrate_inputs(cal_samples: list, logistic_artifact: dict, dc_artifact: dict) -> tuple:
    """Pre-compute per-sample pre-temperature logistic logits and DC prob
    triples once, so the (T, w) grid is pure arithmetic."""
    dc_wrapper = {"type": "dc_outcome", "goals": dc_artifact}
    logits = [_logistic_logits(s, logistic_artifact) for s in cal_samples]
    dc_probs = [outcome_model.predict_proba(s, dc_wrapper) for s in cal_samples]
    cls = [s["cls"] for s in cal_samples]
    return logits, dc_probs, cls


def select_blend(logits: list, dc_probs: list, cls: list, temperatures=None, weights=None) -> tuple:
    """Joint (T, w) grid on the calibrate bucket by log-loss. The blend wants
    a different temperature than the standalone logistic (the DC partner
    already dampens overconfidence). Deterministic: iterate w then T
    ascending, keep strictly-better only."""
    temperatures = temperatures or outcome_train.TEMPERATURES
    weights = weights or WEIGHTS
    eps = 1e-15
    n = len(cls)
    best = None
    for w in weights:
        for T in temperatures:
            total = 0.0
            for i in range(n):
                lp = _softmax([z / T for z in logits[i]])
                p = w * lp[cls[i]] + (1.0 - w) * dc_probs[i][cls[i]]
                total += -math.log(max(p, eps))
            ll = total / n
            if best is None or ll < best[2]:
                best = (T, w, ll)
    return best


def main() -> None:
    conn, samples = outcome_train.load_enriched_buckets()
    buckets = backtest_common.split_by_season(samples)
    backtest_common.verify_no_leakage(buckets)

    shipped = outcome_model.load_model(config.MODELS_DIR / "outcome_model_pl.json")
    feats = shipped["features"]
    decay = shipped.get("decay")
    print(f"blend components: logistic[{','.join(feats)}] decay={decay} + dixon-coles")

    logistic = outcome_train.build_artifact(feats, buckets, decay=decay)
    goals = goals_train.fit_goals_artifact(buckets, decay=decay)

    logits, dc_probs, cls = cache_calibrate_inputs(buckets["calibrate"], logistic, goals)
    T, w, cal_ll = select_blend(logits, dc_probs, cls)
    print(f"selected T={T} w={w} calibrate_log_loss={cal_ll:.4f}")

    logistic["temperature"] = T
    artifact = {
        "type": "blend",
        "classes": ["home", "draw", "away"],
        "components": [
            {"weight": w, "model": logistic},
            {"weight": round(1.0 - w, 4), "model": {"type": "dc_outcome", "max_goals": 6, "goals": goals}},
        ],
        "selected_on": f"calibrate {backtest_common.CALIBRATE_SEASON}: joint (T, w) grid by log_loss",
    }

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MODELS_DIR / "outcome_blend_pl.json"
    out_path.write_text(json.dumps(artifact, indent=2))

    reloaded = outcome_model.load_model(out_path)
    test_scored = outcome_train._score(buckets["test"], reloaded)
    test_metrics = metrics.all_outcome_metrics(test_scored)
    by_class = metrics.group_metrics(test_scored, key_fn=lambda s: s["cls"])

    artifact.update(
        {
            "test_log_loss": test_metrics["log_loss"],
            "test_rps": test_metrics["rps"],
            "test_accuracy": test_metrics["accuracy"],
            "test_draw_log_loss": by_class.get("1", {}).get("log_loss"),
        }
    )
    out_path.write_text(json.dumps(artifact, indent=2))
    print(
        f"wrote {out_path}: test_log_loss={test_metrics['log_loss']:.4f} "
        f"test_rps={test_metrics['rps']:.4f} test_accuracy={test_metrics['accuracy']:.4f} "
        f"test_draw_log_loss={artifact['test_draw_log_loss']:.4f}"
    )


if __name__ == "__main__":
    main()
