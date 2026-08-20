import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import api_client
import config
import db
from leagues import LEAGUES

COVERAGE_FIELD_MAP = {
    "coverage_fixtures_events": ("fixtures", "events"),
    "coverage_fixtures_lineups": ("fixtures", "lineups"),
    "coverage_fixtures_statistics_fixtures": ("fixtures", "statistics_fixtures"),
    "coverage_fixtures_statistics_players": ("fixtures", "statistics_players"),
    "coverage_standings": ("standings", None),
    "coverage_players": ("players", None),
    "coverage_top_scorers": ("top_scorers", None),
    "coverage_top_assists": ("top_assists", None),
    "coverage_top_cards": ("top_cards", None),
    "coverage_injuries": ("injuries", None),
    "coverage_predictions": ("predictions", None),
    "coverage_odds": ("odds", None),
}

KNOWN_TOP_LEVEL_KEYS = {"fixtures", "standings", "players", "top_scorers", "top_assists", "top_cards", "injuries", "predictions", "odds"}
KNOWN_FIXTURES_KEYS = {"events", "lineups", "statistics_fixtures", "statistics_players"}


def default_season() -> int:
    # For the current date, this resolves correctly for both Aug-May European
    # leagues (API convention: starting year, e.g. 2026 for 2026/27) and
    # calendar-year MLS. Callers needing a different season pass --seasons.
    return datetime.now(timezone.utc).year


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


def extract_coverage_flags(coverage_obj) -> tuple:
    flags = {col: None for col in COVERAGE_FIELD_MAP}
    warnings = []

    if coverage_obj is None:
        warnings.append("coverage object missing from season entry")
        return flags, warnings
    if not isinstance(coverage_obj, dict):
        warnings.append(f"coverage object is not a dict: {type(coverage_obj).__name__}")
        return flags, warnings

    fixtures_obj = coverage_obj.get("fixtures")
    if "fixtures" in coverage_obj and not isinstance(fixtures_obj, dict):
        warnings.append(f"coverage.fixtures is not a dict: {type(fixtures_obj).__name__}")
        fixtures_obj = None

    for column, (top_key, sub_key) in COVERAGE_FIELD_MAP.items():
        if sub_key is None:
            if top_key not in coverage_obj:
                warnings.append(f"coverage.{top_key} missing")
                continue
            flags[column] = _to_bool_or_none(coverage_obj.get(top_key), f"coverage.{top_key}", warnings)
        else:
            if fixtures_obj is None:
                continue
            if sub_key not in fixtures_obj:
                warnings.append(f"coverage.fixtures.{sub_key} missing")
                continue
            flags[column] = _to_bool_or_none(fixtures_obj.get(sub_key), f"coverage.fixtures.{sub_key}", warnings)

    extra_top = set(coverage_obj.keys()) - KNOWN_TOP_LEVEL_KEYS
    if extra_top:
        warnings.append(f"unexpected top-level coverage keys: {sorted(extra_top)}")
    if isinstance(fixtures_obj, dict):
        extra_fixtures = set(fixtures_obj.keys()) - KNOWN_FIXTURES_KEYS
        if extra_fixtures:
            warnings.append(f"unexpected coverage.fixtures keys: {sorted(extra_fixtures)}")

    return flags, warnings


def _to_bool_or_none(value, field_name, warnings):
    if isinstance(value, bool):
        return int(value)
    warnings.append(f"{field_name} is not a bool: {value!r}")
    return None


def find_season_entry(seasons: list, season: int):
    for entry in seasons or []:
        if entry.get("year") == season:
            return entry
    return None


def audit_one(client: api_client.APIFootballClient, league_id: int, season: int, expected_name, role, force_refresh=False) -> dict:
    warnings = []
    checked_at = datetime.now(timezone.utc).isoformat()

    row = {
        "league_id": league_id,
        "season": season,
        "checked_at": checked_at,
        "api_league_name": None,
        "expected_league_name": expected_name,
        "name_mismatch": 0,
        "season_found": 0,
        "coverage_raw_json": "null",
        "warnings_json": "[]",
        "raw_response_path": f"leagues/{league_id}_{season}.json",
    }
    for column in db.COVERAGE_COLUMNS:
        row[column] = None

    envelope = client.get_league_coverage(league_id, season, force_refresh=force_refresh)
    payload = envelope.get("response", {})

    errors = payload.get("errors")
    if errors:
        warnings.append(f"API returned errors: {errors}")
        row["warnings_json"] = json.dumps(warnings)
        return row

    entries = payload.get("response", [])
    if not entries:
        warnings.append(f"no league entries returned for id={league_id} season={season}")
        row["warnings_json"] = json.dumps(warnings)
        return row
    if len(entries) > 1:
        warnings.append(f"expected 1 league entry, got {len(entries)}; using the first")

    entry = entries[0]
    api_name = (entry.get("league") or {}).get("name")
    row["api_league_name"] = api_name

    if expected_name is not None and api_name != expected_name:
        row["name_mismatch"] = 1
        warnings.append(f"league name mismatch: expected {expected_name!r}, got {api_name!r}")

    season_entry = find_season_entry(entry.get("seasons"), season)
    if season_entry is None:
        warnings.append(f"season {season} not present in seasons[] for league {league_id}")
        row["warnings_json"] = json.dumps(warnings)
        return row

    row["season_found"] = 1
    coverage_obj = season_entry.get("coverage")
    row["coverage_raw_json"] = json.dumps(coverage_obj)
    flags, flag_warnings = extract_coverage_flags(coverage_obj)
    row.update(flags)
    warnings.extend(flag_warnings)
    row["warnings_json"] = json.dumps(warnings)
    return row


