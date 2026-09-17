"""Betting ledger step of the matchday chain (Betting PRD 14, 15, 18).

    python3 src/betting/advisor.py            # after lifecycle settle, before export_web

Three idempotent passes:

  consensus  market_consensus rows for every odds window not yet summarised.
  context    h2h_summary and team_market_trends for upcoming and locked
             fixtures, as of each fixture's kickoff (PRD 7, 8).
  grade      one betting_recommendations row per (locked prediction, market,
             selection) -- PASS rows too. The market is looked up as of the
             prediction's locked_at, never later, so every grade can be
             reproduced from stored data alone.
  horizon    the same seven rows per fixture at stage h24, written on the
             first run that finds the fixture's 24h consensus, from this
             run's prediction (outputs/predictions.json). A lock-time grade
             is made minutes from the close, so its closing-line value is
             ~0 by construction; the h24 row is the recommendation a day
             out, and its CLV is the real question (PRD 18, 20).
  settle     betting_results for graded fixtures that have a final score:
             won, profit at the graded price, and closing-line value where a
             closing window was archived.

Final-stage locks made by final_pass.sh between hourly runs are graded on
the next hourly run; the as-of rule keeps that honest. Writes
data/status/betting_status.json for /admin.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Chain scripts run as `python src/<file>.py` with src/ on sys.path; this
# lives one level down, so put src/ back before the sibling imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import db  # noqa: E402
from betting import edge as edge_math  # noqa: E402
from betting.consensus import build_consensus, closing_consensus, consensus_as_of  # noqa: E402
from betting.context import build_context  # noqa: E402
from betting.markets import model_probs, selection_won  # noqa: E402
from betting.thresholds import THRESHOLDS_VERSION, grade  # noqa: E402

DECIDED_STATUSES = ("FT", "AET", "PEN")
PREDICTIONS_PATH = config.ROOT_DIR / "outputs" / "predictions.json"
# odds window -> ledger stage. Extend with ("6h", "h6"), ("1h", "h1") for
# the full curve; each adds seven rows per fixture.
HORIZONS = (("24h", "h24"),)

REC_COLUMNS = (
    "fixture_id", "stage", "league_code", "kickoff_utc", "locked_at", "hours_to_kickoff", "market", "selection",
    "model_version", "goals_version", "model_prob", "market_prob", "market_snapshot", "bookmaker_count", "edge",
    "best_odds", "expected_value", "confidence", "level", "reasons_json", "thresholds_version", "generated_at",
)


def _insert_rec(conn, row: dict) -> None:
    conn.execute(
        f"INSERT OR IGNORE INTO betting_recommendations ({', '.join(REC_COLUMNS)})"
        f" VALUES ({', '.join(':' + c for c in REC_COLUMNS)})",
        {c: row.get(c) for c in REC_COLUMNS},
    )


def _graded_row(fixture_id, stage, league_code, kickoff_utc, locked_at, hours, market, sel, p, mkt_row,
                model_version, goals_version, confidence, now_iso) -> dict:
    market_prob = mkt_row["consensus_prob"] if mkt_row else None
    best_odds = mkt_row["best_odds"] if mkt_row else None
    e = edge_math.edge(p, market_prob) if mkt_row else None
    ev = edge_math.expected_value(p, best_odds) if mkt_row else None
    level, reasons = grade(p, market_prob, ev, mkt_row["bookmaker_count"] if mkt_row else None,
                           mkt_row["snapshot"] if mkt_row else None)
    return {
        "fixture_id": fixture_id, "stage": stage, "league_code": league_code, "kickoff_utc": kickoff_utc,
        "locked_at": locked_at, "hours_to_kickoff": round(hours, 2) if hours is not None else None,
        "market": market, "selection": sel, "model_version": model_version, "goals_version": goals_version,
        "model_prob": round(p, 6), "market_prob": market_prob,
        "market_snapshot": mkt_row["snapshot"] if mkt_row else None,
        "bookmaker_count": mkt_row["bookmaker_count"] if mkt_row else None,
        "edge": round(e, 6) if e is not None else None, "best_odds": best_odds,
        "expected_value": round(ev, 6) if ev is not None else None, "confidence": confidence,
        "level": level, "reasons_json": json.dumps(reasons), "thresholds_version": THRESHOLDS_VERSION,
        "generated_at": now_iso,
    }


def grade_locked(conn, now_iso: str) -> dict:
    """Grade every locked prediction that has no ledger rows yet."""
    locked = conn.execute(
        """
        SELECT lp.* FROM locked_predictions lp
        WHERE NOT EXISTS (
            SELECT 1 FROM betting_recommendations br
            WHERE br.fixture_id = lp.fixture_id AND br.stage = lp.stage
        )
        """
    ).fetchall()

    counts = {"fixtures_graded": 0, "recommendations": 0, "PASS": 0, "WATCH": 0}
    for lp in locked:
        hours = (datetime.fromisoformat(lp["kickoff_utc"]) - datetime.fromisoformat(lp["locked_at"])).total_seconds() / 3600
        for market, sels in model_probs(lp).items():
            mkt = consensus_as_of(conn, lp["fixture_id"], market, lp["locked_at"])
            for sel, p in sels.items():
                row = _graded_row(lp["fixture_id"], lp["stage"], lp["league_code"], lp["kickoff_utc"], lp["locked_at"],
                                  hours, market, sel, p, mkt.get(sel) if mkt else None, lp["model_version"],
                                  lp["goals_version"], lp["confidence"], now_iso)
                _insert_rec(conn, row)
                counts["recommendations"] += 1
                counts[row["level"]] = counts.get(row["level"], 0) + 1
        counts["fixtures_graded"] += 1
    conn.commit()
    return counts


def grade_horizon(conn, predictions: dict, now_iso: str) -> dict:
    """Write the h24 (etc.) rows for every upcoming prediction whose horizon
    consensus exists and which has no rows at that stage yet. The model
    probability is this run's; the market is that window's, unchanged."""
    now = datetime.fromisoformat(now_iso)
    counts = {"horizon_fixtures": 0, "horizon_rows": 0}
    if not predictions:
        return counts
    registry = predictions.get("model_registry", {})
    for p in predictions.get("predictions", []):
        kickoff = datetime.fromisoformat(p["kickoff_utc"])
        if kickoff <= now:
            continue
        reg = registry.get(p["league"], {})
        model_version = reg.get("outcome", {}).get("version")
        goals_version = reg.get("goals", {}).get("version")
        if not model_version:
            continue  # cannot stamp a release; the row would be unreproducible
        for window, stage in HORIZONS:
            if conn.execute(
                "SELECT 1 FROM betting_recommendations WHERE fixture_id = ? AND stage = ?", (p["fixture_id"], stage)
            ).fetchone():
                continue
            consensus = conn.execute(
                "SELECT * FROM market_consensus WHERE fixture_id = ? AND snapshot = ?", (p["fixture_id"], window)
            ).fetchall()
            if not consensus:
                continue  # not in this window yet (or the window was missed: honest gap)
            by_market = {}
            for r in consensus:
                by_market.setdefault(r["market"], {})[r["selection"]] = r
            hours = (kickoff - now).total_seconds() / 3600
            wrote = 0
            for market, sels in model_probs(p).items():
                mkt = by_market.get(market)
                for sel, prob in sels.items():
                    row = _graded_row(p["fixture_id"], stage, p["league"], p["kickoff_utc"], now_iso, hours, market, sel,
                                      prob, mkt.get(sel) if mkt else None, model_version, goals_version,
                                      p["confidence"], now_iso)
                    _insert_rec(conn, row)
                    wrote += 1
            counts["horizon_rows"] += wrote
            counts["horizon_fixtures"] += 1
    conn.commit()
    return counts


def settle(conn, now_iso: str) -> dict:
    rows = conn.execute(
        f"""
        SELECT br.recommendation_id, br.fixture_id, br.market, br.selection, br.best_odds,
               mc.median_odds AS graded_median_odds, d1.median_odds AS median_24h,
               f.home_goals, f.away_goals
        FROM betting_recommendations br
        JOIN fixtures f ON f.fixture_id = br.fixture_id
        LEFT JOIN market_consensus mc
          ON mc.fixture_id = br.fixture_id AND mc.market = br.market
         AND mc.selection = br.selection AND mc.snapshot = br.market_snapshot
        LEFT JOIN market_consensus d1
          ON d1.fixture_id = br.fixture_id AND d1.market = br.market
         AND d1.selection = br.selection AND d1.snapshot = '24h'
        WHERE f.status_short IN ({", ".join("?" for _ in DECIDED_STATUSES)})
          AND f.home_goals IS NOT NULL AND f.away_goals IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM betting_results r WHERE r.recommendation_id = br.recommendation_id)
        """,
        DECIDED_STATUSES,
    ).fetchall()

    counts = {"settled": 0, "with_clv": 0}
    closing_cache = {}
    for r in rows:
        won = selection_won(r["market"], r["selection"], r["home_goals"], r["away_goals"])
        profit = edge_math.profit_1u(won, r["best_odds"]) if r["best_odds"] else None
        key = (r["fixture_id"], r["market"])
        if key not in closing_cache:
            closing_cache[key] = closing_consensus(conn, *key)
        close = (closing_cache[key] or {}).get(r["selection"])
        closing_odds = close["median_odds"] if close else None
        closing_prob = close["consensus_prob"] if close else None
        # Median at grade time vs median at close -- never best_odds, which
        # is above the median by construction and would flatter every row.
        graded = r["graded_median_odds"]
        clv = edge_math.clv(graded, closing_odds) if graded and closing_odds else None
        clv_24h = edge_math.clv(r["median_24h"], closing_odds) if r["median_24h"] and closing_odds else None
        conn.execute(
            """
            INSERT OR IGNORE INTO betting_results
                (recommendation_id, result_home, result_away, won, profit_1u, closing_odds, closing_prob,
                 clv, clv_24h, clv_version, settled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (r["recommendation_id"], r["home_goals"], r["away_goals"], int(won),
             round(profit, 4) if profit is not None else None, closing_odds, closing_prob,
             round(clv, 6) if clv is not None else None, round(clv_24h, 6) if clv_24h is not None else None,
             edge_math.CLV_VERSION, now_iso),
        )
        counts["settled"] += 1
        if clv_24h is not None:
            counts["with_clv"] += 1
    conn.commit()
    return counts


