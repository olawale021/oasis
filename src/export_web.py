"""Export real pipeline data to web/src/data/live.json for the frontend.

Combines: outputs/predictions.json (upcoming matches, all live leagues),
current Elo + season standings per league (SQLite), each shipped model's
backtest test-season scoring (the "ledger" -- clearly labelled backtest,
since no live predictions have locked yet), and per-league baseline
comparisons. Stdlib-only. Run after predict.py:

    python3 src/predict.py && python3 src/export_web.py
"""

import json
import math
from datetime import datetime, timezone

import backtest_common
import config
import db
from betting.export import build_betting
import goals_model
import leagues
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
    "form_diff": "Recent form",
    "ew_form_diff": "Recent form (weighted)",
    "h2h_signal": "Head-to-head",
    "gf_diff": "Attack output",
    "ga_diff": "Defensive record",
    "ew_gf_diff": "Attack output",
    "ew_ga_diff": "Defensive record",
    "sot_diff": "Shots on target",
    "possession_diff": "Possession",
    "missing_players_diff": "Missing players",
    "squad_disruption_diff": "Squad disruption",
    "rest_diff": "Rest advantage",
    "congestion_diff": "Fixture congestion",
    "venue_form_diff": "Home/away venue form",
    "pi_pred_gd": "Learned rating margin (pi)",
    "ber_gh": "Rated attack output (home)",
    "ber_ga": "Rated attack output (away)",
    "ghost_game": "Closed-door match",
    "short_rest_diff": "Short-rest disadvantage",
    "long_rest_diff": "Full-rest advantage",
    "ew10_form_diff": "Recent form (long window)",
    "ew10_gf_diff": "Attack output (long window)",
    "ew10_ga_diff": "Defensive record (long window)",
    "elo_trend_diff": "Rating momentum",
    "sched_strength_diff": "Schedule strength",
    "value_diff": "Squad market value",
    "xi_strength_diff": "Expected XI strength",
    "rest_all_diff": "Rest advantage (all comps)",
    "congestion_all_diff": "Fixture congestion (all comps)",
    "xg_diff": "Expected goals for",
    "xga_diff": "Expected goals against",
    "corner_diff": "Corners",
}

# Plain-language meaning of each factor label, for hover text on the match page.
FACTOR_GLOSSARY = {
    "Team strength (Elo)": "Long-run rating from results, adjusted for margin and home advantage.",
    "Recent form": "Points per game over the last five league matches.",
    "Recent form (weighted)": "Points per game over recent matches, weighting the latest most.",
    "Head-to-head": "Result history between these two clubs, trusted only after several meetings.",
    "Attack output": "Goals scored per game recently, weighted to the latest matches.",
    "Defensive record": "Goals conceded per game recently, weighted to the latest matches.",
    "Shots on target": "Recent shots on target per game, home minus away.",
    "Possession": "Recent possession share per game, home minus away.",
    "Missing players": "Reported absences from the injury feed, home minus away.",
    "Squad disruption": "Share of the regular eleven missing from the actual lineup (final stage only).",
    "Rest advantage": "Days since each side's last league match.",
    "Fixture congestion": "Matches played in the last fortnight, league only.",
    "Rest advantage (all comps)": "Days since each side's last match in any competition.",
    "Fixture congestion (all comps)": "Matches in the last fortnight including cups and Europe.",
    "Home/away venue form": "Form at home for the home side versus away form for the visitors.",
    "Learned rating margin (pi)": "Predicted goal margin from pi-ratings, a learned form-and-strength system.",
    "Rated attack output (home)": "Home side's attack rating from the Berrar rating system.",
    "Rated attack output (away)": "Away side's attack rating from the Berrar rating system.",
    "Closed-door match": "Played without spectators.",
    "Rating momentum": "How each side's Elo has moved over recent matches.",
    "Schedule strength": "Average Elo of recent opponents.",
    "Squad market value": "Log ratio of the two squads' Transfermarkt values as of kickoff, top 25 players each.",
    "Expected XI strength": "Summed plus-minus ratings of each side's expected eleven, from lineup history.",
    "Expected goals for": "Recent expected goals created per game, home minus away.",
    "Expected goals against": "Recent expected goals conceded per game, home minus away.",
    "Corners": "Recent corners per game, home minus away.",
}


def _ko_label(kickoff_utc: str) -> str:
    dt = datetime.fromisoformat(kickoff_utc)
    return dt.strftime("%a %H:%M")


