"""Player-based team strength: adjusted plus-minus ratings from lineups.

Every completed league match with lineup data becomes one regression row:
goal difference (home - away) on player indicators (+1 for each home
starter, -1 for each away starter) plus a home-advantage intercept. Ridge
regularisation shrinks players with little evidence toward zero (the
average). The solution is refit at monthly CHECKPOINTS using only matches
kicked off strictly before the checkpoint, so a rating dated d never saw
a match on or after d -- point-in-time by construction, whichever fold
later uses it. Older seasons are down-weighted by DECAY per season, as the
outcome models are.

Normal equations are accumulated incrementally (X'X and X'y), so each
checkpoint is one (P+1)x(P+1) solve, ~0.2 s for 1,500 players. Ridge alpha
is chosen per league by out-of-sample goal-difference MSE across
checkpoints (predict next month's matches from the checkpoint fit).

Output: data/models/player_ratings_{code}.json -- {checkpoint date:
{player_id: rating}} plus alpha/decay/home_adv -- read by
richer_features.PlayerStrengthStore (stdlib) at training and serving time.
Training-only script: numpy imported here, never at serving time.

    python3 src/player_ratings.py --league pl
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

import config
import db
import leagues

DECAY = 0.8
ALPHA_GRID = [20.0, 40.0, 80.0, 160.0, 320.0]
MIN_FIT_MATCHES = 150


def month_starts(first: datetime, last: datetime) -> list:
    out = []
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(datetime(y, m, 1, tzinfo=timezone.utc))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def load_rows(conn, league_id: int) -> tuple[list, dict]:
    """Chronological matches with (date, season, gd, home starters, away starters)."""
    starters = defaultdict(lambda: defaultdict(set))
    for r in db.get_lineup_players_by_league(conn, [league_id]):
        if r["is_starter"]:
            starters[r["fixture_id"]][r["team_id"]].add(r["player_id"])
    fixtures = conn.execute(
        "SELECT fixture_id, season, kickoff_utc, home_team_id, away_team_id, home_goals, away_goals FROM fixtures"
        " WHERE league_id = ? AND status_short IN ('FT','AET','PEN') AND home_goals IS NOT NULL ORDER BY kickoff_utc",
        (league_id,),
    ).fetchall()
    rows = []
    for f in fixtures:
        s = starters.get(f["fixture_id"])
        if not s or len(s.get(f["home_team_id"], ())) != 11 or len(s.get(f["away_team_id"], ())) != 11:
            continue
        rows.append({
            "date": datetime.fromisoformat(f["kickoff_utc"]),
            "season": f["season"],
            "gd": float(f["home_goals"] - f["away_goals"]),
            "home": sorted(s[f["home_team_id"]]),
            "away": sorted(s[f["away_team_id"]]),
        })
    players = sorted({p for r in rows for p in r["home"] + r["away"]})
    return rows, {p: i for i, p in enumerate(players)}


class NormalEquations:
    """Incremental X'X, X'y with season decay applied at season boundaries."""

    def __init__(self, n_players: int):
        self.n = n_players + 1  # last column = home advantage
        self.xtx = np.zeros((self.n, self.n))
        self.xty = np.zeros(self.n)
        self.season = None
        self.count = 0

    def add(self, row: dict, index: dict) -> None:
        if self.season is not None and row["season"] != self.season:
            self.xtx *= DECAY
            self.xty *= DECAY
        self.season = row["season"]
        cols = [index[p] for p in row["home"]] + [index[p] for p in row["away"]] + [self.n - 1]
        vals = np.array([1.0] * 11 + [-1.0] * 11 + [1.0])
        idx = np.array(cols)
        self.xtx[np.ix_(idx, idx)] += np.outer(vals, vals)
        self.xty[idx] += vals * row["gd"]
        self.count += 1

    def solve(self, alpha: float) -> np.ndarray:
        reg = np.full(self.n, alpha)
        reg[-1] = 1e-3  # home advantage effectively unpenalised
        return np.linalg.solve(self.xtx + np.diag(reg), self.xty)


def predict_gd(beta: np.ndarray, row: dict, index: dict) -> float:
    n = len(beta) - 1
    return beta[n] + sum(beta[index[p]] for p in row["home"]) - sum(beta[index[p]] for p in row["away"])


def fit_league(code: str, conn) -> dict:
    league_id = leagues.target_config(code)["league_id"]
    rows, index = load_rows(conn, league_id)
    if len(rows) < MIN_FIT_MATCHES:
        raise SystemExit(f"{code}: only {len(rows)} matches with full lineups -- not enough")
    checkpoints = month_starts(rows[0]["date"], datetime.now(timezone.utc))
    checkpoints = [c for c in checkpoints if c > rows[0]["date"]]
    print(f"{code}: {len(rows)} matches, {len(index)} players, {len(checkpoints)} monthly checkpoints", file=sys.stderr)

    # Alpha selection: rolling one-month-ahead MSE, each alpha from the same
    # incremental pass (solving is the only per-alpha cost).
    mse = {a: [0.0, 0] for a in ALPHA_GRID}
    ne = NormalEquations(len(index))
    ri = 0
    for ci, c in enumerate(checkpoints):
        while ri < len(rows) and rows[ri]["date"] < c:
            ne.add(rows[ri], index)
            ri += 1
        if ne.count < MIN_FIT_MATCHES:
            continue
        nxt = checkpoints[ci + 1] if ci + 1 < len(checkpoints) else None
        ahead = [r for r in rows[ri:] if nxt is None or r["date"] < nxt]
        if not ahead:
            continue
        for a in ALPHA_GRID:
            beta = ne.solve(a)
            for r in ahead:
                mse[a][0] += (predict_gd(beta, r, index) - r["gd"]) ** 2
                mse[a][1] += 1
    alpha = min(ALPHA_GRID, key=lambda a: mse[a][0] / max(mse[a][1], 1))
    naive = sum(r["gd"] ** 2 for r in rows) / len(rows)
    print(f"{code}: alpha={alpha} one-month-ahead gd MSE={mse[alpha][0] / max(mse[alpha][1], 1):.3f} (naive 0: {naive:.3f})", file=sys.stderr)

    # Final pass: ratings at every checkpoint with the chosen alpha.
    ne = NormalEquations(len(index))
    ri = 0
    out = {}
    players = list(index)
    home_adv = None
    for c in checkpoints:
        while ri < len(rows) and rows[ri]["date"] < c:
            ne.add(rows[ri], index)
            ri += 1
        if ne.count < MIN_FIT_MATCHES:
            continue
        beta = ne.solve(alpha)
        home_adv = float(beta[-1])
        out[c.strftime("%Y-%m-%d")] = {str(p): round(float(beta[index[p]]), 4) for p in players if abs(beta[index[p]]) > 1e-4}
    return {
        "type": "player_plus_minus",
        "league": code,
        "alpha": alpha,
        "decay": DECAY,
        "home_adv": home_adv,
        "matches": len(rows),
        "players": len(index),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checkpoints": out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Adjusted plus-minus player ratings at monthly checkpoints.")
    parser.add_argument("--league", type=str, default="pl")
    args = parser.parse_args()
    conn = db.get_connection()
    artifact = fit_league(args.league, conn)
    path = config.MODELS_DIR / f"player_ratings_{args.league}.json"
    path.write_text(json.dumps(artifact))
    top = sorted(artifact["checkpoints"][max(artifact["checkpoints"])].items(), key=lambda kv: -kv[1])[:5]
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB); latest top ratings: {top}")


if __name__ == "__main__":
    main()
