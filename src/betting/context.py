"""Head-to-head and recent-form context per fixture (Betting PRD 7, 8).

Explanation signals only: they never enter a prediction model (PRD 7.2)
unless walk-forward testing earns them a place. Everything is computed from
matches decided strictly before the target fixture's kickoff, in any
competition, so a row is reproducible and contains no future information.
Rows are upserted every run until kickoff: a cup match settled since the
last run changes "last 10", and the row should follow it."""

from datetime import datetime, timedelta, timezone

import leagues

DECIDED = ("FT", "AET", "PEN")
H2H_MATCHES = 5
TREND_MATCHES = 10


def _rate(count: int, n: int):
    return round(count / n, 4) if n else None


def target_fixtures(conn, horizon_days: int) -> list:
    """Fixtures worth context rows: upcoming in the target leagues within the
    horizon, plus anything locked (so a fixture graded at lock always has
    its context frozen alongside). Returns (fixture_id, kickoff_utc, home, away)."""
    now = datetime.now(timezone.utc)
    league_ids = [v["league_id"] for v in leagues.TARGETS.values()]
    marks = ", ".join("?" for _ in league_ids)
    return conn.execute(
        f"""
        SELECT fixture_id, kickoff_utc, home_team_id, away_team_id FROM fixtures
        WHERE (league_id IN ({marks}) AND status_short = 'NS' AND kickoff_utc BETWEEN ? AND ?)
           OR fixture_id IN (SELECT fixture_id FROM locked_predictions)
        """,
        [*league_ids, now.isoformat(), (now + timedelta(days=horizon_days)).isoformat()],
    ).fetchall()


def _decided_before(conn, team_id: int, before_utc: str, limit: int, opponent_id: int = None) -> list:
    """The team's most recent decided matches before `before_utc`, newest
    first. Two indexed queries merged in Python rather than one OR, which
    SQLite cannot serve from the (team, kickoff) indexes."""
    opp = "AND away_team_id = ?" if opponent_id else ""
    opp_h = "AND home_team_id = ?" if opponent_id else ""
    marks = ", ".join("?" for _ in DECIDED)
    params_home = [team_id, before_utc, *DECIDED] + ([opponent_id] if opponent_id else [])
    params_away = [team_id, before_utc, *DECIDED] + ([opponent_id] if opponent_id else [])
    home = conn.execute(
        f"SELECT * FROM fixtures WHERE home_team_id = ? AND kickoff_utc < ? AND status_short IN ({marks}) {opp}"
        f" AND home_goals IS NOT NULL ORDER BY kickoff_utc DESC LIMIT ?",
        [*params_home, limit],
    ).fetchall()
    away = conn.execute(
        f"SELECT * FROM fixtures WHERE away_team_id = ? AND kickoff_utc < ? AND status_short IN ({marks}) {opp_h}"
        f" AND home_goals IS NOT NULL ORDER BY kickoff_utc DESC LIMIT ?",
        [*params_away, limit],
    ).fetchall()
    return sorted(home + away, key=lambda r: r["kickoff_utc"], reverse=True)[:limit]


def h2h_row(conn, fixture_id: int, kickoff_utc: str, home_id: int, away_id: int, now_iso: str) -> dict:
    meetings = _decided_before(conn, home_id, kickoff_utc, H2H_MATCHES, opponent_id=away_id)
    hw = d = aw = hg = ag = btts = over = 0
    for m in meetings:
        # Goals from the perspective of THIS fixture's home team.
        mine, theirs = (m["home_goals"], m["away_goals"]) if m["home_team_id"] == home_id else (m["away_goals"], m["home_goals"])
        hg += mine
        ag += theirs
        if mine > theirs:
            hw += 1
        elif mine < theirs:
            aw += 1
        else:
            d += 1
        btts += int(mine > 0 and theirs > 0)
        over += int(mine + theirs > 2.5)
    n = len(meetings)
    return {
        "fixture_id": fixture_id, "matches_considered": n,
        "home_wins": hw, "draws": d, "away_wins": aw,
        "home_goals": hg, "away_goals": ag,
        "btts_count": btts, "btts_rate": _rate(btts, n),
        "over_2_5_count": over, "over_2_5_rate": _rate(over, n),
        "average_goals": round((hg + ag) / n, 2) if n else None,
        "last_meeting_utc": meetings[0]["kickoff_utc"] if meetings else None,
        "computed_at": now_iso,
    }


def trend_row(conn, fixture_id: int, kickoff_utc: str, team_id: int, now_iso: str) -> dict:
    matches = _decided_before(conn, team_id, kickoff_utc, TREND_MATCHES)
    gf = ga = btts = over = 0
    for m in matches:
        mine, theirs = (m["home_goals"], m["away_goals"]) if m["home_team_id"] == team_id else (m["away_goals"], m["home_goals"])
        gf += mine
        ga += theirs
        btts += int(mine > 0 and theirs > 0)
        over += int(mine + theirs > 2.5)
    n = len(matches)
    return {
        "fixture_id": fixture_id, "team_id": team_id, "matches_considered": n,
        "btts_count": btts, "btts_rate": _rate(btts, n),
        "over_2_5_count": over, "over_2_5_rate": _rate(over, n),
        "goals_for": gf, "goals_against": ga, "computed_at": now_iso,
    }


def build_context(conn, now_iso: str, horizon_days: int = 8) -> dict:
    targets = target_fixtures(conn, horizon_days)
    for f in targets:
        h = h2h_row(conn, f["fixture_id"], f["kickoff_utc"], f["home_team_id"], f["away_team_id"], now_iso)
        conn.execute(
            f"INSERT OR REPLACE INTO h2h_summary ({', '.join(h)}) VALUES ({', '.join(':' + k for k in h)})", h
        )
        for team_id in (f["home_team_id"], f["away_team_id"]):
            t = trend_row(conn, f["fixture_id"], f["kickoff_utc"], team_id, now_iso)
            conn.execute(
                f"INSERT OR REPLACE INTO team_market_trends ({', '.join(t)}) VALUES ({', '.join(':' + k for k in t)})", t
            )
    conn.commit()
    return {"context_fixtures": len(targets)}
