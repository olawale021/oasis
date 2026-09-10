-- Reference table: one upserted row per league ID, latest known truth.
CREATE TABLE IF NOT EXISTS leagues (
    league_id        INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    country          TEXT,
    role             TEXT NOT NULL CHECK (role IN ('target', 'feeder', 'unknown')),
    expected_name    TEXT,
    last_verified_at TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

-- Append-only audit log: one row per run per league-season. NULL in a
-- coverage_* column means "missing/unparseable" (unknown), distinct from 0
-- ("confirmed unavailable") — downstream consumers must treat NULL as
-- unknown and degrade to unavailable, per PRD §7.3.
CREATE TABLE IF NOT EXISTS coverage_audit (
    id                                     INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id                              INTEGER NOT NULL,
    season                                 INTEGER NOT NULL,
    checked_at                             TEXT NOT NULL,
    api_league_name                        TEXT,
    expected_league_name                   TEXT,
    name_mismatch                          INTEGER NOT NULL DEFAULT 0,
    season_found                           INTEGER NOT NULL DEFAULT 0,
    coverage_fixtures_events               INTEGER,
    coverage_fixtures_lineups              INTEGER,
    coverage_fixtures_statistics_fixtures  INTEGER,
    coverage_fixtures_statistics_players   INTEGER,
    coverage_standings                     INTEGER,
    coverage_players                       INTEGER,
    coverage_top_scorers                   INTEGER,
    coverage_top_assists                   INTEGER,
    coverage_top_cards                     INTEGER,
    coverage_injuries                      INTEGER,
    coverage_predictions                   INTEGER,
    coverage_odds                          INTEGER,
    coverage_raw_json                      TEXT NOT NULL DEFAULT 'null',
    warnings_json                          TEXT NOT NULL DEFAULT '[]',
    raw_response_path                      TEXT
);

CREATE INDEX IF NOT EXISTS idx_coverage_audit_league_season
    ON coverage_audit (league_id, season, checked_at DESC);

CREATE TABLE IF NOT EXISTS teams (
    team_id       INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    country       TEXT,
    founded       INTEGER,
    logo_url      TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

-- status_short in ('FT','AET','PEN') = played; others (NS, PST, CANC, ...) are stored
-- with NULL goals -- the schedule itself is useful later, but only played matches count
-- as results for modeling.
CREATE TABLE IF NOT EXISTS fixtures (
    fixture_id     INTEGER PRIMARY KEY,
    league_id      INTEGER NOT NULL,
    season         INTEGER NOT NULL,
    round          TEXT,
    kickoff_utc    TEXT NOT NULL,
    status_short   TEXT NOT NULL,
    status_long    TEXT,
    home_team_id   INTEGER NOT NULL REFERENCES teams(team_id),
    away_team_id   INTEGER NOT NULL REFERENCES teams(team_id),
    home_goals     INTEGER,
    away_goals     INTEGER,
    home_goals_ht  INTEGER,
    away_goals_ht  INTEGER,
    venue_name     TEXT,
    venue_city     TEXT,
    referee        TEXT,
    updated_at     TEXT NOT NULL,
    raw_json       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fixtures_league_season ON fixtures (league_id, season);
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures (kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_fixtures_home_away ON fixtures (home_team_id, away_team_id);

-- expected_goals/goals_prevented are NULLABLE by construction: the API's
-- statistics list omits those two entries entirely for older seasons
-- (confirmed absent 2017/18, present 2024/25) -- not merely null.
CREATE TABLE IF NOT EXISTS fixture_statistics (
    fixture_id          INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    shots_on_goal       INTEGER,
    shots_off_goal      INTEGER,
    total_shots         INTEGER,
    blocked_shots       INTEGER,
    shots_insidebox     INTEGER,
    shots_outsidebox    INTEGER,
    fouls               INTEGER,
    corner_kicks        INTEGER,
    offsides            INTEGER,
    ball_possession_pct REAL,
    yellow_cards        INTEGER,
    red_cards           INTEGER,
    goalkeeper_saves    INTEGER,
    total_passes        INTEGER,
    passes_accurate     INTEGER,
    passes_pct          REAL,
    expected_goals      REAL,
    goals_prevented     REAL,
    fetched_at          TEXT NOT NULL,
    raw_json            TEXT NOT NULL,
    PRIMARY KEY (fixture_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_fixture_statistics_team ON fixture_statistics (team_id);

-- Each row already IS the pre-match state for that exact fixture (injury
-- news arrives before kickoff) -- no point-in-time reconstruction needed.
CREATE TABLE IF NOT EXISTS injuries (
    fixture_id  INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    player_id   INTEGER NOT NULL,
    player_name TEXT,
    status_type TEXT NOT NULL,
    reason      TEXT,
    league_id   INTEGER NOT NULL,
    season      INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL,
    raw_json    TEXT NOT NULL,
    PRIMARY KEY (fixture_id, team_id, player_id)
);

CREATE TABLE IF NOT EXISTS lineups (
    fixture_id INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    team_id    INTEGER NOT NULL REFERENCES teams(team_id),
    formation  TEXT,
    coach_id   INTEGER,
    coach_name TEXT,
    fetched_at TEXT NOT NULL,
    raw_json   TEXT NOT NULL,
    PRIMARY KEY (fixture_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_lineups_team ON lineups (team_id);

CREATE TABLE IF NOT EXISTS lineup_players (
    fixture_id   INTEGER NOT NULL,
    team_id      INTEGER NOT NULL,
    player_id    INTEGER NOT NULL,
    player_name  TEXT,
    shirt_number INTEGER,
    position     TEXT,
    grid         TEXT,
    is_starter   INTEGER NOT NULL CHECK (is_starter IN (0, 1)),
    PRIMARY KEY (fixture_id, team_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_lineup_players_team_starter ON lineup_players (team_id, is_starter);

-- PRD 11: odds archive. Append-only -- a snapshot, once taken, is never
-- updated (INSERT OR IGNORE), satisfying the 18.4 auditability requirement.
-- One row per (fixture, snapshot window, bookmaker, market, outcome).
-- normalized_prob has the bookmaker margin removed within its outcome group
-- (a 1X2 triple, or one over/under line pair).
CREATE TABLE IF NOT EXISTS odds_snapshots (
    fixture_id       INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    snapshot         TEXT NOT NULL CHECK (snapshot IN ('7d', '24h', '6h', '1h', 'lineup', 'closing')),
    bookmaker_id     INTEGER NOT NULL,
    bookmaker        TEXT,
    market_id        INTEGER NOT NULL,
    market           TEXT,
    outcome          TEXT NOT NULL,
    odds_decimal     REAL NOT NULL,
    implied_prob     REAL NOT NULL,
    normalized_prob  REAL,
    hours_to_kickoff REAL NOT NULL,
    fetched_at       TEXT NOT NULL,
    PRIMARY KEY (fixture_id, snapshot, bookmaker_id, market_id, outcome)
);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_fixture ON odds_snapshots (fixture_id, snapshot);

-- PRD 13.4/13.5: the immutable prediction record. One row per fixture,
-- written at lock time (shortly before kickoff) and NEVER updated except by
-- settlement, which fills the result/scoring columns exactly once. The
-- probabilities, features, market snapshot, and model identity are frozen
-- as they stood at lock time -- this is the public track record.
CREATE TABLE IF NOT EXISTS locked_predictions (
    fixture_id        INTEGER PRIMARY KEY REFERENCES fixtures(fixture_id),
    league_code       TEXT NOT NULL,
    season            INTEGER NOT NULL,
    kickoff_utc       TEXT NOT NULL,
    locked_at         TEXT NOT NULL,
    stage             TEXT NOT NULL,            -- initial | injury_update | final
    home              TEXT NOT NULL,
    away              TEXT NOT NULL,
    p_home            REAL NOT NULL,
    p_draw            REAL NOT NULL,
    p_away            REAL NOT NULL,
    likely_score      TEXT,
    mu_home           REAL,
    mu_away           REAL,
    over_2_5          REAL,
    btts              REAL,
    confidence        TEXT,
    why               TEXT,
    market_p_home     REAL,
    market_p_draw     REAL,
    market_p_away     REAL,
    market_snapshot   TEXT,
    market_bookmakers INTEGER,
    model_version     TEXT NOT NULL,
    model_checksum    TEXT NOT NULL,
    goals_version     TEXT,
    goals_checksum    TEXT,
    features_json     TEXT NOT NULL,
    -- settlement (filled once, when the result is known)
    result_home       INTEGER,
    result_away       INTEGER,
    outcome           INTEGER,                  -- 0 home, 1 draw, 2 away
    log_loss          REAL,
    brier             REAL,
    correct           INTEGER,
    settled_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_locked_predictions_settled ON locked_predictions (settled_at);

-- Transfermarkt squad value as of each fixture's kickoff (ingest_squad_values.py).
-- Point-in-time: sum of the top-N latest player valuations dated on or before
-- kickoff for players whose latest valuation places them at the club.
CREATE TABLE IF NOT EXISTS squad_values (
    fixture_id   INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    team_id      INTEGER NOT NULL REFERENCES teams(team_id),
    value_eur    REAL NOT NULL,
    n_players    INTEGER NOT NULL,
    as_of        TEXT NOT NULL,
    computed_at  TEXT NOT NULL,
    PRIMARY KEY (fixture_id, team_id)
);

-- API-Football team_id -> Transfermarkt club_id (auto-matched by name, with
-- explicit overrides in ingest_squad_values.py).
CREATE TABLE IF NOT EXISTS tm_club_map (
    team_id      INTEGER PRIMARY KEY REFERENCES teams(team_id),
    tm_club_id   INTEGER NOT NULL,
    tm_name      TEXT NOT NULL,
    method       TEXT NOT NULL,
    mapped_at    TEXT NOT NULL
);
