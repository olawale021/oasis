"""Betting backtest: the evidence gate for VALUE (Betting PRD 18, 19, 20).

    python3 src/betting/backtest_edges.py [--min-n 100] [--db-path ...]

Answers a different question from the model harness (rolling_backtest.py
optimises log loss): when the model disagreed with the market by X, did
that disagreement beat the closing line and pay? Groups every settled,
odds-backed ledger row by track, market, league, edge bucket, confidence,
bookmaker count and odds range, and reports n, hit rate, ROI at the
graded best price with a 95% CI, closing-line value with a CI, model
calibration, and drawdown.

Two tracks, because they measure different decisions:
  h24   graded a day out (stage h24). CLV = graded price vs close: did the
        market come toward us. This is the gate.
  lock  graded at lock (betting_effective). CLV is ~0 by construction, so
        the movement metric here is clv_24h: 24h consensus vs close.

Then the only number that counts as evidence: a walk-forward replay. A
cell is "validated" when rows BEFORE week k give n >= min_n, a CLV
confidence interval above zero and ROI >= 0; week k's rows in validated
cells are the VALUE rows that rulebook would have emitted, scored out of
sample. With a young ledger every cell reads insufficient. That is the
correct answer, and thresholds.py stays at v0 until it changes.
"""

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import db  # noqa: E402

Z95 = 1.96
DEFAULT_MIN_N = 100
MIN_CELL_PRINT = 20


# --- bucketing --------------------------------------------------------------

def edge_bucket(edge: float) -> str:
    pp = edge * 100
    if pp < 0:
        return "negative"
    if pp < 3:
        return "0-3pp"
    if pp < 5:
        return "3-5pp"
    if pp < 8:
        return "5-8pp"
    return "8pp+"


def books_band(n) -> str:
    if n is None:
        return "none"
    return "<5" if n < 5 else "5-9" if n < 10 else "10+"


def odds_band(odds) -> str:
    if odds is None:
        return "none"
    return "<=1.5" if odds <= 1.5 else "1.5-2.5" if odds <= 2.5 else "2.5-4" if odds <= 4 else "4+"


def prob_band(p: float) -> str:
    lo = int(p * 10) * 10
    return f"{lo}-{lo + 10}%"


def iso_week(kickoff_utc: str) -> str:
    y, w, _ = datetime.fromisoformat(kickoff_utc).isocalendar()
    return f"{y}-W{w:02d}"


# --- statistics ---------------------------------------------------------------

def _mean_ci(values: list):
    n = len(values)
    if n == 0:
        return None, None, None
    m = sum(values) / n
    if n < 2:
        return m, None, None
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))
    half = Z95 * sd / math.sqrt(n)
    return m, m - half, m + half


def _median(values: list):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def max_drawdown(profits_in_time_order: list) -> float:
    peak = cum = 0.0
    dd = 0.0
    for p in profits_in_time_order:
        cum += p
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return dd


def cell_stats(rows: list) -> dict:
    """rows: dicts with won, profit, clv (may be None), model_prob, market_prob, closing_prob, kickoff."""
    rows = sorted(rows, key=lambda r: r["kickoff"])
    profits = [r["profit"] for r in rows if r["profit"] is not None]
    clvs = [r["clv"] for r in rows if r["clv"] is not None]
    roi, roi_lo, roi_hi = _mean_ci(profits)
    clv, clv_lo, clv_hi = _mean_ci(clvs)
    n = len(rows)
    hit = sum(r["won"] for r in rows) / n if n else None
    model_p = sum(r["model_prob"] for r in rows) / n if n else None
    market_p = sum(r["market_prob"] for r in rows) / n if n else None
    moved = [r for r in rows if r["closing_prob"] is not None]
    toward = sum(1 for r in moved if r["closing_prob"] > r["market_prob"]) / len(moved) if moved else None
    r4 = lambda x: round(x, 4) if x is not None else None  # noqa: E731
    return {
        "n": n,
        "hit_rate": r4(hit),
        "model_prob": r4(model_p),
        "market_prob": r4(market_p),
        # Positive: the model said it more often than it happened.
        "calibration_gap": r4(model_p - hit) if n else None,
        "roi": r4(roi), "roi_ci": [r4(roi_lo), r4(roi_hi)],
        "n_clv": len(clvs),
        "clv_mean": r4(clv), "clv_median": r4(_median(clvs)), "clv_ci": [r4(clv_lo), r4(clv_hi)],
        "market_moved_toward": r4(toward),
        "max_drawdown_1u": r4(max_drawdown(profits)),
    }


