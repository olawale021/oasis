from dataclasses import dataclass, field

# Club-football constants. Calibratable starting points, not claimed-precise --
# ported structurally from the World Cup pipeline's Elo engine, but club teams
# play far more matches/season than international sides, so a lower K keeps
# any single result from moving the rating too much.
DEFAULT_K = 20
HOME_ADVANTAGE = 60.0
INITIAL_ELO = 1500.0


@dataclass
class EloRatings:
    ratings: dict = field(default_factory=dict)
    matches_played: dict = field(default_factory=dict)
    use_mov: bool = True

    def get(self, team_id: int) -> float:
        return self.ratings.get(team_id, INITIAL_ELO)

    @staticmethod
    def mov_multiplier(home_goals: int, away_goals: int) -> float:
        diff = abs(home_goals - away_goals)
        if diff <= 1:
            return 1.0
        if diff == 2:
            return 1.5
        return (11 + diff) / 8.0

    def expected(self, home_id: int, away_id: int, neutral: bool) -> float:
        home_elo = self.get(home_id)
        away_elo = self.get(away_id)
        if not neutral:
            home_elo += HOME_ADVANTAGE
        return 1.0 / (1.0 + 10 ** ((away_elo - home_elo) / 400.0))

    def k_factor(self, played: int) -> float:
        if played < 30:
            return DEFAULT_K * 1.25
        if played < 60:
            return DEFAULT_K * 1.1
        return DEFAULT_K

    def update(self, home_id: int, away_id: int, home_goals: int, away_goals: int, neutral: bool) -> None:
        if home_goals > away_goals:
            home_result, away_result = 1.0, 0.0
        elif home_goals < away_goals:
            home_result, away_result = 0.0, 1.0
        else:
            home_result, away_result = 0.5, 0.5

        expected_home = self.expected(home_id, away_id, neutral)
        expected_away = 1.0 - expected_home

        mov = self.mov_multiplier(home_goals, away_goals) if self.use_mov else 1.0
        home_k = self.k_factor(self.matches_played.get(home_id, 0)) * mov
        away_k = self.k_factor(self.matches_played.get(away_id, 0)) * mov

        self.ratings[home_id] = self.get(home_id) + home_k * (home_result - expected_home)
        self.ratings[away_id] = self.get(away_id) + away_k * (away_result - expected_away)
        self.matches_played[home_id] = self.matches_played.get(home_id, 0) + 1
        self.matches_played[away_id] = self.matches_played.get(away_id, 0) + 1

    def fit(self, matches: list) -> None:
        for match in sorted(matches, key=lambda m: m["kickoff_utc"]):
            self.update(
                home_id=match["home_team_id"],
                away_id=match["away_team_id"],
                home_goals=match["home_goals"],
                away_goals=match["away_goals"],
                neutral=match["neutral"],
            )
