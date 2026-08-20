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


def parse_lineup_item(item: dict, fixture_id: int, fetched_at: str) -> tuple:
    team = item.get("team", {}) or {}
    coach = item.get("coach", {}) or {}
    lineup_row = {
        "fixture_id": fixture_id,
        "team_id": team.get("id"),
        "formation": item.get("formation"),
        "coach_id": coach.get("id"),
        "coach_name": coach.get("name"),
        "fetched_at": fetched_at,
        "raw_json": json.dumps(item),
    }

    def _player_row(entry: dict, is_starter: int) -> dict:
        p = entry.get("player", {}) or {}
        return {
            "fixture_id": fixture_id,
            "team_id": team.get("id"),
            "player_id": p.get("id"),
            "player_name": p.get("name"),
            "shirt_number": p.get("number"),
            "position": p.get("pos"),
            "grid": p.get("grid"),
            "is_starter": is_starter,
        }

    player_rows = [_player_row(e, 1) for e in (item.get("startXI") or [])]
    player_rows += [_player_row(e, 0) for e in (item.get("substitutes") or [])]
    return lineup_row, player_rows


def ingest_one_fixture(client: api_client.APIFootballClient, conn, fixture_id: int, force_refresh: bool = False) -> dict:
    result = client.get_lineups(fixture_id, force_refresh=force_refresh)
    items = result["items"]
    if len(items) != 2:
        return {"fixture_id": fixture_id, "teams_seen": len(items), "players_seen": 0, "warning": f"expected 2 team lineups, got {len(items)}"}

    players_seen = 0
    for item in items:
        lineup_row, player_rows = parse_lineup_item(item, fixture_id, result["fetched_at"])
        if lineup_row["team_id"] is not None:
            db.upsert_lineup(conn, lineup_row)
        for prow in player_rows:
            if prow["player_id"] is not None:
                db.upsert_lineup_player(conn, prow)
                players_seen += 1
    return {"fixture_id": fixture_id, "teams_seen": len(items), "players_seen": players_seen, "warning": None}


def run_ingest(league_ids=None, seasons=None, force_refresh=False, db_path: Path = None) -> dict:
    started = datetime.now(timezone.utc)
    league_ids = league_ids or DEFAULT_LEAGUE_IDS
    seasons = seasons or DEFAULT_SEASONS

    conn = db.get_connection(db_path)
    db.init_db(conn)
    client = api_client.APIFootballClient()

    fixtures = db.get_completed_fixtures(conn, league_ids, seasons)
    results = []
    warnings = []
    for i, row in enumerate(fixtures, 1):
        r = ingest_one_fixture(client, conn, row["fixture_id"], force_refresh)
        conn.commit()
        results.append(r)
        if r["warning"]:
            warnings.append({"fixture_id": row["fixture_id"], "warning": r["warning"]})
        if i % 200 == 0:
            print(f"[ingest_lineups] {i}/{len(fixtures)} fixtures processed", file=sys.stderr)

    conn.close()
    finished = datetime.now(timezone.utc)

    summary = {
        "fixtures_processed": len(results),
        "fixtures_with_full_lineups": sum(1 for r in results if r["teams_seen"] == 2),
        "total_players_seen": sum(r["players_seen"] for r in results),
        "fixtures_with_warnings": len(warnings),
    }

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)

    season_tag = "-".join(str(s) for s in seasons) if len(seasons) <= 3 else f"{seasons[0]}-{seasons[-1]}"
    report_path = config.REPORTS_DIR / f"ingest_lineups_{season_tag}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    report = {
        "meta": {"started_at": started.isoformat(), "finished_at": finished.isoformat(), "league_ids": league_ids, "seasons": seasons},
        "summary": summary,
        "warnings": warnings,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    status = {
        "success": True,
        "refreshed_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "counts": summary,
    }
    (config.STATUS_DIR / "ingest_lineups_status.json").write_text(json.dumps(status, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest per-fixture confirmed lineups from API-Football.")
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
        print(f"[ingest_lineups] hard failure: {exc}", file=sys.stderr)
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "ingest_lineups_status.json").write_text(
            json.dumps({"success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)}, indent=2)
        )
        raise SystemExit(1)

    print(f"Processed {report['summary']['fixtures_processed']} fixtures: {report['summary']}")


if __name__ == "__main__":
    main()
