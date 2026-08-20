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


def all_outcome_metrics(samples: list) -> dict:
    return {
        "log_loss": log_loss(samples),
        "brier": brier_score(samples),
        "rps": rps(samples),
        "accuracy": accuracy(samples),
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