def recompute_clv(conn, now_iso: str) -> dict:
    """Re-derive clv for every settled row from stored consensus: median at
    the graded snapshot vs closing median. Idempotent; used once to correct
    rows settled while clv compared best_odds to the closing median."""
    rows = conn.execute(
        """
        SELECT r.recommendation_id, mc.median_odds AS graded, d1.median_odds AS h24, cl.median_odds AS closing
        FROM betting_results r
        JOIN betting_recommendations br USING (recommendation_id)
        LEFT JOIN market_consensus mc
          ON mc.fixture_id = br.fixture_id AND mc.market = br.market
         AND mc.selection = br.selection AND mc.snapshot = br.market_snapshot
        LEFT JOIN market_consensus d1
          ON d1.fixture_id = br.fixture_id AND d1.market = br.market
         AND d1.selection = br.selection AND d1.snapshot = '24h'
        LEFT JOIN market_consensus cl
          ON cl.fixture_id = br.fixture_id AND cl.market = br.market
         AND cl.selection = br.selection AND cl.snapshot = 'closing'
        """
    ).fetchall()
    changed = 0
    for r in rows:
        clv = edge_math.clv(r["graded"], r["closing"]) if r["graded"] and r["closing"] else None
        clv_24h = edge_math.clv(r["h24"], r["closing"]) if r["h24"] and r["closing"] else None
        vals = (round(clv, 6) if clv is not None else None, round(clv_24h, 6) if clv_24h is not None else None)
        cur = conn.execute(
            "UPDATE betting_results SET clv = ?, clv_24h = ?, clv_version = ? WHERE recommendation_id = ?"
            " AND (clv IS NOT ? OR clv_24h IS NOT ? OR clv_version IS NOT ?)",
            (*vals, edge_math.CLV_VERSION, r["recommendation_id"], *vals, edge_math.CLV_VERSION),
        )
        changed += cur.rowcount
    conn.commit()
    return {"rows": len(rows), "changed": changed, "at": now_iso}


