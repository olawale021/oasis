"""Grading rulebook (Betting PRD 15).

VERSION v0-provisional: only PASS and WATCH are ever emitted. VALUE and
STRONG_VALUE require thresholds backed by the point-in-time backtest (PRD
18/19), and the odds archive is weeks old -- there is no evidence yet. Every
recommendation records the rulebook version that graded it, so when a
validated v1 exists the ledger can be re-graded and the two compared.

PASS  the market already prices this; nothing to exploit -- or the model
      has no validated skill on the market at all (NO_SKILL_MARKETS).
WATCH a disagreement exists but cannot be trusted yet -- either the data
      behind it is thin (no odds, few books, stale window) or, in v0, simply
      because no edge bucket has a track record.
"""

THRESHOLDS_VERSION = "v0.1-provisional"

MIN_BOOKMAKERS = 3      # below this the consensus is one or two books' opinion
EDGE_FLOOR = 0.03       # 3pp; inside model noise, not worth watching
STALE_SNAPSHOTS = ("7d",)   # a price taken days out is not the price at lock

# No-bet zone (v0.1, 2026-09-17). src/goals_calibration.py: on the held-out
# 2025/26 season the goals model beats a constant base rate by +0.003 to
# +0.010 nats on Over 2.5 and is WORSE than the base rate on BTTS in three
# leagues; on live rows the market's log loss on totals is 0.568 to the
# model's 0.627 while 1X2 is level. A disagreement between an uninformed
# model and an informed market is not an edge in either direction, so these
# markets grade PASS regardless of the numbers until the goals model shows
# out-of-sample skill (a recalibration layer was tried and lost out of
# sample -- there is no signal to sharpen).
NO_SKILL_MARKETS = {
    "OU25": "goals model shows no validated skill on totals (held-out season: +0.01 nats vs base rate; market 0.57 vs model 0.63 log loss live)",
    "BTTS": "goals model shows no validated skill on BTTS (held-out season: at or below the base rate in most leagues)",
}


def grade(model_prob: float, market_prob, ev, bookmaker_count, snapshot, market: str = None) -> tuple:
    """Returns (level, reasons). reasons is a list of {code, detail} dicts
    built from the numbers themselves, so the card can explain without
    inventing anything (PRD 16)."""
    if market in NO_SKILL_MARKETS:
        return "PASS", [{"code": "market_no_skill", "detail": NO_SKILL_MARKETS[market]}]
    if market_prob is None:
        return "WATCH", [{"code": "no_odds", "detail": "no bookmaker prices archived before lock"}]
    if bookmaker_count is not None and bookmaker_count < MIN_BOOKMAKERS:
        return "WATCH", [{
            "code": "few_bookmakers",
            "detail": f"only {bookmaker_count} bookmaker(s) quoted; consensus needs {MIN_BOOKMAKERS}",
        }]
    if snapshot in STALE_SNAPSHOTS:
        return "WATCH", [{"code": "stale_odds", "detail": f"newest archived price is the {snapshot} window"}]

    e = model_prob - market_prob
    if e < EDGE_FLOOR:
        return "PASS", [{
            "code": "edge_below_floor",
            "detail": f"model {model_prob * 100:.0f}% vs market {market_prob * 100:.0f}%: "
                      f"{e * 100:+.1f}pp is inside the {EDGE_FLOOR * 100:.0f}pp floor",
        }]
    if ev is not None and ev <= 0:
        return "PASS", [{
            "code": "negative_ev",
            "detail": f"best available price returns {ev * 100:+.1f}% per unit at the model's probability",
        }]
    return "WATCH", [{
        "code": "unvalidated_edge",
        "detail": f"{e * 100:+.1f}pp edge, EV {ev * 100:+.1f}%; "
                  f"VALUE withheld until the backtest validates this bucket ({THRESHOLDS_VERSION})",
    }]
