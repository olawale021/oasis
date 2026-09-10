import json
import math

import numpy as np
from sklearn.linear_model import PoissonRegressor

import backtest_common
import config
import db
import goals_model
import leagues
import matches as matches_module
import metrics
import model_registry
import promotion

ALPHAS = [0.1, 0.3, 1.0, 3.0, 10.0]
RHO_STEP = 0.001
RHO_EPS = 1e-6


def team_roster(samples: list) -> list:
    teams = set()
    for s in samples:
        teams.add(s["home_team_id"])
        teams.add(s["away_team_id"])
    return sorted(teams)


STRENGTH_SCALE = 400.0  # Elo points per unit of the strength covariate


def build_design_matrix(samples: list, team_ids: list, use_strength: bool = False) -> tuple:
    index = {t: i for i, t in enumerate(team_ids)}
    n_teams = len(team_ids)
    n = len(samples)
    n_cols = 2 * n_teams + 1 + (1 if use_strength else 0)
    X = np.zeros((2 * n, n_cols))
    y = np.zeros(2 * n)
    for i, s in enumerate(samples):
        home_idx = index[s["home_team_id"]]
        away_idx = index[s["away_team_id"]]
        X[2 * i, home_idx] = 1.0
        X[2 * i, n_teams + away_idx] = 1.0
        X[2 * i, 2 * n_teams] = 1.0
        y[2 * i] = s["home_goals"]

        X[2 * i + 1, away_idx] = 1.0
        X[2 * i + 1, n_teams + home_idx] = 1.0
        y[2 * i + 1] = s["away_goals"]

        if use_strength:
            # Match-strength covariate (PRD 9.6 gap): long-run attack/defense
            # rates alone compress mus toward the league mean; the Elo margin
            # lets favorites' rates spread. +s for the home side's goals row,
            # -s for the away side's.
            strength = s["elo_diff"] / STRENGTH_SCALE
            X[2 * i, n_cols - 1] = strength
            X[2 * i + 1, n_cols - 1] = -strength
    return X, y


def season_weights(samples: list, decay) -> np.ndarray:
    """Per-FIXTURE decay weights (same scheme as outcome_train's), repeated x2
    for the long-format design matrix so both rows of a fixture share its
    weight. Returns None when decay is None."""
    if decay is None:
        return None
    ref = max(s["season"] for s in samples)
    w = np.array([decay ** (ref - s["season"]) for s in samples], dtype=float)
    return np.repeat(w, 2)


