"""Bookmaker consensus per fixture, market, selection and snapshot window
(Betting PRD 10). Median of margin-removed probabilities across books, plus
median and best price. Point-in-time lookups select the newest window whose
odds were fetched no later than a given instant, so a grade made at lock
time can be reproduced exactly (PRD 28) and never sees a later price."""

from datetime import datetime

from betting.markets import MARKETS, MARKET_BY_ID, selection_for


def _median(values: list) -> float:
    values = sorted(values)
    n = len(values)
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


def build_consensus(conn, now_iso: str) -> int:
    """Insert consensus rows for every (fixture, snapshot, market) group in
    odds_snapshots that has none yet. Idempotent: groups are append-only, so
    a group's consensus is computed once and never changes. Returns rows
    inserted."""
    market_ids = ", ".join(str(spec["market_id"]) for spec in MARKETS.values())
    groups = conn.execute(
        f"""
        SELECT DISTINCT o.fixture_id, o.snapshot, o.market_id
        FROM odds_snapshots o
        WHERE o.market_id IN ({market_ids}) AND o.normalized_prob IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM market_consensus mc
            WHERE mc.fixture_id = o.fixture_id AND mc.snapshot = o.snapshot
              AND mc.market = CASE o.market_id
                WHEN 1 THEN '1X2' WHEN 5 THEN 'OU25' WHEN 8 THEN 'BTTS' END
          )
        """
    ).fetchall()

    inserted = 0
    for g in groups:
        market = MARKET_BY_ID[g["market_id"]]
        rows = conn.execute(
            """
            SELECT bookmaker_id, bookmaker, outcome, odds_decimal, normalized_prob, fetched_at
            FROM odds_snapshots
            WHERE fixture_id = ? AND snapshot = ? AND market_id = ? AND normalized_prob IS NOT NULL
            """,
            (g["fixture_id"], g["snapshot"], g["market_id"]),
        ).fetchall()
        quotes = {s: [] for s in MARKETS[market]["selections"]}
        bookmakers = set()
        fetched_at = None
        for r in rows:
            sel = selection_for(market, r["outcome"])
            if sel is None:
                continue  # another O/U line
            quotes[sel].append(r)
            bookmakers.add(r["bookmaker_id"])
            fetched_at = max(fetched_at or r["fetched_at"], r["fetched_at"])
        if any(not q for q in quotes.values()):
            continue  # incomplete market: never publish a one-sided consensus
        for sel, q in quotes.items():
            best = max(q, key=lambda r: r["odds_decimal"])
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO market_consensus
                    (fixture_id, market, selection, snapshot, consensus_prob, median_odds,
                     best_odds, best_bookmaker, bookmaker_count, fetched_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    g["fixture_id"], market, sel, g["snapshot"],
                    round(_median([r["normalized_prob"] for r in q]), 6),
                    round(_median([r["odds_decimal"] for r in q]), 4),
                    best["odds_decimal"], best["bookmaker"], len(bookmakers), fetched_at, now_iso,
                ),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted


def consensus_as_of(conn, fixture_id: int, market: str, as_of_iso: str):
    """The newest consensus window fetched at or before `as_of_iso`, as
    {selection: row}, or None if no window qualifies. Later windows are
    invisible on purpose: the lookup must return what was knowable then."""
    as_of = datetime.fromisoformat(as_of_iso)
    rows = conn.execute(
        "SELECT * FROM market_consensus WHERE fixture_id = ? AND market = ?",
        (fixture_id, market),
    ).fetchall()
    eligible = [r for r in rows if datetime.fromisoformat(r["fetched_at"]) <= as_of]
    if not eligible:
        return None
    newest = max(eligible, key=lambda r: r["fetched_at"])["snapshot"]
    return {r["selection"]: r for r in eligible if r["snapshot"] == newest}


def closing_consensus(conn, fixture_id: int, market: str):
    rows = conn.execute(
        "SELECT * FROM market_consensus WHERE fixture_id = ? AND market = ? AND snapshot = 'closing'",
        (fixture_id, market),
    ).fetchall()
    return {r["selection"]: r for r in rows} or None
