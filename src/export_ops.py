"""Export an operations snapshot to web/src/data/ops.json for the /admin page.

Runs at the end of every matchday chain (success or failure, via the EXIT
trap in scripts/matchday.sh) and is pushed to Cloudflare KV under the key
"ops". The admin page treats the snapshot's age as the server heartbeat:
the site cannot reach the droplet, so "the server stopped reporting" is
the only honest signal that cron, the box, or the network is down.

Contents: host stats, per-step status files, run history (runs.jsonl),
the locked-prediction ledger, the upcoming lock schedule (which cron run
will catch each fixture), odds/result freshness, and the log tail.
Stdlib-only.

    python3 src/export_ops.py [--run-ok|--run-failed STEP] [--duration S]
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import config
import db

OPS_PATH = config.ROOT_DIR / "web" / "src" / "data" / "ops.json"
RUNS_PATH = config.STATUS_DIR / "runs.jsonl"
LOG_PATH = config.STATUS_DIR / "matchday.log"
PREDICTIONS_PATH = config.ROOT_DIR / "outputs" / "predictions.json"

STEP_FILES = [
    ("ingest_odds", "Odds snapshots"),
    ("ingest_fixtures", "Fixtures & results"),
    ("ingest_team_fixtures", "All-competition fixtures"),
    ("ingest_squad_values", "Squad values (Transfermarkt)"),
    ("predict", "Predictions"),
    ("lifecycle", "Lock & settle"),
]
LOCK_WINDOW_MINUTES = 70  # must match scripts/matchday.sh --window-minutes
LEDGER_ROWS = 60
LOG_LINES = 80
RUN_HISTORY = 48
UPCOMING_HOURS = 72
DECIDED_STATUSES = ("FT", "AET", "PEN")
LIVE_LEAGUE_IDS = (39, 140, 135, 78, 253)  # matches scripts/matchday.sh --league-ids


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _cmd(*args: str) -> str | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except Exception:
        return None


def _read_json(path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def host_info() -> dict:
    info = {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "node": _cmd("node", "-v"),
        "git_commit": _cmd("git", "-C", str(config.ROOT_DIR), "rev-parse", "--short", "HEAD"),
        "uptime_s": None,
        "load_1m": None,
        "mem_total_mb": None,
        "mem_available_mb": None,
        "disk_total_gb": None,
        "disk_used_gb": None,
        "cron": None,
    }
    try:
        info["load_1m"] = round(os.getloadavg()[0], 2)
    except Exception:
        pass
    try:
        info["uptime_s"] = int(float(open("/proc/uptime").read().split()[0]))
    except Exception:
        pass
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k] = int(v.strip().split()[0])
        info["mem_total_mb"] = mem["MemTotal"] // 1024
        info["mem_available_mb"] = mem["MemAvailable"] // 1024
    except Exception:
        pass
    try:
        du = shutil.disk_usage(config.ROOT_DIR)
        info["disk_total_gb"] = round(du.total / 1e9, 1)
        info["disk_used_gb"] = round(du.used / 1e9, 1)
    except Exception:
        pass
    cron = _cmd("crontab", "-l")
    if cron:
        lines = [l for l in cron.splitlines() if "matchday" in l]
        info["cron"] = lines[0] if lines else None
    return info


def step_status() -> list:
    out = []
    for key, label in STEP_FILES:
        s = _read_json(config.STATUS_DIR / f"{key}_status.json") or {}
        out.append({
            "key": key,
            "label": label,
            "ok": bool(s.get("success", True)) if s else None,
            "refreshed_at": s.get("refreshed_at"),
            "duration_ms": s.get("duration_ms"),
            "counts": s.get("counts") or {k: v for k, v in s.items() if isinstance(v, (int, float)) and k != "duration_ms"},
            "error": s.get("error"),
        })
    return out


def run_history() -> list:
    if not RUNS_PATH.exists():
        return []
    rows = []
    for line in RUNS_PATH.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-RUN_HISTORY:]


def ledger(conn) -> tuple[list, dict]:
    rows = conn.execute(
        """
        SELECT fixture_id, league_code, kickoff_utc, locked_at, stage, home, away,
               p_home, p_draw, p_away, confidence, market_p_home, market_p_draw, market_p_away,
               result_home, result_away, outcome, log_loss, brier, correct, settled_at,
               model_version
        FROM locked_predictions ORDER BY kickoff_utc DESC LIMIT ?
        """,
        (LEDGER_ROWS,),
    ).fetchall()
    ledger_rows = [dict(r) for r in rows]
    total = conn.execute("SELECT COUNT(*) FROM locked_predictions").fetchone()[0]
    agg = conn.execute(
        "SELECT COUNT(*) n, AVG(log_loss) ll, AVG(brier) br, AVG(correct) acc"
        " FROM locked_predictions WHERE settled_at IS NOT NULL"
    ).fetchone()
    summary = {
        "locked": total,
        "settled": agg["n"],
        "awaiting_result": total - agg["n"],
        "log_loss": round(agg["ll"], 4) if agg["ll"] is not None else None,
        "brier": round(agg["br"], 4) if agg["br"] is not None else None,
        "accuracy": round(agg["acc"], 4) if agg["acc"] is not None else None,
    }
    return ledger_rows, summary


def upcoming_locks(conn, now: datetime) -> list:
    """Every predicted fixture kicking off in the next UPCOMING_HOURS (plus any
    already-kicked-off fixture from the last 6h), with the cron run expected
    to lock it: the first top-of-hour at or after kickoff - LOCK_WINDOW."""
    payload = _read_json(PREDICTIONS_PATH) or {"predictions": []}
    locked_ids = {r[0] for r in conn.execute("SELECT fixture_id FROM locked_predictions")}
    horizon = now + timedelta(hours=UPCOMING_HOURS)
    lookback = now - timedelta(hours=6)
    out = []
    for p in payload["predictions"]:
        ko = datetime.fromisoformat(p["kickoff_utc"])
        if not (lookback <= ko <= horizon):
            continue
        lock_by = ko - timedelta(minutes=LOCK_WINDOW_MINUTES)
        run_at = lock_by.replace(minute=0, second=0, microsecond=0)
        if run_at < lock_by:
            run_at += timedelta(hours=1)
        if p["fixture_id"] in locked_ids:
            state = "locked"
        elif ko < now:
            state = "missed"
        elif run_at < now:
            state = "due"  # the run that should have locked it has passed
        else:
            state = "pending"
        out.append({
            "fixture_id": p["fixture_id"],
            "league": p["league"],
            "home": p["home"],
            "away": p["away"],
            "kickoff_utc": p["kickoff_utc"],
            "lock_by": _iso(lock_by),
            "expected_run": _iso(run_at),
            "state": state,
            "confidence": p["confidence"],
        })
    out.sort(key=lambda r: r["kickoff_utc"])
    return out


def freshness(conn, now: datetime) -> dict:
    live_ids = ", ".join(str(i) for i in LIVE_LEAGUE_IDS)
    odds = conn.execute(
        "SELECT MAX(fetched_at) last, COUNT(DISTINCT fixture_id) fixtures, COUNT(*) rows_ FROM odds_snapshots"
        " WHERE fetched_at >= ?",
        ((now - timedelta(hours=24)).isoformat(),),
    ).fetchone()
    last_result = conn.execute(
        f"SELECT MAX(kickoff_utc) FROM fixtures WHERE league_id IN ({live_ids})"
        " AND status_short IN (?, ?, ?) AND home_goals IS NOT NULL",
        DECIDED_STATUSES,
    ).fetchone()[0]
    # Fixtures that kicked off >3h ago but still have no final status: results
    # the ingest has not caught up with (or postponed/abandoned games).
    stale_results = conn.execute(
        f"SELECT COUNT(*) FROM fixtures WHERE league_id IN ({live_ids})"
        " AND kickoff_utc < ? AND kickoff_utc > ?"
        " AND status_short NOT IN (?, ?, ?, 'PST', 'CANC', 'ABD', 'AWD', 'WO')",
        ((now - timedelta(hours=3)).isoformat(), (now - timedelta(days=7)).isoformat(), *DECIDED_STATUSES),
    ).fetchone()[0]
    fixtures_ahead = conn.execute(
        f"SELECT COUNT(*) FROM fixtures WHERE league_id IN ({live_ids}) AND kickoff_utc BETWEEN ? AND ?",
        (now.isoformat(), (now + timedelta(days=8)).isoformat()),
    ).fetchone()[0]
    live = _read_json(config.ROOT_DIR / "web" / "src" / "data" / "live.json") or {}
    return {
        "odds_last_fetched": odds["last"],
        "odds_fixtures_24h": odds["fixtures"],
        "odds_rows_24h": odds["rows_"],
        "last_result_kickoff": last_result,
        "results_pending": stale_results,
        "fixtures_next_8d": fixtures_ahead,
        "live_json_generated_at": live.get("generated_at"),
        "predictions_generated_at": live.get("predictions_generated_at"),
    }


def log_tail() -> list:
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(errors="replace").splitlines()
    except Exception:
        return []
    return [l for l in lines if "Metrics dispatcher" not in l][-LOG_LINES:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ops snapshot for /admin.")
    parser.add_argument("--run-ok", action="store_true")
    parser.add_argument("--run-failed", metavar="STEP")
    parser.add_argument("--duration", type=int, default=None)
    args = parser.parse_args()

    now = _now()
    conn = db.get_connection()
    try:
        ledger_rows, ledger_summary = ledger(conn)
        payload = {
            "generated_at": _iso(now),
            "lock_window_minutes": LOCK_WINDOW_MINUTES,
            "last_run": {
                "ok": None if not (args.run_ok or args.run_failed) else bool(args.run_ok),
                "failed_step": args.run_failed,
                "duration_s": args.duration,
                "finished_at": _iso(now),
            },
            "host": host_info(),
            "steps": step_status(),
            "runs": run_history(),
            "ledger_summary": ledger_summary,
            "ledger": ledger_rows,
            "upcoming_locks": upcoming_locks(conn, now),
            "freshness": freshness(conn, now),
            "log_tail": log_tail(),
        }
    finally:
        conn.close()

    OPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPS_PATH.write_text(json.dumps(payload, indent=1))
    print(
        f"ops.json: {len(payload['upcoming_locks'])} upcoming, "
        f"{ledger_summary['locked']} locked, {len(payload['runs'])} runs, "
        f"{len(payload['log_tail'])} log lines",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
