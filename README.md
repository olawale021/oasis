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

## Learner bake-off and blend gate (2026-09-10)

```bash
python3 src/model_comparison.py            # SVM / random forest / XGBoost vs logistic, same features + split
python3 src/forest_blend.py [--ship]        # forest as a blend component, 5-fold gate (MIN_GAIN 0.001, v+u <= 0.6)
```

Random forest earned a blend slot in La Liga (0.60) and Bundesliga (0.35)
on the 5-fold mean; XGBoost and both SVM kernels were significantly worse
than logistic (paired bootstrap), and a pooled "global" forest cleared the
floor nowhere. Forest artifacts are exported as flat tree arrays and walked
in pure Python (`outcome_model.py`, float32 feature rounding to match
sklearn); the export refuses unless it reproduces `predict_proba` to <1e-9.

## External data (2026-09-10)

```bash
python3 src/ingest_team_fixtures.py --seasons 2017-2026   # all competitions per club (cups, Europe); ~110 calls/season
python3 src/ingest_squad_values.py [--dry-run]            # Transfermarkt squad values per fixture (public CSVs, no account)
```

* **All-competition fixtures** feed `rest_all_diff` / `congestion_all_diff`
  (friendlies excluded). Harness: no gain (PL -0.0003, others flat). Data
  kept; feature not shipped.
* **Squad values** (`squad_values` table): point-in-time top-25 sum of each
  player's latest valuation at the club, 18-month staleness cut; clubs
  name-matched to team ids (`tm_club_map`), reserve sides filtered.
  Feature `value_diff` = log ratio. Candidate `deployed_value` on the
  harness ladder.
* **xG**: Understat and FBref now sit behind bot protection, so the only
  legitimate source is API-Football's own `expected_goals` (2022/23+;
  statistics ingested for Serie A and MLS from 2022). Candidate
  `deployed_xg`, fair only on folds with data: `--folds 2024-2025`.

* **Player-based strength** (`player_ratings.py`): adjusted plus-minus
  ridge on starter indicators, monthly point-in-time checkpoints, summed
  over the regular XI (`xi_strength_diff`). First version: PL -0.0007,
  LAL/BUN flat -> below the floor, not shipped. Artifacts
  `data/models/player_ratings_{code}.json`; SEA lineups only 2017-18, MLS none.

Paired tests: `python3 src/rolling_backtest.py --league pl --only deployed,deployed_value`.

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

## Production refold (PRD 12.2 -- the *_live serving track)

```bash
python3 src/refold_live.py   # refit frozen methodology through 2025/26
```

Two parallel artifact tracks per league. The EVALUATION track
(`outcome_model_{code}.json`) is fit through 2024/25 with 2025/26 held out —
it is what every backtest number on the performance page comes from, and it
is never refit past that boundary. The LIVE track
(`outcome_model_{code}_live.json`, versions `*_r26`) refits the exact same
frozen methodology (features, decay, blend weights — all harness-selected)
through 2025/26 for serving 2026/27 predictions; it has no held-out season
by design, and the live locked ledger is its evaluation. `predict.py` and
the match-page factors serve the live track when it exists; match/league
pages show the serving version, the performance page shows the evaluation
versions. Re-run `refold_live.py` after any methodology change ships on the
evaluation track.

## Final stage (PRD 13.2 -- confirmed lineups)

```bash
python3 src/final_stage.py --window-minutes 35     # scripts/final_pass.sh runs this every 10 min
python3 src/lifecycle.py status                    # counts by stage; live metrics read locked_effective
```

`locked_predictions` holds one row per (fixture, stage). The hourly chain
locks `initial` 70 min out; the final pass fetches lineups once a fixture
is inside 35 min, and when both elevens are stored re-predicts with the
actual XI (squad disruption; expected-XI strength where a league has
player ratings) and locks `final`. The `locked_effective` view prefers the
final row, and every live metric, the ledger and the board read it -- the
initial row is kept so the two stages can be compared.

## Lock & settle (PRD 13.4/13.5 -- run the matchday chain hourly)

