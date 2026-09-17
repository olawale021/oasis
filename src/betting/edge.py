"""The arithmetic of value (Betting PRD 12, 13, 20). Pure functions;
probabilities in [0,1], odds decimal."""

# Stamped on every betting_results row. Bump when the CLV definition
# changes, so a row says which formula produced its number -- the first
# version compared best-of-N odds to the closing median and was wrong.
CLV_VERSION = "v2-median-vs-median"


def edge(model_prob: float, market_prob: float) -> float:
    """Model minus market, in probability units (x100 for percentage points)."""
    return model_prob - market_prob


def expected_value(model_prob: float, odds: float) -> float:
    """Return per unit staked at these odds if the model is right about the
    probability: p * odds - 1."""
    return model_prob * odds - 1.0


def profit_1u(won: bool, odds: float) -> float:
    return odds - 1.0 if won else -1.0


def clv(taken_odds: float, closing_odds: float) -> float:
    """Closing-line value: how much better the price we graded at was than
    where the market closed. Positive means the market moved our way, which
    is evidence of value independent of whether the selection won.

    Compare like with like: consensus median at grade time against
    consensus median at close. Best-of-N against a median is always
    positive by construction and says nothing."""
    return taken_odds / closing_odds - 1.0
