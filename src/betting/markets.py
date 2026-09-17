"""Market vocabulary shared by consensus, grading and settlement.

Selections are lower-case internal names; `outcomes` maps the labels
API-Football uses in odds_snapshots.outcome onto them."""

MARKETS = {
    "1X2": {
        "market_id": 1,
        "selections": ("home", "draw", "away"),
        "outcomes": {"home": "home", "draw": "draw", "away": "away"},
    },
    "OU25": {
        "market_id": 5,
        "selections": ("over", "under"),
        "outcomes": {"over 2.5": "over", "under 2.5": "under"},
    },
    "BTTS": {
        "market_id": 8,
        "selections": ("yes", "no"),
        "outcomes": {"yes": "yes", "no": "no"},
    },
}

MARKET_BY_ID = {spec["market_id"]: name for name, spec in MARKETS.items()}


def selection_for(market: str, outcome: str):
    """Internal selection for an odds_snapshots outcome label, or None when
    the label is not part of this market (other O/U lines, for instance)."""
    return MARKETS[market]["outcomes"].get(outcome.strip().lower())


def model_probs(locked: dict) -> dict:
    """{market: {selection: p}} in [0,1] from a locked_predictions row, whose
    probabilities are stored as percentages. Markets the goals model did not
    score (NULL over_2_5 / btts) are left out rather than guessed."""
    out = {
        "1X2": {
            "home": locked["p_home"] / 100.0,
            "draw": locked["p_draw"] / 100.0,
            "away": locked["p_away"] / 100.0,
        }
    }
    if locked["over_2_5"] is not None:
        over = locked["over_2_5"] / 100.0
        out["OU25"] = {"over": over, "under": 1.0 - over}
    if locked["btts"] is not None:
        yes = locked["btts"] / 100.0
        out["BTTS"] = {"yes": yes, "no": 1.0 - yes}
    return out


def selection_won(market: str, selection: str, home_goals: int, away_goals: int) -> bool:
    if market == "1X2":
        if selection == "home":
            return home_goals > away_goals
        if selection == "away":
            return away_goals > home_goals
        return home_goals == away_goals
    if market == "OU25":
        over = home_goals + away_goals > 2.5
        return over if selection == "over" else not over
    if market == "BTTS":
        both = home_goals > 0 and away_goals > 0
        return both if selection == "yes" else not both
    raise ValueError(f"unknown market {market}")
