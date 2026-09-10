import sqlite3
from pathlib import Path

import config

COVERAGE_COLUMNS = [
    "coverage_fixtures_events",
    "coverage_fixtures_lineups",
    "coverage_fixtures_statistics_fixtures",
    "coverage_fixtures_statistics_players",
    "coverage_standings",
    "coverage_players",
    "coverage_top_scorers",
    "coverage_top_assists",
    "coverage_top_cards",
    "coverage_injuries",
    "coverage_predictions",
    "coverage_odds",
]


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    db_path = db_path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(config.SCHEMA_PATH.read_text())


def upsert_league(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO leagues (league_id, name, country, role, expected_name, last_verified_at, created_at)
        VALUES (:league_id, :name, :country, :role, :expected_name, :last_verified_at, :last_verified_at)
        ON CONFLICT(league_id) DO UPDATE SET
            name = excluded.name,
            country = excluded.country,
            role = excluded.role,
            expected_name = excluded.expected_name,
            last_verified_at = excluded.last_verified_at
        """,
        row,
    )


def upsert_team(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO teams (team_id, name, country, founded, logo_url, first_seen_at, last_seen_at)
        VALUES (:team_id, :name, :country, :founded, :logo_url, :first_seen_at, :last_seen_at)
        ON CONFLICT(team_id) DO UPDATE SET
            name = excluded.name,
            country = excluded.country,
            founded = excluded.founded,
            logo_url = excluded.logo_url,
            last_seen_at = excluded.last_seen_at
        """,
        row,
    )


FIXTURE_COLUMNS = [
    "fixture_id",
    "league_id",
    "season",
    "round",
    "kickoff_utc",
    "status_short",
    "status_long",
    "home_team_id",
    "away_team_id",
    "home_goals",
    "away_goals",
    "home_goals_ht",
    "away_goals_ht",
    "venue_name",
    "venue_city",
    "referee",
    "updated_at",
    "raw_json",
]


def upsert_fixture(conn: sqlite3.Connection, row: dict) -> None:
    placeholders = ", ".join(f":{c}" for c in FIXTURE_COLUMNS)
    update_cols = [c for c in FIXTURE_COLUMNS if c != "fixture_id"]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conn.execute(
        f"""
        INSERT INTO fixtures ({', '.join(FIXTURE_COLUMNS)}) VALUES ({placeholders})
        ON CONFLICT(fixture_id) DO UPDATE SET {update_clause}
        """,
        {c: row.get(c) for c in FIXTURE_COLUMNS},
    )


def get_completed_fixtures(conn: sqlite3.Connection, league_ids: list, seasons: list = None) -> list:
    query = (
        "SELECT * FROM fixtures WHERE league_id IN ({}) AND status_short IN ('FT','AET','PEN')".format(
            ", ".join("?" for _ in league_ids)
        )
    )
    params = list(league_ids)
    if seasons:
        query += " AND season IN ({})".format(", ".join("?" for _ in seasons))
        params.extend(seasons)
    query += " ORDER BY kickoff_utc ASC"
    return conn.execute(query, params).fetchall()


FIXTURE_STATISTICS_COLUMNS = [
    "fixture_id",
    "team_id",
    "shots_on_goal",
    "shots_off_goal",
    "total_shots",
    "blocked_shots",
    "shots_insidebox",
    "shots_outsidebox",
    "fouls",
    "corner_kicks",
    "offsides",
    "ball_possession_pct",
    "yellow_cards",
    "red_cards",
    "goalkeeper_saves",
    "total_passes",
    "passes_accurate",
    "passes_pct",
    "expected_goals",
    "goals_prevented",
    "fetched_at",
    "raw_json",
]


def upsert_fixture_statistics(conn: sqlite3.Connection, row: dict) -> None:
    placeholders = ", ".join(f":{c}" for c in FIXTURE_STATISTICS_COLUMNS)
    update_cols = [c for c in FIXTURE_STATISTICS_COLUMNS if c not in ("fixture_id", "team_id")]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conn.execute(
        f"""
        INSERT INTO fixture_statistics ({', '.join(FIXTURE_STATISTICS_COLUMNS)}) VALUES ({placeholders})
        ON CONFLICT(fixture_id, team_id) DO UPDATE SET {update_clause}
        """,
        {c: row.get(c) for c in FIXTURE_STATISTICS_COLUMNS},
    )


