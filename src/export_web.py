"""Export real pipeline data to web/src/data/live.json for the frontend.

Combines: outputs/predictions.json (upcoming matches), current Elo + season
standings (SQLite), the shipped model's backtest test-season scoring (the
"ledger" -- clearly labelled backtest, since no live predictions have locked
yet), and the latest evaluate_report (calibration bands, log-loss vs
baselines). Stdlib-only. Run after predict.py:

    python3 src/predict.py && python3 src/export_web.py
"""

import json
import math
from datetime import datetime, timezone

import backtest_common
import config
import db
import goals_model
import matches as matches_module
import metrics
import model_registry
import outcome_model
import predict
import promotion
import richer_features

WEB_DATA_DIR = config.ROOT_DIR / "web" / "src" / "data"
CURRENT_SEASON = 2026
LEDGER_ROWS = 15

FACTOR_LABELS = {
    "elo_diff": "Team strength (Elo)",
    "ew_form_diff": "Recent form (weighted)",
    "h2h_signal": "Head-to-head",
    "ew_gf_diff": "Attack output",
    "ew_ga_diff": "Defensive record",
    "sot_diff": "Shots on target",
    "possession_diff": "Possession",
    "missing_players_diff": "Missing players",
    "squad_disruption_diff": "Squad disruption",
    "rest_diff": "Rest advantage",
    "congestion_diff": "Fixture congestion",
}


def _ko_label(kickoff_utc: str) -> str:
    dt = datetime.fromisoformat(kickoff_utc)
    return dt.strftime("%a %H:%M")


def build_factors(features: dict, model: dict, top_n: int = 5) -> list:
    """Real per-feature contributions to the home-vs-away logit margin of the
    shipped logistic model: z-scored value x (coef_home - coef_away), through
    the calibration temperature. Positive pushes toward the home win."""
    classes = list(model["classes"])
    hi, ai = classes.index("home"), classes.index("away")
    temperature = model.get("temperature", 1.0)
    out = []
    for j, name in enumerate(model["features"]):
        z = (features[name] - model["means"][j]) / model["stds"][j]
        weight = z * (model["coef"][hi][j] - model["coef"][ai][j]) / temperature
        if abs(weight) < 0.005:
            continue
        out.append({"label": FACTOR_LABELS.get(name, name), "weight": round(weight, 2)})
    out.sort(key=lambda f: -abs(f["weight"]))
    return out[:top_n]


def build_score_matrix(mu_home: float, mu_away: float, rho: float) -> dict:
    matrix = goals_model.score_matrix(mu_home, mu_away, max_goals=6, rho=rho)
    peak_h, peak_a = goals_model.most_likely_score(matrix)
    over = {}
    for line in (1.5, 2.5, 3.5):
        p_over, _ = goals_model.over_under_prob(matrix, line)
        over[str(line)] = round(p_over * 100, 1)
    return {
        "grid": [[round(cell * 100, 1) for cell in row] for row in matrix],
        "peakRow": peak_h,
        "peakCol": peak_a,
        "over15": over["1.5"],
        "over25": over["2.5"],
        "over35": over["3.5"],
        "btts": round(goals_model.btts_prob(matrix) * 100, 1),
    }


def fixture_rounds(conn, fixture_ids: list) -> dict:
    if not fixture_ids:
        return {}
    marks = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"SELECT fixture_id, round FROM fixtures WHERE fixture_id IN ({marks})", fixture_ids
    ).fetchall()
    return {r["fixture_id"]: r["round"] for r in rows}


def build_freshness(conn) -> dict:
    def max_of(sql: str) -> str:
        row = conn.execute(sql, (backtest_common.PL_ID,)).fetchone()
        return row[0]

    return {
        "fixtures": max_of("SELECT MAX(updated_at) FROM fixtures WHERE league_id = ?"),
        "injuries": max_of("SELECT MAX(fetched_at) FROM injuries WHERE league_id = ?"),
        "lineups": max_of(
            "SELECT MAX(l.fetched_at) FROM lineups l"
            " JOIN fixtures f ON f.fixture_id = l.fixture_id WHERE f.league_id = ?"
        ),
        "odds": max_of(
            "SELECT MAX(o.fetched_at) FROM odds_snapshots o"
            " JOIN fixtures f ON f.fixture_id = o.fixture_id WHERE f.league_id = ?"
        ),
    }


