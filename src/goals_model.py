import json
import math
from pathlib import Path


def load_model(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run goals_train.py first")
    return json.loads(path.read_text())


def expected_goals(home_id: int, away_id: int, model: dict) -> tuple:
    team_index = {t: i for i, t in enumerate(model["teams"])}
    intercept = model["intercept"]
    home_flag_coef = model["home_flag_coef"]
    attack_coef = model["attack_coef"]
    defense_coef = model["defense_coef"]
    fallback_attack = model.get("fallback_attack_coef", 0.0)
    fallback_defense = model.get("fallback_defense_coef", 0.0)

    a_home = attack_coef[team_index[home_id]] if home_id in team_index else fallback_attack
    d_home = defense_coef[team_index[home_id]] if home_id in team_index else fallback_defense
    a_away = attack_coef[team_index[away_id]] if away_id in team_index else fallback_attack
    d_away = defense_coef[team_index[away_id]] if away_id in team_index else fallback_defense

    mu_home = math.exp(intercept + home_flag_coef + a_home + d_away)
    mu_away = math.exp(intercept + a_away + d_home)
    return mu_home, mu_away


def poisson_pmf(k: int, mu: float) -> float:
    return math.exp(-mu) * mu ** k / math.factorial(k)


def dc_tau(x: int, y: int, mu_home: float, mu_away: float, rho: float) -> float:
    """Dixon-Coles (1997) low-score dependency correction. rho < 0 boosts the
    0-0 and 1-1 cells (the draw scores) while shrinking 1-0/0-1. Because
    p1(mu) = mu * p0(mu), the four perturbations cancel pairwise, so the DC
    joint still sums to 1 over the infinite grid -- the correction only
    redistributes mass among these four cells."""
    if x == 0 and y == 0:
        return 1.0 - mu_home * mu_away * rho
    if x == 0 and y == 1:
        return 1.0 + mu_home * rho
    if x == 1 and y == 0:
        return 1.0 + mu_away * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(mu_home: float, mu_away: float, max_goals: int = 6, rho: float = 0.0) -> list:
    home_pmf = [poisson_pmf(i, mu_home) for i in range(max_goals + 1)]
    away_pmf = [poisson_pmf(j, mu_away) for j in range(max_goals + 1)]
    grid = [[hp * ap for ap in away_pmf] for hp in home_pmf]
    if rho:
        # All four DC cells lie inside the 0-6 cap, so the capped grid's
        # total mass is invariant vs rho=0. No renormalization here -- O/U
        # and BTTS keep the existing truncation semantics; the outcome-triple
        # derivation renormalizes separately.
        for x in (0, 1):
            for y in (0, 1):
                grid[x][y] = max(grid[x][y] * dc_tau(x, y, mu_home, mu_away, rho), 1e-12)
    return grid


def outcome_probs_from_matrix(matrix: list) -> tuple:
    """(p_home, p_draw, p_away) from the score grid's lower/diagonal/upper
    triangles, renormalized so the triple sums to exactly 1 (removes the 0-6
    truncation deficit)."""
    p_home = p_draw = p_away = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


def most_likely_score(matrix: list) -> tuple:
    best = (0, 0)
    best_p = -1.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if p > best_p:
                best_p = p
                best = (i, j)
    return best


def over_under_prob(matrix: list, line: float = 2.5) -> tuple:
    over = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if (i + j) > line:
                over += p
    return over, 1.0 - over


def btts_prob(matrix: list) -> float:
    total = 0.0
    for i, row in enumerate(matrix):
        if i == 0:
            continue
        for j, p in enumerate(row):
            if j >= 1:
                total += p
    return total
