# API-Football league IDs for the oasis platform.
#
# IDs are recalled from memory, not confirmed against the live API. The
# coverage_audit script verifies each one against the API's returned league
# name on every run and warns (never crashes) on mismatch — see PRD §7.3
# "must not assume ... must read the season-specific flags and degrade
# gracefully."
#
# role="target": customer-facing prediction product.
# role="feeder": second-division training data only (promoted-club priors),
# never a customer-facing prediction product in the initial release.

LEAGUES = {
    39: {"expected_name": "Premier League", "role": "target"},
    140: {"expected_name": "La Liga", "role": "target"},
    135: {"expected_name": "Serie A", "role": "target"},
    78: {"expected_name": "Bundesliga", "role": "target"},
    253: {"expected_name": "Major League Soccer", "role": "target"},
    40: {"expected_name": "Championship", "role": "feeder"},
    141: {"expected_name": "Segunda División", "role": "feeder"},
    136: {"expected_name": "Serie B", "role": "feeder"},
    79: {"expected_name": "2. Bundesliga", "role": "feeder"},
}

# target league_id -> feeder league_id, for promotion/relegation Elo bridging.
# Phase 1 only uses the 39: 40 (Premier League / Championship) entry.
PROMOTION_PAIRS = {
    39: 40,
    140: 141,
    135: 136,
    78: 79,
}
