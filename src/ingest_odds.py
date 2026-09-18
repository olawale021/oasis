"""Archive pre-match odds snapshots for upcoming fixtures (PRD section 11).

There is no historical odds archive to buy back, so collection must run from
launch onward. This script is idempotent and schedule-driven: each run works
out which snapshot window (7d / 24h / 6h / 1h / closing) every upcoming
fixture is currently in and archives that window's odds if not already taken.
Windows are hours-to-kickoff bands (see SNAPSHOT_WINDOWS); "24h" is 12-36h.
Run it repeatedly (cron, or manually around matchdays) and each window fills
exactly once per fixture -- rows are INSERT OR IGNORE, never updated, so the
archive is append-only (PRD 18.4). The 'lineup' snapshot is reserved for a
future live lineup-ingestion stage.

    python3 src/ingest_odds.py                 # PL, next 8 days
    python3 src/ingest_odds.py --horizon-days 3
    python3 src/ingest_odds.py --league-ids 39,140

Only core markets are stored in SQLite (Match Winner, Goals Over/Under, Both
Teams Score) -- the full raw response is archived under data/raw/odds/ anyway,
so nothing is lost. Margin removal: within each (bookmaker, market, line)
outcome group, normalized_prob = implied / sum(implied).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import api_client
import config
import db

DEFAULT_LEAGUE_IDS = [39, 140, 135, 78, 253, 2]  # all live target leagues (+ Champions League)
DEFAULT_HORIZON_DAYS = 8

# API-Football bet ids for the markets worth structured storage.
CORE_MARKETS = {1: "Match Winner", 5: "Goals Over/Under", 8: "Both Teams Score"}

# (label, min exclusive, max inclusive) in hours to kickoff. A run archives
# the window the fixture currently sits in; earlier missed windows cannot be
# reconstructed and are simply skipped -- honest gaps, not backfilled fakes.
#
# "24h" was 12-96h until 2026-09-17, so the first run that saw a fixture
# archived it ~4 days out and the label lied. It is now 12-36h, so the
# betting ledger's h24 track (grade a day out, CLV to the close) means what
# it says; the ~4-day price folds into "7d". Every row carries
# hours_to_kickoff, so old- and new-definition rows stay distinguishable.
SNAPSHOT_WINDOWS = [
    ("closing", 0.0, 0.75),
    ("1h", 0.75, 3.0),
    ("6h", 3.0, 12.0),
    ("24h", 12.0, 36.0),
    ("7d", 36.0, 240.0),
]


def snapshot_label(hours_to_kickoff: float):
    for label, lo, hi in SNAPSHOT_WINDOWS:
        if lo < hours_to_kickoff <= hi:
            return label
    return None


def outcome_group_key(market_id: int, outcome: str) -> str:
    """Outcomes normalize against their own alternatives: the 1X2 triple, the
    BTTS pair, or one over/under line pair (the line is the trailing token of
    e.g. 'Over 2.5')."""
    if market_id == 5:
        parts = outcome.rsplit(" ", 1)
        return parts[1] if len(parts) == 2 else outcome
    return ""


def parse_fixture_odds(items: list, snapshot: str, hours: float, fetched_at: str) -> list:
    rows = []
    for entry in items:
        fixture_id = (entry.get("fixture") or {}).get("id")
        for bookmaker in entry.get("bookmakers") or []:
            for bet in bookmaker.get("bets") or []:
                market_id = bet.get("id")
                if market_id not in CORE_MARKETS:
                    continue
                values = bet.get("values") or []
                implied = {}
                for v in values:
                    try:
                        odd = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if odd <= 1.0:
                        continue
                    implied[str(v.get("value"))] = odd
                # margin removal per outcome group
                group_sums = {}
                for outcome, odd in implied.items():
                    key = outcome_group_key(market_id, outcome)
                    group_sums[key] = group_sums.get(key, 0.0) + 1.0 / odd
                for outcome, odd in implied.items():
                    key = outcome_group_key(market_id, outcome)
                    p = 1.0 / odd
                    group_total = group_sums[key]
                    rows.append(
                        {
                            "fixture_id": fixture_id,
                            "snapshot": snapshot,
                            "bookmaker_id": bookmaker.get("id"),
                            "bookmaker": bookmaker.get("name"),
                            "market_id": market_id,
                            "market": CORE_MARKETS[market_id],
                            "outcome": outcome,
                            "odds_decimal": odd,
                            "implied_prob": round(p, 6),
                            "normalized_prob": round(p / group_total, 6) if group_total > 0 else None,
                            "hours_to_kickoff": round(hours, 2),
                            "fetched_at": fetched_at,
                        }
                    )
    return rows


def load_upcoming_fixtures(conn, league_ids: list, horizon_days: int, now: datetime) -> list:
    marks = ", ".join("?" for _ in league_ids)
    rows = conn.execute(
        f"""
        SELECT fixture_id, kickoff_utc FROM fixtures
        WHERE league_id IN ({marks}) AND status_short = 'NS'
        ORDER BY kickoff_utc ASC
        """,
        list(league_ids),
    ).fetchall()
    out = []
    for r in rows:
        kickoff = datetime.fromisoformat(r["kickoff_utc"])
        hours = (kickoff - now).total_seconds() / 3600
        if 0 < hours <= horizon_days * 24:
            out.append({"fixture_id": r["fixture_id"], "kickoff_utc": r["kickoff_utc"], "hours": hours})
    return out


def run_ingest(league_ids=None, horizon_days=DEFAULT_HORIZON_DAYS, force_refresh=False, db_path: Path = None) -> dict:
    started = datetime.now(timezone.utc)
    league_ids = league_ids or DEFAULT_LEAGUE_IDS

    conn = db.get_connection(db_path)
    db.init_db(conn)
    client = api_client.APIFootballClient()

    fixtures = load_upcoming_fixtures(conn, league_ids, horizon_days, started)
    results = []
    for f in fixtures:
        label = snapshot_label(f["hours"])
        if label is None:
            results.append({**f, "snapshot": None, "skipped": "outside all snapshot windows"})
            continue
        already = conn.execute(
            "SELECT COUNT(*) FROM odds_snapshots WHERE fixture_id = ? AND snapshot = ?",
            (f["fixture_id"], label),
        ).fetchone()[0]
        if already and not force_refresh:
            results.append({**f, "snapshot": label, "skipped": "window already archived", "existing_rows": already})
            continue

        fetched = client.get_odds(f["fixture_id"], cache_suffix=label, force_refresh=force_refresh)
        rows = parse_fixture_odds(fetched["items"], label, f["hours"], fetched["fetched_at"])
        inserted = sum(1 for row in rows if db.insert_odds_snapshot(conn, row))
        conn.commit()
        bookmakers = len({row["bookmaker_id"] for row in rows})
        results.append(
            {**f, "snapshot": label, "rows_parsed": len(rows), "rows_inserted": inserted, "bookmakers": bookmakers}
        )

    conn.close()
    finished = datetime.now(timezone.utc)

    summary = {
        "fixtures_in_horizon": len(fixtures),
        "fixtures_archived": sum(1 for r in results if r.get("rows_inserted")),
        "fixtures_skipped": sum(1 for r in results if "skipped" in r),
        "rows_inserted": sum(r.get("rows_inserted", 0) for r in results),
    }

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = config.REPORTS_DIR / f"ingest_odds_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    report = {
        "meta": {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "league_ids": league_ids,
            "horizon_days": horizon_days,
        },
        "summary": summary,
        "results": results,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    status = {
        "success": True,
        "refreshed_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "counts": summary,
    }
    (config.STATUS_DIR / "ingest_odds_status.json").write_text(json.dumps(status, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive pre-match odds snapshots for upcoming fixtures.")
    parser.add_argument("--league-ids", type=str, default=None, help="Comma-separated league IDs (default: 39)")
    parser.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    parser.add_argument("--force-refresh", action="store_true", help="Re-fetch live even if the window was archived")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    league_ids = [int(x) for x in args.league_ids.split(",")] if args.league_ids else None

    try:
        report = run_ingest(
            league_ids=league_ids,
            horizon_days=args.horizon_days,
            force_refresh=args.force_refresh,
            db_path=args.db_path,
        )
    except api_client.APIFootballError as exc:
        print(f"[ingest_odds] hard failure: {exc}", file=sys.stderr)
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "ingest_odds_status.json").write_text(
            json.dumps(
                {"success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)},
                indent=2,
            )
        )
        raise SystemExit(1)

    print(f"odds snapshots: {report['summary']}")
    for r in report["results"]:
        tag = r.get("skipped") or f"{r.get('rows_inserted', 0)} rows ({r.get('bookmakers', 0)} bookmakers)"
        print(f"  fixture {r['fixture_id']} [{r.get('snapshot')}] {tag}")


if __name__ == "__main__":
    main()
