"""Two-legged knockout ties in the European competitions.

A second leg is played with the first leg's score in hand, which changes
both sides' incentives (the side ahead sits, the side behind chases) and
the draw rate. Two features, zero outside the European knockout rounds:

    leg2           1.0 when an earlier match in the same season + round
                   between the same two clubs exists (this is the return leg)
    leg2_agg_diff  the home side's aggregate lead entering the match
                   (its first-leg goals minus the opponent's), signed

Point-in-time by construction: only first legs with kickoff < the match are
visible. The index is built from the completed-match stream that also feeds
the ratings, so training and prediction see the same ties.
"""

import leagues


class TieIndex:
    def __init__(self):
        self._legs = {}

    @staticmethod
    def _key(league_id: int, season: int, round_text, home_id: int, away_id: int):
        return (league_id, season, (round_text or "").strip().lower(), frozenset((home_id, away_id)))

    def load(self, matches: list) -> None:
        for m in matches:
            if not leagues.is_knockout_round(m["league_id"], m.get("round")):
                continue
            if (m.get("round") or "").strip().lower() == "final":
                continue  # single match at a neutral venue
            key = self._key(m["league_id"], m["season"], m.get("round"), m["home_team_id"], m["away_team_id"])
            self._legs.setdefault(key, []).append(
                (m["kickoff_utc"], m["home_team_id"], m["home_goals"], m["away_goals"])
            )
        for legs in self._legs.values():
            legs.sort(key=lambda l: l[0])

    def features(self, league_id: int, season: int, round_text, home_id: int, away_id: int, before) -> dict:
        legs = self._legs.get(self._key(league_id, season, round_text, home_id, away_id))
        if not legs:
            return {"leg2": 0.0, "leg2_agg_diff": 0.0}
        prior = [l for l in legs if l[0] < before]
        if not prior:
            return {"leg2": 0.0, "leg2_agg_diff": 0.0}
        _, first_home, hg, ag = prior[0]
        # First leg was hosted by tonight's away side in the normal case; the
        # home side's aggregate lead is what it scored away minus what it conceded.
        agg = (ag - hg) if first_home == away_id else (hg - ag)
        return {"leg2": 1.0, "leg2_agg_diff": float(agg)}
