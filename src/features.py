from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

import elo as elo_module

FORM_WINDOW = 10
EW_HALF_LIFE = 5  # matches; oldest of a 10-match window keeps 0.5**(9/5) ~= 0.29 weight
# Rest beyond two weeks carries no marginal readiness signal (international
# breaks are ~14 days, the longest normal in-season gap). Without the cap,
# season openers produce 60-90 day raw values whose diffs are fixture-list
# accidents, not competitive advantage. Cold start = cap: a team with no
# prior match is by definition fully rested, so two openers diff to 0.
REST_CAP_DAYS = 14.0
# 21 days spans ~3 league rounds plus any inserted midweek round -- long
# enough that a real pileup shows, short enough to reflect the current
# congestion. NOTE: only PL+Championship fixtures are ingested, so cup and
# European matches are invisible -- this measures LEAGUE congestion only and
# understates true congestion for teams in Europe (PRD 10.5 caveat).
CONGESTION_WINDOW_DAYS = 21

DRAW_WINDOW = 20  # draws are ~23% base rate; a 10-match window is too noisy (0-4 draws)
COLD_DRAW_RATE = 0.23  # PL base draw rate, per team
COLD_LOW_SCORING_RATE = 0.45  # PL under-2.5 base rate, per team


@dataclass
class TeamForm:
    played: int
    points_per_game: float
    goals_for_pg: float
    goals_against_pg: float
    wins: int
    draws: int
    losses: int


@dataclass
class H2HRecord:
    played: int
    home_wins: int
    draws: int
    away_wins: int
    home_win_rate: float
    away_win_rate: float


_COLD_FORM = TeamForm(0, 1.5, 1.35, 1.25, 0, 0, 0)
_COLD_H2H = H2HRecord(0, 0, 0, 0, 0.5, 0.5)


def _result_points(goals_for: int, goals_against: int) -> int:
    if goals_for > goals_against:
        return 3
    if goals_for == goals_against:
        return 1
    return 0


