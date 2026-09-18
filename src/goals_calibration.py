"""Are the goals-market probabilities (Over 2.5, BTTS) sharp enough?

    python3 src/goals_calibration.py            # all leagues + pooled

The betting ledger's first week showed the model's biggest "edges" were
Under 2.5 on big-club fixtures, and that those lost. The suspicion: the
goals model is under-dispersed -- calibrated on average but unable to say
70%+ over or 35% over, where the market does. This scores held-out seasons
with the EVALUATION goals artifacts (test season untouched) and fits a
logistic recalibration  y ~ sigmoid(b + a*logit(p))  per market:

  a = 1, b = 0   calibrated
  a > 1          under-confident: probabilities should be pushed outward
  a < 1          over-confident

Reported two ways: the slope fitted on the test season itself (the
diagnosis) and the gain from a slope fitted on validate+calibrate and
applied to the test season (out of sample: what a correction would earn).
Stdlib only; runs on the laptop against the local DB."""

import json
import math
from datetime import datetime, timezone

import backtest_common
import config
import db
import goals_model
import leagues
import matches as matches_module
import metrics
import promotion

EPS = 1e-6


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(z, 35.0), -35.0)))


def fit_platt(entries: list, iters: int = 60) -> tuple:
    """Newton-Raphson on (intercept b, slope a) for binary (p, y) pairs."""
    xs = [metrics._logit(p) for p, _ in entries]
    ys = [y for _, y in entries]
    b, a = 0.0, 1.0
    for _ in range(iters):
        gb = ga = hbb = hba = haa = 0.0
        for x, y in zip(xs, ys):
            mu = sigmoid(b + a * x)
            w = mu * (1 - mu)
            gb += mu - y
            ga += (mu - y) * x
            hbb += w
            hba += w * x
            haa += w * x * x
        det = hbb * haa - hba * hba
        if abs(det) < 1e-12:
            break
        db_, da = (haa * gb - hba * ga) / det, (hbb * ga - hba * gb) / det
        b -= db_
        a -= da
        if abs(db_) < 1e-9 and abs(da) < 1e-9:
            break
    return a, b


def apply_platt(p: float, a: float, b: float) -> float:
    return sigmoid(b + a * metrics._logit(p))


def log_loss(entries: list) -> float:
    return -sum(math.log(max(p if y else 1 - p, EPS)) for p, y in entries) / len(entries)


def ece(entries: list, n_bins: int = 10) -> float:
    return metrics._binned_calibration(entries, n_bins)["ece"]


def market_entries(samples: list, model: dict) -> dict:
    """{market: [(p, y)]} for every sample scored by the artifact."""
    rho = model.get("rho", 0.0)
    out = {"OU25": [], "BTTS": []}
    for s in samples:
        mu_h, mu_a = goals_model.expected_goals(s["home_team_id"], s["away_team_id"], model, s.get("elo_diff", 0.0))
        m = goals_model.score_matrix(mu_h, mu_a, rho=rho)
        p_over, _ = goals_model.over_under_prob(m)
        out["OU25"].append((p_over, 1.0 if s["home_goals"] + s["away_goals"] > 2.5 else 0.0))
        out["BTTS"].append((goals_model.btts_prob(m), 1.0 if s["home_goals"] >= 1 and s["away_goals"] >= 1 else 0.0))
    return out


def league_samples(conn, code: str) -> dict:
    cfg = leagues.target_config(code)
    target_id, feeder_id = cfg["league_id"], cfg["feeder_id"]
    matches = matches_module.load_matches(conn, [target_id] + ([feeder_id] if feeder_id else []))
    transitions = promotion.compute_transitions(conn, target_id, feeder_id, backtest_common.ALL_SEASONS) if feeder_id else {}
    samples = backtest_common.collect_samples(matches, transitions, use_mov=True, target_league_id=target_id)
    return backtest_common.split_by_season(samples), cfg


def base_rate_log_loss(entries: list) -> tuple:
    """The constant-probability benchmark: what a model with no information
    beyond the outcome frequency scores. Skill = this minus the model."""
    ys = [y for _, y in entries]
    base = sum(ys) / len(ys)
    return base, -(base * math.log(base) + (1 - base) * math.log(1 - base))


