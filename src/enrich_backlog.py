"""Quota-aware enrichment backlog runner (PRD 8.2 depth for every league).

Works through fixture-statistics + lineups ingestion for the leagues that
don't have them yet (Serie A, Bundesliga, MLS -- ~20.5k API calls, ~3 daily
Pro quotas), one league-season chunk at a time. Before each chunk it checks
the live /status quota and stops cleanly when the day's budget is spent --
already-ingested chunks cost zero API calls (raw-response cache + DB
upserts), so just run it once a day until it prints "backlog complete":

    python3 src/enrich_backlog.py            # spend down to the safety floor
    python3 src/enrich_backlog.py --budget 3000   # cap this run's spend

Cron-friendly (exit 0 both on out-of-quota and on complete):
    0 6 * * * cd <repo> && .venv/bin/python src/enrich_backlog.py >> data/status/enrich_backlog.log 2>&1
"""

import argparse
import sys
from datetime import datetime, timezone

import requests

import config
import db
import ingest_fixture_statistics
import ingest_lineups

# League-season chunks, cheapest-league-first so whole leagues finish sooner.
BACKLOG_LEAGUES = [78, 135, 253]  # Bundesliga, Serie A, MLS
SEASONS = list(range(2017, 2026))
QUOTA_FLOOR = 250  # keep headroom for the daily odds/fixtures jobs


def quota_remaining() -> int:
    resp = requests.get(
        f"{config.API_FOOTBALL_BASE_URL}/status",
        headers={"x-apisports-key": config.API_FOOTBALL_KEY},
        timeout=15,
    )
    req = resp.json()["response"]["requests"]
    return req["limit_day"] - req["current"]


def missing_counts(conn, league_id: int, season: int) -> tuple:
    """(fixtures missing stats, fixtures missing lineups) for one league-season."""
    decided = "SELECT fixture_id FROM fixtures WHERE league_id = ? AND season = ? AND status_short IN ('FT','AET','PEN')"
    n_stats = conn.execute(
        f"SELECT COUNT(*) FROM ({decided}) d WHERE NOT EXISTS"
        " (SELECT 1 FROM fixture_statistics fs WHERE fs.fixture_id = d.fixture_id)",
        (league_id, season),
    ).fetchone()[0]
    n_lineups = conn.execute(
        f"SELECT COUNT(*) FROM ({decided}) d WHERE NOT EXISTS"
        " (SELECT 1 FROM lineups l WHERE l.fixture_id = d.fixture_id)",
        (league_id, season),
    ).fetchone()[0]
    return n_stats, n_lineups


def main() -> None:
    parser = argparse.ArgumentParser(description="Quota-aware enrichment backlog runner.")
    parser.add_argument("--budget", type=int, default=None, help="Max API calls this run (default: down to floor)")
    parser.add_argument("--quota-floor", type=int, default=QUOTA_FLOOR)
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)
    spent_estimate = 0
    chunks_done = 0
    incomplete = False

    for league_id in BACKLOG_LEAGUES:
        for season in SEASONS:
            n_stats, n_lineups = missing_counts(conn, league_id, season)
            for kind, n_missing, module in (
                ("stats", n_stats, ingest_fixture_statistics),
                ("lineups", n_lineups, ingest_lineups),
            ):
                if n_missing == 0:
                    continue
                cost = n_missing + 20  # small retry/pagination buffer
                if args.budget is not None and spent_estimate + cost > args.budget:
                    incomplete = True
                    print(f"[enrich_backlog] budget reached before {league_id}/{season} {kind} ({n_missing} calls)")
                    print(f"[enrich_backlog] done for now: {chunks_done} chunks, ~{spent_estimate} calls. Re-run to continue.")
                    return
                remaining = quota_remaining()
                if remaining - cost < args.quota_floor:
                    incomplete = True
                    print(
                        f"[enrich_backlog] quota floor reached (remaining={remaining}, next chunk needs ~{cost}): "
                        f"stopping before {league_id}/{season} {kind}. Re-run after quota reset to continue."
                    )
                    print(f"[enrich_backlog] done for now: {chunks_done} chunks, ~{spent_estimate} calls.")
                    return
                print(
                    f"[enrich_backlog] {datetime.now(timezone.utc).isoformat()[:19]} "
                    f"league={league_id} season={season} {kind}: {n_missing} fixtures (quota remaining {remaining})"
                )
                module.run_ingest(league_ids=[league_id], seasons=[season])
                spent_estimate += cost
                chunks_done += 1

    if not incomplete:
        print(f"[enrich_backlog] backlog complete ({chunks_done} chunks this run, ~{spent_estimate} calls)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # cron-friendly: log and exit nonzero only on real errors
        print(f"[enrich_backlog] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