def build_factors(features: dict, model: dict, top_n: int = 5) -> list:
    """Real per-feature contributions to the home-vs-away logit margin of the
    shipped logistic model: z-scored value x (coef_home - coef_away), through
    the calibration temperature. Positive pushes toward the home win.
    For a blend artifact, factors come from its dominant logistic component
    (an approximation; the blend's league component carries most weight)."""
    if model.get("type") == "blend":
        logistic_components = [
            c for c in model["components"] if c["model"].get("type") == "multinomial_logistic"
        ]
        if not logistic_components:
            return []
        model = max(logistic_components, key=lambda c: c["weight"])["model"]
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
    grid = [[round(cell * 100, 1) for cell in row] for row in matrix]
    return {
        "grid": grid,
        "peakRow": peak_h,
        "peakCol": peak_a,
        "peakPct": grid[peak_h][peak_a],
        "over15": over["1.5"],
        "over25": over["2.5"],
        "over35": over["3.5"],
        "btts": round(goals_model.btts_prob(matrix) * 100, 1),
    }


def conditional_top_score(grid: list, outcome: int) -> tuple:
    """Most likely scoreline CONSISTENT WITH the given outcome (0=home win,
    1=draw, 2=away win). The unconditional mode is 1-1 for almost any
    realistic pair of goal rates (Poisson mode = floor(mu), and football mus
    live in [1,2)), so the outcome-conditional mode is what actually
    differentiates matches for display."""
    best, best_p = (0, 0), -1.0
    for i, row in enumerate(grid):
        for j, cell in enumerate(row):
            consistent = i > j if outcome == 0 else (i == j if outcome == 1 else i < j)
            if consistent and cell > best_p:
                best_p, best = cell, (i, j)
    return f"{best[0]}–{best[1]}", best_p


def fixture_rounds(conn, fixture_ids: list) -> dict:
    if not fixture_ids:
        return {}
    marks = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"SELECT fixture_id, round FROM fixtures WHERE fixture_id IN ({marks})", fixture_ids
    ).fetchall()
    return {r["fixture_id"]: r["round"] for r in rows}


def build_freshness(conn, target_ids: list) -> dict:
    marks = ", ".join("?" for _ in target_ids)

    def max_of(sql: str) -> str:
        row = conn.execute(sql.format(marks=marks), target_ids).fetchone()
        return row[0]

    return {
        "fixtures": max_of("SELECT MAX(updated_at) FROM fixtures WHERE league_id IN ({marks})"),
        "injuries": max_of("SELECT MAX(fetched_at) FROM injuries WHERE league_id IN ({marks})"),
        "lineups": max_of(
            "SELECT MAX(l.fetched_at) FROM lineups l"
            " JOIN fixtures f ON f.fixture_id = l.fixture_id WHERE f.league_id IN ({marks})"
        ),
        "odds": max_of(
            "SELECT MAX(o.fetched_at) FROM odds_snapshots o"
            " JOIN fixtures f ON f.fixture_id = o.fixture_id WHERE f.league_id IN ({marks})"
        ),
    }


def apply_final_locks(conn, predictions: dict) -> int:
    """Once a fixture has a final-stage lock (confirmed lineups), the board
    shows THAT forecast rather than the hourly pre-lineup one: probabilities,
    scoreline, stage label and explanation are replaced in place."""
    rows = conn.execute("SELECT * FROM locked_predictions WHERE stage = 'final' AND settled_at IS NULL").fetchall()
    by_id = {r["fixture_id"]: r for r in rows}
    n = 0
    for p in predictions["predictions"]:
        r = by_id.get(p["fixture_id"])
        if not r:
            continue
        p.update({
            "p_home": r["p_home"], "p_draw": r["p_draw"], "p_away": r["p_away"],
            "likely_score": r["likely_score"], "over_2_5": r["over_2_5"], "btts": r["btts"],
            "confidence": r["confidence"], "why": r["why"], "stage": "final · lineups confirmed",
            "expected_goals": {"home": r["mu_home"], "away": r["mu_away"]},
        })
        try:
            p["features"] = json.loads(r["features_json"])
        except Exception:
            pass
        n += 1
    return n


def build_matches(predictions: dict, missing_counts: dict, outcome_models: dict, rounds: dict) -> list:
    out = []
    for p in predictions["predictions"]:
        fid = p["fixture_id"]
        code = p["league"]
        rho = predictions["models"][code].get("goals_rho") or 0.0
        matrix = build_score_matrix(p["expected_goals"]["home"], p["expected_goals"]["away"], rho)
        outcome = max(range(3), key=lambda i: (p["p_home"], p["p_draw"], p["p_away"])[i])
        cond_score, cond_pct = conditional_top_score(matrix["grid"], outcome)
        out.append(
            {
                "id": fid,
                "lg": code,
                "home": p["home"],
                "away": p["away"],
                "homeId": p["home_team_id"],
                "awayId": p["away_team_id"],
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
                "matrix": matrix,
                "condScore": cond_score,
                "condPct": cond_pct,
                "pick": ["home", "draw", "away"][outcome],
                "missingHome": missing_counts.get((fid, p["home_team_id"]), 0),
                "missingAway": missing_counts.get((fid, p["away_team_id"]), 0),
                "factors": build_factors(p["features"], outcome_models[code]),
                "stage": p["stage"],
            }
        )
    return out


