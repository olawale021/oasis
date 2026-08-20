import json
import math

import numpy as np
from sklearn.linear_model import LogisticRegressionCV

import backtest_common
import config
import db
import elo as elo_module
import matches as matches_module
import metrics
import model_registry
import outcome_model
import promotion
import richer_features

CLASS_NAMES = ["home", "draw", "away"]

THREE = ["elo_diff", "form_diff", "h2h_signal"]
FIVE = THREE + ["gf_diff", "ga_diff"]
SEVEN = FIVE + ["sot_diff", "possession_diff"]
NINE = SEVEN + ["missing_players_diff", "squad_disruption_diff"]

ELEVEN_SCHED = NINE + ["rest_diff", "congestion_diff"]
# EW variants REPLACE flat form/gf/ga (correlate >0.9 -- both would split one
# signal across two collinear columns in a ~2,200-row L2 logistic).
ELEVEN_EW = [
    "elo_diff", "ew_form_diff", "h2h_signal", "ew_gf_diff", "ew_ga_diff",
    "sot_diff", "possession_diff", "missing_players_diff", "squad_disruption_diff",
    "rest_diff", "congestion_diff",
]
TWELVE_CORN = ELEVEN_SCHED + ["corner_diff"]
THIRTEEN_XG = TWELVE_CORN + ["xg_diff"]
FOURTEEN_KS = ELEVEN_EW + ["corner_diff", "xg_diff", "xga_diff"]
# Draw-aware rungs: one isolating the representational fix (-abs(elo_diff)),
# one with the full draw pack.
TWELVE_CLOSE = ELEVEN_SCHED + ["elo_closeness"]
FOURTEEN_DRAW = ELEVEN_SCHED + ["elo_closeness", "draw_rate_sum", "low_scoring_sum"]

CANDIDATES = [
    ("logistic9", NINE),  # incumbent / control
    ("logistic11_sched", ELEVEN_SCHED),
    ("logistic11_ew", ELEVEN_EW),
    ("logistic12_corn", TWELVE_CORN),
    ("logistic13_xg", THIRTEEN_XG),
    ("logistic14_ks", FOURTEEN_KS),
    ("logistic12_close", TWELVE_CLOSE),
    ("logistic14_draw", FOURTEEN_DRAW),
]

DECAY_GRID = [None, 0.9, 0.8, 0.7]  # None = unweighted control; PRD 8.3 target is 0.8
TEMPERATURES = [round(0.5 + 0.05 * i, 2) for i in range(41)]  # 0.50..2.50 step 0.05


def matrix(samples: list, feats: list) -> np.ndarray:
    return np.array([[s[f] for f in feats] for s in samples], dtype=float)


def labels(samples: list) -> np.ndarray:
    return np.array([s["cls"] for s in samples], dtype=int)


def season_weights(samples: list, decay) -> np.ndarray:
    """decay ** (max_fit_season - season). Anchor is the most recent season IN
    THE FIT SET, so it's automatically 2022 during candidate evaluation (fit
    on train) and 2024 during the final refit."""
    if decay is None:
        return None
    ref = max(s["season"] for s in samples)
    return np.array([decay ** (ref - s["season"]) for s in samples], dtype=float)


def fit_logistic(X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray = None) -> LogisticRegressionCV:
    clf = LogisticRegressionCV(Cs=12, cv=5, max_iter=2000, scoring="neg_log_loss")
    return clf.fit(X, y, sample_weight=sample_weight)


def standardize(cols: np.ndarray, ref: np.ndarray) -> tuple:
    mean = ref.mean(axis=0)
    std = ref.std(axis=0)
    std[std == 0] = 1.0
    return (cols - mean) / std, mean, std


def _score(samples: list, artifact: dict) -> list:
    scored = []
    for s in samples:
        ph, pd, pa = outcome_model.predict_proba(s, artifact)
        scored.append({**s, "p_home": ph, "p_draw": pd, "p_away": pa})
    return scored


def evaluate_candidate(feats: list, train: list, validate: list, decay=None) -> float:
    Xtr_raw = matrix(train, feats)
    Xtr, mean, std = standardize(Xtr_raw, Xtr_raw)
    ytr = labels(train)
    clf = fit_logistic(Xtr, ytr, sample_weight=season_weights(train, decay))
    artifact = {
        "type": "multinomial_logistic",
        "features": feats,
        "means": mean.tolist(),
        "stds": std.tolist(),
        "coef": clf.coef_.tolist(),
        "intercept": clf.intercept_.tolist(),
        "home_advantage": elo_module.HOME_ADVANTAGE,
    }
    scored = _score(validate, artifact)
    return metrics.log_loss(scored)


def calibrate_temperature(base_artifact: dict, calibrate_samples: list) -> tuple:
    best_T, best_ll = 1.0, math.inf
    for T in TEMPERATURES:
        artifact = {**base_artifact, "temperature": T}
        scored = _score(calibrate_samples, artifact)
        ll = metrics.log_loss(scored)
        if ll < best_ll:
            best_ll, best_T = ll, T
    return best_T, best_ll


