"""Betting ledger: consensus, point-in-time grading, settlement.

    .venv/bin/python -m unittest tests.test_betting -v

Stdlib only, in-memory SQLite built from src/schema.sql."""

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
from betting import edge as edge_math  # noqa: E402
from betting.advisor import grade_locked, settle  # noqa: E402
from betting.consensus import build_consensus, consensus_as_of  # noqa: E402
from betting.markets import selection_won  # noqa: E402
from betting.thresholds import EDGE_FLOOR, MIN_BOOKMAKERS, grade  # noqa: E402

FIX = 9001
T_24H = "2026-09-13T15:00:00+00:00"   # 24h window fetched
T_LOCK = "2026-09-14T14:00:00+00:00"  # prediction locked (only 24h window knowable)
T_CLOSE = "2026-09-14T14:40:00+00:00" # closing window fetched, after the lock
NOW = "2026-09-14T16:30:00+00:00"


def fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(config.SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO fixtures (fixture_id, league_id, season, kickoff_utc, status_short, home_team_id, away_team_id, updated_at, raw_json)"
        " VALUES (?, 39, 2026, '2026-09-14T15:00:00+00:00', 'NS', 1, 2, ?, '{}')",
        (FIX, NOW),
    )
    return conn


def add_odds(conn, snapshot, fetched_at, books):
    """books: {name: {(market_id, outcome): odds}}; normalized per group like ingest_odds."""
    for i, (name, quotes) in enumerate(books.items(), start=1):
        groups = {}
        for (mid, outcome), odd in quotes.items():
            key = (mid, outcome.rsplit(" ", 1)[1] if mid == 5 else "")
            groups[key] = groups.get(key, 0.0) + 1.0 / odd
        for (mid, outcome), odd in quotes.items():
            key = (mid, outcome.rsplit(" ", 1)[1] if mid == 5 else "")
            conn.execute(
                "INSERT INTO odds_snapshots (fixture_id, snapshot, bookmaker_id, bookmaker, market_id, market, outcome,"
                " odds_decimal, implied_prob, normalized_prob, hours_to_kickoff, fetched_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?)",
                (FIX, snapshot, i, name, mid, str(mid), outcome, odd, 1 / odd, (1 / odd) / groups[key], fetched_at),
            )
    conn.commit()


def book(h, d, a, over, under, yes, no):
    return {(1, "Home"): h, (1, "Draw"): d, (1, "Away"): a,
            (5, "Over 2.5"): over, (5, "Under 2.5"): under, (5, "Over 1.5"): 1.2, (5, "Under 1.5"): 4.0,
            (8, "Yes"): yes, (8, "No"): no}


def add_lock(conn, p_home=60.0, p_draw=22.0, p_away=18.0, over=64.0, btts=55.0, stage="initial"):
    conn.execute(
        "INSERT INTO locked_predictions (fixture_id, league_code, season, kickoff_utc, locked_at, stage, home, away,"
        " p_home, p_draw, p_away, over_2_5, btts, confidence, model_version, model_checksum, features_json)"
        " VALUES (?, 'EPL', 2026, '2026-09-14T15:00:00+00:00', ?, ?, 'H', 'A', ?, ?, ?, ?, ?, 'HIGH', 'm1', 'c', '{}')",
        (FIX, T_LOCK, stage, p_home, p_draw, p_away, over, btts),
    )
    conn.commit()


class EdgeMath(unittest.TestCase):
    def test_ev_and_clv(self):
        self.assertAlmostEqual(edge_math.expected_value(0.58, 2.0), 0.16)
        self.assertAlmostEqual(edge_math.clv(2.10, 1.82), 2.10 / 1.82 - 1)
        self.assertEqual(edge_math.profit_1u(True, 2.5), 1.5)
        self.assertEqual(edge_math.profit_1u(False, 2.5), -1.0)


class Grading(unittest.TestCase):
    def test_market_agreement_is_pass(self):
        level, reasons = grade(0.90, 0.88, 0.026, 9, "1h")
        self.assertEqual(level, "PASS")
        self.assertEqual(reasons[0]["code"], "edge_below_floor")

    def test_real_edge_is_watch_not_value_in_v0(self):
        level, reasons = grade(0.48, 0.39, 0.20, 9, "1h")
        self.assertEqual(level, "WATCH")
        self.assertEqual(reasons[0]["code"], "unvalidated_edge")

    def test_data_quality_gates(self):
        self.assertEqual(grade(0.6, None, None, None, None)[0], "WATCH")
        self.assertEqual(grade(0.6, 0.5, 0.2, MIN_BOOKMAKERS - 1, "1h")[1][0]["code"], "few_bookmakers")
        self.assertEqual(grade(0.6, 0.5, 0.2, 9, "7d")[1][0]["code"], "stale_odds")

    def test_floor_is_exclusive(self):
        self.assertEqual(grade(0.5 + EDGE_FLOOR, 0.5, 0.1, 9, "1h")[0], "WATCH")


