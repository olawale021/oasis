import elo as elo_module

# Fixed defaults, explicitly flagged as calibratable later -- not grid-searched
# in Phase 1. A team promoted from Championship to PL is systematically
# under-rated by a Championship-only rating (it only ever moved relative to
# weaker opposition); a relegated team is symmetrically over-rated.
PROMOTED_ELO_BUMP = 50.0
RELEGATION_ELO_PENALTY = -50.0
# Below the INITIAL_ELO=1500 anchor -- a team with zero visible history in our
# ingested window (e.g. promoted from a division we don't ingest) is typically
# weaker than the tier-average team we DO have data on.
NEWCOMER_NO_HISTORY_ELO = 1400.0


def season_rosters(conn, league_id: int, seasons: list) -> dict:
    """season -> set(team_id) that played league_id that season, derived from
    fixtures (no standings endpoint needed)."""
    placeholders = ", ".join("?" for _ in seasons)
    rows = conn.execute(
        f"""
        SELECT DISTINCT season, home_team_id AS team_id FROM fixtures
        WHERE league_id = ? AND season IN ({placeholders})
        UNION
        SELECT DISTINCT season, away_team_id AS team_id FROM fixtures
        WHERE league_id = ? AND season IN ({placeholders})
        """,
        [league_id, *seasons, league_id, *seasons],
    ).fetchall()
    rosters = {season: set() for season in seasons}
    for row in rows:
        rosters[row["season"]].add(row["team_id"])
    return rosters


def compute_transitions(conn, target_league_id: int, feeder_league_id: int, seasons: list) -> dict:
    """Roster-diff target(season) vs target(season-1) [and feeder equivalently]
    to classify each team entering the target league as promoted/newcomer, and
    each team leaving it as relegated. Keyed by (team_id, season) where season
    is the season the team is ENTERING under its new/first division."""
    seasons = sorted(seasons)
    target_rosters = season_rosters(conn, target_league_id, seasons)
    feeder_rosters = season_rosters(conn, feeder_league_id, seasons)

    transitions = {}
    for i, season in enumerate(seasons):
        target_cur = target_rosters[season]
        feeder_prev = feeder_rosters[seasons[i - 1]] if i > 0 else set()
        target_prev = target_rosters[seasons[i - 1]] if i > 0 else set()
        feeder_cur = feeder_rosters[season]

        promoted = target_cur - target_prev
        for team_id in promoted:
            if team_id in feeder_prev:
                transitions[(team_id, season)] = {"kind": "promoted", "delta": PROMOTED_ELO_BUMP}
            else:
                transitions[(team_id, season)] = {"kind": "newcomer", "delta": None}

        relegated = target_prev - target_cur
        for team_id in relegated:
            if team_id in feeder_cur:
                transitions[(team_id, season)] = {"kind": "relegated", "delta": RELEGATION_ELO_PENALTY}

    return transitions


def apply_pending_transition(elo: "elo_module.EloRatings", team_id: int, season: int, transitions: dict, applied: set) -> None:
    """Called once per team per season, before elo.update(), inside the combined
    fit loop. Idempotent per (team_id, season) via the `applied` set."""
    key = (team_id, season)
    if key in applied:
        return
    applied.add(key)

    transition = transitions.get(key)
    if transition is None:
        return

    if transition["kind"] == "newcomer":
        elo.ratings[team_id] = NEWCOMER_NO_HISTORY_ELO
    else:
        elo.ratings[team_id] = elo.get(team_id) + transition["delta"]
