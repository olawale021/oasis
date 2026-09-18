import json
import math

import numpy as np
from sklearn.linear_model import LogisticRegressionCV

import backtest_common
import config
import db
import elo as elo_module
import leagues
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

# Fixtures+injuries-only ladder for leagues without shot-stat/lineup
# enrichment ingested yet (everything here derives from fixtures/results
# plus the /injuries feed).
BASE_FIVE = ["elo_diff", "ew_form_diff", "h2h_signal", "ew_gf_diff", "ew_ga_diff"]
BASE_SEVEN = BASE_FIVE + ["rest_diff", "congestion_diff"]
BASE_EIGHT = BASE_SEVEN + ["missing_players_diff"]
# New all-league features (fixtures-only construction): venue-split form,
# Elo momentum, schedule strength.
NEW3 = ["venue_form_diff", "elo_trend_diff", "sched_strength_diff"]

# Literature batch A: learned rating features (pi + Berrar) -- the largest
# documented gain in the field is these replacing recency aggregates.
RATING3 = ["pi_pred_gd", "ber_gh", "ber_ga"]
# Literature batch B: closed-door flag, threshold rest, longer EW window.
GHOST = ["ghost_game"]
RESTBINS = ["short_rest_diff", "long_rest_diff"]
EW_TRIO = ["ew_form_diff", "ew_gf_diff", "ew_ga_diff"]
EW10_TRIO = ["ew10_form_diff", "ew10_gf_diff", "ew10_ga_diff"]
# The literature's "ratings replace recency" thesis, as a compact set.
RATINGS_CORE = ["elo_diff", "pi_pred_gd", "ber_gh", "ber_ga",
                "rest_diff", "congestion_diff", "missing_players_diff", "sched_strength_diff"]
# Knockout-tie flag (European competitions; 0 for every league round).
KO = ["ko_stage"]


def _swap(feats, old, new):
    return [f for f in feats if f not in old] + new


def _minus(feats, drop):
    return [f for f in feats if f != drop]

BASE_CANDIDATES = [
    ("logistic5_base", BASE_FIVE),
    ("logistic7_base", BASE_SEVEN),
    ("logistic8_inj", BASE_EIGHT),
    ("logistic9_venue", BASE_EIGHT + ["venue_form_diff"]),
    ("logistic9_trend", BASE_EIGHT + ["elo_trend_diff"]),
    ("logistic9_schedstr", BASE_EIGHT + ["sched_strength_diff"]),
    ("logistic11_new3", BASE_EIGHT + NEW3),
    ("base_ratings", BASE_EIGHT + RATING3),
    ("base_minus_h2h", _minus(BASE_EIGHT, "h2h_signal")),
    ("base_ghost", BASE_EIGHT + GHOST),
    ("base_restbins", BASE_EIGHT + RESTBINS),
    ("base_ew10", _swap(BASE_EIGHT, EW_TRIO, EW10_TRIO)),
    ("ratings_core", RATINGS_CORE),
    ("base_kitchen", BASE_EIGHT + NEW3 + RATING3 + GHOST),
]

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

# Appended after NEW3 exists (list built above CANDIDATES for the base ladder).
CANDIDATES += [
    ("logistic12_venue", ELEVEN_EW + ["venue_form_diff"]),
    ("logistic12_trend", ELEVEN_EW + ["elo_trend_diff"]),
    ("logistic12_schedstr", ELEVEN_EW + ["sched_strength_diff"]),
    ("logistic14_new3", ELEVEN_EW + NEW3),
    ("full_ratings", ELEVEN_EW + RATING3),
    ("full_minus_h2h", _minus(ELEVEN_EW, "h2h_signal")),
    ("full_ghost", ELEVEN_EW + GHOST),
    ("full_restbins", ELEVEN_EW + RESTBINS),
    ("full_ew10", _swap(ELEVEN_EW, EW_TRIO, EW10_TRIO)),
    ("ratings_core", RATINGS_CORE),
    ("full_kitchen", ELEVEN_EW + NEW3 + RATING3 + GHOST),
]