class Settlement(unittest.TestCase):
    def test_selection_won(self):
        self.assertTrue(selection_won("1X2", "home", 2, 1))
        self.assertTrue(selection_won("1X2", "draw", 1, 1))
        self.assertTrue(selection_won("OU25", "over", 2, 1))
        self.assertTrue(selection_won("OU25", "under", 1, 1))
        self.assertTrue(selection_won("BTTS", "yes", 1, 1))
        self.assertTrue(selection_won("BTTS", "no", 3, 0))


class Ledger(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db()
        add_odds(self.conn, "24h", T_24H, {
            "A": book(1.80, 3.60, 4.50, 1.70, 2.10, 1.75, 2.00),
            "B": book(1.85, 3.50, 4.40, 1.72, 2.05, 1.72, 2.05),
            "C": book(1.83, 3.55, 4.60, 1.68, 2.15, 1.78, 1.98),
        })
        add_odds(self.conn, "closing", T_CLOSE, {
            "A": book(1.60, 3.90, 5.50, 1.55, 2.40, 1.75, 2.00),
            "B": book(1.62, 3.80, 5.40, 1.57, 2.35, 1.72, 2.05),
            "C": book(1.61, 3.85, 5.60, 1.56, 2.38, 1.78, 1.98),
        })
        self.assertEqual(build_consensus(self.conn, NOW), 2 * 7)  # 2 windows x (3+2+2), 1.5 line ignored
        self.assertEqual(build_consensus(self.conn, NOW), 0)     # idempotent

    def test_consensus_ignores_other_lines_and_takes_best_price(self):
        mkt = consensus_as_of(self.conn, FIX, "OU25", NOW)
        self.assertEqual(set(mkt), {"over", "under"})
        self.assertEqual(mkt["over"]["snapshot"], "closing")
        self.assertEqual(mkt["over"]["best_odds"], 1.57)
        self.assertEqual(mkt["over"]["best_bookmaker"], "B")
        self.assertEqual(mkt["over"]["bookmaker_count"], 3)

    def test_grade_uses_only_prices_knowable_at_lock(self):
        add_lock(self.conn)
        counts = grade_locked(self.conn, NOW)
        self.assertEqual(counts["recommendations"], 7)
        self.assertEqual(grade_locked(self.conn, NOW)["recommendations"], 0)  # idempotent
        rows = {(r["market"], r["selection"]): r for r in
                self.conn.execute("SELECT * FROM betting_recommendations").fetchall()}
        home = rows[("1X2", "home")]
        self.assertEqual(home["market_snapshot"], "24h")   # closing came after locked_at
        self.assertEqual(home["best_odds"], 1.85)
        self.assertAlmostEqual(home["edge"], 0.60 - home["market_prob"], places=6)
        self.assertEqual(home["thresholds_version"], "v0-provisional")
        self.assertIn(home["level"], ("PASS", "WATCH"))
        for r in rows.values():
            self.assertNotIn(r["level"], ("VALUE", "STRONG_VALUE"))
            self.assertTrue(json.loads(r["reasons_json"])[0]["code"])

    def test_settle_scores_pass_rows_too_and_computes_clv(self):
        add_lock(self.conn)
        grade_locked(self.conn, NOW)
        self.assertEqual(settle(self.conn, NOW)["settled"], 0)  # not played yet
        self.conn.execute("UPDATE fixtures SET status_short='FT', home_goals=2, away_goals=1 WHERE fixture_id=?", (FIX,))
        counts = settle(self.conn, NOW)
        self.assertEqual(counts, {"settled": 7, "with_clv": 7})
        self.assertEqual(settle(self.conn, NOW)["settled"], 0)  # idempotent
        res = {(r["market"], r["selection"]): r for r in self.conn.execute(
            "SELECT br.market, br.selection, br.best_odds, r.* FROM betting_results r"
            " JOIN betting_recommendations br USING (recommendation_id)").fetchall()}
        self.assertEqual(res[("1X2", "home")]["won"], 1)
        self.assertAlmostEqual(res[("1X2", "home")]["profit_1u"], 0.85)
        self.assertEqual(res[("1X2", "away")]["won"], 0)
        self.assertEqual(res[("1X2", "away")]["profit_1u"], -1.0)
        self.assertEqual(res[("OU25", "over")]["won"], 1)
        self.assertEqual(res[("BTTS", "yes")]["won"], 1)
        # Home shortened from a 1.83 median to a 1.61 median at the close: we
        # beat the line. Median vs median -- the best price (1.85) must not
        # enter, or every row would look like value.
        self.assertEqual(res[("1X2", "home")]["closing_odds"], 1.61)
        self.assertAlmostEqual(res[("1X2", "home")]["clv"], 1.83 / 1.61 - 1, places=5)
        # Away drifted from 4.50 to 5.50: the market moved against us.
        self.assertLess(res[("1X2", "away")]["clv"], 0)
        # BTTS did not move: flat line, zero CLV, not a flattering positive.
        self.assertAlmostEqual(res[("BTTS", "yes")]["clv"], 0.0, places=5)


if __name__ == "__main__":
    unittest.main()


class ClvRecompute(unittest.TestCase):
    def test_recompute_replaces_old_definition(self):
        from betting.advisor import recompute_clv
        conn = fresh_db()
        add_odds(conn, "24h", T_24H, {"A": book(1.80, 3.60, 4.50, 1.70, 2.10, 1.75, 2.00),
                                      "B": book(1.85, 3.50, 4.40, 1.72, 2.05, 1.72, 2.05),
                                      "C": book(1.83, 3.55, 4.60, 1.68, 2.15, 1.78, 1.98)})
        add_odds(conn, "closing", T_CLOSE, {"A": book(1.60, 3.90, 5.50, 1.55, 2.40, 1.75, 2.00),
                                            "B": book(1.62, 3.80, 5.40, 1.57, 2.35, 1.72, 2.05),
                                            "C": book(1.61, 3.85, 5.60, 1.56, 2.38, 1.78, 1.98)})
        build_consensus(conn, NOW); add_lock(conn); grade_locked(conn, NOW)
        conn.execute("UPDATE fixtures SET status_short='FT', home_goals=2, away_goals=1 WHERE fixture_id=?", (FIX,))
        settle(conn, NOW)
        # Simulate rows settled under the old best-vs-median definition.
        conn.execute("UPDATE betting_results SET clv = 0.5"); conn.commit()
        out = recompute_clv(conn, NOW)
        self.assertEqual(out["changed"], 7)
        home = conn.execute("SELECT r.clv FROM betting_results r JOIN betting_recommendations br USING(recommendation_id)"
                            " WHERE br.market='1X2' AND br.selection='home'").fetchone()["clv"]
        self.assertAlmostEqual(home, 1.83 / 1.61 - 1, places=5)
        self.assertEqual(recompute_clv(conn, NOW)["changed"], 0)  # idempotent


class Context(unittest.TestCase):
    """H2H / trends are as-of kickoff: later meetings and undecided matches
    must not count, and wins are from the target fixture's home side."""

    def setUp(self):
        from betting.context import build_context
        self.build = build_context
        self.conn = fresh_db()
        # Target: team 1 (home) v team 2 (away), kickoff 2026-09-14T15:00.
        rows = [
            # meetings before kickoff (any venue)
            (101, 1, 2, "2026-01-10T15:00:00+00:00", "FT", 2, 0),   # team1 win, no btts, under
            (102, 2, 1, "2026-03-10T15:00:00+00:00", "FT", 1, 1),   # draw, btts, under
            (103, 2, 1, "2026-05-10T15:00:00+00:00", "AET", 3, 1),  # team2 win, btts, over
            (104, 1, 2, "2026-09-13T20:00:00+00:00", "NS", None, None),  # undecided: ignored
            (105, 1, 2, "2026-10-01T15:00:00+00:00", "FT", 5, 0),   # AFTER kickoff: must not count
            # team 1 form filler (cup, different league_id)
            (201, 1, 9, "2026-09-01T15:00:00+00:00", "FT", 4, 2),
            (202, 9, 1, "2026-09-05T15:00:00+00:00", "FT", 0, 0),
        ]
        for fid, h, a, ko, st, hg, ag in rows:
            self.conn.execute(
                "INSERT INTO fixtures (fixture_id, league_id, season, kickoff_utc, status_short, home_team_id, away_team_id,"
                " home_goals, away_goals, updated_at, raw_json) VALUES (?, 99, 2026, ?, ?, ?, ?, ?, ?, ?, '{}')",
                (fid, ko, st, h, a, hg, ag, NOW))
        add_lock(self.conn)  # makes FIX a target regardless of the horizon
        self.conn.commit()
        self.build(self.conn, NOW)

    def test_h2h_is_point_in_time_and_home_perspective(self):
        h = self.conn.execute("SELECT * FROM h2h_summary WHERE fixture_id = ?", (FIX,)).fetchone()
        self.assertEqual(h["matches_considered"], 3)
        self.assertEqual((h["home_wins"], h["draws"], h["away_wins"]), (1, 1, 1))
        self.assertEqual((h["home_goals"], h["away_goals"]), (2 + 1 + 1, 0 + 1 + 3))
        self.assertEqual(h["btts_count"], 2)
        self.assertAlmostEqual(h["btts_rate"], 2 / 3, places=3)
        self.assertEqual(h["over_2_5_count"], 1)
        self.assertEqual(h["average_goals"], 2.67)  # (2+0 + 1+1 + 3+1) / 3
        self.assertEqual(h["last_meeting_utc"], "2026-05-10T15:00:00+00:00")

    def test_trends_span_competitions_and_exclude_future(self):
        t = {r["team_id"]: r for r in self.conn.execute(
            "SELECT * FROM team_market_trends WHERE fixture_id = ?", (FIX,)).fetchall()}
        self.assertEqual(t[1]["matches_considered"], 5)     # 3 meetings + 2 cup ties
        self.assertEqual(t[1]["goals_for"], 2 + 1 + 1 + 4 + 0)
        self.assertEqual(t[1]["goals_against"], 0 + 1 + 3 + 2 + 0)
        self.assertEqual(t[1]["over_2_5_count"], 2)         # 3-1 and 4-2
        self.assertEqual(t[2]["matches_considered"], 3)
        self.assertEqual(t[2]["btts_count"], 2)

    def test_empty_history_gives_null_rates_not_zero(self):
        self.conn.execute("DELETE FROM fixtures WHERE fixture_id BETWEEN 101 AND 202")
        self.build(self.conn, NOW)
        h = self.conn.execute("SELECT * FROM h2h_summary WHERE fixture_id = ?", (FIX,)).fetchone()
        self.assertEqual(h["matches_considered"], 0)
        self.assertIsNone(h["btts_rate"])
        self.assertIsNone(h["average_goals"])


class Export(unittest.TestCase):
    """live.json betting block: ledger rows win over previews, previews use
    the newest consensus, context rides along per fixture."""

    def setUp(self):
        from betting.export import build_betting
        self.build = build_betting
        self.conn = fresh_db()
        add_odds(self.conn, "24h", T_24H, {
            "A": book(1.80, 3.60, 4.50, 1.70, 2.10, 1.75, 2.00),
            "B": book(1.85, 3.50, 4.40, 1.72, 2.05, 1.72, 2.05),
            "C": book(1.83, 3.55, 4.60, 1.68, 2.15, 1.78, 1.98),
        })
        build_consensus(self.conn, NOW)
        self.pred = {"predictions": [{
            "fixture_id": FIX, "home_team_id": 1, "away_team_id": 2,
            "p_home": 60.0, "p_draw": 22.0, "p_away": 18.0, "over_2_5": 64.0, "btts": 55.0,
        }]}

    def test_preview_rows_graded_from_current_consensus(self):
        b = self.build(self.conn, self.pred, NOW)
        self.assertEqual(b["thresholds_version"], "v0-provisional")
        rows = {(r["market"], r["sel"]): r for r in b["rows"]}
        self.assertEqual(len(rows), 7)
        home = rows[("1X2", "home")]
        self.assertFalse(home["locked"])
        self.assertEqual(home["p"], 60.0)
        self.assertEqual(home["odds"], 1.85)
        self.assertEqual(home["book"], "B")
        self.assertEqual(home["snap"], "24h")
        self.assertAlmostEqual(home["edge"], round(60.0 - home["mp"], 1), places=1)
        self.assertIn(home["level"], ("PASS", "WATCH"))
        self.assertEqual(b["context"][str(FIX)]["h2h"], None)  # no context rows built

    def test_ledger_rows_replace_previews_once_locked(self):
        add_lock(self.conn, p_home=70.0)           # ledger will say 70, prediction says 60
        grade_locked(self.conn, NOW)
        b = self.build(self.conn, self.pred, NOW)
        home = next(r for r in b["rows"] if r["market"] == "1X2" and r["sel"] == "home")
        self.assertTrue(home["locked"])
        self.assertEqual(home["p"], 70.0)
        self.assertTrue(home["reasons"][0]["code"])

    def test_no_odds_gives_null_market_and_watch(self):
        self.conn.execute("DELETE FROM market_consensus")
        b = self.build(self.conn, self.pred, NOW)
        home = next(r for r in b["rows"] if r["market"] == "1X2" and r["sel"] == "home")
        self.assertIsNone(home["mp"]); self.assertIsNone(home["edge"]); self.assertIsNone(home["odds"])
        self.assertEqual(home["level"], "WATCH")
        self.assertEqual(home["reasons"][0]["code"], "no_odds")
