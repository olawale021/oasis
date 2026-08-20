import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import api_client
import config
import db
from ingest_fixtures import parse_seasons_arg

DEFAULT_LEAGUE_IDS = [39]
DEFAULT_SEASONS = list(range(2017, 2026))
KNOWN_STATUS_TYPES = {"Missing Fixture", "Questionable"}


def parse_injury_item(item: dict, fetched_at: str) -> dict:
    player = item.get("player", {}) or {}
    team = item.get("team", {}) or {}
    fixture = item.get("fixture", {}) or {}
    league = item.get("league", {}) or {}
    return {
        "fixture_id": fixture.get("id"),
        "team_id": team.get("id"),
        "player_id": player.get("id"),
        "player_name": player.get("name"),
        "status_type": player.get("type"),
        "reason": player.get("reason"),
        "league_id": league.get("id"),
        "season": league.get("season"),
        "fetched_at": fetched_at,
        "raw_json": json.dumps(item),
    }


def ingest_league_season(client: api_client.APIFootballClient, conn, league_id: int, season: int, force_refresh: bool = False) -> dict:
    result = client.get_injuries(league_id, season, force_refresh=force_refresh)
    rows_seen = 0
    skipped = 0
    unknown_status = 0
    for item in result["items"]:
        row = parse_injury_item(item, result["fetched_at"])
        if row["fixture_id"] is None or row["team_id"] is None or row["player_id"] is None:
            skipped += 1
            continue
        if row["status_type"] not in KNOWN_STATUS_TYPES:
            unknown_status += 1
        db.upsert_injury(conn, row)
        rows_seen += 1
    return {
        "league_id": league_id,
        "season": season,
        "rows_seen": rows_seen,
        "rows_skipped": skipped,
        "unknown_status_type_count": unknown_status,
        "pages_fetched": result["pages_fetched"],
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
        "total_rows_seen": sum(r["rows_seen"] for r in results),
        "total_unknown_status_type": sum(r["unknown_status_type_count"] for r in results),
    }

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)

    season_tag = "-".join(str(s) for s in seasons) if len(seasons) <= 3 else f"{seasons[0]}-{seasons[-1]}"
    report_path = config.REPORTS_DIR / f"ingest_injuries_{season_tag}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    report = {
        "meta": {"started_at": started.isoformat(), "finished_at": finished.isoformat(), "league_ids": league_ids, "seasons": seasons},
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
    (config.STATUS_DIR / "ingest_injuries_status.json").write_text(json.dumps(status, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest per-season injury records from API-Football.")
    parser.add_argument("--league-ids", type=str, default=None, help="Comma-separated league IDs (default: 39)")
    parser.add_argument("--seasons", type=str, default=None, help='e.g. "2017-2025" (default: 2017-2025)')
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    league_ids = [int(x) for x in args.league_ids.split(",")] if args.league_ids else None
    seasons = parse_seasons_arg(args.seasons) if args.seasons else None

    try:
        report = run_ingest(league_ids=league_ids, seasons=seasons, force_refresh=args.force_refresh, db_path=args.db_path)
    except api_client.APIFootballError as exc:
        print(f"[ingest_injuries] hard failure: {exc}", file=sys.stderr)
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "ingest_injuries_status.json").write_text(
            json.dumps({"success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)}, indent=2)
        )
        raise SystemExit(1)

    print(f"Ingested {report['summary']['league_seasons_ingested']} league-seasons: {report['summary']}")


if __name__ == "__main__":
    main()