def build_matches(predictions: dict, missing_counts: dict, model: dict, rounds: dict) -> list:
    rho = predictions["model"].get("goals_rho") or 0.0
    out = []
    for p in predictions["predictions"]:
        fid = p["fixture_id"]
        out.append(
            {
                "id": fid,
                "lg": "EPL",
                "home": p["home"],
                "away": p["away"],
                "ko": _ko_label(p["kickoff_utc"]),
                "h": p["p_home"],
                "d": p["p_draw"],
                "a": p["p_away"],
                "mh": p.get("market_p_home"),  # null until an odds snapshot exists for the fixture
                "md": p.get("market_p_draw"),
                "ma": p.get("market_p_away"),
                "marketSnapshot": p.get("market_snapshot"),
                "marketBookmakers": p.get("market_bookmakers"),
                "score": p["likely_score"].replace("-", "–"),
                "conf": p["confidence"],
                "st": "initial · lineups pending",
                "why": p["why"],
                "kickoffUtc": p["kickoff_utc"],
                "round": rounds.get(fid),
                "muHome": p["expected_goals"]["home"],
                "muAway": p["expected_goals"]["away"],
                "matrix": build_score_matrix(
                    p["expected_goals"]["home"], p["expected_goals"]["away"], rho
                ),
                "missingHome": missing_counts.get((fid, p["home_team_id"]), 0),
                "missingAway": missing_counts.get((fid, p["away_team_id"]), 0),
                "factors": build_factors(p["features"], model),
                "stage": p["stage"],
            }
        )
    return out


def build_standings(conn) -> list:
    played_matches = matches_module.load_matches(
        conn, [backtest_common.PL_ID, backtest_common.CHAMP_ID], list(range(2017, CURRENT_SEASON + 1))
    )
    transitions = promotion.compute_transitions(
        conn, backtest_common.PL_ID, backtest_common.CHAMP_ID, list(range(2017, CURRENT_SEASON + 1))
    )
    elo, _, applied = predict.replay_state(played_matches, transitions)

    rosters = promotion.season_rosters(conn, backtest_common.PL_ID, [CURRENT_SEASON])
    team_ids = rosters[CURRENT_SEASON]
    names = {
        row["team_id"]: row["name"]
        for row in conn.execute("SELECT team_id, name FROM teams").fetchall()
    }

    stats = {t: {"played": 0, "gf": 0, "ga": 0, "points": 0} for t in team_ids}
    for m in played_matches:
        if m["league_id"] != backtest_common.PL_ID or m["season"] != CURRENT_SEASON:
            continue
        for team, gf, ga in (
            (m["home_team_id"], m["home_goals"], m["away_goals"]),
            (m["away_team_id"], m["away_goals"], m["home_goals"]),
        ):
            s = stats[team]
            s["played"] += 1
            s["gf"] += gf
            s["ga"] += ga
            s["points"] += 3 if gf > ga else (1 if gf == ga else 0)

    # Apply pending season transitions so promoted teams show their adjusted Elo.
    for t in team_ids:
        promotion.apply_pending_transition(elo, t, CURRENT_SEASON, transitions, applied)

    rows = []
    for t in team_ids:
        s = stats[t]
        gd = s["gf"] - s["ga"]
        rows.append(
            {
                "team": names.get(t, f"team {t}"),
                "played": s["played"],
                "goalDiff": f"{gd:+d}".replace("-", "−") if gd else "0",
                "points": s["points"],
                "elo": round(elo.get(t)),
            }
        )
    rows.sort(key=lambda r: (-r["points"], -r["elo"]))
    return rows


