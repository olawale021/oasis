import elo as elo_module
import features as features_module
import leagues
import promotion
import ratings as ratings_module

PL_ID = 39
CHAMP_ID = 40

# A club season is ~38-46 games, so 6 already represents real in-pool evidence
# without requiring most of a season to elapse first (vs WC's 15, tuned for a
# handful of international matches per year). Promoted teams already clear
# this via their Championship history before their first PL match.
MIN_GAMES = 6

TRAIN_SEASONS = list(range(2017, 2023))  # 2017/18 .. 2022/23 (6 seasons)
VALIDATE_SEASON = 2023  # 2023/24
CALIBRATE_SEASON = 2024  # 2024/25
TEST_SEASON = 2025  # 2025/26
# Replay/state history starts earlier than the scored window: 2010-2016
# fixtures (2012+ for MLS) are ingested as Elo/feature WARM-UP only -- they
# never enter train/validate/calibrate/test buckets (split_by_season keys on
# the season lists above), so scored splits are unchanged and before/after
# comparisons stay clean.
HISTORY_START = 2010
ALL_SEASONS = list(range(HISTORY_START, 2026))


def actual_class(home_goals: int, away_goals: int) -> int:
    """0 = home win, 1 = draw, 2 = away win."""
    if home_goals > away_goals:
        return 0
    if home_goals < away_goals:
        return 2
    return 1


def collect_samples(matches: list, transitions: dict, use_mov: bool = True, target_league_id: int = PL_ID, score_feeders: bool = False, schedule_matches: list = None) -> list:
    """One forward pass over the combined chronological target+feeder stream.
    A match becomes a scored sample only if it's in the target league and both
    teams have matches_played >= MIN_GAMES (checked BEFORE this match). Every
    match unconditionally applies pending promotion transitions, updates Elo,
    and (via the pre-loaded, date-filtered FeatureStore) contributes to
    form/h2h, regardless of scoring eligibility."""
    elo = elo_module.EloRatings(use_mov=use_mov)
    store = features_module.FeatureStore()
    store.load(matches)
    if schedule_matches:
        store.load_schedule(schedule_matches)

    # Learned rating stores (pi + Berrar), hyperparameters fitted on the
    # warm-up years only (cached per league) -- zero fold leakage.
    code = next(c for c, cfg in leagues.TARGETS.items() if cfg["league_id"] == target_league_id)
    rating_params = ratings_module.get_params(code, matches)
    pi, berrar = ratings_module.build_stores(rating_params)
    context = features_module.LeagueContext()
    feeder_id = leagues.TARGETS[code]["feeder_id"]

    applied = set()
    samples = []

    for match in matches:
        home_id = match["home_team_id"]
        away_id = match["away_team_id"]
        season = match["season"]
        before = match["kickoff_utc"]
        neutral = match["neutral"]

        promotion.apply_pending_transition(elo, home_id, season, transitions, applied)
        promotion.apply_pending_transition(elo, away_id, season, transitions, applied)

        is_target = match["league_id"] == target_league_id
        is_feeder_row = score_feeders and feeder_id is not None and match["league_id"] == feeder_id
        eligible = (
            (is_target or is_feeder_row)
            and elo.matches_played.get(home_id, 0) >= MIN_GAMES
            and elo.matches_played.get(away_id, 0) >= MIN_GAMES
        )

        if eligible:
            feats = store.match_features(home_id, away_id, before, elo, neutral)
            feats.update(leagues.league_dummies(target_league_id))
            gh_hat, ga_hat = berrar.pred_goals(home_id, away_id)
            feats["pi_pred_gd"] = pi.pred_gd(home_id, away_id)
            feats["ber_gh"] = gh_hat
            feats["ber_ga"] = ga_hat
            feats.update(context.features(match["league_id"]))
            feats["tier2"] = 1.0 if is_feeder_row else 0.0
            samples.append(
                {
                    "fixture_id": match["fixture_id"],
                    "season": season,
                    "kickoff_utc": before,
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                    "home_goals": match["home_goals"],
                    "away_goals": match["away_goals"],
                    "cls": actual_class(match["home_goals"], match["away_goals"]),
                    **feats,
                }
            )

        elo.update(home_id, away_id, match["home_goals"], match["away_goals"], neutral)
        pi.update(home_id, away_id, match["home_goals"], match["away_goals"])
        berrar.update(home_id, away_id, match["home_goals"], match["away_goals"])
        context.update(match["league_id"], season, home_id, away_id, match["home_goals"], match["away_goals"])

    return samples


def split_by_season(
    samples: list,
    train_seasons: list = TRAIN_SEASONS,
    validate_season: int = VALIDATE_SEASON,
    calibrate_season: int = CALIBRATE_SEASON,
    test_season: int = TEST_SEASON,
) -> dict:
    others = {validate_season, calibrate_season, test_season}
    assert len(others) == 3, "validate/calibrate/test seasons must be distinct"
    assert not (set(train_seasons) & others), "train_seasons must not overlap validate/calibrate/test"

    buckets = {"train": [], "validate": [], "calibrate": [], "test": []}
    for sample in samples:
        season = sample["season"]
        if season in train_seasons:
            buckets["train"].append(sample)
        elif season == validate_season:
            buckets["validate"].append(sample)
        elif season == calibrate_season:
            buckets["calibrate"].append(sample)
        elif season == test_season:
            buckets["test"].append(sample)
    return buckets


def verify_no_leakage(buckets: dict) -> None:
    """Season boundaries never overlap in real kickoff dates -- a cheap,
    printable leakage guard."""
    order = ["train", "validate", "calibrate", "test"]
    prev_max = None
    prev_name = None
    for name in order:
        bucket = buckets[name]
        if not bucket:
            print(f"WARNING: bucket '{name}' is empty")
            continue
        times = [s["kickoff_utc"] for s in bucket]
        bucket_min, bucket_max = min(times), max(times)
        if prev_max is not None:
            assert prev_max < bucket_min, f"leakage: {prev_name} max {prev_max} >= {name} min {bucket_min}"
        prev_max = bucket_max
        prev_name = name

    print(
        f"OK: no season overlap, {len(buckets['train'])} train / "
        f"{len(buckets['validate'])} validate / {len(buckets['calibrate'])} calibrate / "
        f"{len(buckets['test'])} test"
    )
