"""Betting ledger step of the matchday chain (Betting PRD 14, 15, 18).

    python3 src/betting/advisor.py            # after lifecycle settle, before export_web

Three idempotent passes:

  consensus  market_consensus rows for every odds window not yet summarised.
  grade      one betting_recommendations row per (locked prediction, market,
             selection) -- PASS rows too. The market is looked up as of the
             prediction's locked_at, never later, so every grade can be
             reproduced from stored data alone.
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
from betting.markets import model_probs, selection_won  # noqa: E402
from betting.thresholds import THRESHOLDS_VERSION, grade  # noqa: E402

DECIDED_STATUSES = ("FT", "AET", "PEN")


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
        probs = model_probs(lp)
        for market, sels in probs.items():
            mkt = consensus_as_of(conn, lp["fixture_id"], market, lp["locked_at"])
            for sel, p in sels.items():
                row = mkt.get(sel) if mkt else None
                market_prob = row["consensus_prob"] if row else None
                best_odds = row["best_odds"] if row else None
                e = edge_math.edge(p, market_prob) if row else None
                ev = edge_math.expected_value(p, best_odds) if row else None
                level, reasons = grade(p, market_prob, ev, row["bookmaker_count"] if row else None,
                                       row["snapshot"] if row else None)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO betting_recommendations
                        (fixture_id, stage, league_code, kickoff_utc, locked_at, market, selection,
                         model_version, goals_version, model_prob, market_prob, market_snapshot,
                         bookmaker_count, edge, best_odds, expected_value, confidence, level,
                         reasons_json, thresholds_version, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lp["fixture_id"], lp["stage"], lp["league_code"], lp["kickoff_utc"], lp["locked_at"],
                        market, sel, lp["model_version"], lp["goals_version"], round(p, 6),
                        market_prob, row["snapshot"] if row else None, row["bookmaker_count"] if row else None,
                        round(e, 6) if e is not None else None, best_odds,
                        round(ev, 6) if ev is not None else None, lp["confidence"], level,
                        json.dumps(reasons), THRESHOLDS_VERSION, now_iso,
                    ),
                )
                counts["recommendations"] += 1
                counts[level] = counts.get(level, 0) + 1
        counts["fixtures_graded"] += 1
    conn.commit()
    return counts


def settle(conn, now_iso: str) -> dict:
    rows = conn.execute(
        f"""
        SELECT br.recommendation_id, br.fixture_id, br.market, br.selection, br.best_odds,
               f.home_goals, f.away_goals
        FROM betting_recommendations br
        JOIN fixtures f ON f.fixture_id = br.fixture_id
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
        clv = edge_math.clv(r["best_odds"], closing_odds) if r["best_odds"] and closing_odds else None
        conn.execute(
            """
            INSERT OR IGNORE INTO betting_results
                (recommendation_id, result_home, result_away, won, profit_1u, closing_odds, closing_prob, clv, settled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (r["recommendation_id"], r["home_goals"], r["away_goals"], int(won),
             round(profit, 4) if profit is not None else None, closing_odds, closing_prob,
             round(clv, 6) if clv is not None else None, now_iso),
        )
        counts["settled"] += 1
        if clv is not None:
            counts["with_clv"] += 1
    conn.commit()
    return counts


def run(db_path: Path = None) -> dict:
    started = time.monotonic()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection(db_path)
    db.init_db(conn)
    counts = {"consensus_rows": build_consensus(conn, now_iso)}
    counts.update(grade_locked(conn, now_iso))
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
    args = parser.parse_args()

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
        f"betting ledger: +{c['consensus_rows']} consensus rows, {c['fixtures_graded']} fixture(s) graded "
        f"({c['recommendations']} rows: {c.get('PASS', 0)} PASS, {c.get('WATCH', 0)} WATCH), "
        f"{c['settled']} settled ({c['with_clv']} with CLV)"
    )


if __name__ == "__main__":
    main()