INJURY_COLUMNS = [
    "fixture_id",
    "team_id",
    "player_id",
    "player_name",
    "status_type",
    "reason",
    "league_id",
    "season",
    "fetched_at",
    "raw_json",
]


def upsert_injury(conn: sqlite3.Connection, row: dict) -> None:
    placeholders = ", ".join(f":{c}" for c in INJURY_COLUMNS)
    update_cols = [c for c in INJURY_COLUMNS if c not in ("fixture_id", "team_id", "player_id")]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conn.execute(
        f"""
        INSERT INTO injuries ({', '.join(INJURY_COLUMNS)}) VALUES ({placeholders})
        ON CONFLICT(fixture_id, team_id, player_id) DO UPDATE SET {update_clause}
        """,
        {c: row.get(c) for c in INJURY_COLUMNS},
    )


LINEUP_COLUMNS = ["fixture_id", "team_id", "formation", "coach_id", "coach_name", "fetched_at", "raw_json"]


def upsert_lineup(conn: sqlite3.Connection, row: dict) -> None:
    placeholders = ", ".join(f":{c}" for c in LINEUP_COLUMNS)
    update_cols = [c for c in LINEUP_COLUMNS if c not in ("fixture_id", "team_id")]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conn.execute(
        f"""
        INSERT INTO lineups ({', '.join(LINEUP_COLUMNS)}) VALUES ({placeholders})
        ON CONFLICT(fixture_id, team_id) DO UPDATE SET {update_clause}
        """,
        {c: row.get(c) for c in LINEUP_COLUMNS},
    )


LINEUP_PLAYER_COLUMNS = [
    "fixture_id",
    "team_id",
    "player_id",
    "player_name",
    "shirt_number",
    "position",
    "grid",
    "is_starter",
]


def upsert_lineup_player(conn: sqlite3.Connection, row: dict) -> None:
    placeholders = ", ".join(f":{c}" for c in LINEUP_PLAYER_COLUMNS)
    update_cols = [c for c in LINEUP_PLAYER_COLUMNS if c not in ("fixture_id", "team_id", "player_id")]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conn.execute(
        f"""
        INSERT INTO lineup_players ({', '.join(LINEUP_PLAYER_COLUMNS)}) VALUES ({placeholders})
        ON CONFLICT(fixture_id, team_id, player_id) DO UPDATE SET {update_clause}
        """,
        {c: row.get(c) for c in LINEUP_PLAYER_COLUMNS},
    )


def get_fixture_statistics_by_league(conn: sqlite3.Connection, league_ids: list, seasons: list = None) -> list:
    query = """
        SELECT fs.*, f.kickoff_utc, f.season, f.league_id
        FROM fixture_statistics fs
        JOIN fixtures f ON f.fixture_id = fs.fixture_id
        WHERE f.league_id IN ({})
    """.format(", ".join("?" for _ in league_ids))
    params = list(league_ids)
    if seasons:
        query += " AND f.season IN ({})".format(", ".join("?" for _ in seasons))
        params.extend(seasons)
    query += " ORDER BY f.kickoff_utc ASC"
    return conn.execute(query, params).fetchall()


def get_missing_player_counts(conn: sqlite3.Connection, league_ids: list, seasons: list = None) -> list:
    query = """
        SELECT i.fixture_id, i.team_id, COUNT(DISTINCT i.player_id) AS missing_count
        FROM injuries i
        JOIN fixtures f ON f.fixture_id = i.fixture_id
        WHERE i.status_type = 'Missing Fixture' AND f.league_id IN ({})
    """.format(", ".join("?" for _ in league_ids))
    params = list(league_ids)
    if seasons:
        query += " AND f.season IN ({})".format(", ".join("?" for _ in seasons))
        params.extend(seasons)
    query += " GROUP BY i.fixture_id, i.team_id"
    return conn.execute(query, params).fetchall()


def get_lineup_players_by_league(conn: sqlite3.Connection, league_ids: list, seasons: list = None) -> list:
    query = """
        SELECT lp.fixture_id, lp.team_id, lp.player_id, lp.is_starter, f.kickoff_utc
        FROM lineup_players lp
        JOIN fixtures f ON f.fixture_id = lp.fixture_id
        WHERE f.league_id IN ({})
    """.format(", ".join("?" for _ in league_ids))
    params = list(league_ids)
    if seasons:
        query += " AND f.season IN ({})".format(", ".join("?" for _ in seasons))
        params.extend(seasons)
    query += " ORDER BY f.kickoff_utc ASC"
    return conn.execute(query, params).fetchall()


