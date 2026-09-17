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
    fixture_id        INTEGER NOT NULL REFERENCES fixtures(fixture_id),
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
,
    PRIMARY KEY (fixture_id, stage)
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

-- One row per fixture: the final-stage lock (confirmed lineups, ~25 min
-- before kickoff) when it exists, else the initial lock. Every live metric
-- and ledger reads this view; the raw table keeps both stages for comparison.
CREATE VIEW IF NOT EXISTS locked_effective AS
SELECT lp.* FROM locked_predictions lp
WHERE lp.stage = CASE
    WHEN EXISTS (SELECT 1 FROM locked_predictions x WHERE x.fixture_id = lp.fixture_id AND x.stage = 'final') THEN 'final'
    ELSE 'initial' END;

-- ---------------------------------------------------------------------------
-- Betting layer (Betting PRD 22). Derived from odds_snapshots and
-- locked_predictions; never an input to the prediction models.
-- ---------------------------------------------------------------------------

-- Per (fixture, market, selection, snapshot window): the bookmaker
-- consensus. A pure function of odds_snapshots, so it is rebuilt
-- idempotently and never updated once written (windows are append-only).
CREATE TABLE IF NOT EXISTS market_consensus (
    fixture_id       INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    market           TEXT NOT NULL,            -- 1X2 | OU25 | BTTS
    selection        TEXT NOT NULL,            -- home|draw|away, over|under, yes|no
    snapshot         TEXT NOT NULL,            -- odds_snapshots.snapshot window
    consensus_prob   REAL NOT NULL,            -- median margin-removed prob, [0,1]
    median_odds      REAL NOT NULL,
    best_odds        REAL NOT NULL,
    best_bookmaker   TEXT,
    bookmaker_count  INTEGER NOT NULL,         -- distinct bookmakers quoting the market
    fetched_at       TEXT NOT NULL,            -- newest odds row used: the point-in-time stamp
    created_at       TEXT NOT NULL,
    PRIMARY KEY (fixture_id, market, selection, snapshot)
);

-- One row per (prediction, stage, market, selection), PASS rows included:
-- the backtest needs to know what happened to the bets we did NOT
-- recommend (PRD 18/19). Probabilities in [0,1]; edge = model - market in
-- the same units (multiply by 100 for percentage points).
--
-- Stages: `initial` and `final` mirror locked_predictions (graded at lock,
-- ~60 and ~25 min before kickoff). `h24` is the horizon track (PRD 18):
-- graded on the first run that sees the fixture inside the 24h odds
-- window, from that run's prediction and that window's consensus, so its
-- CLV is honestly "the price we graded at vs the close".
CREATE TABLE IF NOT EXISTS betting_recommendations (
    recommendation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id         INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    stage              TEXT NOT NULL,          -- locked_predictions.stage graded from
    league_code        TEXT NOT NULL,
    kickoff_utc        TEXT NOT NULL,
    locked_at          TEXT NOT NULL,          -- as-of instant for the market lookup
    hours_to_kickoff   REAL,                   -- at locked_at; horizon rows span a window, so keep the exact distance
    market             TEXT NOT NULL,
    selection          TEXT NOT NULL,
    model_version      TEXT NOT NULL,
    goals_version      TEXT,
    model_prob         REAL NOT NULL,
    market_prob        REAL,                   -- NULL: no odds archived before lock
    market_snapshot    TEXT,
    bookmaker_count    INTEGER,
    edge               REAL,
    best_odds          REAL,
    expected_value     REAL,                   -- model_prob * best_odds - 1
    confidence         TEXT,
    level              TEXT NOT NULL,          -- PASS | WATCH | VALUE | STRONG_VALUE
    reasons_json       TEXT NOT NULL,          -- structured; the card explains from this
    thresholds_version TEXT NOT NULL,          -- rulebook that graded it (re-gradeable)
    generated_at       TEXT NOT NULL,
    UNIQUE (fixture_id, stage, market, selection)
);

CREATE TABLE IF NOT EXISTS betting_results (
    recommendation_id  INTEGER PRIMARY KEY REFERENCES betting_recommendations(recommendation_id),
    result_home        INTEGER NOT NULL,
    result_away        INTEGER NOT NULL,
    won                INTEGER NOT NULL,
    profit_1u          REAL,                   -- at best_odds; NULL without odds
    closing_odds       REAL,                   -- consensus median odds, closing window
    closing_prob       REAL,
    -- Two closing-line values. `clv` is the graded window vs close; locks
    -- land ~25 min before kickoff, after the closing fetch, so it is ~0 by
    -- construction and kept only for completeness. `clv_24h` is the 24h
    -- consensus vs close: whether the market moved toward the model's view
    -- over the last day, which is the informative one (PRD 18 horizon).
    clv                REAL,
    clv_24h            REAL,
    clv_version        TEXT,                   -- edge.CLV_VERSION that produced clv/clv_24h
    settled_at         TEXT NOT NULL
);

-- Mirror of locked_effective for the betting ledger: the final-stage grade
-- when one exists, else the initial. Performance reporting reads this.
CREATE VIEW IF NOT EXISTS betting_effective AS
SELECT br.* FROM betting_recommendations br
WHERE br.stage = CASE
    WHEN EXISTS (SELECT 1 FROM betting_recommendations x WHERE x.fixture_id = br.fixture_id AND x.stage = 'final') THEN 'final'
    ELSE 'initial' END;

-- Fixture context (Betting PRD 7, 8): explanation signals, not model
-- features. Both are computed strictly from matches decided before the
-- fixture's kickoff, so they contain no future information (PRD 28), and
-- are re-computed on each run until kickoff so late-decided cup matches
-- are picked up. Rates are NULL, not 0, when nothing was considered.
CREATE TABLE IF NOT EXISTS h2h_summary (
    fixture_id         INTEGER PRIMARY KEY REFERENCES fixtures(fixture_id),
    matches_considered INTEGER NOT NULL,       -- last 5 decided meetings, any venue, any competition
    home_wins          INTEGER NOT NULL,       -- from the perspective of this fixture's home team
    draws              INTEGER NOT NULL,
    away_wins          INTEGER NOT NULL,
    home_goals         INTEGER NOT NULL,
    away_goals         INTEGER NOT NULL,
    btts_count         INTEGER NOT NULL,
    btts_rate          REAL,
    over_2_5_count     INTEGER NOT NULL,
    over_2_5_rate      REAL,
    average_goals      REAL,
    last_meeting_utc   TEXT,
    computed_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_market_trends (
    fixture_id         INTEGER NOT NULL REFERENCES fixtures(fixture_id),
    team_id            INTEGER NOT NULL REFERENCES teams(team_id),
    matches_considered INTEGER NOT NULL,       -- last 10 decided matches, any competition
    btts_count         INTEGER NOT NULL,
    btts_rate          REAL,
    over_2_5_count     INTEGER NOT NULL,
    over_2_5_rate      REAL,
    goals_for          INTEGER NOT NULL,
    goals_against      INTEGER NOT NULL,
    computed_at        TEXT NOT NULL,
    PRIMARY KEY (fixture_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_fixtures_home_kickoff ON fixtures (home_team_id, kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_fixtures_away_kickoff ON fixtures (away_team_id, kickoff_utc);
