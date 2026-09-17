"""Tell the web Worker what happened this run so it can send Telegram alerts.

    python3 src/telegram_dispatch.py          # end of matchday.sh / final_pass.sh

The droplet never talks to Telegram and never holds the bot token. It
POSTs events to /api/telegram/dispatch with a shared secret; the Worker
builds and sends the messages from the same live.json it serves. Events are
derived from the ledger since the last announcement (state in
data/status/telegram_dispatch.json), so nothing is announced twice and a
missed run catches up on the next. First run initialises the watermark to
now and announces nothing: the backlog is history, not news.

Never fails the chain: a missing secret or an unreachable Worker is
recorded in the status file (shown on /admin) and the script exits 0."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import config
import db

STATE_PATH = config.STATUS_DIR / "telegram_dispatch.json"
STATUS_PATH = config.STATUS_DIR / "telegram_dispatch_status.json"
DIGEST_HOUR_UTC = 8
DEFAULT_URL = "https://realscores.app/api/telegram/dispatch"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def events_since(conn, state: dict, now: datetime) -> tuple:
    """(events, new_state). Watermarks are ISO timestamps from the ledger's
    own columns, so a row is announced exactly once."""
    now_iso = now.isoformat()
    if not state:
        return [], {"lock_at": now_iso, "final_at": now_iso, "settle_at": now_iso, "digest_day": None}
    events = []
    new = dict(state)

    locks = conn.execute(
        "SELECT fixture_id, locked_at FROM locked_predictions WHERE stage='initial' AND locked_at > ? ORDER BY locked_at",
        (state["lock_at"],),
    ).fetchall()
    if locks:
        events.append({"type": "lock", "fixture_ids": [r["fixture_id"] for r in locks]})
        new["lock_at"] = locks[-1]["locked_at"]

    finals = conn.execute(
        "SELECT fixture_id, locked_at FROM locked_predictions WHERE stage='final' AND locked_at > ? ORDER BY locked_at",
        (state["final_at"],),
    ).fetchall()
    if finals:
        events.append({"type": "final", "fixture_ids": [r["fixture_id"] for r in finals]})
        new["final_at"] = finals[-1]["locked_at"]

    settled = conn.execute(
        "SELECT DISTINCT fixture_id, settled_at FROM locked_predictions WHERE settled_at > ? ORDER BY settled_at",
        (state["settle_at"],),
    ).fetchall()
    if settled:
        events.append({"type": "settled", "fixture_ids": sorted({r["fixture_id"] for r in settled})})
        new["settle_at"] = settled[-1]["settled_at"]

    today = now.strftime("%Y-%m-%d")
    if now.hour == DIGEST_HOUR_UTC and state.get("digest_day") != today:
        events.append({"type": "digest"})
        new["digest_day"] = today
    return events, new


def post(url: str, secret: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"content-type": "application/json", "authorization": f"Bearer {secret}"},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())


def main() -> None:
    now = datetime.now(timezone.utc)
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    secret = os.environ.get("TELEGRAM_DISPATCH_SECRET", "")
    url = os.environ.get("TELEGRAM_DISPATCH_URL", DEFAULT_URL)

    def finish(ok: bool, counts: dict, error: str = None) -> None:
        status = {"success": ok, "refreshed_at": now.isoformat(), "counts": counts}
        if error:
            status["error"] = error
        STATUS_PATH.write_text(json.dumps(status, indent=2))

    if not secret:
        finish(True, {"events": 0, "sent": 0, "note": 1})
        print("telegram dispatch: TELEGRAM_DISPATCH_SECRET not set, skipped")
        return

    conn = db.get_connection()
    state = load_state()
    events, new_state = events_since(conn, state, now)
    conn.close()
    if not state:
        STATE_PATH.write_text(json.dumps(new_state, indent=2))
        finish(True, {"events": 0, "sent": 0})
        print("telegram dispatch: initialised watermark, nothing announced")
        return
    if not events:
        finish(True, {"events": 0, "sent": 0})
        print("telegram dispatch: nothing new")
        return

    sent = total = 0
    cursor = 0
    try:
        while True:
            res = post(url, secret, {"events": events, "cursor": cursor})
            sent += res.get("sent", 0)
            total = res.get("total", total)
            if res.get("errors"):
                print(f"telegram dispatch: send errors {res['errors']}", file=sys.stderr)
            if res.get("next") is None:
                break
            cursor = res["next"]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        # Do not advance the watermark: the next run retries these events.
        finish(False, {"events": len(events), "sent": sent}, str(exc))
        print(f"telegram dispatch: FAILED {exc}", file=sys.stderr)
        return

    STATE_PATH.write_text(json.dumps(new_state, indent=2))
    finish(True, {"events": len(events), "messages": total, "sent": sent, **{e["type"]: len(e.get("fixture_ids", [])) or 1 for e in events}})
    print(f"telegram dispatch: {[e['type'] for e in events]} -> {sent}/{total} messages")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never fail the chain over alerts
        print(f"telegram dispatch: ERROR {exc}", file=sys.stderr)
