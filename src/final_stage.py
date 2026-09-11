"""Final-stage prediction (PRD 13.2): confirmed lineups -> second lock.

Runs every ten minutes on matchdays (scripts/final_pass.sh). For each
fixture that already has an initial lock, kicks off within WINDOW minutes
and has no final lock yet, fetch the lineups from API-Football (published
by the clubs ~60-75 min before kickoff, relayed by the API ~20-40 min
before). Once BOTH confirmed elevens are stored, regenerate the prediction
for those fixtures with the actual XI driving squad disruption and, where a
league has player ratings, expected-XI strength, then lock it as
stage='final'. The initial lock is kept; locked_effective prefers the
final row for every live metric.

Prints the number of fixtures locked at final stage (the shell wrapper
re-exports the web payload only when > 0). One lineup call per candidate
per pass, so quota use is a few calls per match.

    python3 src/final_stage.py [--window-minutes 35] [--dry-run]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import api_client
import config
import db
import ingest_lineups
import lifecycle
import predict

WINDOW_MINUTES = 35


def candidates(conn, window_minutes: int) -> list:
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        """
        SELECT f.fixture_id, f.kickoff_utc, f.home_team_id, f.away_team_id, lp.home, lp.away
        FROM locked_predictions lp JOIN fixtures f ON f.fixture_id = lp.fixture_id
        WHERE lp.stage = 'initial' AND f.status_short = 'NS'
          AND f.kickoff_utc > ? AND f.kickoff_utc <= ?
          AND NOT EXISTS (SELECT 1 FROM locked_predictions x WHERE x.fixture_id = lp.fixture_id AND x.stage = 'final')
        ORDER BY f.kickoff_utc
        """,
        (now.isoformat(), (now + timedelta(minutes=window_minutes)).isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def has_both_xis(conn, fixture_id: int, home_id: int, away_id: int) -> bool:
    counts = {r[0]: r[1] for r in conn.execute(
        "SELECT team_id, COUNT(*) FROM lineup_players WHERE fixture_id = ? AND is_starter = 1 GROUP BY team_id",
        (fixture_id,),
    )}
    return counts.get(home_id, 0) == 11 and counts.get(away_id, 0) == 11


def main() -> int:
    parser = argparse.ArgumentParser(description="Confirmed-lineup final-stage lock.")
    parser.add_argument("--window-minutes", type=int, default=WINDOW_MINUTES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    conn = db.get_connection()
    db.init_db(conn)
    cands = candidates(conn, args.window_minutes)
    if not cands:
        print(0)
        return 0
    client = api_client.APIFootballClient()
    ready = []
    for c in cands:
        if not has_both_xis(conn, c["fixture_id"], c["home_team_id"], c["away_team_id"]):
            # Always re-fetch: the cached page from an earlier pass may be
            # empty or partial until the API has both sheets.
            ingest_lineups.ingest_one_fixture(client, conn, c["fixture_id"], force_refresh=True)
            conn.commit()
        if has_both_xis(conn, c["fixture_id"], c["home_team_id"], c["away_team_id"]):
            ready.append(c)
        else:
            print(f"  waiting for lineups: {c['home']} v {c['away']} ({c['kickoff_utc'][11:16]})", file=sys.stderr)
    if not ready:
        print(0)
        return 0
    ids = {c["fixture_id"] for c in ready}
    payload = predict.run_predictions(horizon_days=2, quiet=True, fixture_ids=ids, stage="final", out_name="predictions_final.json")
    if not payload["predictions"]:
        print(0)
        return 0
    rows = lifecycle.lock(conn, window_minutes=args.window_minutes + 5, dry_run=args.dry_run, stage="final", source="predictions_final.json")
    for r in rows:
        print(f"  final lock: {r['home']} v {r['away']} {r['p_home']:.1f}/{r['p_draw']:.1f}/{r['p_away']:.1f}", file=sys.stderr)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATUS_DIR / "final_stage_status.json").write_text(json.dumps({
        "refreshed_at": datetime.now(timezone.utc).isoformat(), "candidates": len(cands), "ready": len(ready), "locked_final": len(rows)}, indent=2))
    print(len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
