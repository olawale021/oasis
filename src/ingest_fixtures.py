import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import api_client
import config
import db

DEFAULT_LEAGUE_IDS = [39, 40]
DEFAULT_SEASONS = list(range(2017, 2026))


def parse_seasons_arg(raw: str) -> list:
    seasons = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            seasons.extend(range(int(start), int(end) + 1))
        else:
            seasons.append(int(chunk))
    return seasons


def parse_fixture_item(item: dict, league_id: int, season: int, now: str) -> tuple:
    fixture = item.get("fixture", {}) or {}
    league = item.get("league", {}) or {}
    teams = item.get("teams", {}) or {}
    goals = item.get("goals", {}) or {}
    score = item.get("score", {}) or {}
    halftime = score.get("halftime", {}) or {}
    venue = fixture.get("venue", {}) or {}
    status = fixture.get("status", {}) or {}
    home = teams.get("home", {}) or {}
    away = teams.get("away", {}) or {}

    def team_row(t):
        return {
            "team_id": t.get("id"),
            "name": t.get("name"),
            "country": league.get("country"),
            "founded": None,
            "logo_url": t.get("logo"),
            "first_seen_at": now,
            "last_seen_at": now,
        }

    fixture_row = {
        "fixture_id": fixture.get("id"),
        "league_id": league_id,
        "season": season,
        "round": league.get("round"),
        "kickoff_utc": fixture.get("date"),
        "status_short": status.get("short"),
        "status_long": status.get("long"),
        "home_team_id": home.get("id"),
        "away_team_id": away.get("id"),
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
        "home_goals_ht": halftime.get("home"),
        "away_goals_ht": halftime.get("away"),
        "venue_name": venue.get("name"),
        "venue_city": venue.get("city"),
        "referee": fixture.get("referee"),
        "updated_at": now,
        "raw_json": json.dumps(item),
    }
    return team_row(home), team_row(away), fixture_row


def ingest_league_season(client: api_client.APIFootballClient, conn, league_id: int, season: int, force_refresh: bool = False) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    result = client.get_fixtures(league_id, season, force_refresh=force_refresh)
    teams_seen = {}
    fixtures_seen = 0
    for item in result["items"]:
        home_row, away_row, fixture_row = parse_fixture_item(item, league_id, season, now)
        if home_row["team_id"] is not None:
            teams_seen[home_row["team_id"]] = home_row
        if away_row["team_id"] is not None:
            teams_seen[away_row["team_id"]] = away_row
        if fixture_row["fixture_id"] is not None:
            db.upsert_fixture(conn, fixture_row)
            fixtures_seen += 1

    for team_row in teams_seen.values():
        db.upsert_team(conn, team_row)

    return {
        "league_id": league_id,
        "season": season,
        "fixtures_seen": fixtures_seen,
        "teams_seen": len(teams_seen),
        "pages_fetched": result["pages_fetched"],
        "warnings": result["warnings"],
    }


def run_ingest(league_ids=None, seasons=None, force_refresh=False, db_path: Path = None) -> dict:
    started = datetime.now(timezone.utc)
    league_ids = league_ids or DEFAULT_LEAGUE_IDS
    seasons = seasons or DEFAULT_SEASONS

    conn = db.get_connection(db_path)
    db.init_db(conn)
    client = api_client.APIFootballClient()

    results = []
    for league_id in league_ids:
        for season in seasons:
            row = ingest_league_season(client, conn, league_id, season, force_refresh)
            conn.commit()
            results.append(row)

    conn.close()
    finished = datetime.now(timezone.utc)

    summary = {
        "league_seasons_ingested": len(results),
        "total_fixtures_seen": sum(r["fixtures_seen"] for r in results),
        "total_teams_seen": sum(r["teams_seen"] for r in results),
    }

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)

    season_tag = "-".join(str(s) for s in seasons) if len(seasons) <= 3 else f"{seasons[0]}-{seasons[-1]}"
    report_path = config.REPORTS_DIR / f"ingest_fixtures_{season_tag}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    report = {
        "meta": {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "league_ids": league_ids,
            "seasons": seasons,
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
    (config.STATUS_DIR / "ingest_fixtures_status.json").write_text(json.dumps(status, indent=2))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest fixtures/teams from API-Football.")
    parser.add_argument("--league-ids", type=str, default=None, help="Comma-separated league IDs (default: 39,40)")
    parser.add_argument("--seasons", type=str, default=None, help='e.g. "2017-2025" (default: 2017-2025)')
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    league_ids = [int(x) for x in args.league_ids.split(",")] if args.league_ids else None
    seasons = parse_seasons_arg(args.seasons) if args.seasons else None

    try:
        report = run_ingest(
            league_ids=league_ids,
            seasons=seasons,
            force_refresh=args.force_refresh,
            db_path=args.db_path,
        )
    except api_client.APIFootballError as exc:
        print(f"[ingest_fixtures] hard failure: {exc}", file=sys.stderr)
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "ingest_fixtures_status.json").write_text(
            json.dumps(
                {
                    "success": False,
                    "refreshed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                },
                indent=2,
            )
        )
        raise SystemExit(1)

    print(f"Ingested {report['summary']['league_seasons_ingested']} league-seasons: {report['summary']}")


if __name__ == "__main__":
    main()