class FeatureStore:
    """Point-in-time feature store, keyed by team_id. `before` cutoffs are
    strict (< before), so no future match ever leaks into a form/h2h window."""

    def __init__(self):
        self._team_matches = defaultdict(list)
        self._h2h = defaultdict(list)

    def load(self, matches: list) -> None:
        for match in matches:
            home_id, away_id = match["home_team_id"], match["away_team_id"]
            hg, ag = match["home_goals"], match["away_goals"]
            date = match["kickoff_utc"]

            self._team_matches[home_id].append(
                {"date": date, "goals_for": hg, "goals_against": ag}
            )
            self._team_matches[away_id].append(
                {"date": date, "goals_for": ag, "goals_against": hg}
            )
            self._h2h[frozenset((home_id, away_id))].append(
                {"date": date, "home_team_id": home_id, "away_team_id": away_id, "home_goals": hg, "away_goals": ag}
            )

    def form(self, team_id: int, before, window: int = FORM_WINDOW) -> TeamForm:
        history = [m for m in self._team_matches.get(team_id, []) if m["date"] < before]
        recent = history[-window:]
        if not recent:
            return _COLD_FORM
        n = len(recent)
        points = sum(_result_points(m["goals_for"], m["goals_against"]) for m in recent)
        gf = sum(m["goals_for"] for m in recent)
        ga = sum(m["goals_against"] for m in recent)
        wins = sum(1 for m in recent if m["goals_for"] > m["goals_against"])
        draws = sum(1 for m in recent if m["goals_for"] == m["goals_against"])
        losses = n - wins - draws
        return TeamForm(n, points / n, gf / n, ga / n, wins, draws, losses)

    def ew_form(self, team_id: int, before, window: int = FORM_WINDOW, half_life: int = EW_HALF_LIFE) -> tuple:
        """Exponentially weighted (points_per_game, goals_for_pg, goals_against_pg)
        over the last `window` matches before `before`. Weight for the match k
        positions back (most recent = 0) is 0.5 ** (k / half_life). Cold start
        returns the same neutral constants as _COLD_FORM."""
        history = [m for m in self._team_matches.get(team_id, []) if m["date"] < before]
        recent = history[-window:]
        if not recent:
            return _COLD_FORM.points_per_game, _COLD_FORM.goals_for_pg, _COLD_FORM.goals_against_pg
        n = len(recent)
        total_w = ppg = gf = ga = 0.0
        for k, m in enumerate(reversed(recent)):  # k=0 is the most recent
            w = 0.5 ** (k / half_life)
            total_w += w
            ppg += w * _result_points(m["goals_for"], m["goals_against"])
            gf += w * m["goals_for"]
            ga += w * m["goals_against"]
        return ppg / total_w, gf / total_w, ga / total_w

    def schedule(self, team_id: int, before) -> tuple:
        """(rest_days capped at REST_CAP_DAYS, matches in the trailing
        CONGESTION_WINDOW_DAYS). Strict `date < before` on both."""
        history = [m for m in self._team_matches.get(team_id, []) if m["date"] < before]
        if not history:
            return REST_CAP_DAYS, 0
        rest_days = min((before - history[-1]["date"]).total_seconds() / 86400.0, REST_CAP_DAYS)
        cutoff = before - timedelta(days=CONGESTION_WINDOW_DAYS)
        congestion = sum(1 for m in history if m["date"] >= cutoff)
        return rest_days, congestion

    def draw_rate(self, team_id: int, before, window: int = DRAW_WINDOW) -> float:
        f = self.form(team_id, before, window)
        if f.played == 0:
            return COLD_DRAW_RATE
        return f.draws / f.played

    def low_scoring_rate(self, team_id: int, before, window: int = DRAW_WINDOW) -> float:
        history = [m for m in self._team_matches.get(team_id, []) if m["date"] < before]
        recent = history[-window:]
        if not recent:
            return COLD_LOW_SCORING_RATE
        return sum(1 for m in recent if m["goals_for"] + m["goals_against"] < 2.5) / len(recent)

    def h2h(self, home_id: int, away_id: int, before) -> H2HRecord:
        meetings = [m for m in self._h2h.get(frozenset((home_id, away_id)), []) if m["date"] < before]
        if not meetings:
            return _COLD_H2H
        n = len(meetings)
        home_wins = draws = away_wins = 0
        for m in meetings:
            if m["home_team_id"] == home_id:
                hg, ag = m["home_goals"], m["away_goals"]
            else:
                hg, ag = m["away_goals"], m["home_goals"]
            if hg > ag:
                home_wins += 1
            elif hg == ag:
                draws += 1
            else:
                away_wins += 1
        home_win_rate = (home_wins + 0.5 * draws) / n
        away_win_rate = (away_wins + 0.5 * draws) / n
        return H2HRecord(n, home_wins, draws, away_wins, home_win_rate, away_win_rate)

    def match_features(self, home_id: int, away_id: int, before, elo: "elo_module.EloRatings", neutral: bool) -> dict:
        hf = self.form(home_id, before)
        af = self.form(away_id, before)
        h2h = self.h2h(home_id, away_id, before)
        trust = min(h2h.played / 5.0, 1.0)

        h_ew_ppg, h_ew_gf, h_ew_ga = self.ew_form(home_id, before)
        a_ew_ppg, a_ew_gf, a_ew_ga = self.ew_form(away_id, before)
        h_rest, h_congestion = self.schedule(home_id, before)
        a_rest, a_congestion = self.schedule(away_id, before)

        home_adv = 0 if neutral else elo_module.HOME_ADVANTAGE
        elo_diff = elo.get(home_id) + home_adv - elo.get(away_id)
        return {
            "elo_diff": elo_diff,
            "form_diff": hf.points_per_game - af.points_per_game,
            "h2h_signal": trust * (h2h.home_win_rate - 0.5),
            "gf_diff": hf.goals_for_pg - af.goals_for_pg,
            "ga_diff": hf.goals_against_pg - af.goals_against_pg,
            "ew_form_diff": h_ew_ppg - a_ew_ppg,
            "ew_gf_diff": h_ew_gf - a_ew_gf,
            "ew_ga_diff": h_ew_ga - a_ew_ga,
            "rest_diff": h_rest - a_rest,
            "congestion_diff": float(h_congestion - a_congestion),
            # Draw-aware features. The draw logit of a linear model in SIGNED
            # elo_diff cannot represent "draws peak when teams are evenly
            # matched" -- -abs() fixes exactly that representational gap.
            "elo_closeness": -abs(elo_diff),
            # Sum, not diff: a draw is a joint outcome -- either side's draw
            # propensity raises match draw probability; differencing would
            # cancel the signal.
            "draw_rate_sum": self.draw_rate(home_id, before) + self.draw_rate(away_id, before),
            "low_scoring_sum": self.low_scoring_rate(home_id, before) + self.low_scoring_rate(away_id, before),
        }
