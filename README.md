# oasis

Five-league football prediction platform (Premier League, La Liga, Serie A,
Bundesliga, MLS), built on API-Football. See `PRD.md` for the product
requirements.

This is Phase 0: before any real ingestion, audit what API-Football actually
provides per league-season (fixtures, standings, injuries, lineups,
predictions, odds, ...) and never assume — read the coverage flags and
degrade gracefully.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API_FOOTBALL_KEY
```

## Run the coverage audit

```bash
python3 src/coverage_audit.py
```

Checks all 9 configured leagues (5 target + 4 feeder divisions, see
`src/leagues.py`) for the current season. Results land in:

- `data/oasis.sqlite` — `leagues` (reference) and `coverage_audit` (append-only
  audit log, one row per run per league-season) tables.
- `data/raw/leagues/{league_id}_{season}.json` — cached raw API response per
  request; re-running the audit reuses these instead of re-hitting the API.
- `data/reports/coverage_audit_*.json` — full report for one run.
- `data/status/coverage_audit_status.json` — small status artifact, overwritten
  each run.

### Options

```bash
python3 src/coverage_audit.py --league-ids 39,140 --seasons 2017-2026
python3 src/coverage_audit.py --force-refresh   # bypass the raw-response cache
```

`--seasons` accepts a single year, a comma list, a range (`2017-2026`), or a
mix. This is the same mechanism used to check ten-season historical
availability later — no code changes needed, just a wider `--seasons` value.

## Phase 1: Premier League ingestion, Elo, baselines, backtest

```bash
pip install -r requirements-dev.txt   # numpy/scikit-learn, training scripts only

