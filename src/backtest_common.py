import elo as elo_module
import features as features_module
import promotion

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
ALL_SEASONS = list(range(2017, 2026))


def actual_class(home_goals: int, away_goals: int) -> int:
    """0 = home win, 1 = draw, 2 = away win."""
    if home_goals > away_goals:
        return 0
    if home_goals < away_goals:
        return 2
    return 1


def collect_samples(matches: list, transitions: dict, use_mov: bool = True) -> list:
    """One forward pass over the combined chronological PL+Championship stream.
    A match becomes a scored sample only if it's in the PL and both teams have
    matches_played >= MIN_GAMES (checked BEFORE this match). Every match
    unconditionally applies pending promotion transitions, updates Elo, and
    (via the pre-loaded, date-filtered FeatureStore) contributes to form/h2h,
    regardless of scoring eligibility."""
    elo = elo_module.EloRatings(use_mov=use_mov)
    store = features_module.FeatureStore()
    store.load(matches)

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

        eligible = (
            match["league_id"] == PL_ID
            and elo.matches_played.get(home_id, 0) >= MIN_GAMES
            and elo.matches_played.get(away_id, 0) >= MIN_GAMES
        )

        if eligible:
            feats = store.match_features(home_id, away_id, before, elo, neutral)
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