def build_ledger_and_bands(conn) -> tuple:
    """Score the held-out 2025/26 test season with the shipped model -- the
    honest 'ledger' until live predictions start locking. Clearly labelled
    backtest."""
    matches = matches_module.load_matches(conn, [backtest_common.PL_ID, backtest_common.CHAMP_ID])
    transitions = promotion.compute_transitions(
        conn, backtest_common.PL_ID, backtest_common.CHAMP_ID, backtest_common.ALL_SEASONS
    )
    samples = backtest_common.collect_samples(matches, transitions, use_mov=True)
    samples = richer_features.enrich_samples(samples, conn)
    buckets = backtest_common.split_by_season(samples)

    model = outcome_model.load_model(config.MODELS_DIR / "outcome_model_pl.json")
    names = {row["team_id"]: row["name"] for row in conn.execute("SELECT team_id, name FROM teams").fetchall()}

    scored = []
    for s in buckets["test"]:
        ph, pd, pa = outcome_model.predict_proba(s, model)
        scored.append({**s, "p_home": ph, "p_draw": pd, "p_away": pa})

    version = "logistic11_ew · backtest"
    ledger = []
    for s in scored[-LEDGER_ROWS:]:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        probs_label = f"{round(p[0] * 100)}/{round(p[1] * 100)}/{round(p[2] * 100)}"
        ledger.append(
            {
                "date": s["kickoff_utc"].strftime("%Y-%m-%d"),
                "lg": "EPL",
                "fixture": f"{names[s['home_team_id']]} v {names[s['away_team_id']]}",
                "published": probs_label,
                "final": probs_label,
                "result": f"{s['home_goals']}–{s['away_goals']}",
                "won": max(range(3), key=lambda i: p[i]) == s["cls"],
                "logLoss": round(-math.log(max(p[s["cls"]], 1e-15)), 2),
                "modelVersion": version,
            }
        )
    ledger.reverse()

    test_metrics = metrics.all_outcome_metrics(scored)
    calibration = metrics.calibration_error(scored)

    bands = []
    bars = []
    for b in calibration["bins"]:
        if not b["count"]:
            continue
        bands.append(
            {
                "band": f"{round(b['lo'] * 100)}–{round(b['hi'] * 100)}%",
                "n": b["count"],
                "pred": round(b["predicted_rate"] * 100, 1),
                "actual": round(b["actual_rate"] * 100, 1),
            }
        )
        bars.append(round(b["actual_rate"] * 100))

    headline = {
        "n_test": test_metrics["n"],
        "log_loss": round(test_metrics["log_loss"], 3),
        "rps": round(test_metrics["rps"], 3),
        "accuracy": round(test_metrics["accuracy"] * 100, 1),
        "ece": round(calibration["ece"], 3),
        "season": "2025/26 held-out test season (backtest)",
    }
    return ledger, bands, bars, headline


def main() -> None:
    conn = db.get_connection()
    predictions = json.loads((predict.OUTPUTS_DIR / "predictions.json").read_text())

    missing_index = richer_features.MissingPlayersIndex()
    missing_index.load(db.get_missing_player_counts(conn, [backtest_common.PL_ID]))

    ledger, bands, bars, headline = build_ledger_and_bands(conn)

    outcome_path = config.MODELS_DIR / "outcome_model_pl.json"
    registry_entry = model_registry.verify_deployed(outcome_path)
    model = outcome_model.load_model(outcome_path)
    freq_ll = 1.0851  # test-season frequency baseline, from evaluate_report
    ll = model["test_log_loss"]

    fixture_ids = [p["fixture_id"] for p in predictions["predictions"]]
    rounds = fixture_rounds(conn, fixture_ids)

    live = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "predictions_generated_at": predictions["generated_at"],
        "model_version": registry_entry["version"],
        "model_checksum": registry_entry["checksum_sha256"],
        "freshness": build_freshness(conn),
        "matches": build_matches(predictions, missing_index._counts, model, rounds),
        "standings": {"EPL": build_standings(conn), "LAL": [], "SEA": [], "BUN": [], "MLS": []},
        "league_perf": {
            "EPL": {"ll": f"{ll:.2f}", "base": f"{ll - freq_ll:+.2f}".replace("-", "−"), "mkt": "—"},
            "LAL": {"ll": "—", "base": "—", "mkt": "—"},
            "SEA": {"ll": "—", "base": "—", "mkt": "—"},
            "BUN": {"ll": "—", "base": "—", "mkt": "—"},
            "MLS": {"ll": "—", "base": "—", "mkt": "—"},
        },
        "ledger": ledger,
        "confidence_bands": bands,
        "calibration_bars": bars,
        "league_log_loss": [
            {
                "code": "EPL",
                "label": "EPL",
                "value": max(5, min(95, round((1.20 - ll) / (1.20 - 0.90) * 100))),
                "detail": f"{ll:.2f} / {freq_ll:.2f}",
                "belowBaseline": ll < freq_ll,
            }
        ],
        "headline": headline,
    }

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEB_DATA_DIR / "live.json"
    out_path.write_text(json.dumps(live, indent=2, ensure_ascii=False))
    print(f"wrote {out_path}: {len(live['matches'])} matches, {len(ledger)} ledger rows, {len(bands)} bands")


if __name__ == "__main__":
    main()
