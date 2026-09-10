import math

EPS = 1e-15


# --- Outcome metrics: samples carry p_home/p_draw/p_away/cls ---

def log_loss(samples: list) -> float:
    total = 0.0
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        total += -math.log(max(p[s["cls"]], EPS))
    return total / len(samples)


def brier_score(samples: list) -> float:
    total = 0.0
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        total += sum((pi - (1.0 if i == s["cls"] else 0.0)) ** 2 for i, pi in enumerate(p))
    return total / len(samples)


def rps(samples: list) -> float:
    """Ranked Probability Score for 3 ordered classes (home, draw, away)."""
    total = 0.0
    for s in samples:
        cls = s["cls"]
        cum_p1 = s["p_home"]
        cum_p2 = s["p_home"] + s["p_draw"]
        cum_o1 = 1.0 if cls == 0 else 0.0
        cum_o2 = 1.0 if cls in (0, 1) else 0.0
        total += 0.5 * ((cum_p1 - cum_o1) ** 2 + (cum_p2 - cum_o2) ** 2)
    return total / len(samples)


def accuracy(samples: list) -> float:
    correct = 0
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        pred = max(range(3), key=lambda i: p[i])
        correct += int(pred == s["cls"])
    return correct / len(samples)


def calibration_error(samples: list, n_bins: int = 10) -> dict:
    bins = [[] for _ in range(n_bins)]
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        p_max = max(p)
        pred = max(range(3), key=lambda i: p[i])
        bin_idx = min(int(p_max * n_bins), n_bins - 1)
        bins[bin_idx].append((p_max, int(pred == s["cls"])))

    bin_reports = []
    ece = 0.0
    n = len(samples)
    for i, entries in enumerate(bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not entries:
            bin_reports.append({"lo": lo, "hi": hi, "count": 0, "predicted_rate": None, "actual_rate": None})
            continue
        predicted_rate = sum(e[0] for e in entries) / len(entries)
        actual_rate = sum(e[1] for e in entries) / len(entries)
        bin_reports.append(
            {"lo": lo, "hi": hi, "count": len(entries), "predicted_rate": predicted_rate, "actual_rate": actual_rate}
        )
        ece += (len(entries) / n) * abs(predicted_rate - actual_rate)

    return {"ece": ece, "bins": bin_reports}


def balanced_accuracy(samples: list) -> float:
    """Mean recall across the three classes -- robust to class imbalance
    (draws are the minority class in every league)."""
    correct = [0, 0, 0]
    totals = [0, 0, 0]
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        pred = max(range(3), key=lambda i: p[i])
        totals[s["cls"]] += 1
        correct[s["cls"]] += int(pred == s["cls"])
    recalls = [c / t for c, t in zip(correct, totals) if t]
    return sum(recalls) / len(recalls) if recalls else 0.0


def confusion_matrix(samples: list) -> dict:
    """3x3 counts: rows = actual (home/draw/away), cols = predicted top class."""
    labels = ["home", "draw", "away"]
    grid = [[0, 0, 0] for _ in range(3)]
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        pred = max(range(3), key=lambda i: p[i])
        grid[s["cls"]][pred] += 1
    return {
        "labels": labels,
        "rows_actual_cols_predicted": grid,
    }


def _logit(p: float) -> float:
    p = min(max(p, EPS), 1.0 - EPS)
    return math.log(p / (1.0 - p))


def calibration_slope_intercept(samples: list, iters: int = 50) -> dict:
    """Logistic recalibration fit (Cox 1958 style), pooled one-vs-rest over
    all three classes: y ~ sigmoid(intercept + slope * logit(p)). Perfect
    calibration gives slope=1, intercept=0; slope<1 means overconfident,
    slope>1 underconfident. Pure-Python Newton-Raphson, no sklearn."""
    xs, ys = [], []
    for s in samples:
        p = (s["p_home"], s["p_draw"], s["p_away"])
        for c in range(3):
            xs.append(_logit(p[c]))
            ys.append(1.0 if s["cls"] == c else 0.0)

    a, b = 0.0, 1.0  # intercept, slope
    for _ in range(iters):
        ga = gb = 0.0
        haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            z = a + b * x
            mu = 1.0 / (1.0 + math.exp(-max(min(z, 35.0), -35.0)))
            w = mu * (1.0 - mu)
            ga += mu - y
            gb += (mu - y) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a -= da
        b -= db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            break
    return {"slope": b, "intercept": a}


def paired_bootstrap_log_loss_delta(scored_a: list, scored_b: list, n_boot: int = 2000, seed: int = 7) -> dict:
    """Paired bootstrap 95% CI for mean(log_loss_a - log_loss_b) over the
    same matches. Negative delta = model A assigns better probabilities.
    'significant' = the CI excludes zero. Both lists must score the SAME
    matches in the same order."""
    import random as _random

    assert len(scored_a) == len(scored_b), "paired bootstrap requires identically-sized scored lists"
    for sa, sb in zip(scored_a, scored_b):
        assert sa["fixture_id"] == sb["fixture_id"], "paired bootstrap requires the same matches in the same order"

    def loss(s):
        p = (s["p_home"], s["p_draw"], s["p_away"])
        return -math.log(max(p[s["cls"]], EPS))

    deltas = [loss(sa) - loss(sb) for sa, sb in zip(scored_a, scored_b)]
    n = len(deltas)
    point = sum(deltas) / n

    rng = _random.Random(seed)
    means = []
    for _ in range(n_boot):
        total = 0.0
        for _ in range(n):
            total += deltas[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot) - 1]
    return {
        "delta": point,
        "ci_lo": lo,
        "ci_hi": hi,
        "significant": (lo > 0 and hi > 0) or (lo < 0 and hi < 0),
        "n_matches": n,
        "n_boot": n_boot,
    }