def analyse(fit_entries: list, test_entries: list) -> dict:
    a_test, b_test = fit_platt(test_entries)              # diagnosis, in-sample
    a_fit, b_fit = fit_platt(fit_entries)                 # correction, fitted out of sample
    corrected = [(apply_platt(p, a_fit, b_fit), y) for p, y in test_entries]
    ps = [p for p, _ in test_entries]
    cps = [p for p, _ in corrected]
    base, ll_base = base_rate_log_loss(test_entries)
    ll_model = log_loss(test_entries)
    return {
        "n_test": len(test_entries), "n_fit": len(fit_entries),
        "base_rate": round(base, 4), "base_log_loss": round(ll_base, 4),
        # Positive: the model knows something the base rate does not.
        "skill_vs_base": round(ll_base - ll_model, 4),
        "slope_on_test": round(a_test, 3), "intercept_on_test": round(b_test, 3),
        "slope_fitted_oos": round(a_fit, 3), "intercept_fitted_oos": round(b_fit, 3),
        "raw": {"log_loss": round(log_loss(test_entries), 4), "ece": round(ece(test_entries), 4),
                "p_min": round(min(ps), 3), "p_max": round(max(ps), 3)},
        "corrected_oos": {"log_loss": round(log_loss(corrected), 4), "ece": round(ece(corrected), 4),
                          "p_min": round(min(cps), 3), "p_max": round(max(cps), 3)},
        "log_loss_gain": round(log_loss(test_entries) - log_loss(corrected), 4),
    }


def main() -> None:
    conn = db.get_connection()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "leagues": {}, "pooled": {}}
    pooled_fit = {"OU25": [], "BTTS": []}
    pooled_test = {"OU25": [], "BTTS": []}
    for code in leagues.pooled_targets():
        try:
            buckets, cfg = league_samples(conn, code)
        except Exception as exc:
            print(f"{code}: skipped ({exc})")
            continue
        model = goals_model.load_model(config.MODELS_DIR / cfg["goals_artifact"])
        fit = market_entries(buckets["validate"] + buckets["calibrate"], model)
        test = market_entries(buckets["test"], model)
        report["leagues"][cfg["web_code"]] = {mk: analyse(fit[mk], test[mk]) for mk in ("OU25", "BTTS")}
        for mk in ("OU25", "BTTS"):
            pooled_fit[mk].extend(fit[mk])
            pooled_test[mk].extend(test[mk])
    report["pooled"] = {mk: analyse(pooled_fit[mk], pooled_test[mk]) for mk in ("OU25", "BTTS")}

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (config.REPORTS_DIR / f"goals_calibration_{stamp}.json").write_text(json.dumps(report, indent=2))
    # export_web.py reads this into live.json as `goals_skill` (Performance page).
    (config.REPORTS_DIR / "goals_calibration_latest.json").write_text(json.dumps(report, indent=2))

    print(f"{'league':7} {'market':5} {'n':>5} {'base%':>6} {'skill':>7} {'slope':>6} {'raw range':>13} {'corrected':>13} {'LL raw':>8} {'LL corr':>8} {'gain':>8}")
    rows = [(lg, mk, r[mk]) for lg, r in report["leagues"].items() for mk in ("OU25", "BTTS")]
    rows += [("POOLED", mk, report["pooled"][mk]) for mk in ("OU25", "BTTS")]
    for lg, mk, r in rows:
        print(f"{lg:7} {mk:5} {r['n_test']:5} {r['base_rate']*100:6.1f} {r['skill_vs_base']:+7.4f} {r['slope_on_test']:6.2f} "
              f"{r['raw']['p_min']:.2f}–{r['raw']['p_max']:.2f}     {r['corrected_oos']['p_min']:.2f}–{r['corrected_oos']['p_max']:.2f}     "
              f"{r['raw']['log_loss']:8.4f} {r['corrected_oos']['log_loss']:8.4f} {r['log_loss_gain']:+8.4f}")


if __name__ == "__main__":
    main()