# Transfermarkt squad value (ingest_squad_values.py): every rung gets a
# "+value" twin so the harness-endorsed set can ship by name. Paired 5-fold
# test 2026-09-10: PL -0.0036, LAL -0.0010, SEA -0.0051, BUN -0.0020, MLS 0.
VALUE = ["value_diff"]
BASE_CANDIDATES += [(name + "_value", feats + VALUE) for name, feats in list(BASE_CANDIDATES)]
CANDIDATES += [(name + "_value", feats + VALUE) for name, feats in list(CANDIDATES)]
# Player-based strength (player_ratings.py): "+xi" twins. Paired 5-fold test
# 2026-09-10: PL -0.0007, LAL 0, BUN +0.0001 -- below the floor; shipped in
# PL on the operator's call (2026-09-10).
XI = ["xi_strength_diff"]
BASE_CANDIDATES += [(name + "_xi", feats + XI) for name, feats in list(BASE_CANDIDATES)]
# Champions League (2026-09-18 harness): league-relative form features hurt
# across leagues of different strength; the pooled-Elo + squad-value pair is
# the endorsed set (5-fold mean 0.9186 vs calibrated Elo 0.9289).
ELO_VALUE = ["elo_diff", "elo_closeness"] + VALUE
LEG2 = ["leg2", "leg2_agg_diff"]
BASE_CANDIDATES += [("elo_value", ELO_VALUE), ("elo_value_ko", ELO_VALUE + KO), ("elo_value_leg2", ELO_VALUE + LEG2),
                    ("elo_value_ko_leg2", ELO_VALUE + KO + LEG2)]
CANDIDATES += [(name + "_xi", feats + XI) for name, feats in list(CANDIDATES)]

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


def _weighted_ll(samples, artifact, weights):
    total = w_total = 0.0
    for s, w in zip(samples, weights):
        p = outcome_model.predict_proba(s, artifact)
        total += w * -math.log(max(p[s["cls"]], 1e-15))
        w_total += w
    return total / w_total


