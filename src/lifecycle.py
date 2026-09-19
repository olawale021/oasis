"""Prediction lifecycle: lock at kickoff, settle after full time (PRD 13.4/13.5).

lock    Freeze the current prediction for every fixture kicking off within
        --window-minutes (default 30). A fixture locks AT MOST ONCE -- later
        runs never overwrite an existing lock, so run the matchday chain
        repeatedly and each fixture freezes at its last pre-kickoff state:

            python3 src/predict.py && python3 src/lifecycle.py lock

settle  Attach final results to locked, unsettled fixtures and score them
        (log loss, Brier, correct-pick). Run after refreshing results:

            python3 src/ingest_fixtures.py --seasons 2026 --force-refresh
            python3 src/lifecycle.py settle

status  Show locked/settled counts and the live record so far.

Matchday cron (hourly covers the 24h/6h/1h odds windows + locking + results):

    0 * * * * cd <repo> && .venv/bin/python src/ingest_odds.py && \
      .venv/bin/python src/ingest_fixtures.py --seasons 2026 --force-refresh && \
      .venv/bin/python src/predict.py && .venv/bin/python src/lifecycle.py lock && \
      .venv/bin/python src/lifecycle.py settle && .venv/bin/python src/export_web.py
"""

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import db

OUTPUTS_DIR = config.ROOT_DIR / "outputs"
DECIDED_STATUSES = ("FT", "AET", "PEN")

LOCK_COLUMNS = [
    "fixture_id", "league_code", "season", "kickoff_utc", "locked_at", "stage",
    "home", "away", "p_home", "p_draw", "p_away", "likely_score", "mu_home",
    "mu_away", "over_2_5", "btts", "confidence", "why", "market_p_home",
    "market_p_draw", "market_p_away", "market_snapshot", "market_bookmakers",
    "model_version", "model_checksum", "goals_version", "goals_checksum",
    "features_json",
]


def lock(conn, window_minutes: int, dry_run: bool = False, stage: str = "initial", source: str = "predictions.json") -> list:
    """Freeze predictions from `source` for fixtures kicking off within the
    window, one row per (fixture, stage). stage='initial' is the hourly
    pre-lineup lock; stage='final' comes from final_stage.py once both
    confirmed lineups are in (source predictions_final.json)."""
    payload = json.loads((OUTPUTS_DIR / source).read_text())
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=window_minutes)
    locked = []
    for p in payload["predictions"]:
        kickoff = datetime.fromisoformat(p["kickoff_utc"])
        if not (now <= kickoff <= horizon):
            continue
        already = conn.execute(
            "SELECT 1 FROM locked_predictions WHERE fixture_id = ? AND stage = ?", (p["fixture_id"], stage)
        ).fetchone()
        if already:
            continue
        registry = payload["model_registry"][p["league"]]
        row = {
            "fixture_id": p["fixture_id"],
            "league_code": p["league"],
            "season": p["season"],
            "kickoff_utc": p["kickoff_utc"],
            "locked_at": now.isoformat(),
            "stage": stage,
            "home": p["home"],
            "away": p["away"],
            "p_home": p["p_home"],
            "p_draw": p["p_draw"],
            "p_away": p["p_away"],
            "likely_score": p["likely_score"],
            "mu_home": p["expected_goals"]["home"],
            "mu_away": p["expected_goals"]["away"],
            "over_2_5": p["over_2_5"],
            "btts": p["btts"],
            "confidence": p["confidence"],
            "why": p["why"],
            "market_p_home": p.get("market_p_home"),
            "market_p_draw": p.get("market_p_draw"),
            "market_p_away": p.get("market_p_away"),
            "market_snapshot": p.get("market_snapshot"),
            "market_bookmakers": p.get("market_bookmakers"),
            "model_version": registry["outcome"]["version"],
            "model_checksum": registry["outcome"]["checksum_sha256"],
            "goals_version": registry["goals"]["version"],
            "goals_checksum": registry["goals"]["checksum_sha256"],
            "features_json": json.dumps(p["features"]),
        }
        if not dry_run:
            placeholders = ", ".join(f":{c}" for c in LOCK_COLUMNS)
            conn.execute(
                f"INSERT OR IGNORE INTO locked_predictions ({', '.join(LOCK_COLUMNS)}) VALUES ({placeholders})",
                row,
            )
        locked.append(row)
    if not dry_run:
        conn.commit()
    return locked