# --- data -----------------------------------------------------------------------

def load_rows(conn) -> list:
    """Every settled row with a market, on both tracks, in a flat dict shape.
    The lock track is betting_effective (final over initial)."""
    out = []
    for track, source in (("h24", "betting_recommendations"), ("lock", "betting_effective")):
        stage_clause = "AND br.stage = 'h24'" if track == "h24" else ""
        for r in conn.execute(
            f"""
            SELECT br.*, r.won, r.profit_1u, r.clv, r.clv_24h, r.closing_prob
            FROM {source} br JOIN betting_results r USING (recommendation_id)
            WHERE br.market_prob IS NOT NULL {stage_clause}
            """
        ).fetchall():
            out.append({
                "track": track,
                "market": r["market"], "selection": r["selection"], "league": r["league_code"],
                "kickoff": r["kickoff_utc"], "week": iso_week(r["kickoff_utc"]),
                "edge": r["edge"], "edge_bucket": edge_bucket(r["edge"]),
                "confidence": r["confidence"] or "n/a",
                "books": books_band(r["bookmaker_count"]),
                "odds": odds_band(r["best_odds"]),
                "hours": r["hours_to_kickoff"],
                "model_prob": r["model_prob"], "market_prob": r["market_prob"], "closing_prob": r["closing_prob"],
                "won": r["won"], "profit": r["profit_1u"],
                # The movement metric that is not zero by construction on each track.
                "clv": r["clv"] if track == "h24" else r["clv_24h"],
                "level": r["level"],
            })
    return out


# --- grouping ---------------------------------------------------------------------

def group(rows: list, keys: tuple) -> dict:
    cells = defaultdict(list)
    for r in rows:
        cells[tuple(r[k] for k in keys)].append(r)
    return {" | ".join(map(str, k)): cell_stats(v) for k, v in sorted(cells.items())}


def calibration(rows: list) -> dict:
    """Selection-level calibration from live rows: by market x model
    probability band, and by market x edge bucket (who was right where we
    disagreed)."""
    return {
        "by_prob_band": group(rows, ("track", "market", "selection")),
        "by_market_prob_band": group([{**r, "band": prob_band(r["model_prob"])} for r in rows], ("track", "market", "band")),
        "by_disagreement": group(rows, ("track", "market", "edge_bucket")),
    }


# --- the gate ------------------------------------------------------------------

GATE_KEYS = ("track", "market", "edge_bucket")


def validated_cells(rows: list, min_n: int) -> dict:
    """Cells that would be allowed to emit VALUE, judged on `rows` only:
    n >= min_n, CLV CI entirely above zero, ROI >= 0. Returns {key: stats}."""
    out = {}
    for key, s in group(rows, GATE_KEYS).items():
        if s["n"] >= min_n and s["clv_ci"][0] is not None and s["clv_ci"][0] > 0 and (s["roi"] or 0) >= 0:
            out[key] = s
    return out


def walk_forward(rows: list, min_n: int) -> dict:
    """Weekly folds: validate on everything before week k, score week k's
    rows that fall in validated cells. The out-of-sample total is the only
    ROI/CLV a rulebook may claim."""
    weeks = sorted({r["week"] for r in rows})
    folds, oos = [], []
    for wk in weeks:
        train = [r for r in rows if r["week"] < wk]
        test = [r for r in rows if r["week"] == wk]
        cells = validated_cells(train, min_n)
        picked = [r for r in test if " | ".join(str(r[k]) for k in GATE_KEYS) in cells]
        oos.extend(picked)
        folds.append({"week": wk, "train_n": len(train), "validated_cells": sorted(cells),
                      "test_n": len(test), "value_rows": len(picked),
                      "value": cell_stats(picked) if picked else None})
    return {"min_n": min_n, "folds": folds, "oos_value": cell_stats(oos) if oos else {"n": 0}}


