"""Generate forward predictions for upcoming PL fixtures.

Replays the full PL+Championship history (Elo + point-in-time feature
stores), applies promotion transitions for the new season, then runs the
shipped outcome + goals models on not-started fixtures within the horizon.

This is the PRD 13.1 "initial prediction" stage: no confirmed lineups exist
yet for future fixtures, so squad_disruption_diff is 0.0 by the neutral
fallback, and missing_players_diff reflects whatever injury records the
provider has already tagged to the upcoming fixture. Stdlib-only (plus the
pipeline's own modules) -- no numpy/sklearn at predict time.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import backtest_common
import config
import db
import elo as elo_module
import features as features_module
import goals_model
import matches as matches_module
import model_registry
import outcome_model
import promotion
import richer_features

OUTPUTS_DIR = config.ROOT_DIR / "outputs"
DEFAULT_HORIZON_DAYS = 8
PREDICT_SEASONS = list(range(2017, 2027))


def replay_state(matches: list, transitions: dict):
    """One chronological pass over all completed matches: Elo updates,
    promotion transitions, feature-store history. Mirrors
    backtest_common.collect_samples without the sample scoring."""
    elo = elo_module.EloRatings(use_mov=True)
    store = features_module.FeatureStore()
    store.load(matches)
    applied = set()
    for m in matches:
        promotion.apply_pending_transition(elo, m["home_team_id"], m["season"], transitions, applied)
        promotion.apply_pending_transition(elo, m["away_team_id"], m["season"], transitions, applied)
        elo.update(m["home_team_id"], m["away_team_id"], m["home_goals"], m["away_goals"], m["neutral"])
    return elo, store, applied


def load_upcoming(conn, horizon_days: int) -> list:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    rows = conn.execute(
        """
        SELECT f.*, th.name AS home_name, ta.name AS away_name
        FROM fixtures f
        JOIN teams th ON th.team_id = f.home_team_id
        JOIN teams ta ON ta.team_id = f.away_team_id
        WHERE f.league_id = ? AND f.status_short = 'NS'
          AND f.kickoff_utc >= ? AND f.kickoff_utc <= ?
        ORDER BY f.kickoff_utc ASC
        """,
        (backtest_common.PL_ID, now.isoformat(), horizon.isoformat()),
    ).fetchall()
    return rows


def confidence_band(p_max: float) -> str:
    if p_max >= 0.55:
        return "HIGH"
    if p_max >= 0.45:
        return "MED"
    return "LOW"


def build_why(feats: dict, p: tuple) -> str:
    parts = []
    if abs(feats["elo_diff"]) >= 25:
        side = "home" if feats["elo_diff"] > 0 else "away"
        parts.append(f"Elo edge {side} ({feats['elo_diff']:+.0f})")
    if abs(feats["ew_form_diff"]) >= 0.4:
        side = "home" if feats["ew_form_diff"] > 0 else "away"
        parts.append(f"recent form favors {side} ({feats['ew_form_diff']:+.2f} ppg)")
    if abs(feats["missing_players_diff"]) >= 2:
        side = "away" if feats["missing_players_diff"] > 0 else "home"
        parts.append(f"injuries favor {side} ({feats['missing_players_diff']:+.0f} out)")
    if abs(feats["rest_diff"]) >= 2:
        side = "home" if feats["rest_diff"] > 0 else "away"
        parts.append(f"{side} better rested ({feats['rest_diff']:+.1f}d)")
    if not parts:
        parts.append("evenly matched on rating and form")
    return "; ".join(parts)


def run_predictions(horizon_days: int = DEFAULT_HORIZON_DAYS, quiet: bool = False) -> dict:
    started = datetime.now(timezone.utc)
    conn = db.get_connection()

    played = matches_module.load_matches(conn, [backtest_common.PL_ID, backtest_common.CHAMP_ID], PREDICT_SEASONS)
    transitions = promotion.compute_transitions(
        conn, backtest_common.PL_ID, backtest_common.CHAMP_ID, PREDICT_SEASONS
    )
    elo, store, applied = replay_state(played, transitions)

    stat_rows = db.get_fixture_statistics_by_league(conn, [backtest_common.PL_ID])
    shot_store = richer_features.ShotStatsStore()
    shot_store.load(stat_rows)
    missing_index = richer_features.MissingPlayersIndex()
    missing_index.load(db.get_missing_player_counts(conn, [backtest_common.PL_ID]))
    squad_store = richer_features.SquadDisruptionStore()
    squad_store.load(db.get_lineup_players_by_league(conn, [backtest_common.PL_ID]))

    # Registry gate (PRD 17.3/17.4): refuse to predict from artifacts the
    # registry can't account for, and stamp every prediction with the exact
    # registered release it came from.
    outcome_path = config.MODELS_DIR / "outcome_model_pl.json"
    goals_path = config.MODELS_DIR / "goals_model.json"
    outcome_entry = model_registry.verify_deployed(outcome_path)
    goals_entry = model_registry.verify_deployed(goals_path)
    outcome = outcome_model.load_model(outcome_path)
    goals = goals_model.load_model(goals_path)

    upcoming = load_upcoming(conn, horizon_days)
    market = db.get_market_outcome_probs(conn, [r["fixture_id"] for r in upcoming])

    predictions = []
    for row in upcoming:
        home_id, away_id = row["home_team_id"], row["away_team_id"]
        season = row["season"]
        before = datetime.fromisoformat(row["kickoff_utc"])

        # Promotion/newcomer adjustments for teams whose first match of the
        # new season hasn't been played yet.
        promotion.apply_pending_transition(elo, home_id, season, transitions, applied)
        promotion.apply_pending_transition(elo, away_id, season, transitions, applied)

        feats = store.match_features(home_id, away_id, before, elo, neutral=False)
        feats.update(
            richer_features.richer_match_features(
                row["fixture_id"], home_id, away_id, before, shot_store, missing_index, squad_store
            )
        )

        sample = {**feats, "home_team_id": home_id, "away_team_id": away_id}
        p_home, p_draw, p_away = outcome_model.predict_proba(sample, outcome)

        mu_home, mu_away = goals_model.expected_goals(home_id, away_id, goals)
        matrix = goals_model.score_matrix(mu_home, mu_away, rho=goals.get("rho", 0.0))
        likely = goals_model.most_likely_score(matrix)
        p_over, p_under = goals_model.over_under_prob(matrix)
        p_btts = goals_model.btts_prob(matrix)

        p_max = max(p_home, p_draw, p_away)
        mkt = market.get(row["fixture_id"])
        predictions.append(
            {
                "fixture_id": row["fixture_id"],
                "league": "EPL",
                "season": season,
                "kickoff_utc": row["kickoff_utc"],
                "home": row["home_name"],
                "away": row["away_name"],
                "home_team_id": home_id,
                "away_team_id": away_id,
                "p_home": round(p_home * 100, 1),
                "p_draw": round(p_draw * 100, 1),
                "p_away": round(p_away * 100, 1),
                # Bookmaker consensus (median margin-removed prob across
                # bookmakers, latest archived snapshot) -- benchmark only,
                # never a model input (PRD 10.8). Null when no snapshot yet.
                "market_p_home": round(mkt["home"] * 100, 1) if mkt else None,
                "market_p_draw": round(mkt["draw"] * 100, 1) if mkt else None,
                "market_p_away": round(mkt["away"] * 100, 1) if mkt else None,
                "market_snapshot": mkt["snapshot"] if mkt else None,
                "market_bookmakers": mkt["bookmakers"] if mkt else None,
                "likely_score": f"{likely[0]}-{likely[1]}",
                "expected_goals": {"home": round(mu_home, 2), "away": round(mu_away, 2)},
                "over_2_5": round(p_over * 100, 1),
                "btts": round(p_btts * 100, 1),
                "confidence": confidence_band(p_max),
                "why": build_why(feats, (p_home, p_draw, p_away)),
                "stage": "initial",  # pre-lineup (PRD 13.1); no confirmed-XI signal yet
                "features": {k: round(v, 4) for k, v in feats.items()},
            }
        )

    payload = {
        "generated_at": started.isoformat(),
        "horizon_days": horizon_days,
        "model": {
            "outcome": outcome.get("label"),
            "outcome_test_log_loss": outcome.get("test_log_loss"),
            "goals": goals.get("type"),
            "goals_rho": goals.get("rho"),
        },
        # PRD 17.4: every published prediction is traceable to the exact
        # registered model release (version + artifact checksum).
        "model_registry": {
            "outcome": {
                "version": outcome_entry["version"],
                "checksum_sha256": outcome_entry["checksum_sha256"],
                "registered_at": outcome_entry["registered_at"],
            },
            "goals": {
                "version": goals_entry["version"],
                "checksum_sha256": goals_entry["checksum_sha256"],
                "registered_at": goals_entry["registered_at"],
            },
        },
        "predictions": predictions,
    }

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / "predictions.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    status = {
        "success": True,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"upcoming_predicted": len(predictions)},
    }
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATUS_DIR / "predict_status.json").write_text(json.dumps(status, indent=2))

    if not quiet:
        for p in predictions:
            print(
                f"{p['kickoff_utc'][:16]}  {p['home']:22s} vs {p['away']:22s} "
                f"H {p['p_home']:4.1f}%  D {p['p_draw']:4.1f}%  A {p['p_away']:4.1f}%  "
                f"score {p['likely_score']}  O2.5 {p['over_2_5']:4.1f}%  [{p['confidence']}]"
            )
        print(f"\nwrote {OUTPUTS_DIR / 'predictions.json'} ({len(predictions)} matches)")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate predictions for upcoming PL fixtures.")
    parser.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    args = parser.parse_args()
    run_predictions(horizon_days=args.horizon_days)


if __name__ == "__main__":
    main()
