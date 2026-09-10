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

# Closed-door COVID window (approximate, all leagues): a measured collapse
# of home advantage sits inside the training years -- flagging it removes a
# known bias from ~10% of training rows (Leitner 2023; Arrondel 2024).
GHOST_START = "2020-03-08"
GHOST_END = "2021-06-30"

VENUE_FORM_WINDOW = 5  # PRD 10.2: home-only / away-only form over last 5 venue matches
SCHED_STRENGTH_WINDOW = 10  # opponents considered for schedule strength

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


class LeagueContext:
    """Point-in-time league-level covariates (Hubacek et al. 2019, sec 4.6):
    rolling home-win rate, draw rate, average home/away goals, and team count
    for the league a match belongs to. These generalise across divisions --
    the block that made pooled training beat per-league in the only published
    head-to-head. Update AFTER reading features for a match (like Elo)."""

    WINDOW = 760  # ~2 seasons of a 20-team league

    COLD = {"lg_hw_rate": 0.45, "lg_draw_rate": 0.25, "lg_goals_h": 1.5, "lg_goals_a": 1.2, "lg_n_teams": 20.0}

    def __init__(self):
        from collections import deque
        self._hist = defaultdict(lambda: deque(maxlen=self.WINDOW))
        self._season_teams = defaultdict(set)

    def features(self, league_id: int) -> dict:
        hist = self._hist.get(league_id)
        if not hist or len(hist) < 50:
            return dict(self.COLD)
        n = len(hist)
        hw = sum(1 for hg, ag in hist if hg > ag) / n
        dr = sum(1 for hg, ag in hist if hg == ag) / n
        gh = sum(hg for hg, _ in hist) / n
        ga = sum(ag for _, ag in hist) / n
        return {"lg_hw_rate": hw, "lg_draw_rate": dr, "lg_goals_h": gh, "lg_goals_a": ga,
                "lg_n_teams": float(len(self._season_teams.get(league_id, [])) or 20)}

    def update(self, league_id: int, season: int, home_id: int, away_id: int, hg: int, ag: int) -> None:
        self._hist[league_id].append((hg, ag))
        key = league_id
        # reset the roster set at a season boundary
        if getattr(self, "_season_of", None) is None:
            self._season_of = {}
        if self._season_of.get(key) != season:
            self._season_of[key] = season
            self._season_teams[key] = set()
        self._season_teams[key].update((home_id, away_id))