def poisson_deviance_np(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_pred = np.clip(y_pred, 1e-10, None)
    term = np.zeros_like(y_true, dtype=float)
    nonzero = y_true > 0
    term[nonzero] = y_true[nonzero] * np.log(y_true[nonzero] / y_pred[nonzero])
    dev = 2.0 * (term - (y_true - y_pred))
    return float(dev.mean())


def rho_bounds(mus: list) -> tuple:
    """Positivity bounds for the DC taus over every (mu_home, mu_away) in the
    fit set: rho > -1/max(mu) and rho < min(1, 1/max(mu_h*mu_a))."""
    max_mu = max(max(mh, ma) for mh, ma in mus)
    max_prod = max(mh * ma for mh, ma in mus)
    lo = -1.0 / max_mu + RHO_EPS
    hi = min(1.0, 1.0 / max_prod) - RHO_EPS
    return lo, hi


def fit_rho(fit_samples: list, artifact: dict, weights=None, step: float = RHO_STEP) -> tuple:
    """Profile MLE for rho: attack/defense/home are fixed from the Poisson
    fit; only fixtures whose observed score is in the four DC cells
    contribute non-constant likelihood terms. 1-D grid over the positivity
    bounds -- no scipy needed."""
    entries = []
    for i, s in enumerate(fit_samples):
        x, y = s["home_goals"], s["away_goals"]
        if x <= 1 and y <= 1:
            mu_h, mu_a = goals_model.expected_goals(s["home_team_id"], s["away_team_id"], artifact, s.get("elo_diff", 0.0))
            w = 1.0 if weights is None else float(weights[i])
            entries.append((x, y, mu_h, mu_a, w))

    all_mus = []
    for s in fit_samples:
        mu_h, mu_a = goals_model.expected_goals(s["home_team_id"], s["away_team_id"], artifact, s.get("elo_diff", 0.0))
        all_mus.append((mu_h, mu_a))
    lo, hi = rho_bounds(all_mus)

    def loglik(rho):
        return sum(w * math.log(goals_model.dc_tau(x, y, mu_h, mu_a, rho)) for x, y, mu_h, mu_a, w in entries)

    best_rho, best_ll = 0.0, loglik(0.0)
    rho = lo
    while rho <= hi:
        ll = loglik(rho)
        if ll > best_ll:
            best_ll, best_rho = ll, rho
        rho += step

    return best_rho, best_ll - loglik(0.0), (lo, hi)


DECAY_GRID = [None, 0.9, 0.8, 0.7]  # None = flat control; PRD 8.3 target is 0.8


def fit_goals_artifact(buckets: dict, decay="grid") -> dict:
    """The full goals-model ship protocol minus test scoring/writing:
    joint (alpha, decay) grid on train->validate deviance, final
    PoissonRegressor fit on train+validate+calibrate with the selected decay
    weights, then the DC rho profile fit on the same set. Flat-history fits
    dilute current team strength with seven-year-old seasons and compress the
    mu spread toward the league mean -- the decay grid lets validation decide.
    Pass an explicit decay (or None) to skip the decay grid; the default
    "grid" searches it. Reused by rolling_backtest.py."""
    train, validate, calibrate = buckets["train"], buckets["validate"], buckets["calibrate"]
    team_ids = team_roster(train + validate + calibrate)

    decay_grid = DECAY_GRID if decay == "grid" else [decay]
    best_alpha, best_dev, best_decay, best_strength = None, float("inf"), None, False
    for use_strength in (False, True):
        X_train, y_train = build_design_matrix(train, team_ids, use_strength)
        X_validate, y_validate = build_design_matrix(validate, team_ids, use_strength)
        for d in decay_grid:
            w_train = season_weights(train, d)
            for alpha in ALPHAS:
                clf = PoissonRegressor(alpha=alpha, fit_intercept=True, max_iter=300).fit(
                    X_train, y_train, sample_weight=w_train
                )
                dev = poisson_deviance_np(y_validate, clf.predict(X_validate))
                if dev < best_dev:
                    best_dev, best_alpha, best_decay, best_strength = dev, alpha, d, use_strength
    decay = best_decay

    fit_samples = train + validate + calibrate
    X_fit, y_fit = build_design_matrix(fit_samples, team_ids, best_strength)
    w_fit = season_weights(fit_samples, decay)
    clf = PoissonRegressor(alpha=best_alpha, fit_intercept=True, max_iter=300).fit(
        X_fit, y_fit, sample_weight=w_fit
    )

    n_teams = len(team_ids)
    coef = clf.coef_
    artifact = {
        "type": "poisson_dixon_coles",
        "teams": team_ids,
        "intercept": float(clf.intercept_),
        "home_flag_coef": float(coef[2 * n_teams]),
        "attack_coef": coef[:n_teams].tolist(),
        "defense_coef": coef[n_teams : 2 * n_teams].tolist(),
        "alpha": best_alpha,
        "fallback_attack_coef": 0.0,
        "fallback_defense_coef": 0.0,
        "decay": decay,
    }
    if best_strength:
        artifact["strength_coef"] = float(coef[2 * n_teams + 1])
        artifact["strength_scale"] = STRENGTH_SCALE

    fixture_weights = None if decay is None else season_weights(fit_samples, decay)[::2]
    rho, loglik_gain, bounds = fit_rho(fit_samples, artifact, weights=fixture_weights)
    # Shrink toward independence: sampling SE for rho is ~1.2/sqrt(n); apply
    # the DC correction only where |rho| clears 2*SE (Petretta 2025: England
    # ~0, Germany genuinely negative). A sub-noise rho adds nothing.
    rho_se = 1.2 / math.sqrt(max(len(fit_samples), 1))
    artifact["rho_raw"] = rho
    artifact["rho_se"] = rho_se
    if abs(rho) < 2.0 * rho_se:
        rho = 0.0
    artifact["rho"] = rho
    artifact["rho_bounds"] = list(bounds)
    artifact["rho_loglik_gain"] = loglik_gain
    return artifact


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train and ship a league goals model.")
    parser.add_argument("--league", type=str, default="pl", help=f"League code: {list(leagues.TARGETS)}")
    args = parser.parse_args()
    league_cfg = leagues.target_config(args.league)
    target_id, feeder_id = league_cfg["league_id"], league_cfg["feeder_id"]

    conn = db.get_connection()
    league_ids = [target_id] + ([feeder_id] if feeder_id else [])
    matches = matches_module.load_matches(conn, league_ids)
    transitions = (
        promotion.compute_transitions(conn, target_id, feeder_id, backtest_common.ALL_SEASONS)
        if feeder_id
        else {}
    )
    samples = backtest_common.collect_samples(matches, transitions, use_mov=True, target_league_id=target_id)
    buckets = backtest_common.split_by_season(samples)
    backtest_common.verify_no_leakage(buckets)

    model = fit_goals_artifact(buckets)  # joint (alpha, decay) grid on validate deviance
    print(
        f"goals model: alpha={model['alpha']} decay={model['decay']} strength={model.get('strength_coef')} rho={model['rho']:.4f} "
        f"rho_bounds=({model['rho_bounds'][0]:.4f}, {model['rho_bounds'][1]:.4f}) "
        f"rho_loglik_gain={model['rho_loglik_gain']:.2f}"
    )
    model["trained_on"] = (
        f"{backtest_common.TRAIN_SEASONS[0]}-{backtest_common.CALIBRATE_SEASON} (train+validate+calibrate PL fixtures)"
    )

    test_scored = []
    for s in buckets["test"]:
        mu_home, mu_away = goals_model.expected_goals(s["home_team_id"], s["away_team_id"], model, s.get("elo_diff", 0.0))
        test_scored.append({**s, "mu_home": mu_home, "mu_away": mu_away})

    rho = model["rho"]
    model["test_poisson_deviance"] = metrics.poisson_deviance(test_scored)
    model["test_mae_goals"] = metrics.mean_abs_goal_error(test_scored)
    model["test_exact_score_accuracy"] = metrics.exact_score_accuracy(test_scored, rho=rho)
    model["test_ou_ece"] = metrics.ou_calibration(test_scored, rho=rho)["ece"]
    model["test_btts_ece"] = metrics.btts_calibration(test_scored, rho=rho)["ece"]

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.MODELS_DIR / league_cfg["goals_artifact"]
    out_path.write_text(json.dumps(model, indent=2))
    model_registry.register(out_path, deployed=True)
    print(
        f"wrote {out_path}: test_poisson_deviance={model['test_poisson_deviance']} "
        f"test_mae={model['test_mae_goals']} test_exact_score_acc={model['test_exact_score_accuracy']:.4f}"
    )


if __name__ == "__main__":
    main()
