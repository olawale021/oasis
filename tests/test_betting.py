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
        # Home shortened from ~1.83 to ~1.61 at the close: we beat the line.
        self.assertGreater(res[("1X2", "home")]["clv"], 0)
        self.assertEqual(res[("1X2", "home")]["closing_odds"], 1.61)


if __name__ == "__main__":
    unittest.main()
