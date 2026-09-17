"""The `betting` block of live.json (Betting PRD 4, 5, 16).

One row per upcoming match x market x selection, plus the H2H / form
context per fixture. Two sources, one rulebook:

  locked   the fixture already has ledger rows (betting_effective): those
           are shown verbatim -- graded as of lock, reproducible.
  preview  not locked yet: graded now from the current prediction and the
           newest consensus window, with the same thresholds. Flagged
           locked=false so the UI can say "provisional until lock".

Access gating happens in the web layer (lib/gate.ts) per fixture, exactly as
for match probabilities; this block never decides who may see what."""

import json
from datetime import datetime, timezone

from betting import edge as edge_math
from betting.consensus import consensus_as_of
from betting.markets import MARKETS, model_probs
from betting.thresholds import THRESHOLDS_VERSION, grade


def _pct(x):
    return round(x * 100, 1) if x is not None else None


def _row(fixture_id, market, sel, p, mkt_row, level, reasons, locked):
    market_prob = mkt_row["consensus_prob"] if mkt_row else None
    best_odds = mkt_row["best_odds"] if mkt_row else None
    return {
        "id": fixture_id,
        "market": market,
        "sel": sel,
        "p": _pct(p),
        "mp": _pct(market_prob),
        "edge": _pct(edge_math.edge(p, market_prob)) if mkt_row else None,
        "odds": best_odds,
        "book": mkt_row["best_bookmaker"] if mkt_row else None,
        "ev": _pct(edge_math.expected_value(p, best_odds)) if mkt_row else None,
        "books": mkt_row["bookmaker_count"] if mkt_row else None,
        "snap": mkt_row["snapshot"] if mkt_row else None,
        "level": level,
        "reasons": reasons,
        "locked": locked,
    }


def _preview_rows(conn, prediction: dict, now_iso: str) -> list:
    rows = []
    for market, sels in model_probs(prediction).items():
        mkt = consensus_as_of(conn, prediction["fixture_id"], market, now_iso)
        for sel, p in sels.items():
            r = mkt.get(sel) if mkt else None
            ev = edge_math.expected_value(p, r["best_odds"]) if r else None
            level, reasons = grade(p, r["consensus_prob"] if r else None, ev,
                                   r["bookmaker_count"] if r else None, r["snapshot"] if r else None)
            rows.append(_row(prediction["fixture_id"], market, sel, p, r, level, reasons, False))
    return rows


def _locked_rows(conn, fixture_id: int) -> list:
    out = []
    for br in conn.execute("SELECT * FROM betting_effective WHERE fixture_id = ?", (fixture_id,)).fetchall():
        mkt_row = None
        if br["market_prob"] is not None:
            mkt_row = {
                "consensus_prob": br["market_prob"], "best_odds": br["best_odds"],
                "best_bookmaker": None, "bookmaker_count": br["bookmaker_count"], "snapshot": br["market_snapshot"],
            }
        out.append(_row(fixture_id, br["market"], br["selection"], br["model_prob"], mkt_row,
                        br["level"], json.loads(br["reasons_json"]), True))
    return out


def _context(conn, fixture_id: int, home_id: int, away_id: int):
    h = conn.execute("SELECT * FROM h2h_summary WHERE fixture_id = ?", (fixture_id,)).fetchone()
    trends = {r["team_id"]: r for r in conn.execute(
        "SELECT * FROM team_market_trends WHERE fixture_id = ?", (fixture_id,)).fetchall()}

    def trend(team_id):
        t = trends.get(team_id)
        if not t:
            return None
        return {"n": t["matches_considered"], "btts": t["btts_count"], "over25": t["over_2_5_count"],
                "gf": t["goals_for"], "ga": t["goals_against"]}

    return {
        "h2h": None if not h else {
            "n": h["matches_considered"], "hw": h["home_wins"], "d": h["draws"], "aw": h["away_wins"],
            "hg": h["home_goals"], "ag": h["away_goals"], "btts": h["btts_count"], "over25": h["over_2_5_count"],
            "avg": h["average_goals"], "last": h["last_meeting_utc"],
        },
        "home": trend(home_id),
        "away": trend(away_id),
    }


def build_betting(conn, predictions: dict, now_iso: str = None) -> dict:
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    rows, context = [], {}
    for p in predictions["predictions"]:
        fid = p["fixture_id"]
        locked = _locked_rows(conn, fid)
        rows.extend(locked or _preview_rows(conn, p, now_iso))
        context[str(fid)] = _context(conn, fid, p["home_team_id"], p["away_team_id"])
    return {
        "thresholds_version": THRESHOLDS_VERSION,
        "markets": {k: list(v["selections"]) for k, v in MARKETS.items()},
        "generated_at": now_iso,
        "rows": rows,
        "context": context,
    }