def build_summary(results: list) -> dict:
    return {
        "league_seasons_checked": len(results),
        "name_mismatches": sum(1 for r in results if r["name_mismatch"]),
        "seasons_not_found": sum(1 for r in results if not r["season_found"]),
        "rows_with_warnings": sum(1 for r in results if json.loads(r["warnings_json"])),
    }


def print_report(results: list) -> None:
    for row in results:
        name_check = "MISMATCH" if row["name_mismatch"] else "OK"
        print(f"\nLeague {row['league_id']} — {row['api_league_name'] or '?'} (season {row['season']})")
        print(f"  name check: {name_check} (expected {row['expected_league_name']!r})")
        print(f"  season found: {'yes' if row['season_found'] else 'no'}")
        for column in db.COVERAGE_COLUMNS:
            label = column.replace("coverage_", "").replace("_", " ")
            value = row[column]
            value_str = "unknown" if value is None else ("yes" if value else "no")
            print(f"  {label}: {value_str}")
        warnings = json.loads(row["warnings_json"])
        print(f"  warnings: {'; '.join(warnings) if warnings else 'none'}")

    summary = build_summary(results)
    print("\n--- summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")


def run_audit(league_ids=None, seasons=None, force_refresh=False, db_path: Path = None) -> dict:
    started = datetime.now(timezone.utc)
    league_ids = league_ids or list(LEAGUES.keys())
    seasons = seasons or [default_season()]

    conn = db.get_connection(db_path)
    db.init_db(conn)
    client = api_client.APIFootballClient()

    results = []
    for league_id in league_ids:
        cfg = LEAGUES.get(league_id, {"expected_name": None, "role": "unknown"})
        for season in seasons:
            row = audit_one(client, league_id, season, cfg["expected_name"], cfg["role"], force_refresh)
            db.insert_coverage_audit(conn, row)
            db.upsert_league(
                conn,
                {
                    "league_id": league_id,
                    "name": row["api_league_name"] or cfg["expected_name"] or f"league {league_id}",
                    "country": None,
                    "role": cfg["role"],
                    "expected_name": cfg["expected_name"],
                    "last_verified_at": row["checked_at"],
                },
            )
            results.append(row)
    conn.commit()
    conn.close()

    finished = datetime.now(timezone.utc)
    summary = build_summary(results)

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)

    season_tag = "-".join(str(s) for s in seasons) if len(seasons) <= 3 else f"{seasons[0]}-{seasons[-1]}"
    report_path = config.REPORTS_DIR / f"coverage_audit_{season_tag}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
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
    (config.STATUS_DIR / "coverage_audit_status.json").write_text(json.dumps(status, indent=2))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit API-Football coverage for configured leagues.")
    parser.add_argument("--league-ids", type=str, default=None, help="Comma-separated league IDs (default: all configured)")
    parser.add_argument("--seasons", type=str, default=None, help='e.g. "2026" or "2017-2026" or "2020,2023-2026" (default: current year)')
    parser.add_argument("--force-refresh", action="store_true", help="Bypass raw-response cache and re-hit the API")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    league_ids = [int(x) for x in args.league_ids.split(",")] if args.league_ids else None
    seasons = parse_seasons_arg(args.seasons) if args.seasons else None

    try:
        report = run_audit(
            league_ids=league_ids,
            seasons=seasons,
            force_refresh=args.force_refresh,
            db_path=args.db_path,
        )
    except api_client.APIFootballError as exc:
        print(f"[coverage_audit] hard failure: {exc}", file=sys.stderr)
        config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (config.STATUS_DIR / "coverage_audit_status.json").write_text(
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

    print_report(report["results"])


if __name__ == "__main__":
    main()
