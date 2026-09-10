import json
import math
from pathlib import Path

import goals_model


def load_model(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run outcome_train.py first")
    return json.loads(path.read_text())


def _walk_gbm_tree(node: dict, x: tuple) -> float:
    while not node["leaf"]:
        fval = x[node["split_feature"]]
        if fval != fval:  # NaN guard; unreachable given richer_features' no-None
            # guarantee, but naive `nan <= t` is always False, which would
            # silently ignore default_left -- so this must be explicit.
            go_left = node["default_left"]
        else:
            go_left = fval <= node["threshold"]
        node = node["left"] if go_left else node["right"]
    return node["value"]


def _gbm_margins(sample: dict, model: dict) -> list:
    x = tuple(sample[name] for name in model["features"])
    base = model.get("base_score", [0.0] * model["num_class"])
    margins = []
    for class_trees, b in zip(model["trees"], base):
        total = b
        for root in class_trees:
            total += _walk_gbm_tree(root, x)
        margins.append(total)
    return margins


def predict_proba(sample: dict, model: dict) -> tuple:
    model_type = model.get("type", "multinomial_logistic")

    # Probability-returning types: must return BEFORE the shared
    # temperature/softmax tail, which applies only to logit-producing types.
    if model_type == "blend":
        parts = [(c["weight"], predict_proba(sample, c["model"])) for c in model["components"]]
        return tuple(sum(w * p[k] for w, p in parts) for k in range(3))
    if model_type == "ordered_logit":
        # One latent strength score, two cutpoints (Robberechts & Davis 2018;
        # Hvattum & Arntzen 2010). 3 params -- parameter parsimony over a
        # rating difference, deliberately NOT ordinality on many features.
        x = sample[model["feat"]]
        z = model["beta"] * x

        def F(v):
            return 1.0 / (1.0 + math.exp(-max(min(v, 35.0), -35.0)))

        p_away = F(model["c1"] - z)
        p_draw = F(model["c2"] - z) - p_away
        p_home = 1.0 - F(model["c2"] - z)
        eps = 1e-9
        total = p_home + p_draw + p_away
        return (max(p_home, eps) / total, max(p_draw, eps) / total, max(p_away, eps) / total)
    if model_type == "davidson":
        # Bradley-Terry with Davidson explicit-tie term (Tsokos et al. 2019):
        # p_home ~ pi, p_away ~ 1, p_draw ~ nu*sqrt(pi), pi = exp(beta*x + h).
        x = sample[model["feat"]]
        pi_h = math.exp(max(min(model["beta"] * x + model["h"], 35.0), -35.0))
        nu = model["nu"]
        denom = pi_h + 1.0 + nu * math.sqrt(pi_h)
        return (pi_h / denom, nu * math.sqrt(pi_h) / denom, 1.0 / denom)
    if model_type == "dc_outcome":
        goals = model["goals"]
        mu_h, mu_a = goals_model.expected_goals(sample["home_team_id"], sample["away_team_id"], goals, sample.get("elo_diff", 0.0))
        matrix = goals_model.score_matrix(mu_h, mu_a, model.get("max_goals", 6), goals.get("rho", 0.0))
        return goals_model.outcome_probs_from_matrix(matrix)

    if model_type == "multinomial_logistic":
        feats = tuple(sample[name] for name in model["features"])
        x = [(f - mean) / std for f, mean, std in zip(feats, model["means"], model["stds"])]
        logits = [
            inter + sum(c * xi for c, xi in zip(coef, x))
            for coef, inter in zip(model["coef"], model["intercept"])
        ]
    elif model_type == "lightgbm_trees":
        logits = _gbm_margins(sample, model)
    else:
        raise ValueError(f"unknown model type {model_type!r}")

    vec_scale = model.get("vec_scale")
    temperature = model.get("temperature", 1.0)
    class_bias = model.get("class_bias", [0.0, 0.0, 0.0])
    if vec_scale is not None:
        logits = [z * sc + b for z, sc, b in zip(logits, vec_scale, class_bias)]
    else:
        logits = [z / temperature + b for z, b in zip(logits, class_bias)]
    top = max(logits)
    exps = [math.exp(z - top) for z in logits]
    total = sum(exps)
    p = [e / total for e in exps]
    return p[0], p[1], p[2]