def insert_coverage_audit(conn: sqlite3.Connection, row: dict) -> None:
    columns = [
        "league_id",
        "season",
        "checked_at",
        "api_league_name",
        "expected_league_name",
        "name_mismatch",
        "season_found",
        *COVERAGE_COLUMNS,
        "coverage_raw_json",
        "warnings_json",
        "raw_response_path",
    ]
    placeholders = ", ".join(f":{c}" for c in columns)
    conn.execute(
        f"INSERT INTO coverage_audit ({', '.join(columns)}) VALUES ({placeholders})",
        {c: row.get(c) for c in columns},
    )


ODDS_COLUMNS = [
    "fixture_id",
    "snapshot",
    "bookmaker_id",
    "bookmaker",
    "market_id",
    "market",
    "outcome",
    "odds_decimal",
    "implied_prob",
    "normalized_prob",
    "hours_to_kickoff",
    "fetched_at",
]


def insert_odds_snapshot(conn: sqlite3.Connection, row: dict) -> bool:
    """Append-only by design (PRD 18.4): a snapshot already taken is never
    overwritten. Returns True if the row was actually inserted."""
    placeholders = ", ".join(f":{c}" for c in ODDS_COLUMNS)
    cur = conn.execute(
        f"INSERT OR IGNORE INTO odds_snapshots ({', '.join(ODDS_COLUMNS)}) VALUES ({placeholders})",
        {c: row.get(c) for c in ODDS_COLUMNS},
    )
    return cur.rowcount > 0


def get_market_outcome_probs(conn: sqlite3.Connection, fixture_ids: list) -> dict:
    """Latest-snapshot consensus 1X2 probabilities per fixture: the median
    across bookmakers of margin-removed (normalized) probabilities, from the
    most recent snapshot window that has Match Winner rows. Returns
    {fixture_id: {"home": p, "draw": p, "away": p, "snapshot": s, "bookmakers": n}}
    with probabilities in [0, 1]."""
    if not fixture_ids:
        return {}
    marks = ", ".join("?" for _ in fixture_ids)
    rows = conn.execute(
        f"""
        SELECT fixture_id, snapshot, bookmaker_id, outcome, normalized_prob, fetched_at
        FROM odds_snapshots
        WHERE fixture_id IN ({marks}) AND market_id = 1 AND normalized_prob IS NOT NULL
        """,
        list(fixture_ids),
    ).fetchall()

    by_fixture = {}
    for r in rows:
        by_fixture.setdefault(r["fixture_id"], []).append(r)

    def median(values: list) -> float:
        values = sorted(values)
        n = len(values)
        mid = n // 2
        return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2

    out = {}
    for fid, frows in by_fixture.items():
        latest_snapshot = max(frows, key=lambda r: r["fetched_at"])["snapshot"]
        snap_rows = [r for r in frows if r["snapshot"] == latest_snapshot]
        per_outcome = {}
        bookmakers = set()
        for r in snap_rows:
            per_outcome.setdefault(r["outcome"].lower(), []).append(r["normalized_prob"])
            bookmakers.add(r["bookmaker_id"])
        if not all(k in per_outcome for k in ("home", "draw", "away")):
            continue
        out[fid] = {
            "home": median(per_outcome["home"]),
            "draw": median(per_outcome["draw"]),
            "away": median(per_outcome["away"]),
            "snapshot": latest_snapshot,
            "bookmakers": len(bookmakers),
        }
    return out


def get_squad_values_by_league(conn: sqlite3.Connection, league_ids: list, seasons: list = None) -> list:
    """(fixture_id, team_id, value_eur) for every fixture in the leagues --
    played or upcoming -- so the SquadValueStore serves both training and
    prediction from the same table."""
    query = (
        "SELECT sv.fixture_id, sv.team_id, sv.value_eur FROM squad_values sv"
        " JOIN fixtures f ON f.fixture_id = sv.fixture_id WHERE f.league_id IN ({})".format(", ".join("?" for _ in league_ids))
    )
    params = list(league_ids)
    if seasons:
        query += " AND f.season IN ({})".format(", ".join("?" for _ in seasons))
        params.extend(seasons)
    return conn.execute(query, params).fetchall()