class FeatureStore:
    """Point-in-time feature store, keyed by team_id. `before` cutoffs are
    strict (< before), so no future match ever leaks into a form/h2h window."""

    def __init__(self):
        self._team_matches = defaultdict(list)
        self._h2h = defaultdict(list)
        # All-competition kickoff dates per team (cups, Europe, friendlies),
        # for rest/congestion only. Empty until load_schedule() is called, in
        # which case the *_all features fall back to league-only values.
        self._team_schedule = defaultdict(list)

    def load_schedule(self, matches: list) -> None:
        for match in matches:
            date = match["kickoff_utc"]
            self._team_schedule[match["home_team_id"]].append(date)
            self._team_schedule[match["away_team_id"]].append(date)
        for dates in self._team_schedule.values():
            dates.sort()

    def schedule_all(self, team_id: int, before) -> tuple:
        """schedule() over every competition the club played. Falls back to
        the league-only schedule when no all-competition index is loaded."""
        dates = self._team_schedule.get(team_id)
        if not dates:
            return self.schedule(team_id, before)
        history = [d for d in dates if d < before]
        if not history:
            return REST_CAP_DAYS, 0
        rest_days = min((before - history[-1]).total_seconds() / 86400.0, REST_CAP_DAYS)
        cutoff = before - timedelta(days=CONGESTION_WINDOW_DAYS)
        congestion = sum(1 for d in history if d >= cutoff)
        return rest_days, congestion

    def load(self, matches: list) -> None:
        for match in matches:
            home_id, away_id = match["home_team_id"], match["away_team_id"]
            hg, ag = match["home_goals"], match["away_goals"]
            date = match["kickoff_utc"]

            self._team_matches[home_id].append(
                {"date": date, "goals_for": hg, "goals_against": ag, "at_home": True, "opponent_id": away_id}
            )
            self._team_matches[away_id].append(
                {"date": date, "goals_for": ag, "goals_against": hg, "at_home": False, "opponent_id": home_id}
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

    def venue_form(self, team_id: int, before, at_home: bool, window: int = VENUE_FORM_WINDOW) -> float:
        """Points per game over the team's last `window` matches AT THIS VENUE
        (home matches for the home side, away matches for the away side).
        Cold start returns the neutral overall-form constant."""
        history = [
            m for m in self._team_matches.get(team_id, []) if m["date"] < before and m["at_home"] == at_home
        ]
        recent = history[-window:]
        if not recent:
            return _COLD_FORM.points_per_game
        return sum(_result_points(m["goals_for"], m["goals_against"]) for m in recent) / len(recent)

    def schedule_strength(self, team_id: int, before, elo: "elo_module.EloRatings", window: int = SCHED_STRENGTH_WINDOW) -> float:
        """Mean CURRENT Elo of the opponents faced in the last `window`
        matches -- distinguishes a good run against weak sides from one
        against strong sides. Uses opponents' present ratings (still
        point-in-time safe: at feature time the Elo store contains only past
        matches). Cold start is league-neutral INITIAL_ELO."""
        history = [m for m in self._team_matches.get(team_id, []) if m["date"] < before]
        recent = history[-window:]
        if not recent:
            return elo_module.INITIAL_ELO
        return sum(elo.get(m["opponent_id"]) for m in recent) / len(recent)

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
        h_rest_all, h_cong_all = self.schedule_all(home_id, before)
        a_rest_all, a_cong_all = self.schedule_all(away_id, before)

        home_adv = 0 if neutral else elo_module.HOME_ADVANTAGE
        elo_diff = elo.get(home_id) + home_adv - elo.get(away_id)
        before_str = before.isoformat() if hasattr(before, "isoformat") else str(before)
        ghost = 1.0 if GHOST_START <= before_str[:10] <= GHOST_END else 0.0
        h10 = self.ew_form(home_id, before, half_life=10)
        a10 = self.ew_form(away_id, before, half_life=10)
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
            # Same two, counting every competition (ingest_team_fixtures.py).
            "rest_all_diff": h_rest_all - a_rest_all,
            "congestion_all_diff": float(h_cong_all - a_cong_all),
            "short_rest_all_diff": float(h_rest_all <= 2.0) - float(a_rest_all <= 2.0),
            "long_rest_all_diff": float(h_rest_all >= 4.0) - float(a_rest_all >= 4.0),
            # Draw-aware features. The draw logit of a linear model in SIGNED
            # elo_diff cannot represent "draws peak when teams are evenly
            # matched" -- -abs() fixes exactly that representational gap.
            "elo_closeness": -abs(elo_diff),
            # Sum, not diff: a draw is a joint outcome -- either side's draw
            # propensity raises match draw probability; differencing would
            # cancel the signal.
            "draw_rate_sum": self.draw_rate(home_id, before) + self.draw_rate(away_id, before),
            "low_scoring_sum": self.low_scoring_rate(home_id, before) + self.low_scoring_rate(away_id, before),
            # Venue-split form (PRD 10.2): the home side's home record vs the
            # away side's away record -- overall form hides strong-at-home /
            # weak-on-the-road asymmetries.
            "venue_form_diff": self.venue_form(home_id, before, True) - self.venue_form(away_id, before, False),
            # Elo momentum (PRD 10.1 "Elo change"): improving vs declining,
            # which the rating LEVEL already in elo_diff cannot express.
            "elo_trend_diff": elo.trend(home_id) - elo.trend(away_id),
            # Strength of recent schedule: same form against tougher opponents
            # should count for more.
            "sched_strength_diff": self.schedule_strength(home_id, before, elo)
            - self.schedule_strength(away_id, before, elo),
            # Batch B (literature review): closed-door flag, threshold-coded
            # rest (the effect is a step at <=2 / >=4 days, not a slope), and
            # a longer EW half-life variant (5 matches is the extreme short
            # end of everything published).
            "ghost_game": ghost,
            "short_rest_diff": float(h_rest <= 2.0) - float(a_rest <= 2.0),
            "long_rest_diff": float(h_rest >= 4.0) - float(a_rest >= 4.0),
            "ew10_form_diff": h10[0] - a10[0],
            "ew10_gf_diff": h10[1] - a10[1],
            "ew10_ga_diff": h10[2] - a10[2],
        }
