import math

SCALES = [180, 220, 260, 300, 350, 400, 450, 500, 600, 700]
DRAW_BASES = [0.26, 0.30, 0.34, 0.38, 0.42, 0.46]
DRAW_SCALES = [160, 220, 280, 360, 440, 520]
EPS = 1e-15


def frequency_baseline(train_samples: list) -> dict:
    n = len(train_samples)
    counts = {0: 0, 1: 0, 2: 0}
    for s in train_samples:
        counts[s["cls"]] += 1
    return {"home": counts[0] / n, "draw": counts[1] / n, "away": counts[2] / n}


def frequency_probs(freq: dict, sample: dict) -> tuple:
    return freq["home"], freq["draw"], freq["away"]


def elo_probs(diff: float, scale: float, d0: float, tau: float) -> tuple:
    p2 = 1.0 / (1.0 + 10 ** (-diff / scale))
    draw = d0 * math.exp(-abs(diff) / tau)
    return (1.0 - draw) * p2, draw, (1.0 - draw) * (1.0 - p2)


def _elo_log_loss(samples: list, params: tuple) -> float:
    scale, d0, tau = params
    total = 0.0
    for s in samples:
        p = elo_probs(s["elo_diff"], scale, d0, tau)
        total += -math.log(max(p[s["cls"]], EPS))
    return total / len(samples)


def calibrate_elo(train_samples: list) -> tuple:
    best_params, best_ll = None, math.inf
    for scale in SCALES:
        for d0 in DRAW_BASES:
            for tau in DRAW_SCALES:
                ll = _elo_log_loss(train_samples, (scale, d0, tau))
                if ll < best_ll:
                    best_ll, best_params = ll, (scale, d0, tau)
    return best_params


def score_samples(samples: list, probs_fn) -> list:
    scored = []
    for s in samples:
        ph, pd, pa = probs_fn(s)
        scored.append({**s, "p_home": ph, "p_draw": pd, "p_away": pa})
    return scored
