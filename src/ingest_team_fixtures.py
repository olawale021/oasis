"""All-competition fixtures for every club in the live leagues.

The league ingest only sees league matches, so rest days and congestion
miss midweek cup and European games. This pulls /fixtures?team=&season=
for each club that appears in a tracked league-season and upserts every
fixture it returns -- any competition -- into the same fixtures table
(with its real league_id, and a leagues row so the id is named).

Idempotent; raw responses cached under data/raw/fixtures/team_*.json.
One API call per club-season (~110 clubs -> ~110 calls per season).

    python3 src/ingest_team_fixtures.py --seasons 2026                     # matchday refresh
    python3 src/ingest_team_fixtures.py --seasons 2017-2026 --force-refresh # backfill
"""

import argparse
import json
import sys
from datetime import datetime, timezone

import api_client
import config
import db
import ingest_fixtures
import leagues

DEFAULT_LEAGUE_IDS = [cfg["league_id"] for cfg in leagues.pooled_targets().values()]


def club_ids(conn, league_id: int, season: int) -> list:
    rows = conn.execute(
        "SELECT home_team_id AS t FROM fixtures WHERE league_id = ? AND season = ?"
        " UNION SELECT away_team_id FROM fixtures WHERE league_id = ? AND season = ?",
        (league_id, season, league_id, season),
    ).fetchall()
    return sorted(r["t"] for r in rows if r["t"] is not None)


def ingest_team_season(client, conn, team_id: int, season: int, known_leagues: set, force_refresh: bool) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    result = client.get_team_fixtures(team_id, season, force_refresh=force_refresh)
    fixtures = 0
    new_leagues = 0
    by_league = {}
    for item in result["items"]:
        league = item.get("league") or {}
        league_id = league.get("id")
        item_season = league.get("season") or season
        if league_id is None:
            continue
        if league_id not in known_leagues:
            db.upsert_league(conn, {
                "league_id": league_id,
                "name": league.get("name"),
                "country": league.get("country"),
                "role": "unknown",  # not a target/feeder: schedule index only
                "expected_name": league.get("name"),
                "last_verified_at": now,
            })
            known_leagues.add(league_id)
            new_leagues += 1
        home_row, away_row, fixture_row = ingest_fixtures.parse_fixture_item(item, league_id, item_season, now)
        if fixture_row["fixture_id"] is None:
            continue
        db.upsert_fixture(conn, fixture_row)
        for t in (home_row, away_row):
            if t["team_id"] is not None:
                db.upsert_team(conn, t)
        fixtures += 1
        by_league[league_id] = by_league.get(league_id, 0) + 1
    return {"team_id": team_id, "season": season, "fixtures": fixtures, "leagues": len(by_league), "new_leagues": new_leagues}


def run(league_ids: list, seasons: list, force_refresh: bool) -> dict:
    started = datetime.now(timezone.utc)
    conn = db.get_connection()
    db.init_db(conn)
    client = api_client.APIFootballClient()
    known_leagues = {r["league_id"] for r in conn.execute("SELECT league_id FROM leagues")}
    rows = []
    done = set()
    for season in seasons:
        for league_id in league_ids:
            for team_id in club_ids(conn, league_id, season):
                if (team_id, season) in done:
                    continue
                done.add((team_id, season))
                rows.append(ingest_team_season(client, conn, team_id, season, known_leagues, force_refresh))
                conn.commit()
                print(f"  team {team_id} {season}: {rows[-1]['fixtures']} fixtures across {rows[-1]['leagues']} competitions", file=sys.stderr)
    conn.close()
    finished = datetime.now(timezone.utc)
    summary = {
        "club_seasons": len(rows),
        "fixtures_seen": sum(r["fixtures"] for r in rows),
        "new_leagues": sum(r["new_leagues"] for r in rows),
    }
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATUS_DIR / "ingest_team_fixtures_status.json").write_text(json.dumps({
        "success": True,
        "refreshed_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "counts": summary,
    }, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="All-competition fixtures per club (rest/congestion index).")
    parser.add_argument("--league-ids", type=str, default=None, help=f"default: {DEFAULT_LEAGUE_IDS}")
    parser.add_argument("--seasons", type=str, default=str(config.CURRENT_SEASON) if hasattr(config, "CURRENT_SEASON") else "2026")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()
    league_ids = [int(x) for x in args.league_ids.split(",")] if args.league_ids else DEFAULT_LEAGUE_IDS
    seasons = ingest_fixtures.parse_seasons_arg(args.seasons)
    try:
        summary = run(league_ids, seasons, args.force_refresh)
    except Exception as exc:  # status file first, then re-raise for the chain
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "ingest_team_fixtures_status.json").write_text(json.dumps({
            "success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)}, indent=2))
        raise
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