def migrate(conn) -> None:
    """schema.sql only creates; columns added later need ALTER on live DBs."""
    for table, added in (
        ("betting_results", (("clv_24h", "REAL"), ("clv_version", "TEXT"))),
        ("betting_recommendations", (("hours_to_kickoff", "REAL"),)),
    ):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in added:
            if name not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.commit()


def run(db_path: Path = None) -> dict:
    started = time.monotonic()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection(db_path)
    db.init_db(conn)
    migrate(conn)
    counts = {"consensus_rows": build_consensus(conn, now_iso)}
    counts.update(build_context(conn, now_iso))
    counts.update(grade_locked(conn, now_iso))
    predictions = json.loads(PREDICTIONS_PATH.read_text()) if PREDICTIONS_PATH.exists() else None
    counts.update(grade_horizon(conn, predictions, now_iso))
    counts.update(settle(conn, now_iso))
    conn.close()
    return {
        "success": True,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "counts": counts,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Consensus, grading and settlement for the betting ledger.")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--recompute-clv", action="store_true", help="re-derive clv for all settled rows and exit")
    args = parser.parse_args()

    if args.recompute_clv:
        conn = db.get_connection(args.db_path)
        db.init_db(conn)
        migrate(conn)
        out = recompute_clv(conn, datetime.now(timezone.utc).isoformat())
        conn.close()
        print(f"clv recomputed: {out['changed']} of {out['rows']} settled rows changed")
        return

    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    status_path = config.STATUS_DIR / "betting_status.json"
    try:
        status = run(args.db_path)
    except Exception as exc:
        status_path.write_text(json.dumps(
            {"success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)}, indent=2))
        print(f"[betting] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    status_path.write_text(json.dumps(status, indent=2))
    c = status["counts"]
    print(
        f"betting ledger: +{c['consensus_rows']} consensus rows, context for {c['context_fixtures']} fixture(s), "
        f"{c['fixtures_graded']} graded at lock "
        f"({c['recommendations']} rows: {c.get('PASS', 0)} PASS, {c.get('WATCH', 0)} WATCH), "
        f"{c['horizon_fixtures']} graded at 24h ({c['horizon_rows']} rows), "
        f"{c['settled']} settled ({c['with_clv']} with CLV)"
    )


if __name__ == "__main__":
    main()
