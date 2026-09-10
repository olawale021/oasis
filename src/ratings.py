"""Learned rating systems (literature batch A).

pi-ratings (Constantinou & Fenton 2013, JQAS 9(1)) and Berrar ratings
(Berrar, Lopes & Dubitzky 2019, ML 108) -- the single largest documented
feature gain in the football-forecasting literature is replacing windowed
recency aggregates with these learned rating features (-0.007 to -0.0105
RPS on identical models/data). Both are pure-python, O(1) per match, and
update chronologically exactly like the Elo store.

Per-league hyperparameters are fitted by grid search minimising squared
goal(-difference) error over the WARM-UP years only (2010-2016, before
backtest_common.TRAIN_SEASONS) -- outside every harness fold, so the fold
evaluations carry no parameter leakage. Fitted params are cached in
data/models/rating_params_{code}.json and reused by training, the harness,
evaluation, and predict.
"""

import json
import math

import config

PI_B = 10.0
PI_C = 3.0


class PiRatings:
    """Two ratings per team (home venue, away venue) targeting expected goal
    difference, with logarithmic error damping and cross-venue leakage."""

    def __init__(self, lam: float = 0.054, gamma: float = 0.7):
        self.lam = lam
        self.gamma = gamma
        self.home_r = {}
        self.away_r = {}

    @staticmethod
    def _gd(rating: float) -> float:
        return math.copysign(PI_B ** (abs(rating) / PI_C) - 1.0, rating)

    def pred_gd(self, home_id: int, away_id: int) -> float:
        return self._gd(self.home_r.get(home_id, 0.0)) - self._gd(self.away_r.get(away_id, 0.0))

    def update(self, home_id: int, away_id: int, home_goals: int, away_goals: int) -> None:
        err = (home_goals - away_goals) - self.pred_gd(home_id, away_id)
        psi = math.copysign(PI_C * math.log10(1.0 + abs(err)), err)
        d_home = self.lam * psi
        self.home_r[home_id] = self.home_r.get(home_id, 0.0) + d_home
        self.away_r[home_id] = self.away_r.get(home_id, 0.0) + self.gamma * d_home
        d_away = -self.lam * psi
        self.away_r[away_id] = self.away_r.get(away_id, 0.0) + d_away
        self.home_r[away_id] = self.home_r.get(away_id, 0.0) + self.gamma * d_away


class BerrarRatings:
    """Venue-specific attack/defence ratings with a sigmoid goals link
    (caps expected goals at alpha, which beats an exponential link on
    blowouts). Simplified parameterisation: shared beta/gamma/omegas across
    venues -- 4 fitted params instead of the paper's 7."""

    def __init__(self, beta: float = 1.2, gamma0: float = 0.3, omega_o: float = 0.1, omega_d: float = 0.1, alpha: float = 5.0):
        self.alpha = alpha
        self.beta = beta
        self.gamma0 = gamma0
        self.omega_o = omega_o
        self.omega_d = omega_d
        self.o_home = {}
        self.d_home = {}
        self.o_away = {}
        self.d_away = {}

    def _g(self, o: float, d: float) -> float:
        z = -self.beta * (o - d) - self.gamma0
        return self.alpha / (1.0 + math.exp(max(min(z, 35.0), -35.0)))

    def pred_goals(self, home_id: int, away_id: int) -> tuple:
        gh = self._g(self.o_home.get(home_id, 0.0), self.d_away.get(away_id, 0.0))
        ga = self._g(self.o_away.get(away_id, 0.0), self.d_home.get(home_id, 0.0))
        return gh, ga

    def update(self, home_id: int, away_id: int, home_goals: int, away_goals: int) -> None:
        # Attack rises when you score more than expected; defense FALLS when
        # you concede more than expected (higher d suppresses opponent goals
        # in the link, so the defense update must be error-negative -- the
        # error-positive form quoted in some summaries is a positive-feedback
        # loop that diverges, which our smoke test confirmed empirically).
        gh_hat, ga_hat = self.pred_goals(home_id, away_id)
        self.o_home[home_id] = self.o_home.get(home_id, 0.0) + self.omega_o * (home_goals - gh_hat)
        self.d_home[home_id] = self.d_home.get(home_id, 0.0) + self.omega_d * (ga_hat - away_goals)
        self.o_away[away_id] = self.o_away.get(away_id, 0.0) + self.omega_o * (away_goals - ga_hat)
        self.d_away[away_id] = self.d_away.get(away_id, 0.0) + self.omega_d * (gh_hat - home_goals)


