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
    # European competitions. role="target" for the Champions League product;
    # the other two are rating feeders only (cross-league ties calibrate the
    # pooled European rating stream), never customer-facing.
    2: {"expected_name": "UEFA Champions League", "role": "target"},
    3: {"expected_name": "UEFA Europa League", "role": "euro_feeder"},
    848: {"expected_name": "UEFA Europa Conference League", "role": "euro_feeder"},
}

# Domestic leagues of regular European participants: rating feeders for the
# Champions League pool only (domestic form + a rating anchor for clubs the
# five tracked leagues never see). league_id -> (expected_name, country).
# Ids verified against /leagues on 2026-09-18.
EURO_DOMESTIC_FEEDERS = {
    61: ("Ligue 1", "France"),
    94: ("Primeira Liga", "Portugal"),
    88: ("Eredivisie", "Netherlands"),
    144: ("Jupiler Pro League", "Belgium"),
    203: ("Süper Lig", "Turkey"),
    179: ("Premiership", "Scotland"),
    218: ("Bundesliga", "Austria"),
    207: ("Super League", "Switzerland"),
    345: ("Czech Liga", "Czech Republic"),
    197: ("Super League 1", "Greece"),
    210: ("HNL", "Croatia"),
    333: ("Premier League", "Ukraine"),
    119: ("Superliga", "Denmark"),
    103: ("Eliteserien", "Norway"),
    113: ("Allsvenskan", "Sweden"),
    106: ("Ekstraklasa", "Poland"),
    286: ("Super Liga", "Serbia"),
    318: ("1. Division", "Cyprus"),
    383: ("Ligat Ha'al", "Israel"),
    332: ("Super Liga", "Slovakia"),
    389: ("Premier League", "Kazakhstan"),
    419: ("Premyer Liqa", "Azerbaijan"),
    116: ("Premier League", "Belarus"),
    283: ("Liga I", "Romania"),
    235: ("Premier League", "Russia"),
}
for _lid, (_name, _country) in EURO_DOMESTIC_FEEDERS.items():
    LEAGUES.setdefault(_lid, {"expected_name": _name, "role": "euro_feeder"})

EURO_COMPETITION_IDS = [2, 3, 848]
# The pooled European rating stream: every competition whose results move a
# Champions League club's rating. MLS is left out (never connected by a
# competitive tie). Order is irrelevant; the stream is sorted by kickoff.
EURO_POOL_IDS = [39, 140, 135, 78, 40, 141, 136, 79] + EURO_COMPETITION_IDS + list(EURO_DOMESTIC_FEEDERS)

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
    # Champions League: no promotion feeder; its rating/feature stream is the
    # pooled European stream (pool_ids) rather than target+feeder.
    "ucl": {"league_id": 2, "web_code": "UCL", "feeder_id": None, "pool_ids": EURO_POOL_IDS, "live": True,
            "outcome_artifact": "outcome_model_ucl.json", "goals_artifact": "goals_model_ucl.json"},
}

# The five domestic leagues: the pooled global fit, the all-competition
# schedule ingest and the refold track are defined over these.
DOMESTIC_CODES = ("pl", "lal", "sea", "bun", "mls")


def pooled_targets() -> dict:
    return {c: TARGETS[c] for c in DOMESTIC_CODES}


def live_targets() -> dict:
    """Targets that reach customers: predictions, locks, web export, betting
    context. A target with live=False trains and backtests but ships nothing."""
    return {c: cfg for c, cfg in TARGETS.items() if cfg.get("live", True)}


def pool_ids(cfg: dict) -> list:
    """League ids whose completed matches feed a target's ratings, form and
    context: an explicit pool when configured, else target + feeder."""
    if cfg.get("pool_ids"):
        return list(cfg["pool_ids"])
    return [cfg["league_id"]] + ([cfg["feeder_id"]] if cfg.get("feeder_id") else [])


# Champions League rounds that are scored/predicted. Qualifying rounds and
# the August play-off round are rating updates only: they involve clubs that
# mostly never reach the league phase and precede the product's window.
_UCL_UNSCORED = ("qualifying", "preliminary")


def is_scored_round(league_id: int, round_text) -> bool:
    if league_id != 2:
        return True
    text = (round_text or "").lower()
    if any(k in text for k in _UCL_UNSCORED):
        return False
    # "Play-offs" (August, pre-league-phase) vs "Knockout Round Play-offs" (February).
    if text.strip() == "play-offs":
        return False
    return True


def is_knockout_round(league_id: int, round_text) -> bool:
    """Two-legged or single-match knockout tie (as opposed to a league phase
    or group match). Only meaningful for the European competitions."""
    if league_id not in EURO_COMPETITION_IDS:
        return False
    text = (round_text or "").lower()
    return any(k in text for k in ("round of", "quarter", "semi", "final", "knockout"))


def target_config(code: str) -> dict:
    if code not in TARGETS:
        raise KeyError(f"unknown league code {code!r}; choices: {list(TARGETS)}")
    return {"code": code, **TARGETS[code]}


# League-identity one-hot features for the PRD 9.2 global model. PL is the
# reference class (all zeros).
DUMMY_FEATURES = ["lg_lal", "lg_sea", "lg_bun", "lg_mls", "lg_ucl"]
_DUMMY_BY_LEAGUE_ID = {140: "lg_lal", 135: "lg_sea", 78: "lg_bun", 253: "lg_mls", 2: "lg_ucl"}


def league_dummies(league_id: int) -> dict:
    active = _DUMMY_BY_LEAGUE_ID.get(league_id)
    return {name: (1.0 if name == active else 0.0) for name in DUMMY_FEATURES}