def build_artifact(feats: list, buckets: dict, decay=None) -> dict:
    """The full ship protocol minus test scoring/writing: fit on
    train+validate+calibrate with decay weights, temperature-scale on
    calibrate. Reused verbatim by rolling_backtest.py."""
    fit_samples = buckets["train"] + buckets["validate"] + buckets["calibrate"]
    X_raw = matrix(fit_samples, feats)
    X, mean, std = standardize(X_raw, X_raw)
    y = labels(fit_samples)
    clf = fit_logistic(X, y, sample_weight=season_weights(fit_samples, decay))

    artifact = {
        "type": "multinomial_logistic",
        "features": feats,
        "classes": CLASS_NAMES,
        "home_advantage": elo_module.HOME_ADVANTAGE,
        "means": mean.tolist(),
        "stds": std.tolist(),
        "coef": clf.coef_.tolist(),
        "intercept": clf.intercept_.tolist(),
        "decay": decay,
    }
    T, _ = calibrate_temperature(artifact, buckets["calibrate"])
    artifact["temperature"] = T
    return artifact


def load_enriched_buckets():
    conn = db.get_connection()
    matches = matches_module.load_matches(conn, [backtest_common.PL_ID, backtest_common.CHAMP_ID])
    transitions = promotion.compute_transitions(
        conn, backtest_common.PL_ID, backtest_common.CHAMP_ID, backtest_common.ALL_SEASONS
    )
    samples = backtest_common.collect_samples(matches, transitions, use_mov=True)
    samples = richer_features.enrich_samples(samples, conn)
    return conn, samples


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train and ship the PL outcome model.")
    parser.add_argument(
        "--ship",
        type=str,
        default=None,
        help="Candidate name to ship, bypassing single-season validate selection. "
        "Use when rolling_backtest.py's mean-across-folds decision overrules the "
        "single-split pick (the harness is the honest bar; one validate season is noise).",
    )
    parser.add_argument("--decay", type=str, default=None, help='Decay override, e.g. "0.8" or "none"')
    args = parser.parse_args()

    conn, samples = load_enriched_buckets()
    buckets = backtest_common.split_by_season(samples)
    backtest_common.verify_no_leakage(buckets)

    candidates_by_name = dict(CANDIDATES)

    if args.ship:
        if args.ship not in candidates_by_name:
            raise SystemExit(f"unknown candidate {args.ship!r}; choices: {list(candidates_by_name)}")
        ship_name = args.ship
        feats = candidates_by_name[ship_name]
        if args.decay is None:
            best_decay = 0.8  # the harness evaluates ladder rows at the PRD 8.3 decay
        else:
            best_decay = None if args.decay.lower() == "none" else float(args.decay)
        print(f"shipping {ship_name} (harness override, decay={best_decay}): {feats}")
    else:
        # Stage 1: pick decay on the incumbent feature set (None row doubles
        # as the no-decay control).
        decay_results = []
        for decay in DECAY_GRID:
            ll = evaluate_candidate(NINE, buckets["train"], buckets["validate"], decay=decay)
            decay_results.append((decay, ll))
            print(f"decay grid: decay={decay} validate_log_loss={ll:.4f}")
        best_decay, _ = min(decay_results, key=lambda r: r[1])
        print(f"selected decay: {best_decay}")

        # Stage 2: feature ladder at the selected decay.
        results = []
        for name, feats in CANDIDATES:
            ll = evaluate_candidate(feats, buckets["train"], buckets["validate"], decay=best_decay)
            results.append((name, feats, ll))
            print(f"validate log_loss: {name}={ll:.4f}")

        ship_name, feats, _ = min(results, key=lambda r: r[2])
        print(f"shipping {ship_name}: {feats}")

    artifact = build_artifact(feats, buckets, decay=best_decay)
    print(f"temperature={artifact['temperature']}")

    test_scored = _score(buckets["test"], artifact)
    test_metrics = metrics.all_outcome_metrics(test_scored)
    by_class = metrics.group_metrics(test_scored, key_fn=lambda s: s["cls"])

    artifact.update(
        {
            "label": f"{ship_name} [{', '.join(feats)}] logistic regression (sklearn L2-CV), "
            f"decay={best_decay}, temperature-scaled on {backtest_common.CALIBRATE_SEASON}",
            "test_log_loss": test_metrics["log_loss"],
            "test_accuracy": test_metrics["accuracy"],
            "test_rps": test_metrics["rps"],
            "test_draw_log_loss": by_class.get("1", {}).get("log_loss"),
            "selected_on": f"validate={backtest_common.VALIDATE_SEASON} (decay grid + ladder); calibrated on {backtest_common.CALIBRATE_SEASON} (temperature); test={backtest_common.TEST_SEASON} scored once",
            "trained_on": f"{backtest_common.TRAIN_SEASONS[0]}-{backtest_common.CALIBRATE_SEASON} (train+validate+calibrate), min_games={backtest_common.MIN_GAMES}",
        }
    )

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MODELS_DIR / "outcome_model_pl.json"
    out_path.write_text(json.dumps(artifact, indent=2))
    entry = model_registry.register(out_path, deployed=True)
    print(
        f"wrote {out_path}: test_log_loss={test_metrics['log_loss']:.4f} "
        f"test_accuracy={test_metrics['accuracy']:.4f} test_rps={test_metrics['rps']:.4f} "
        f"test_draw_log_loss={artifact['test_draw_log_loss']:.4f}"
    )
    print(f"registered {entry['version']} [deployed] sha256={entry['checksum_sha256'][:12]}…")


if __name__ == "__main__":
    main()