def settle(conn) -> list:
    rows = conn.execute(
        """
        SELECT lp.fixture_id, lp.stage, lp.p_home, lp.p_draw, lp.p_away, lp.home, lp.away,
               f.home_goals, f.away_goals, f.status_short
        FROM locked_predictions lp
        JOIN fixtures f ON f.fixture_id = lp.fixture_id
        WHERE lp.settled_at IS NULL AND f.status_short IN (?, ?, ?)
          AND f.home_goals IS NOT NULL AND f.away_goals IS NOT NULL
        """,
        DECIDED_STATUSES,
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    settled = []
    for r in rows:
        hg, ag = r["home_goals"], r["away_goals"]
        m = score_row(r["p_home"], r["p_draw"], r["p_away"], hg, ag)
        # One row per (fixture, stage): each stage is scored on ITS OWN
        # probabilities. Updating by fixture_id alone stamped the initial
        # lock's verdict onto the final-stage row too (bug, fixed 2026-09-19).
        conn.execute(
            """
            UPDATE locked_predictions
            SET result_home = ?, result_away = ?, outcome = ?, log_loss = ?,
                brier = ?, correct = ?, settled_at = ?
            WHERE fixture_id = ? AND stage = ? AND settled_at IS NULL
            """,
            (hg, ag, m["outcome"], m["log_loss"], m["brier"], m["correct"], now, r["fixture_id"], r["stage"]),
        )
        settled.append({"fixture": f"{r['home']} v {r['away']}", "stage": r["stage"], "result": f"{hg}-{ag}", "log_loss": m["log_loss"], "correct": bool(m["correct"])})
    conn.commit()
    return settled


def score_row(p_home: float, p_draw: float, p_away: float, hg: int, ag: int) -> dict:
    outcome = 0 if hg > ag else (2 if hg < ag else 1)
    probs = [p_home / 100.0, p_draw / 100.0, p_away / 100.0]
    log_loss = -math.log(max(probs[outcome], 1e-15))
    brier = sum((probs[i] - (1.0 if i == outcome else 0.0)) ** 2 for i in range(3))
    correct = int(max(range(3), key=lambda i: probs[i]) == outcome)
    return {"outcome": outcome, "log_loss": round(log_loss, 4), "brier": round(brier, 4), "correct": correct}


def resettle(conn) -> dict:
    """Recompute every settled row's metrics from its own probabilities and
    recorded result (idempotent). Repairs rows settled before the per-stage
    fix, where a final-stage row carried the initial lock's numbers."""
    rows = conn.execute(
        "SELECT fixture_id, stage, p_home, p_draw, p_away, result_home, result_away, log_loss, brier, correct"
        " FROM locked_predictions WHERE settled_at IS NOT NULL AND result_home IS NOT NULL"
    ).fetchall()
    fixed = 0
    for r in rows:
        m = score_row(r["p_home"], r["p_draw"], r["p_away"], r["result_home"], r["result_away"])
        if (m["log_loss"], m["brier"], m["correct"]) != (r["log_loss"], r["brier"], r["correct"]):
            conn.execute(
                "UPDATE locked_predictions SET outcome = ?, log_loss = ?, brier = ?, correct = ? WHERE fixture_id = ? AND stage = ?",
                (m["outcome"], m["log_loss"], m["brier"], m["correct"], r["fixture_id"], r["stage"]),
            )
            fixed += 1
    conn.commit()
    return {"checked": len(rows), "repaired": fixed}


def status(conn) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM locked_effective").fetchone()[0]
    settled = conn.execute("SELECT COUNT(*) FROM locked_effective WHERE settled_at IS NOT NULL").fetchone()[0]
    by_stage = {r[0]: r[1] for r in conn.execute("SELECT stage, COUNT(*) FROM locked_predictions GROUP BY stage")}
    live = conn.execute(
        "SELECT COUNT(*) AS n, AVG(log_loss) AS ll, AVG(brier) AS brier, AVG(correct) AS acc"
        " FROM locked_effective WHERE settled_at IS NOT NULL"
    ).fetchone()
    return {
        "locked": total,
        "by_stage": by_stage,
        "awaiting_result": total - settled,
        "settled": settled,
        "live_log_loss": round(live["ll"], 4) if live["ll"] is not None else None,
        "live_brier": round(live["brier"], 4) if live["brier"] is not None else None,
        "live_accuracy": round(live["acc"], 4) if live["acc"] is not None else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lock and settle predictions (PRD 13.4/13.5).")
    sub = parser.add_subparsers(dest="command", required=True)
    p_lock = sub.add_parser("lock", help="Freeze predictions for fixtures kicking off soon")
    p_lock.add_argument("--window-minutes", type=int, default=30)
    p_lock.add_argument("--stage", type=str, default="initial", choices=["initial", "final"])
    p_lock.add_argument("--source", type=str, default="predictions.json", help="file under outputs/ to lock from")
    p_lock.add_argument("--dry-run", action="store_true")
    p_lock.add_argument("--db-path", type=Path, default=None)
    p_settle = sub.add_parser("settle", help="Attach results to locked fixtures and score them")
    p_settle.add_argument("--db-path", type=Path, default=None)
    p_status = sub.add_parser("status", help="Locked/settled counts and live record")
    p_status.add_argument("--db-path", type=Path, default=None)
    p_resettle = sub.add_parser("resettle", help="Recompute settled metrics per (fixture, stage) from each row's own probabilities")
    p_resettle.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    conn = db.get_connection(args.db_path)
    db.init_db(conn)

    if args.command == "lock":
        rows = lock(conn, args.window_minutes, dry_run=args.dry_run, stage=args.stage, source=args.source)
        tag = " (dry run)" if args.dry_run else ""
        for r in rows:
            print(
                f"locked{tag}: {r['home']} v {r['away']} [{r['league_code']}] "
                f"{r['p_home']:.1f}/{r['p_draw']:.1f}/{r['p_away']:.1f} "
                f"model {r['model_version']} stage {r['stage']}"
            )
        print(f"{len(rows)} fixture(s) locked{tag}")
    elif args.command == "settle":
        rows = settle(conn)
        for r in rows:
            mark = "✓" if r["correct"] else "✗"
            print(f"settled: {r['fixture']} {r['result']} {mark} log_loss={r['log_loss']}")
        print(f"{len(rows)} fixture(s) settled")
    elif args.command == "resettle":
        print(json.dumps(resettle(conn)))
    elif args.command == "status":
        print(json.dumps(status(conn), indent=2))

    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATUS_DIR / "lifecycle_status.json").write_text(
        json.dumps({"refreshed_at": datetime.now(timezone.utc).isoformat(), **status(conn)}, indent=2)
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[lifecycle] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
