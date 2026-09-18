import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import api_client
import config
import db
import leagues
from ingest_fixtures import parse_seasons_arg

DEFAULT_LEAGUE_IDS = [39]
DEFAULT_SEASONS = list(range(2017, 2026))

STAT_TYPE_MAP = {
    "Shots on Goal": "shots_on_goal",
    "Shots off Goal": "shots_off_goal",
    "Total Shots": "total_shots",
    "Blocked Shots": "blocked_shots",
    "Shots insidebox": "shots_insidebox",
    "Shots outsidebox": "shots_outsidebox",
    "Fouls": "fouls",
    "Corner Kicks": "corner_kicks",
    "Offsides": "offsides",
    "Ball Possession": "ball_possession_pct",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Goalkeeper Saves": "goalkeeper_saves",
    "Total passes": "total_passes",
    "Passes accurate": "passes_accurate",
    "Passes %": "passes_pct",
    "expected_goals": "expected_goals",
    "goals_prevented": "goals_prevented",
}
PCT_TYPES = {"Ball Possession", "Passes %"}
FLOAT_TYPES = {"expected_goals", "goals_prevented"}


def _parse_stat_value(stat_type: str, raw_value):
    if raw_value is None:
        return None
    if stat_type in PCT_TYPES:
        if isinstance(raw_value, str):
            return float(raw_value.rstrip("%"))
        return float(raw_value)
    if stat_type in FLOAT_TYPES:
        return float(raw_value)
    return int(raw_value)


def parse_fixture_statistics_item(item: dict, fixture_id: int, fetched_at: str) -> dict:
    team = item.get("team", {}) or {}
    row = {column: None for column in STAT_TYPE_MAP.values()}
    for stat in item.get("statistics", []) or []:
        stat_type = stat.get("type")
        column = STAT_TYPE_MAP.get(stat_type)
        if column is None:
            continue
        row[column] = _parse_stat_value(stat_type, stat.get("value"))
    row.update(
        {
            "fixture_id": fixture_id,
            "team_id": team.get("id"),
            "fetched_at": fetched_at,
            "raw_json": json.dumps(item),
        }
    )
    return row


def ingest_one_fixture(client: api_client.APIFootballClient, conn, fixture_id: int, force_refresh: bool = False) -> dict:
    result = client.get_fixture_statistics(fixture_id, force_refresh=force_refresh)
    items = result["items"]
    if len(items) != 2:
        return {"fixture_id": fixture_id, "teams_seen": len(items), "warning": f"expected 2 team-stat blocks, got {len(items)}"}
    for item in items:
        row = parse_fixture_statistics_item(item, fixture_id, result["fetched_at"])
        if row["team_id"] is not None:
            db.upsert_fixture_statistics(conn, row)
    return {"fixture_id": fixture_id, "teams_seen": len(items), "warning": None}


def run_ingest(league_ids=None, seasons=None, force_refresh=False, db_path: Path = None) -> dict:
    started = datetime.now(timezone.utc)
    league_ids = league_ids or DEFAULT_LEAGUE_IDS
    seasons = seasons or DEFAULT_SEASONS

    conn = db.get_connection(db_path)
    db.init_db(conn)
    client = api_client.APIFootballClient()

    # Champions League qualifiers are rating updates only, never scored: skip
    # their per-fixture calls (about half the competition's fixtures).
    fixtures = [r for r in db.get_completed_fixtures(conn, league_ids, seasons) if leagues.is_scored_round(r["league_id"], r["round"])]
    results = []
    warnings = []
    for i, row in enumerate(fixtures, 1):
        r = ingest_one_fixture(client, conn, row["fixture_id"], force_refresh)
        conn.commit()
        results.append(r)
        if r["warning"]:
            warnings.append({"fixture_id": row["fixture_id"], "warning": r["warning"]})
        if i % 200 == 0:
            print(f"[ingest_fixture_statistics] {i}/{len(fixtures)} fixtures processed", file=sys.stderr)

    conn.close()
    finished = datetime.now(timezone.utc)

    summary = {
        "fixtures_processed": len(results),
        "fixtures_with_full_stats": sum(1 for r in results if r["teams_seen"] == 2),
        "fixtures_with_warnings": len(warnings),
    }

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)

    season_tag = "-".join(str(s) for s in seasons) if len(seasons) <= 3 else f"{seasons[0]}-{seasons[-1]}"
    report_path = config.REPORTS_DIR / f"ingest_fixture_statistics_{season_tag}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
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
    (config.STATUS_DIR / "ingest_fixture_statistics_status.json").write_text(json.dumps(status, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest per-fixture shot/possession statistics from API-Football.")
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
        print(f"[ingest_fixture_statistics] hard failure: {exc}", file=sys.stderr)
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "ingest_fixture_statistics_status.json").write_text(
            json.dumps({"success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)}, indent=2)
        )
        raise SystemExit(1)

    print(f"Processed {report['summary']['fixtures_processed']} fixtures: {report['summary']}")


if __name__ == "__main__":
    main()