```bash
python3 src/predict.py && python3 src/lifecycle.py lock     # freeze fixtures kicking off within 30 min
python3 src/ingest_fixtures.py --seasons 2026 --force-refresh && python3 src/lifecycle.py settle
python3 src/lifecycle.py status
```

`locked_predictions` is the immutable public track record: one row per
fixture, frozen at lock time with probabilities, features, market snapshot,
and the registered model version + checksum; settlement fills the
result/scoring columns exactly once. Re-runs are no-ops (verified). Settled
live rows appear at the top of the web ledger tagged `· live`, and the
performance-page header switches to the live record as it accumulates.
Matchday cron chain (odds -> results -> predict -> lock -> settle -> export)
is in `src/lifecycle.py`'s docstring. Settlement feeds ratings/features for
the NEXT matchday automatically; it never silently retrains models -- refits
are explicit, harness-validated, and registered as new versions.

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

Built: Phase 0 (coverage audit), Phase 1 (PL model + feature enrichment),
Phase 2 first pass (2026-08-20): ten seasons of fixtures ingested for all 5
target leagues + 4 feeder divisions, injuries for all targets, per-league
outcome + goals models trained/calibrated/registered (train through 2022,
validate 2023, calibrate 2024, test 2025), odds snapshot collection live for
all 5 leagues, model registry with serving-time enforcement, and the web
frontend running entirely on real exported multi-league data.

Per-league training scripts: `--league pl|lal|sea|bun|mls` on
`outcome_train.py` / `goals_train.py` / `evaluate_report.py`. Non-PL leagues
train on the fixtures+injuries feature ladder until their shot-stat/lineup
enrichment is ingested (the ladder auto-upgrades when the data lands in the
DB — `outcome_train.py` detects it per league).

`evaluate_report.py` reports, per league: log loss / Brier / RPS / accuracy /
balanced accuracy against uniform, empirical-frequency, majority-class
(accuracy-only), calibrated Elo-only, and Dixon-Coles baselines; a
calibration slope/intercept fit (target 1.0 / 0.0) alongside binned ECE; a
confusion matrix; and paired-bootstrap 95% CIs on the log-loss delta vs the
frequency and Elo-only baselines. Selection policy (stamped in every
report): models are chosen on out-of-sample log loss with calibration
required — accuracy metrics are context only, never a selection criterion.

New all-league features (2026-08-20, fixtures-only construction, no API
cost): venue-split form (last 5 home matches vs last 5 away matches), Elo
trend (rating change over last 6 matches, promotion adjustments excluded),
and schedule strength (mean current Elo of last 10 opponents). All three
went through the per-league walk-forward harness (`rolling_backtest.py
--league <code>`, now league-generalized with enrichment-aware candidate
rows). Harness-endorsed ships: PL logistic14_new3 (mean 5-fold log-loss
0.9790 vs 0.9843 prior — schedule strength is the main driver), SEA + BUN
logistic11_new3, MLS logistic7_base (injuries feature dropped — not real
there), LAL logistic9 (none of the new features proved real; the single-split
picks were noise).

Elo warm-up (2026-08-20): 2010-2016 fixtures ingested for all 9 leagues
(17,962 fixtures; MLS exists from 2012) as replay-only history —
`HISTORY_START = 2010` in backtest_common; the scored train/validate/
calibrate/test seasons are unchanged, so ratings/venue-form/h2h enter 2017
already converged instead of cold-starting at 1500. The harness endorsed it
everywhere except MLS (old MLS is structurally different; ~flat): best-mean
log loss PL 0.9790 -> 0.9762, LAL 0.9871 -> 0.9847, SEA 0.9956 -> 0.9873,
BUN 1.0015 -> 0.9932. Cross-run comparisons are indicative, not exact —
warm-up makes a few returning teams sample-eligible earlier in early folds
(within-run decisions are clean, and the elo_only control row improving too
confirms the warm ratings themselves).