def _fit_scalar_params(fit_samples, weights, make_artifact, grids, rounds=3):
    """Cyclic coordinate search with grid refinement -- pure python, enough
    for 3-4 parameter challengers."""
    params = {k: g[len(g) // 2] for k, g in grids.items()}
    for _ in range(rounds):
        for k, g in grids.items():
            best_v, best_ll = params[k], float("inf")
            for v in g:
                trial = dict(params)
                trial[k] = v
                ll = _weighted_ll(fit_samples, make_artifact(trial), weights)
                if ll < best_ll:
                    best_ll, best_v = ll, v
            params[k] = best_v
            span = (g[-1] - g[0]) / (len(g) - 1)
            grids[k] = [best_v + span * f for f in (-0.75, -0.375, 0.0, 0.375, 0.75)]
    return params


def build_ordered_artifact(feat: str, buckets: dict, decay=None) -> dict:
    fit = buckets["train"] + buckets["validate"] + buckets["calibrate"]
    w = season_weights(fit, decay)
    weights = [1.0] * len(fit) if w is None else list(w)
    scale = max(1e-9, float(np.std([s[feat] for s in fit])))
    grids = {
        "beta": [i / (10.0 * scale) for i in range(1, 21)],
        "c1": [-1.5 + 0.15 * i for i in range(11)],
        "c2": [-0.3 + 0.15 * i for i in range(11)],
    }
    params = _fit_scalar_params(fit, weights, lambda pr: {"type": "ordered_logit", "feat": feat, **pr}, grids)
    if params["c1"] > params["c2"]:
        params["c1"], params["c2"] = params["c2"], params["c1"]
    return {"type": "ordered_logit", "feat": feat, **params}


def build_davidson_artifact(feat: str, buckets: dict, decay=None) -> dict:
    fit = buckets["train"] + buckets["validate"] + buckets["calibrate"]
    w = season_weights(fit, decay)
    weights = [1.0] * len(fit) if w is None else list(w)
    scale = max(1e-9, float(np.std([s[feat] for s in fit])))
    grids = {
        "beta": [i / (10.0 * scale) for i in range(1, 21)],
        "h": [-0.2 + 0.08 * i for i in range(11)],
        "nu": [0.4 + 0.08 * i for i in range(11)],
    }
    params = _fit_scalar_params(fit, weights, lambda pr: {"type": "davidson", "feat": feat, **pr}, grids)
    return {"type": "davidson", "feat": feat, **params}


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


def load_enriched_buckets(league_cfg: dict = None, score_feeders: bool = False):
    league_cfg = league_cfg or leagues.target_config("pl")
    target_id, feeder_id = league_cfg["league_id"], league_cfg["feeder_id"]
    conn = db.get_connection()
    league_ids = leagues.pool_ids(league_cfg)
    matches = matches_module.load_matches(conn, league_ids)
    transitions = (
        promotion.compute_transitions(conn, target_id, feeder_id, backtest_common.ALL_SEASONS)
        if feeder_id
        else {}
    )
    schedule = matches_module.load_schedule_matches(conn)
    samples = backtest_common.collect_samples(matches, transitions, use_mov=True, target_league_id=target_id, score_feeders=score_feeders, schedule_matches=schedule)
    samples = richer_features.enrich_samples(samples, conn, league_id=target_id)
    return conn, samples


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train and ship a league outcome model.")
    parser.add_argument("--league", type=str, default="pl", help=f"League code: {list(leagues.TARGETS)}")
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

    league_cfg = leagues.target_config(args.league)

    conn, samples = load_enriched_buckets(league_cfg)
    buckets = backtest_common.split_by_season(samples)
    backtest_common.verify_no_leakage(buckets)

    # The full ladder needs shot-stat + lineup enrichment ingested for this
    # league; without it those columns are all-zero and the wider rungs are
    # meaningless, so fall back to the fixtures+injuries ladder.
    target_id = league_cfg["league_id"]
    n_stats = conn.execute(
        "SELECT COUNT(*) FROM fixture_statistics fs JOIN fixtures f ON f.fixture_id = fs.fixture_id"
        " WHERE f.league_id = ?",
        (target_id,),
    ).fetchone()[0]
    n_lineups = conn.execute(
        "SELECT COUNT(*) FROM lineup_players lp JOIN fixtures f ON f.fixture_id = lp.fixture_id"
        " WHERE f.league_id = ?",
        (target_id,),
    ).fetchone()[0]
    enriched = n_stats > 1000 and n_lineups > 1000
    print(f"enrichment: {n_stats} stat rows, {n_lineups} lineup-player rows -> {'full' if enriched else 'base'} ladder")

    candidates = CANDIDATES if enriched else BASE_CANDIDATES
    decay_probe_feats = NINE if enriched else BASE_SEVEN
    candidates_by_name = dict(candidates)

    if args.ship:
        # Ship-by-name may reference either ladder: a league's enrichment
        # status can flip when statistics are ingested, but the harness
        # endorsed a specific named set.
        ship_choices = dict(BASE_CANDIDATES + CANDIDATES)
        if args.ship not in ship_choices:
            raise SystemExit(f"unknown candidate {args.ship!r}; choices: {list(ship_choices)}")
        ship_name = args.ship
        feats = ship_choices[ship_name]
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
            ll = evaluate_candidate(decay_probe_feats, buckets["train"], buckets["validate"], decay=decay)
            decay_results.append((decay, ll))
            print(f"decay grid: decay={decay} validate_log_loss={ll:.4f}")
        best_decay, _ = min(decay_results, key=lambda r: r[1])
        print(f"selected decay: {best_decay}")

        # Stage 2: feature ladder at the selected decay.
        results = []
        for name, feats in candidates:
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
    out_path = config.MODELS_DIR / league_cfg["outcome_artifact"]
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