python3 src/ingest_fixtures.py                    # PL (39) + Championship (40), 2017-2025
python3 src/outcome_train.py                      # -> data/models/outcome_model_pl.json
python3 src/goals_train.py                        # -> data/models/goals_model.json
python3 src/evaluate_report.py                    # -> data/reports/evaluate_report_*.json
```

`evaluate_report.py` compares three outcome-probability baselines (league
historical frequency, calibrated Elo-only, and a temperature-calibrated
multinomial logistic regression) on the held-out 2025/26 test season, plus a
Poisson (Maher-style attack/defense) goals model. Chronological split: train
2017/18-2022/23, validate 2023/24, calibrate 2024/25, test 2025/26 — never
random, no season overlap (`backtest_common.verify_no_leakage` checks this on
every run). Championship data trains Elo/features only (never scored) so
promoted/relegated teams carry a real rating into their first PL season
instead of starting cold.

Only `outcome_train.py`/`goals_train.py` need numpy/scikit-learn — ingestion,
the trained-model inference modules (`outcome_model.py`/`goals_model.py`), and
`evaluate_report.py` itself stay stdlib-only, mirroring the wc pipeline's
training/inference dependency split.

## Feature enrichment: shots, injuries, lineups (PL only)

```bash
python3 src/ingest_fixture_statistics.py   # shots/possession/corners/cards/passes, ~3420 calls
python3 src/ingest_injuries.py             # 9 calls, one per season, already fixture-tagged
python3 src/ingest_lineups.py              # confirmed startXI/subs, ~3420 calls
python3 src/outcome_train.py               # now compares 4 candidate feature sets
python3 src/evaluate_report.py
```

Adds `sot_diff`/`possession_diff`/`corner_diff` (rolling shot-stat form, same
point-in-time discipline as `form_diff`), `missing_players_diff` (confirmed
absences from `/injuries`, already fixture-tagged pre-kickoff — no
reconstruction needed), and `squad_disruption_diff` (fraction of a team's
"regular XI," built from lineup history, missing from the actual confirmed
startXI). `outcome_train.py` now picks the best of 3/5/7/9-feature candidates
by validate log-loss automatically. `expected_goals`/`goals_prevented` (real
provider xG) are stored but not used as features — confirmed present only
from ~2022/23 onward, absent in 2017/18, so unusable across the full training
window.

Squad-disruption uses the actual *confirmed* lineup, which maps to PRD §13.3
("final prediction," ~1h pre-kickoff) rather than §13.1 ("initial prediction,"
12-24h out) — a documented simplification; a true two-stage initial/final
model is a live-serving concern for a later phase.

**Result: logistic(9 features) beats both baselines and Phase 1's original
5-feature model on every metric** on the held-out 2025/26 test season —
log-loss 1.030 (vs 1.037 elo-only, 1.085 frequency, 1.034 Phase-1 logistic),
accuracy 48.2% (vs 46.1%), RPS 0.209 (vs 0.211). `evaluate_report.py` prints a
prominent warning if a future retrain regresses below either baseline.

## LightGBM candidate (negative result, kept for the record)

```bash
python3 src/outcome_train_gbm.py   # -> data/models/outcome_model_pl_gbm.json
```

A LightGBM multiclass candidate on the same 9 features, exported to JSON and
evaluated by a pure-Python tree walker in `outcome_model.py` (the stdlib-only
inference invariant holds — no lightgbm import outside the training script).
The training script refuses to write an artifact until the pure-Python
reconstruction matches `booster.predict(raw_score=True)` to <1e-9 on every
row (it derives the class-mapping/shrinkage/base-score recipe empirically
rather than trusting documentation); the shipped artifact records the proof
in its `verification` block. Test metrics are computed through the shipped
JSON file, not the in-memory booster.

**Outcome: GBM does not beat logistic here** — test log-loss 1.068 vs
logistic's 1.030 (worse than elo-only's 1.037 too, better than frequency's
1.085). With only ~2,220 training rows, boosted trees overfit despite a
conservative grid; the linear model remains the shipped production artifact
(`outcome_model_pl.json`, untouched). The GBM artifact stays on disk as a
comparison row in `evaluate_report.py` (skipped gracefully if absent). Worth
revisiting once multi-league data multiplies the training set ~5x.

## Walk-forward harness + draw/schedule/xG improvement pass

```bash
python3 src/rolling_backtest.py    # 5-fold walk-forward comparison (ships nothing)
python3 src/outcome_train.py --ship logistic11_ew   # harness-endorsed ship
python3 src/goals_train.py         # goals model, now Dixon-Coles capable
python3 src/blend_train.py         # optional: logistic+DC blend (not currently shipped)
```

`rolling_backtest.py` evaluates fixed candidates across 5 test seasons
(2021-2025; per fold train=2017..T-3, validate=T-2, calibrate=T-1). Decision
rule: a candidate is real only if it beats the incumbent on MEAN log-loss
across folds — single-fold wins don't count. The single-split protocol in
`outcome_train.py` selects on one validate season, which is noise-prone; when
the harness disagrees, `--ship <candidate>` overrides.

Shipped: **logistic11_ew** — EW form (half-life 5) replacing flat form, plus
rest-days (capped 14) and 21-day league congestion, decay 0.8. Mean 5-fold
log-loss 0.9843 vs incumbent 0.9857 (better in 4/5 folds); 2025/26 test
log-loss 1.0274 (was 1.0300), RPS 0.2083, draw log-loss 1.4274 (was 1.4319).

Honest negatives, kept for the record: draw-focused features (elo_closeness,
draw rates, low-scoring rates) did NOT improve mean log-loss in a linear
model; the Dixon-Coles rho fit on this data is ~0 (-0.009, negligible
likelihood gain) — DC's better draw probabilities (draw log-loss 1.39 vs
logistic's 1.43) come from the Poisson score-matrix structure itself, but its
overall log-loss (1.05) is far behind the logistic, and the calibrate-fitted
blend did not beat the logistic alone (so no blend ships). Draw-only bias
calibration improved draw log-loss but not overall mean — not adopted.
xG-era features and corner_diff: no reliable gain yet (xG only exists from
2022 onward; revisit when more xG-era seasons accumulate).

## Live predictions

```bash
python3 src/predict.py                 # -> outputs/predictions.json
python3 src/predict.py --horizon-days 14
```

Generates forward predictions for upcoming PL fixtures (2026/27 season):
W/D/L probabilities from the shipped outcome model, likely score / O2.5 /
BTTS from the goals model, confidence band, and a short "why" summary. This
is the PRD 13.1 "initial prediction" stage -- no confirmed lineups exist for
future fixtures, so squad_disruption is neutral until a final-prediction
stage exists. `market_p_home` is null until odds collection starts.

## Odds collection (PRD 11 -- run this often)

```bash
python3 src/ingest_odds.py        # archive the current snapshot window per upcoming fixture
```

Append-only odds archive in the `odds_snapshots` table. Each run works out
which snapshot window (7d / 24h / 6h / 1h / closing) every upcoming PL
fixture is currently in and archives that window's odds once -- INSERT OR
IGNORE, never updated (PRD 18.4). Run it repeatedly (an hourly cron is ideal:
`0 * * * * cd <repo> && .venv/bin/python src/ingest_odds.py`) and each window
fills exactly once per fixture. Missed windows are honest gaps, never
backfilled. Core markets (Match Winner, O/U, BTTS) get structured rows with
margin-removed `normalized_prob`; the full raw responses land in
`data/raw/odds/`. `predict.py` picks up the latest snapshot's consensus
(median across bookmakers) as `market_p_home/draw/away` -- benchmark only,
never a model input (PRD 10.8) -- which flows into the web UI's market
comparison and edge column.

## Model registry (PRD 17.3)

```bash
python3 src/model_registry.py list
python3 src/model_registry.py verify   # checksums vs artifacts on disk
```

Append-only registry at `data/models/registry.json`: version, role, training
window, features, hyperparameters, calibration, test metrics, sha256
checksum, and deployment state per artifact release. The training scripts
(`outcome_train.py`, `goals_train.py`, `outcome_train_gbm.py`) register
automatically after writing an artifact -- a retrain appends a new entry and
demotes the previous deployed one, so the registry doubles as the deployment
log. `verify` fails loudly if a deployed artifact on disk no longer matches
its registered checksum.

The registry is enforced at serving time: `predict.py` and `export_web.py`
refuse to run against an artifact that is not the registered, deployed
release for its role (byte-for-byte checksum match), and every
`predictions.json` payload carries a `model_registry` block with the exact
version + sha256 it was generated from (PRD 17.4 traceability).

## Web export (real data, no mocks)

```bash
python3 src/predict.py && python3 src/export_web.py   # -> web/src/data/live.json
cd web && npm run build
```

`export_web.py` is the single bridge between the pipeline and the frontend.
It writes `web/src/data/live.json` with: upcoming-match predictions (plus
per-match Dixon-Coles score matrix, O/U + BTTS, and real factor
contributions -- z-scored feature x (coef_home - coef_away) from the shipped
logistic model), replayed-Elo standings, the 2025/26 backtest ledger /
calibration bands / headline metrics, and data-freshness timestamps from
SQLite. The web app (`web/src/lib/data.ts`) reads only this file -- there is
no mock data. Anything the pipeline can't supply yet renders an honest
placeholder: `mh` (market probability) is null until odds collection starts,
non-EPL leagues show a "not live yet" state, and the performance page is
explicitly labelled a backtest until live predictions lock.
(`export_web_data.py` is an earlier iteration of the same idea, superseded by
`export_web.py`.)

## Status

Built: Phase 0 (coverage audit), Phase 1 (PL+Championship ingestion, Elo,
outcome/goals baselines, chronological backtest+calibration, evaluation
report), PL feature enrichment (shot stats, injuries, lineups), and a web
frontend in `web/` running entirely on real exported pipeline data (see "Web
export" above), odds snapshot collection (live since 2026-08-20, PL
matchweek 1), and the model registry — all Premier League only. Not yet
built: La Liga/Serie A/Bundesliga/MLS, auth/payments/entitlements,
any Cloudflare (D1/R2) or Convex integration. Storage is local-only (SQLite +
flat JSON) until the model proves out further and a live app is actually
being deployed.
