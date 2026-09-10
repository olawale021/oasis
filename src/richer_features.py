import math
from collections import Counter, defaultdict
from datetime import datetime

import db
from features import FORM_WINDOW

PL_ID = 39


def _parse_kickoff(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


# --- 1. Shot/possession rolling form -------------------------------------

class ShotStatsStore:
    """Point-in-time PL-only shot/possession/corner rolling-form store,
    mirroring FeatureStore.form()'s strict `date < before` discipline and
    partial-window handling, but sourced from fixture_statistics (PL-only
    ingestion). A promoted team's Championship matches never contribute rows
    here -- the window just naturally shrinks to whatever real PL rows exist
    so far, same as TeamForm's partial-window handling.

    Neutrality rule: if EITHER side has zero real rows in its window, all
    three diffs fall back to 0.0 rather than diffing a real average against
    nothing -- these are pure diff features into a standardized logistic
    regression, so "no evidence of an edge" should mean 0.0, not a fabricated
    skew.
    """

    def __init__(self):
        self._team_stats = defaultdict(list)

    def load(self, stat_rows: list) -> None:
        # Pair each team-row with its opponent's row so a team's xGA for a
        # fixture is the opponent's expected_goals. Pre-2022 rows carry
        # xg/xga = None (the API omits the field entirely for that era),
        # which the per-key None-filtering in _avg handles: a window with no
        # real xG rows averages to None -> the diff falls back to 0.0.
        by_fixture = defaultdict(list)
        for row in stat_rows:
            by_fixture[row["fixture_id"]].append(row)

        for row in stat_rows:
            sot, poss, corners = row["shots_on_goal"], row["ball_possession_pct"], row["corner_kicks"]
            if sot is None and poss is None and corners is None and row["expected_goals"] is None:
                continue  # xG-only rows (FBref backfill, ingest_xg.py) are kept
            opponent_xg = None
            for other in by_fixture[row["fixture_id"]]:
                if other["team_id"] != row["team_id"]:
                    opponent_xg = other["expected_goals"]
                    break
            self._team_stats[row["team_id"]].append(
                {
                    "date": _parse_kickoff(row["kickoff_utc"]),
                    "sot": sot,
                    "poss": poss,
                    "corners": corners,
                    "xg": row["expected_goals"],
                    "xga": opponent_xg,
                }
            )
        for team_id in self._team_stats:
            self._team_stats[team_id].sort(key=lambda r: r["date"])

    def _window(self, team_id: int, before, window: int = FORM_WINDOW) -> list:
        history = [r for r in self._team_stats.get(team_id, []) if r["date"] < before]
        return history[-window:]

    @staticmethod
    def _avg(recent: list, key: str):
        values = [r[key] for r in recent if r[key] is not None]
        return sum(values) / len(values) if values else None

    def diffs(self, home_id: int, away_id: int, before, window: int = FORM_WINDOW) -> dict:
        home_recent = self._window(home_id, before, window)
        away_recent = self._window(away_id, before, window)
        if not home_recent or not away_recent:
            return {"sot_diff": 0.0, "possession_diff": 0.0, "corner_diff": 0.0, "xg_diff": 0.0, "xga_diff": 0.0}

        out = {}
        for key, out_name in (
            ("sot", "sot_diff"),
            ("poss", "possession_diff"),
            ("corners", "corner_diff"),
            ("xg", "xg_diff"),
            ("xga", "xga_diff"),
        ):
            h, a = self._avg(home_recent, key), self._avg(away_recent, key)
            out[out_name] = (h - a) if (h is not None and a is not None) else 0.0
        return out


# --- 2. Missing players (injuries) ---------------------------------------

class MissingPlayersIndex:
    """Fixture-scoped lookup, not a rolling window: each injuries row already
    IS the pre-match state for that exact fixture (injury news arrives before
    kickoff -- the premise of the PRD's 'injury update' prediction stage), so
    this is a direct (fixture_id, team_id) -> count lookup. Only counts
    status_type == 'Missing Fixture' (confirmed absences); 'Questionable' is
    deliberately excluded rather than blended in, since mixing two confidence
    levels into one number would add noise, not signal."""

    def __init__(self):
        self._counts = {}

    def load(self, missing_count_rows: list) -> None:
        for row in missing_count_rows:
            self._counts[(row["fixture_id"], row["team_id"])] = row["missing_count"]

    def missing_count(self, fixture_id: int, team_id: int) -> int:
        return self._counts.get((fixture_id, team_id), 0)

    def diff(self, fixture_id: int, home_id: int, away_id: int) -> dict:
        return {
            "missing_players_diff": float(
                self.missing_count(fixture_id, home_id) - self.missing_count(fixture_id, away_id)
            )
        }


# --- 3. Squad disruption (lineups) ---------------------------------------
#
# PHASE-1.5 SIMPLIFICATION (documented, not a bug): this feature uses the
# CURRENT fixture's ACTUAL confirmed startXI -- known only ~1 hour pre-kickoff
# (PRD SS13.3 "final prediction"), not a *predicted* XI 12-24h out (PRD SS13.1
# "initial prediction"). A true two-stage initial-vs-final model is a
# live-serving-architecture concern, explicitly out of scope for this pass --
# this pass is purely about proving whether squad-disruption signal has any
# predictive value at all, via one enriched backtest.

class SquadDisruptionStore:
    """Point-in-time store for lineup-composition history. 'Regular XI' = the
    11 player_ids with the highest start-count across the last `window` PL
    matches (with lineup data) before `before`. Ties broken by player_id
    ascending -- deterministic."""

    def __init__(self):
        self._team_lineups = defaultdict(list)
        self._fixture_starters = {}

    def load(self, lineup_player_rows: list) -> None:
        grouped = defaultdict(lambda: {"starters": set(), "date": None})
        for row in lineup_player_rows:
            if not row["is_starter"]:
                continue
            key = (row["team_id"], row["fixture_id"])
            grouped[key]["starters"].add(row["player_id"])
            grouped[key]["date"] = _parse_kickoff(row["kickoff_utc"])

        for (team_id, fixture_id), entry in grouped.items():
            starters = frozenset(entry["starters"])
            self._team_lineups[team_id].append({"date": entry["date"], "fixture_id": fixture_id, "starters": starters})
            self._fixture_starters[(fixture_id, team_id)] = starters

        for team_id in self._team_lineups:
            self._team_lineups[team_id].sort(key=lambda e: e["date"])

    def fixture_starters(self, fixture_id: int, team_id: int):
        return self._fixture_starters.get((fixture_id, team_id))

    def _regular_xi(self, team_id: int, before, window: int = FORM_WINDOW) -> frozenset:
        history = [e for e in self._team_lineups.get(team_id, []) if e["date"] < before]
        recent = history[-window:]
        if not recent:
            return frozenset()
        counts = Counter()
        for e in recent:
            counts.update(e["starters"])
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return frozenset(pid for pid, _ in ranked[:11])

    def disruption(self, team_id: int, before, actual_starters, window: int = FORM_WINDOW) -> float:
        if actual_starters is None:
            return 0.0
        regulars = self._regular_xi(team_id, before, window)
        if not regulars:
            return 0.0
        absent = regulars - actual_starters
        return len(absent) / len(regulars)

    def match_disruption_diff(self, fixture_id: int, home_id: int, away_id: int, before) -> dict:
        home_actual = self.fixture_starters(fixture_id, home_id)
        away_actual = self.fixture_starters(fixture_id, away_id)
        home_disruption = self.disruption(home_id, before, home_actual)
        away_disruption = self.disruption(away_id, before, away_actual)
        return {"squad_disruption_diff": home_disruption - away_disruption}


# --- MIN_GAMES=6 interaction (documented, not a bug) ----------------------
#
# backtest_common.MIN_GAMES=6 gates sample eligibility via elo.matches_played,
# which increments on every match (PL and Championship) in the single
# chronological pass. A team that spent time in the Championship within the
# ingested window can reach matches_played>=6 purely from Championship
# matches, before playing a single PL match -- so their first-ever scored PL
# sample can have zero PL lineup history. This hits _regular_xi's cold-start
# path (empty history -> disruption=0.0), which is the correct, intentional
# fallback, not a leak. Established PL teams reach matches_played=6 via their
# own first ~6 PL matches, by which point real PL lineup rows already exist
# too, so this cold path is rare beyond each team's first few PL matches.


# --- 4. Single entrypoint --------------------------------------------------

# --- 4. Squad market value (Transfermarkt, point-in-time) ------------------


class SquadValueStore:
    """Squad value as of kickoff, keyed by (fixture_id, team_id), from the
    squad_values table (ingest_squad_values.py). The feature is the log
    ratio of the two squads' values -- a strong prior on strength that is
    sharpest exactly where Elo and form are weakest (season start,
    promoted clubs). 0.0 when either side is missing, per the neutrality
    rule for diff features."""

    def __init__(self):
        self._value = {}

    def load(self, rows: list) -> None:
        for r in rows:
            if r["value_eur"] and r["value_eur"] > 0:
                self._value[(r["fixture_id"], r["team_id"])] = float(r["value_eur"])

    def diff(self, fixture_id: int, home_id: int, away_id: int) -> dict:
        h = self._value.get((fixture_id, home_id))
        a = self._value.get((fixture_id, away_id))
        if not h or not a:
            return {"value_diff": 0.0}
        return {"value_diff": math.log(h) - math.log(a)}


def richer_match_features(
    fixture_id: int,
    home_id: int,
    away_id: int,
    before,
    shot_store: ShotStatsStore,
    missing_index: MissingPlayersIndex,
    squad_store: SquadDisruptionStore,
    value_store: "SquadValueStore" = None,
) -> dict:
    feats = {}
    feats.update(shot_store.diffs(home_id, away_id, before))
    feats.update(missing_index.diff(fixture_id, home_id, away_id))
    feats.update(squad_store.match_disruption_diff(fixture_id, home_id, away_id, before))
    feats.update((value_store or SquadValueStore()).diff(fixture_id, home_id, away_id))
    return feats


def enrich_samples(samples: list, conn, league_id: int = PL_ID, seasons: list = None) -> list:
    """Post-processing enrichment pass over backtest_common.collect_samples()'s
    output, joined purely by keys already present on each sample dict. Does
    NOT touch collect_samples()'s signature or behavior -- goals_train.py,
    which also calls collect_samples() but never calls this function, is
    unaffected."""
    stat_rows = db.get_fixture_statistics_by_league(conn, [league_id], seasons)
    shot_store = ShotStatsStore()
    shot_store.load(stat_rows)

    missing_rows = db.get_missing_player_counts(conn, [league_id], seasons)
    missing_index = MissingPlayersIndex()
    missing_index.load(missing_rows)

    lineup_rows = db.get_lineup_players_by_league(conn, [league_id], seasons)
    squad_store = SquadDisruptionStore()
    squad_store.load(lineup_rows)
    value_store = SquadValueStore()
    value_store.load(db.get_squad_values_by_league(conn, [league_id], seasons))

    enriched = []
    for s in samples:
        feats = richer_match_features(
            s["fixture_id"], s["home_team_id"], s["away_team_id"], s["kickoff_utc"],
            shot_store, missing_index, squad_store, value_store,
        )
        enriched.append({**s, **feats})
    return enriched