# --- report --------------------------------------------------------------------

def build_report(conn, min_n: int) -> dict:
    rows = load_rows(conn)
    by_track = {t: [r for r in rows if r["track"] == t] for t in ("h24", "lock")}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_n": min_n,
        "rows": {t: len(v) for t, v in by_track.items()},
        "headline": {t: cell_stats(v) for t, v in by_track.items() if v},
        "by_edge": group(rows, ("track", "edge_bucket")),
        "by_market_edge": group(rows, ("track", "market", "edge_bucket")),
        "by_market_league_edge": {k: v for k, v in group(rows, ("track", "market", "league", "edge_bucket")).items()
                                  if v["n"] >= MIN_CELL_PRINT},
        "by_confidence": group(rows, ("track", "confidence", "edge_bucket")),
        "by_books": group(rows, ("track", "books", "edge_bucket")),
        "by_odds": group(rows, ("track", "odds", "edge_bucket")),
        "by_level": group(rows, ("track", "level")),
        "calibration": calibration(rows),
        "validated_now": {t: sorted(validated_cells(v, min_n)) for t, v in by_track.items()},
        "walk_forward": {t: walk_forward(v, min_n) for t, v in by_track.items()},
    }


def print_summary(rep: dict) -> None:
    def line(name, s):
        ci = s["clv_ci"]
        clv = f"{s['clv_mean'] * 100:+.2f}% [{ci[0] * 100:+.2f}, {ci[1] * 100:+.2f}]" if s["clv_mean"] is not None and ci[0] is not None else "—"
        roi = f"{s['roi'] * 100:+.1f}%" if s["roi"] is not None else "—"
        print(f"  {name:44} n={s['n']:4}  hit {s['hit_rate'] * 100:4.0f}%  roi {roi:>7}  clv {clv:<28} gap {s['calibration_gap'] * 100:+.1f}pp")

    print(f"betting backtest · rows h24={rep['rows']['h24']} lock={rep['rows']['lock']} · min_n={rep['min_n']}")
    for t in ("h24", "lock"):
        if t in rep["headline"]:
            print(f"[{t}]")
            line("all", rep["headline"][t])
            for k, s in rep["by_edge"].items():
                if k.startswith(t):
                    line(k, s)
    for t in ("h24", "lock"):
        wf = rep["walk_forward"][t]
        v = wf["oos_value"]
        vn = v["n"]
        print(f"[{t}] validated cells now: {rep['validated_now'][t] or 'none'} · walk-forward VALUE rows out of sample: {vn}"
              + (f" · roi {v['roi'] * 100:+.1f}% clv {v['clv_mean'] * 100:+.2f}%" if vn else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Betting backtest: edge buckets, CLV, walk-forward gate.")
    parser.add_argument("--min-n", type=int, default=DEFAULT_MIN_N)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()

    started = time.monotonic()
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    status_path = config.STATUS_DIR / "backtest_edges_status.json"
    try:
        conn = db.get_connection(args.db_path)
        db.init_db(conn)
        rep = build_report(conn, args.min_n)
        conn.close()
    except Exception as exc:
        status_path.write_text(json.dumps({"success": False, "refreshed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)}, indent=2))
        print(f"[backtest_edges] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (config.REPORTS_DIR / f"backtest_edges_{stamp}.json").write_text(json.dumps(rep, indent=2))
    (config.REPORTS_DIR / "backtest_edges_latest.json").write_text(json.dumps(rep, indent=2))
    oos = {t: rep["walk_forward"][t]["oos_value"]["n"] for t in ("h24", "lock")}
    status_path.write_text(json.dumps({
        "success": True, "refreshed_at": rep["generated_at"],
        "duration_ms": int((time.monotonic() - started) * 1000),
        "counts": {"rows_h24": rep["rows"]["h24"], "rows_lock": rep["rows"]["lock"],
                   "validated_cells_h24": len(rep["validated_now"]["h24"]),
                   "validated_cells_lock": len(rep["validated_now"]["lock"]),
                   "oos_value_rows_h24": oos["h24"], "oos_value_rows_lock": oos["lock"]},
    }, indent=2))
    print_summary(rep)


if __name__ == "__main__":
    main()