Global model + blend (PRD 9.2/9.4, 2026-08-20): `global_train.py` pools all
five leagues into one 15-feature logistic (common fixtures+injuries features
plus league-identity dummies, PL as reference) and blends it with each
league's deployed model: p = w x league + (1-w) x global. The blend weight is
selected on the 5-fold harness MEAN over a fixed-w grid — never on one
calibrate season (the single-season protocol degenerated to w=1.0 wrappers
and was scrapped). Verdict: the blend is endorsed in ALL five leagues, with
weights near the PRD's 60/40 hypothesis (PL 0.60, LAL 0.65, SEA 0.45, BUN
0.45, MLS 0.75). Deployed as self-contained blend artifacts
(`blend60_global` etc.); harness means (vs elo-only): PL 0.9740/0.9811,
LAL 0.9833/0.9850, SEA 0.9850/0.9879, BUN 0.9912/0.9947, MLS 1.0469/1.0533 —
every league now clears Elo-only. Caveats, recorded not hidden: w is one
parameter tuned on the same folds that endorse the blend (mildly optimistic,
same class of choice as the decay grid); and season-indexed pooling means the
global fit contains other-league matches wall-clock concurrent with a
league's test window (no feature crosses leagues; the only path is global
coefficients seeing contemporaneous other-league results). Enrichment
ingestion for SEA/BUN/MLS (~20.5k calls, ~3 daily quotas) runs via
`python3 src/enrich_backlog.py` once a day until it prints "backlog
complete" — after which both the league models and the global model get a
richer common feature set and the whole ladder re-runs.

Literature batch (2026-08-21, see the feature/algorithm review): learned
rating features (pi-ratings + Berrar ratings in `ratings.py`, params fitted
on the 2010-2016 warm-up years only — outside every fold; note the Berrar
defense-update sign in some summaries is a divergent positive-feedback loop
and is corrected here), a closed-door COVID flag, threshold-coded rest,
EW half-life-10 variants, minus-h2h parsimony rungs, and rho shrinkage
(|rho| must clear 2·SE; PL and LAL now at exact independence, BUN keeps its
genuinely significant -0.129 — matching Petretta 2025 exactly). Harness
verdicts vs the frozen 2026-08-21 baseline (5-fold blend means): PL 0.9740
(tie — full_kitchen "won" by 0.0001, parsimony kept logistic14_new3), LAL
0.9833 -> 0.9822 (full_kitchen), BUN 0.9912 -> 0.9877 (full_ratings, on
completed enrichment), MLS 1.0469 -> 1.0464 (base_minus_h2h — the
literature's drop-h2h claim validated), SEA held: partial enrichment
(2 of 9 seasons) contaminated its ladder run — re-evaluate after the
backlog completes. All five leagues clear Elo-only by 0.003-0.007.
Honest read: the literature's headline rating-feature gain (-0.007 to
-0.0105 RPS) did not fully materialize here because our recency block was
already warm-started, EW-weighted, venue-split and schedule-adjusted — the
ratings' marginal value is real (BUN) but smaller on an already-strong base.

Prior per-league state vs the Elo-only baseline (warm harness means): PL
0.9762 vs 0.9811; LAL 0.9847 vs 0.9850; SEA 0.9873 vs 0.9879 (ahead for the
first time — schedule strength did it); BUN 0.9932 vs 0.9947; MLS 1.0475 vs
1.0533. All five leagues now lead Elo-only on the harness mean. Single-test-
season bootstrap CIs still straddle zero for all leagues — deltas of this
size need multi-fold evidence, which is exactly what the harness provides.
Noted for later: LAL's top harness row is actually blend_draw_dc (0.9842,
+0.0005 over the shipped logistic9) — below noise and blend_train.py is not
league-generalized yet, so no blend ships; revisit if the gap grows.

Not yet built: fixture-statistics/lineup ingestion for non-PL leagues
(quota-bounded, ~2 days of Pro quota), the global model + per-league blend
(PRD 9.2/9.4), auth/payments/entitlements, any Cloudflare (D1/R2) or Convex
integration. Storage is local-only (SQLite +
flat JSON) until the model proves out further and a live app is actually
being deployed.
