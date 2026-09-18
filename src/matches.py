from datetime import datetime

import db


def is_neutral_round(round_text: str) -> bool:
    """True only for a Championship play-off Final (played at a neutral venue,
    historically Wembley). Play-off semi-finals are two-legged, played at each
    club's own ground, so they're NOT neutral. Everything else in this dataset
    (regular league fixtures) is never neutral. Documented Phase-1 simplification
    -- low-stakes, ~1 match/season, feeder-league only."""
    if not round_text:
        return False
    text = round_text.lower().strip()
    # European finals are single matches at a pre-chosen neutral venue.
    if text == "final":
        return True
    return "play-off" in text and "final" in text


def _parse_kickoff(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_matches(conn, league_ids: list, seasons: list = None) -> list:
    """Single source of truth for 'what counts as a played match' for every
    downstream modeling script. Returns matches sorted by kickoff_utc ascending."""
    rows = db.get_completed_fixtures(conn, league_ids, seasons)
    matches = []
    for row in rows:
        if row["home_goals"] is None or row["away_goals"] is None:
            continue
        matches.append(
            {
                "fixture_id": row["fixture_id"],
                "league_id": row["league_id"],
                "season": row["season"],
                "kickoff_utc": _parse_kickoff(row["kickoff_utc"]),
                "home_team_id": row["home_team_id"],
                "away_team_id": row["away_team_id"],
                "home_goals": row["home_goals"],
                "away_goals": row["away_goals"],
                "neutral": is_neutral_round(row["round"]),
                "round": row["round"],
            }
        )
    matches.sort(key=lambda m: m["kickoff_utc"])
    return matches


FRIENDLIES_LEAGUE_ID = 667  # API-Football "Friendlies Clubs": heavy rotation, not real load


def load_schedule_matches(conn, seasons: list = None, exclude_league_ids: tuple = (FRIENDLIES_LEAGUE_ID,)) -> list:
    """Every completed fixture in the DB regardless of competition -- the
    all-competition schedule index for rest/congestion. Includes the tracked
    leagues themselves, so the index is a superset of load_matches. Only
    dates and team ids are needed; goals are ignored downstream."""
    query = "SELECT fixture_id, league_id, season, kickoff_utc, home_team_id, away_team_id FROM fixtures WHERE status_short IN ('FT','AET','PEN')"
    params = []
    if exclude_league_ids:
        query += " AND league_id NOT IN ({})".format(", ".join("?" for _ in exclude_league_ids))
        params.extend(exclude_league_ids)
    if seasons:
        query += " AND season IN ({})".format(", ".join("?" for _ in seasons))
        params.extend(seasons)
    rows = conn.execute(query + " ORDER BY kickoff_utc ASC", params).fetchall()
    return [
        {
            "fixture_id": r["fixture_id"],
            "league_id": r["league_id"],
            "season": r["season"],
            "kickoff_utc": _parse_kickoff(r["kickoff_utc"]),
            "home_team_id": r["home_team_id"],
            "away_team_id": r["away_team_id"],
        }
        for r in rows
    ]