TASTER_PER_DAY = 2
TASTER_PATH = config.DATA_DIR / "taster.json"


def build_taster(matches: list, today: str = None) -> dict:
    """Free-tier taster: the TASTER_PER_DAY highest-confidence fixtures of the
    current UTC day, pinned the first time the chain runs that day and never
    recomputed, so a lineup-stage update cannot swap in a third fixture and
    leak an extra prediction. Persisted in data/taster.json ({date: [ids]});
    the site only ever reads today's entry, so old dates are pruned here."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pinned = {}
    if TASTER_PATH.exists():
        try:
            pinned = json.loads(TASTER_PATH.read_text())
        except json.JSONDecodeError:
            pinned = {}
    if today not in pinned:
        todays = [m for m in matches if m["kickoffUtc"][:10] == today]
        todays.sort(key=lambda m: (-max(m["h"], m["d"], m["a"]), m["kickoffUtc"], m["id"]))
        pinned[today] = [m["id"] for m in todays[:TASTER_PER_DAY]]
    pinned = {d: ids for d, ids in pinned.items() if d >= today}
    TASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASTER_PATH.write_text(json.dumps(pinned, indent=2))
    return pinned


def build_bookmakers(conn) -> list:
    """Distinct bookmaker names behind the market line (Match Winner rows,
    last 30 days), so the site can say exactly whose odds the median is."""
    rows = conn.execute(
        """
        SELECT DISTINCT bookmaker FROM odds_snapshots
        WHERE market_id = 1 AND fetched_at >= datetime('now', '-30 days')
        ORDER BY bookmaker
        """
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def build_standings(conn, league_cfg: dict) -> list:
    target_id, feeder_id = league_cfg["league_id"], league_cfg["feeder_id"]
    league_ids = [target_id] + ([feeder_id] if feeder_id else [])
    seasons = list(range(backtest_common.HISTORY_START, CURRENT_SEASON + 1))
    played_matches = matches_module.load_matches(conn, league_ids, seasons)
    transitions = (
        promotion.compute_transitions(conn, target_id, feeder_id, seasons) if feeder_id else {}
    )
    elo, _, applied, _, _, _ = predict.replay_state(played_matches, transitions)

    rosters = promotion.season_rosters(conn, target_id, [CURRENT_SEASON])
    team_ids = rosters.get(CURRENT_SEASON, [])
    names = {
        row["team_id"]: row["name"]
        for row in conn.execute("SELECT team_id, name FROM teams").fetchall()
    }

    stats = {t: {"played": 0, "gf": 0, "ga": 0, "points": 0} for t in team_ids}
    for m in played_matches:
        if m["league_id"] != target_id or m["season"] != CURRENT_SEASON:
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
                "teamId": t,
                "played": s["played"],
                "goalDiff": f"{gd:+d}".replace("-", "−") if gd else "0",
                "points": s["points"],
                "elo": round(elo.get(t)),
            }
        )
    rows.sort(key=lambda r: (-r["points"], -r["elo"]))
    return rows


def frequency_log_loss(fit_samples: list, test_samples: list) -> float:
    """League-frequency baseline: constant class distribution from the fit
    seasons, scored on the test season."""
    counts = [0, 0, 0]
    for s in fit_samples:
        counts[s["cls"]] += 1
    total = sum(counts) or 1
    probs = [max(c / total, 1e-15) for c in counts]
    return sum(-math.log(probs[s["cls"]]) for s in test_samples) / max(len(test_samples), 1)


def build_backtest_sections(conn) -> dict:
    """Per-league backtest scoring of the shipped models on their held-out
    test seasons: ledger rows, aggregate calibration, per-league performance,
    and the combined headline. Honest 'record' until live predictions lock."""
    names = {row["team_id"]: row["name"] for row in conn.execute("SELECT team_id, name FROM teams").fetchall()}

    all_scored = []
    ledger = []
    league_perf = {}
    league_log_loss = []
    versions = {}
    retro_probs = {}

    for code, cfg in leagues.TARGETS.items():
        outcome_path = config.MODELS_DIR / cfg["outcome_artifact"]
        if not outcome_path.exists():
            continue
        entry = model_registry.verify_deployed(outcome_path)
        model = outcome_model.load_model(outcome_path)
        web_code = cfg["web_code"]
        versions[web_code] = entry["version"]

        target_id, feeder_id = cfg["league_id"], cfg["feeder_id"]
        league_ids = [target_id] + ([feeder_id] if feeder_id else [])
        matches = matches_module.load_matches(conn, league_ids)
        transitions = (
            promotion.compute_transitions(conn, target_id, feeder_id, backtest_common.ALL_SEASONS)
            if feeder_id
            else {}
        )
        samples = backtest_common.collect_samples(matches, transitions, use_mov=True, target_league_id=target_id)
        samples = richer_features.enrich_samples(samples, conn, league_id=target_id)
        buckets = backtest_common.split_by_season(samples)

        # Retrospective probabilities for CURRENT-season played fixtures that
        # were never locked: point-in-time features (pre-match Elo/form, no
        # leakage -- same construction as backtest samples), scored by the
        # serving artifact. Display-only; never enters the locked ledger or
        # the live record.
        live_path = config.MODELS_DIR / cfg["outcome_artifact"].replace(".json", "_live.json")
        serving_path = live_path if live_path.exists() else outcome_path
        serving_entry = model_registry.verify_deployed(serving_path)
        serving_model = outcome_model.load_model(serving_path)
        for s in samples:
            if s["season"] != CURRENT_SEASON:
                continue
            ph, pd, pa = outcome_model.predict_proba(s, serving_model)
            retro_probs[s["fixture_id"]] = {
                "h": round(ph * 100, 1),
                "d": round(pd * 100, 1),
                "a": round(pa * 100, 1),
                "modelVersion": serving_entry["version"],
            }

        scored = []
        for s in buckets["test"]:
            ph, pd, pa = outcome_model.predict_proba(s, model)
            scored.append({**s, "p_home": ph, "p_draw": pd, "p_away": pa, "_lg": web_code})
        all_scored.extend(scored)

        version_label = f"{entry['version']} · backtest"
        for s in scored:
            p = (s["p_home"], s["p_draw"], s["p_away"])
            probs_label = f"{round(p[0] * 100)}/{round(p[1] * 100)}/{round(p[2] * 100)}"
            ledger.append(
                {
                    "date": s["kickoff_utc"].strftime("%Y-%m-%d"),
                    "lg": web_code,
                    "fixture": f"{names[s['home_team_id']]} v {names[s['away_team_id']]}",
                    "published": probs_label,
                    "final": probs_label,
                    "result": f"{s['home_goals']}–{s['away_goals']}",
                    "won": max(range(3), key=lambda i: p[i]) == s["cls"],
                    "logLoss": round(-math.log(max(p[s["cls"]], 1e-15)), 2),
                    "modelVersion": version_label,
                }
            )

        ll = model["test_log_loss"]
        fit = buckets["train"] + buckets["validate"] + buckets["calibrate"]
        freq_ll = frequency_log_loss(fit, buckets["test"])
        harness = latest_harness_means(code, entry["version"])
        display_ll = harness.get("harness_ll") or ll
        display_freq = harness.get("harness_freq_ll") or freq_ll
        league_perf[web_code] = {
            "ll": f"{display_ll:.2f}",
            "base": f"{display_ll - display_freq:+.2f}".replace("-", "−"),
            "mkt": "—",
        }
        league_log_loss.append(
            {
                "code": web_code,
                "label": web_code if web_code != "EPL" else "EPL",
                "value": max(5, min(95, round((1.20 - display_ll) / (1.20 - 0.90) * 100))),
                "detail": f"{display_ll:.2f} / {display_freq:.2f}",
                "modelLl": round(ll, 4),
                "freqLl": round(freq_ll, 4),
                "harnessLl": harness.get("harness_ll"),
                "harnessEloLl": harness.get("harness_elo_ll"),
                "harnessFreqLl": harness.get("harness_freq_ll"),
                "belowBaseline": display_ll < display_freq,
            }
        )

    ledger.sort(key=lambda r: r["date"], reverse=True)
    ledger = ledger[:LEDGER_ROWS]

    # Live locked-and-settled predictions (PRD 13.4/13.5) go on top of the
    # ledger -- the real track record, prepended as it accumulates.
    live_rows = conn.execute(
        """
        SELECT * FROM locked_effective WHERE settled_at IS NOT NULL
        ORDER BY kickoff_utc DESC LIMIT ?
        """,
        (LEDGER_ROWS,),
    ).fetchall()
    for r in live_rows:
        probs_label = f"{round(r['p_home'])}/{round(r['p_draw'])}/{round(r['p_away'])}"
        ledger.insert(
            0,
            {
                "date": r["kickoff_utc"][:10],
                "lg": r["league_code"],
                "fixture": f"{r['home']} v {r['away']}",
                "published": probs_label,
                "final": probs_label,
                "result": f"{r['result_home']}–{r['result_away']}",
                "won": bool(r["correct"]),
                "logLoss": round(r["log_loss"], 2),
                "modelVersion": f"{r['model_version']} · live",
            },
        )

    live_stats = conn.execute(
        "SELECT COUNT(*) AS n, AVG(log_loss) AS ll, AVG(brier) AS brier, AVG(correct) AS acc"
        " FROM locked_effective WHERE settled_at IS NOT NULL"
    ).fetchone()
    n_locked = conn.execute("SELECT COUNT(*) FROM locked_effective").fetchone()[0]
    # Market benchmark on the SAME settled matches: bookmaker consensus at
    # lock time (margin removed), never a model input.
    mkt_rows = conn.execute(
        "SELECT outcome, market_p_home, market_p_draw, market_p_away, log_loss FROM locked_effective"
        " WHERE settled_at IS NOT NULL AND market_p_home IS NOT NULL"
    ).fetchall()
    mkt_ll = model_ll_on_mkt = None
    closer_n = 0
    if mkt_rows:
        for r in mkt_rows:
            mp = (r["market_p_home"], r["market_p_draw"], r["market_p_away"])[r["outcome"]] / 100.0
            if r["log_loss"] < -math.log(max(mp, 1e-15)):
                closer_n += 1
        mkt_ll = sum(-math.log(max((r["market_p_home"], r["market_p_draw"], r["market_p_away"])[r["outcome"]] / 100.0, 1e-15)) for r in mkt_rows) / len(mkt_rows)
        model_ll_on_mkt = sum(r["log_loss"] for r in mkt_rows) / len(mkt_rows)
    live_record = {
        "locked": n_locked,
        "settled": live_stats["n"],
        "log_loss": round(live_stats["ll"], 4) if live_stats["ll"] is not None else None,
        "brier": round(live_stats["brier"], 4) if live_stats["brier"] is not None else None,
        "accuracy": round(live_stats["acc"] * 100, 1) if live_stats["acc"] is not None else None,
        "market_n": len(mkt_rows),
        "market_log_loss": round(mkt_ll, 4) if mkt_ll is not None else None,
        "model_log_loss_on_market": round(model_ll_on_mkt, 4) if model_ll_on_mkt is not None else None,
        # Settled rows where the model gave the real result more probability
        # than the bookmaker consensus did.
        "closer_n": closer_n,
    }

    test_metrics = metrics.all_outcome_metrics(all_scored)
    calibration = metrics.calibration_error(all_scored)

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
        "season": "2025/26 held-out test seasons, all live leagues (backtest)",
    }
    return {
        "ledger": ledger,
        "bands": bands,
        "bars": bars,
        "headline": headline,
        "league_perf": league_perf,
        "league_log_loss": league_log_loss,
        "versions": versions,
        "live_record": live_record,
        "retro_probs": retro_probs,
    }


def latest_harness_means(code: str, version: str) -> dict:
    """Pull the deployed version's mean log loss (plus baselines) from the
    league's most recent walk-forward harness report -- the 5-fold mean is
    the selection metric and the honest headline; the single test-season
    number on the artifact is one (often the hardest) fold."""
    # Newest report that actually evaluated this version: paired candidate
    # runs (--only deployed,deployed_x) also write reports, keyed by row name.
    report, row, mean = None, None, {}
    for path in sorted(config.REPORTS_DIR.glob(f"rolling_backtest_{code}_*.json"), reverse=True):
        candidate = json.loads(path.read_text())
        if version in candidate.get("mean", {}):
            report, mean, row = candidate, candidate["mean"], candidate["mean"][version]
            break
    if not row:
        return {}
    return {
        "harness_ll": round(row["log_loss"], 4),
        "harness_elo_ll": round(mean["elo_only"]["log_loss"], 4) if "elo_only" in mean else None,
        "harness_freq_ll": round(mean["frequency"]["log_loss"], 4) if "frequency" in mean else None,
        "harness_folds": len(report.get("meta", {}).get("folds", [])) or 5,
    }


PAIRED_EXPERIMENTS = [
    ("squad_value", "Squad market value", "deployed_value", "value_diff",
     "Transfermarkt point-in-time top-25 squad value, as a log ratio (ingest_squad_values.py)."),
    ("all_comp_schedule", "All-competition rest & congestion", "deployed_allsched", "rest_all_diff",
     "Rest days and congestion counting cups and European games, not just the league (ingest_team_fixtures.py)."),
    ("player_strength", "Player-based team strength", "deployed_xi", "xi_strength_diff",
     "Adjusted plus-minus player ratings at monthly checkpoints, summed over the expected XI (player_ratings.py)."),
    ("xg", "Expected goals", "deployed_xg", "xg_diff",
     "Rolling xG for/against from API-Football statistics; data exists from 2022/23, so judged on the 2024 and 2025 folds only."),
]


def _deployed_logistic_features(code: str) -> list:
    """Feature list of the league's latest pure-logistic release (the blend's
    league component) straight from the registry -- stdlib, no numpy."""
    role = leagues.TARGETS[code]["outcome_artifact"].rsplit(".", 1)[0]
    registry = json.loads((config.MODELS_DIR / "registry.json").read_text())
    logistic = [e for e in registry if e["role"] == role and e.get("features") and e.get("model_type") != "blend"]
    return max(logistic, key=lambda e: e["registered_at"])["features"] if logistic else []


def build_experiments() -> list:
    """Experiment log for the performance page: every candidate the harness
    has judged, with the 5-fold mean before/after and whether it shipped.
    Sources: rolling_backtest_{code}_*.json paired runs, forest_blend_*.json,
    model_comparison_*.json. Read-only over the reports directory."""
    out = []
    for key, label, cand, feature, blurb in PAIRED_EXPERIMENTS:
        rows = []
        for code, cfg in leagues.TARGETS.items():
            picked = None
            for path in sorted(config.REPORTS_DIR.glob(f"rolling_backtest_{code}_*.json"), reverse=True):
                rep = json.loads(path.read_text())
                if "deployed" in rep.get("mean", {}) and cand in rep["mean"]:
                    picked = rep
                    break
            if not picked:
                continue
            before = picked["mean"]["deployed"]["log_loss"]
            after = picked["mean"][cand]["log_loss"]
            folds = picked["meta"]["folds"]
            won = sum(1 for T in folds if picked["per_fold"][str(T)][cand]["log_loss"] < picked["per_fold"][str(T)]["deployed"]["log_loss"])
            rows.append({
                "lg": cfg["web_code"], "before": round(before, 4), "after": round(after, 4),
                "delta": round(after - before, 4), "folds": len(folds), "folds_won": won,
                "shipped": feature in _deployed_logistic_features(code),
                "ran_at": picked["meta"]["started_at"][:10],
            })
        if rows:
            out.append({"key": key, "label": label, "blurb": blurb, "metric": "5-fold mean log loss", "rows": rows})

    forest = sorted(config.REPORTS_DIR.glob("forest_blend_*.json"))
    if forest:
        rep = json.loads(forest[-1].read_text())
        rows = []
        for code, d in rep["decisions"].items():
            m = d["means"]
            after_key = "blend4" if "blend4" in m else "blend3"
            rows.append({
                "lg": leagues.TARGETS[code]["web_code"], "before": round(m["blend2"], 4), "after": round(m[after_key], 4),
                "delta": round(m[after_key] - m["blend2"], 4), "folds": len(rep["meta"]["folds"]), "folds_won": None,
                "shipped": bool(d["forest_endorsed"]),
                "detail": f"forest weight {d['fixed_v']}" + (f", global forest {d['fixed_u']}" if d.get("fixed_u") else ""),
                "ran_at": rep["meta"]["started_at"][:10],
            })
        out.append({"key": "random_forest", "label": "Random forest as a blend component", "metric": "5-fold mean log loss",
                    "blurb": "League and pooled random forests added to the logistic blend; weight chosen on the 5-fold mean, capped at 0.6, shipped only if the gain is at least 0.001 (forest_blend.py).",
                    "rows": rows})

    bake = sorted(config.REPORTS_DIR.glob("model_comparison_*.json"))
    if bake:
        rep = json.loads(bake[-1].read_text())
        base = next(r for r in rep["pooled"]["results"] if r["model"] == "logistic")["test_log_loss"]
        rows = []
        for r in rep["pooled"]["results"]:
            if r["model"] == "logistic":
                continue
            v = r.get("vs_logistic") or {}
            rows.append({
                "lg": "ALL", "label": r["model"].replace("_", " "), "before": round(base, 4), "after": round(r["test_log_loss"], 4),
                "delta": round(r["test_log_loss"] - base, 4), "folds": 1, "folds_won": None, "shipped": False,
                "detail": ("significantly worse" if v.get("significant") and v.get("delta", 0) > 0 else
                           "significantly better" if v.get("significant") else "not significant") + " (paired bootstrap)",
                "ran_at": rep["generated_at"][:10],
            })
        out.append({"key": "learner_bakeoff", "label": "Learner bake-off vs logistic", "metric": "test-season log loss, pooled 1982 matches",
                    "blurb": "SVM (linear, RBF), random forest and XGBoost on the deployed features with the same split, decay and temperature calibration (model_comparison.py).",
                    "rows": rows})
    return out


def build_recent_results(conn, retro_probs: dict = None, days: int = 7) -> list:
    """Finished fixtures from the last `days` days across the target leagues,
    each with its LOCKED prediction where one exists. Fixtures played before
    the lifecycle went live (2026-08-20) honestly have none -- the UI says so
    rather than reconstructing a prediction after the result is known."""
    code_by_id = {cfg["league_id"]: cfg["web_code"] for cfg in leagues.TARGETS.values()}
    marks = ", ".join("?" for _ in code_by_id)
    rows = conn.execute(
        f"""
        SELECT f.fixture_id, f.league_id, f.kickoff_utc, f.home_goals, f.away_goals,
               th.name AS home, ta.name AS away, f.home_team_id, f.away_team_id,
               lp.p_home, lp.p_draw, lp.p_away, lp.correct, lp.log_loss,
               lp.model_version, lp.stage, lp.settled_at, lp.outcome,
               lp.market_p_home, lp.market_p_draw, lp.market_p_away, lp.market_bookmakers
        FROM fixtures f
        JOIN teams th ON th.team_id = f.home_team_id
        JOIN teams ta ON ta.team_id = f.away_team_id
        LEFT JOIN locked_effective lp ON lp.fixture_id = f.fixture_id
        WHERE f.league_id IN ({marks}) AND f.status_short IN ('FT','AET','PEN')
          AND f.kickoff_utc >= datetime('now', ?)
        ORDER BY f.kickoff_utc DESC
        """,
        (*code_by_id.keys(), f"-{days} days"),
    ).fetchall()
    retro_probs = retro_probs or {}
    out = []
    for r in rows:
        retro = None
        if r["p_home"] is None and r["fixture_id"] in retro_probs:
            rp = retro_probs[r["fixture_id"]]
            hg, ag = r["home_goals"], r["away_goals"]
            outcome = 0 if hg > ag else (2 if hg < ag else 1)
            top = max(range(3), key=lambda i: (rp["h"], rp["d"], rp["a"])[i])
            retro = {**rp, "correct": top == outcome}
        locked = None
        if r["p_home"] is not None:
            # Market benchmark on the same row: bookmaker consensus at lock
            # time (margin removed). "closer" = whoever gave the real result
            # more probability -- the plain-language verdict on the home page.
            settled = r["settled_at"] is not None and r["outcome"] is not None
            has_mkt = r["market_p_home"] is not None
            mkt_ll = None
            if settled and has_mkt:
                mp = (r["market_p_home"], r["market_p_draw"], r["market_p_away"])[r["outcome"]] / 100.0
                mkt_ll = round(-math.log(max(mp, 1e-15)), 4)
            locked = {
                "h": r["p_home"],
                "d": r["p_draw"],
                "a": r["p_away"],
                "mh": r["market_p_home"],
                "md": r["market_p_draw"],
                "ma": r["market_p_away"],
                "marketBookmakers": r["market_bookmakers"],
                "outcome": r["outcome"] if settled else None,
                "correct": bool(r["correct"]) if r["settled_at"] else None,
                "logLoss": r["log_loss"],
                "marketLogLoss": mkt_ll,
                "closer": (r["log_loss"] < mkt_ll) if (mkt_ll is not None and r["log_loss"] is not None) else None,
                "modelVersion": r["model_version"],
                "stage": r["stage"],
            }
        out.append(
            {
                "id": r["fixture_id"],
                "lg": code_by_id[r["league_id"]],
                "home": r["home"],
                "away": r["away"],
                "homeId": r["home_team_id"],
                "awayId": r["away_team_id"],
                "kickoffUtc": r["kickoff_utc"],
                "ko": _ko_label(r["kickoff_utc"]),
                "score": f"{r['home_goals']}–{r['away_goals']}",
                "locked": locked,
                "retro": retro,
            }
        )
    return out


def build_model_releases() -> list:
    """Per-league deployed release + release history, straight from the
    registry (PRD 14 'model version history' on the performance page)."""
    registry = json.loads((config.MODELS_DIR / "registry.json").read_text())
    out = []
    for code, cfg in leagues.TARGETS.items():
        role = cfg["outcome_artifact"].rsplit(".", 1)[0]
        entries = [e for e in registry if e["role"] == role]
        deployed = next((e for e in entries if e["deployed"]), None)
        if not deployed:
            continue
        history = [
            {
                "version": e["version"],
                "registered_at": e["registered_at"],
                "deployed": e["deployed"],
                "test_log_loss": (e.get("metrics") or {}).get("test_log_loss"),
                "test_accuracy": (e.get("metrics") or {}).get("test_accuracy"),
                "test_rps": (e.get("metrics") or {}).get("test_rps"),
                "features": len(e.get("features") or []),
                # 5-fold harness mean for this version, when the league's
                # latest harness report evaluated a candidate of that name.
                "harness_ll": latest_harness_means(code, e["version"]).get("harness_ll"),
            }
            for e in sorted(entries, key=lambda e: e["registered_at"])
        ]
        # The card shows what is actually SERVING: the *_live refold release
        # when one is deployed (its metrics live in the locked ledger, not a
        # held-out season), with the evaluation-track methodology it froze.
        live_entries = [e for e in registry if e["role"] == f"{role}_live"]
        live_deployed = next((e for e in live_entries if e["deployed"]), None)
        out.append(
            {
                "lg": cfg["web_code"],
                "version": (live_deployed or deployed)["version"],
                "deployed_at": (live_deployed or deployed).get(
                    "deployed_at", (live_deployed or deployed)["registered_at"]
                ),
                "methodology_version": deployed["version"] if live_deployed else None,
                "test_log_loss": (deployed.get("metrics") or {}).get("test_log_loss"),
                "n_releases": len(entries) + len(live_entries),
                "history": history[-8:],
                **latest_harness_means(code, deployed["version"]),
            }
        )
    return out


def main() -> None:
    conn = db.get_connection()
    predictions = json.loads((predict.OUTPUTS_DIR / "predictions.json").read_text())
    conn_final = db.get_connection()
    n_final = apply_final_locks(conn_final, predictions)
    conn_final.close()
    if n_final:
        print(f"{n_final} fixture(s) showing final-stage (confirmed lineup) forecasts")

    live_codes = set(predictions["models"].keys())
    target_ids = [cfg["league_id"] for cfg in leagues.TARGETS.values()]

    missing_index = richer_features.MissingPlayersIndex()
    missing_index.load(db.get_missing_player_counts(conn, target_ids))

    # Factors on match rows must come from the artifact that actually made
    # the predictions -- the *_live refold when present.
    outcome_models = {}
    for code, cfg in leagues.TARGETS.items():
        live_path = config.MODELS_DIR / cfg["outcome_artifact"].replace(".json", "_live.json")
        path = live_path if live_path.exists() else config.MODELS_DIR / cfg["outcome_artifact"]
        if path.exists():
            outcome_models[cfg["web_code"]] = outcome_model.load_model(path)

    backtest = build_backtest_sections(conn)

    fixture_ids = [p["fixture_id"] for p in predictions["predictions"]]
    rounds = fixture_rounds(conn, fixture_ids)

    standings = {}
    for code, cfg in leagues.TARGETS.items():
        standings[cfg["web_code"]] = build_standings(conn, {"code": code, **cfg}) if cfg["web_code"] in live_codes else []

    league_perf = {
        cfg["web_code"]: backtest["league_perf"].get(cfg["web_code"], {"ll": "—", "base": "—", "mkt": "—"})
        for cfg in leagues.TARGETS.values()
    }

    matches = build_matches(predictions, missing_index._counts, outcome_models, rounds)
    live = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "predictions_generated_at": predictions["generated_at"],
        "live_leagues": sorted(live_codes),
        # Match/league pages show the SERVING version (the *_live refold when
        # present); the performance page's backtest sections keep scoring the
        # evaluation artifacts, whose held-out season stays untouched.
        "model_versions": {
            **backtest["versions"],
            **{
                cfg["web_code"]: model_registry.verify_deployed(
                    config.MODELS_DIR / cfg["outcome_artifact"].replace(".json", "_live.json")
                )["version"]
                for cfg in leagues.TARGETS.values()
                if (config.MODELS_DIR / cfg["outcome_artifact"].replace(".json", "_live.json")).exists()
            },
        },
        "model_releases": build_model_releases(),
        "freshness": build_freshness(conn, target_ids),
        "matches": matches,
        "taster": build_taster(matches),
        "standings": standings,
        "league_perf": league_perf,
        "ledger": backtest["ledger"],
        "confidence_bands": backtest["bands"],
        "calibration_bars": backtest["bars"],
        "league_log_loss": backtest["league_log_loss"],
        "headline": backtest["headline"],
        "live_record": backtest["live_record"],
        "recent_results": build_recent_results(conn, backtest["retro_probs"]),
        "bookmakers": build_bookmakers(conn),
        "experiments": build_experiments(),
        "factor_glossary": FACTOR_GLOSSARY,
        # Betting PRD 4/16: per-selection grades and H2H/form context. Locked
        # fixtures show their ledger rows; the rest are previews graded now.
        "betting": build_betting(conn, predictions),
    }

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEB_DATA_DIR / "live.json"
    out_path.write_text(json.dumps(live, indent=2, ensure_ascii=False))
    print(
        f"wrote {out_path}: {len(live['matches'])} matches across {sorted(live_codes)}, "
        f"{len(backtest['ledger'])} ledger rows, {len(backtest['bands'])} bands, "
        f"headline n={backtest['headline']['n_test']}"
    )


if __name__ == "__main__":
    main()