def _replay_pi(matches: list, lam: float, gamma: float) -> float:
    pi = PiRatings(lam, gamma)
    sse = 0.0
    for m in matches:
        sse += ((m["home_goals"] - m["away_goals"]) - pi.pred_gd(m["home_team_id"], m["away_team_id"])) ** 2
        pi.update(m["home_team_id"], m["away_team_id"], m["home_goals"], m["away_goals"])
    return sse


def _replay_berrar(matches: list, beta: float, gamma0: float, omega_o: float, omega_d: float) -> float:
    br = BerrarRatings(beta, gamma0, omega_o, omega_d)
    sse = 0.0
    for m in matches:
        gh, ga = br.pred_goals(m["home_team_id"], m["away_team_id"])
        sse += (m["home_goals"] - gh) ** 2 + (m["away_goals"] - ga) ** 2
        br.update(m["home_team_id"], m["away_team_id"], m["home_goals"], m["away_goals"])
    return sse


def fit_params(matches_warmup: list) -> dict:
    """Grid-fit pi and Berrar hyperparameters on the warm-up window."""
    best_pi, best_sse = (0.054, 0.7), float("inf")
    for lam in (0.03, 0.045, 0.06, 0.08):
        for gamma in (0.4, 0.6, 0.8):
            sse = _replay_pi(matches_warmup, lam, gamma)
            if sse < best_sse:
                best_sse, best_pi = sse, (lam, gamma)

    best_br, best_sse = (1.2, 0.3, 0.1, 0.1), float("inf")
    for beta in (0.8, 1.2, 1.8):
        for gamma0 in (0.0, 0.3, 0.6):
            for omega_o in (0.05, 0.1, 0.2):
                for omega_d in (0.05, 0.1, 0.2):
                    sse = _replay_berrar(matches_warmup, beta, gamma0, omega_o, omega_d)
                    if sse < best_sse:
                        best_sse, best_br = sse, (beta, gamma0, omega_o, omega_d)

    return {
        "pi": {"lam": best_pi[0], "gamma": best_pi[1]},
        "berrar": {"beta": best_br[0], "gamma0": best_br[1], "omega_o": best_br[2], "omega_d": best_br[3]},
    }


def get_params(code: str, matches: list, warmup_end_season: int = 2017) -> dict:
    """Cached per-league params, fitted on seasons before `warmup_end_season`
    (the warm-up years -- outside every harness fold). Falls back to
    literature defaults when there is no warm-up history."""
    path = config.MODELS_DIR / f"rating_params_{code}.json"
    if path.exists():
        return json.loads(path.read_text())
    warmup = [m for m in matches if m["season"] < warmup_end_season]
    if len(warmup) < 500:
        params = {"pi": {"lam": 0.054, "gamma": 0.7}, "berrar": {"beta": 1.2, "gamma0": 0.3, "omega_o": 0.1, "omega_d": 0.1}}
    else:
        params = fit_params(warmup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params, indent=2))
    return params


def build_stores(params: dict) -> tuple:
    pi = PiRatings(params["pi"]["lam"], params["pi"]["gamma"])
    br = BerrarRatings(
        params["berrar"]["beta"], params["berrar"]["gamma0"],
        params["berrar"]["omega_o"], params["berrar"]["omega_d"],
    )
    return pi, br