def all_outcome_metrics(samples: list) -> dict:
    return {
        "log_loss": log_loss(samples),
        "brier": brier_score(samples),
        "rps": rps(samples),
        # Accuracy metrics are reported for context only and are never a
        # model-selection criterion -- selection is on out-of-sample log loss.
        "accuracy": accuracy(samples),
        "balanced_accuracy": balanced_accuracy(samples),
        "n": len(samples),
    }


def group_metrics(samples: list, key_fn) -> dict:
    groups = {}
    for s in samples:
        groups.setdefault(key_fn(s), []).append(s)
    return {str(key): all_outcome_metrics(items) for key, items in sorted(groups.items(), key=lambda kv: str(kv[0]))}


# --- Goals metrics: samples carry mu_home/mu_away/home_goals/away_goals ---

def _deviance_term(y: int, mu: float) -> float:
    if y == 0:
        return 2.0 * mu
    return 2.0 * (y * math.log(y / mu) - (y - mu))


def poisson_deviance(samples: list) -> dict:
    home = sum(_deviance_term(s["home_goals"], s["mu_home"]) for s in samples) / len(samples)
    away = sum(_deviance_term(s["away_goals"], s["mu_away"]) for s in samples) / len(samples)
    return {"home": home, "away": away, "combined": (home + away) / 2.0}


def mean_abs_goal_error(samples: list) -> dict:
    home = sum(abs(s["home_goals"] - s["mu_home"]) for s in samples) / len(samples)
    away = sum(abs(s["away_goals"] - s["mu_away"]) for s in samples) / len(samples)
    total = sum(abs((s["home_goals"] + s["away_goals"]) - (s["mu_home"] + s["mu_away"])) for s in samples) / len(samples)
    return {"home": home, "away": away, "total": total}


def exact_score_accuracy(samples: list, max_goals: int = 6, rho: float = 0.0) -> float:
    import goals_model

    correct = 0
    for s in samples:
        matrix = goals_model.score_matrix(s["mu_home"], s["mu_away"], max_goals, rho)
        predicted = goals_model.most_likely_score(matrix)
        actual = (s["home_goals"], s["away_goals"])
        if actual[0] > max_goals or actual[1] > max_goals:
            continue
        correct += int(predicted == actual)
    return correct / len(samples)


def ou_calibration(samples: list, line: float = 2.5, n_bins: int = 10, rho: float = 0.0) -> dict:
    import goals_model

    entries = []
    for s in samples:
        matrix = goals_model.score_matrix(s["mu_home"], s["mu_away"], rho=rho)
        p_over, _ = goals_model.over_under_prob(matrix, line)
        actual = 1.0 if (s["home_goals"] + s["away_goals"]) > line else 0.0
        entries.append((p_over, actual))
    return _binned_calibration(entries, n_bins)


def btts_calibration(samples: list, n_bins: int = 10, rho: float = 0.0) -> dict:
    import goals_model

    entries = []
    for s in samples:
        matrix = goals_model.score_matrix(s["mu_home"], s["mu_away"], rho=rho)
        p_btts = goals_model.btts_prob(matrix)
        actual = 1.0 if s["home_goals"] >= 1 and s["away_goals"] >= 1 else 0.0
        entries.append((p_btts, actual))
    return _binned_calibration(entries, n_bins)


def _binned_calibration(entries: list, n_bins: int) -> dict:
    bins = [[] for _ in range(n_bins)]
    for p, actual in entries:
        bin_idx = min(int(p * n_bins), n_bins - 1)
        bins[bin_idx].append((p, actual))

    bin_reports = []
    ece = 0.0
    n = len(entries)
    for i, items in enumerate(bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not items:
            bin_reports.append({"lo": lo, "hi": hi, "count": 0, "predicted_rate": None, "actual_rate": None})
            continue
        predicted_rate = sum(p for p, _ in items) / len(items)
        actual_rate = sum(a for _, a in items) / len(items)
        bin_reports.append(
            {"lo": lo, "hi": hi, "count": len(items), "predicted_rate": predicted_rate, "actual_rate": actual_rate}
        )
        ece += (len(items) / n) * abs(predicted_rate - actual_rate)

    return {"ece": ece, "bins": bin_reports}
