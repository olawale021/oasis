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


# Per-target-league model configuration: short artifact code, web display
# code, and feeder league (None = no promotion bridging, e.g. MLS).
# PL keeps its Phase 1 artifact filenames so registry roles/history persist.
TARGETS = {
    "pl": {"league_id": 39, "web_code": "EPL", "feeder_id": 40,
           "outcome_artifact": "outcome_model_pl.json", "goals_artifact": "goals_model.json"},
    "lal": {"league_id": 140, "web_code": "LAL", "feeder_id": 141,
            "outcome_artifact": "outcome_model_lal.json", "goals_artifact": "goals_model_lal.json"},
    "sea": {"league_id": 135, "web_code": "SEA", "feeder_id": 136,
            "outcome_artifact": "outcome_model_sea.json", "goals_artifact": "goals_model_sea.json"},
    "bun": {"league_id": 78, "web_code": "BUN", "feeder_id": 79,
            "outcome_artifact": "outcome_model_bun.json", "goals_artifact": "goals_model_bun.json"},
    "mls": {"league_id": 253, "web_code": "MLS", "feeder_id": None,
            "outcome_artifact": "outcome_model_mls.json", "goals_artifact": "goals_model_mls.json"},
}


def target_config(code: str) -> dict:
    if code not in TARGETS:
        raise KeyError(f"unknown league code {code!r}; choices: {list(TARGETS)}")
    return {"code": code, **TARGETS[code]}


# League-identity one-hot features for the PRD 9.2 global model. PL is the
# reference class (all zeros).
DUMMY_FEATURES = ["lg_lal", "lg_sea", "lg_bun", "lg_mls"]
_DUMMY_BY_LEAGUE_ID = {140: "lg_lal", 135: "lg_sea", 78: "lg_bun", 253: "lg_mls"}


def league_dummies(league_id: int) -> dict:
    active = _DUMMY_BY_LEAGUE_ID.get(league_id)
    return {name: (1.0 if name == active else 0.0) for name in DUMMY_FEATURES}
