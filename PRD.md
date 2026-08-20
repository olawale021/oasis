# Product Requirements Document

## Five-League Football Prediction Platform

**Status:** Draft  
**Version:** 1.0  
**Date:** August 19, 2026  
**Primary delivery:** Web application  
**Secondary delivery:** Telegram bot and alerts

---

## 1. Product Summary

Build a paid football prediction platform covering:

1. English Premier League
2. La Liga
3. Serie A
4. Bundesliga
5. Major League Soccer

The product will produce transparent pre-match probabilities, likely scores, and supporting explanations from independently trained models. A responsive web application will be the main product. A Telegram bot will distribute daily predictions, alerts, and account access.

Users will be able to purchase one-time lifetime access. Lifetime access should initially be offered as a limited founding-member product so recurring data and infrastructure costs do not create an unsustainable obligation.

The product must not promise betting profits. All predictions must be presented as probabilistic forecasts.

---

## 2. Problem

Football prediction products commonly suffer from:

- Unverifiable accuracy claims
- Deleted or edited losing predictions
- No explanation of model inputs
- Poor probability calibration
- Predictions published only after market movement
- Generic models that ignore league-specific behavior
- Excessive focus on “AI picks” instead of measurable performance

Users need a transparent platform that:

- Publishes predictions before kickoff
- Permanently records every prediction
- Shows probabilities rather than guaranteed picks
- Explains the major factors behind each forecast
- Reports historical performance honestly
- Updates forecasts when injuries and lineups change

---

## 3. Goals

### 3.1 Product goals

- Cover all scheduled matches in the five selected leagues.
- Generate independent home-win, draw, and away-win probabilities.
- Generate expected goals and likely scorelines.
- Publish initial and lineup-adjusted predictions.
- Show the model factors influencing each prediction.
- Maintain an immutable historical prediction record.
- Distribute premium alerts through Telegram.
- Monetize through one-time paid lifetime access.
- Build a reusable pipeline for adding competitions later.

### 3.2 Model goals

- Beat simple baselines such as home-team frequency and league-table position.
- Produce calibrated probabilities.
- Evaluate performance separately for every league.
- Compare performance with bookmaker closing probabilities.
- Prevent future-data leakage in training and evaluation.
- Track results by model version.

### 3.3 Business goals

- Validate paid demand with a limited founding-member launch.
- Convert free users through transparent historical performance.
- Keep initial data and infrastructure costs below recurring revenue reserves.
- Establish web and Telegram channels without maintaining two separate products.

---

## 4. Non-Goals

The first release will not:

- Place bets automatically.
- Guarantee returns or market the platform as risk-free.
- Provide live in-play betting recommendations.
- Cover leagues outside the selected five.
- Train on API-Football’s prediction endpoint.
- Build a proprietary shot-level expected-goals model without shot coordinates.
- Redistribute raw API-Football feeds as a standalone data product.
- Provide native iOS or Android applications.

---

## 5. Target Users

### 5.1 Data-driven football fan

Wants probabilities, recent form, team strength, and explainable predictions.

### 5.2 Betting-oriented user

Wants to compare model probabilities with bookmaker-implied probabilities. The product must clearly communicate uncertainty and responsible-use warnings.

### 5.3 Telegram-first user

Wants concise daily forecasts and important prediction-change alerts without repeatedly opening a website.

### 5.4 Analyst or content creator

Wants historical performance, league comparisons, and shareable match insights.

---

## 6. Competition Scope

| League | API-Football ID | Season format |
|---|---:|---|
| English Premier League | 39 | Starting year, e.g. `2026` for 2026/27 |
| La Liga | 140 | Starting year |
| Serie A | 135 | Starting year |
| Bundesliga | 78 | Starting year |
| Major League Soccer | 253 | Calendar year |

European promotion initialization requires supporting data from:

- Championship
- Segunda División
- Serie B
- 2. Bundesliga

These second divisions are training inputs only and are not customer-facing prediction products in the initial release.

---

## 7. Data Provider

### 7.1 Primary provider

API-Football by API-Sports.

### 7.2 Required API-Football data

- Leagues and season coverage
- Fixtures and results
- Standings
- Match events
- Fixture statistics
- Fixture player statistics
- Team season statistics
- Squads and player statistics
- Injuries and suspensions
- Confirmed lineups and formations
- Coaches
- Transfers
- Head-to-head fixtures
- Top scorers, assists, and cards
- Pre-match odds
- In-play odds only if introduced in a later phase

API-Football’s own `/predictions` response may be stored as an external benchmark, but it must not be used as a training feature or target.

### 7.3 Coverage verification

Before ingestion, query the `coverage` object for every league-season:

```text
/leagues?id=39&season=2026
/leagues?id=140&season=2026
/leagues?id=135&season=2026
/leagues?id=78&season=2026
/leagues?id=253&season=2026
```

The pipeline must not assume that injuries, player statistics, lineups, predictions, or odds are available. It must read the season-specific flags and degrade gracefully.

### 7.4 Known data gaps

API-Football does not reliably provide:

- Native expected goals
- Shot locations or shot maps
- Player market values
- Weather
- Reliable predicted lineups several days before kickoff
- A complete historical odds archive

The MVP will use an attack-quality proxy based on goals, shots, shots on target, possession, corners, player output, and opponent strength. It must not label this value as provider-supplied xG.

### 7.5 API plan

The free plan will be used to validate coverage and response quality. The expected initial production plan is Pro, subject to confirming that required historical seasons are accessible.

All provider requests must be server-side and cached. The API key must never be exposed to browsers or Telegram clients.

---

## 8. Historical Data Strategy

### 8.1 Results history

Pull ten seasons of fixtures and results for each selected league.

For European leagues:

```text
2017/18 through 2026/27
```

For MLS:

```text
2017 through 2026
```

Exact starting seasons may shift depending on provider availability.

### 8.2 Deeper data history

| Data type | Desired depth |
|---|---:|
| Fixtures and results | 10 seasons |
| Team season statistics | 5 seasons |
| Fixture statistics | 3–5 seasons |
| Player statistics | 2–3 seasons |
| Lineups | 2–3 seasons |
| Head-to-head | Up to 10 seasons, low weight |
| Coaches and manager changes | 3 seasons |
| Transfers | 2–3 seasons |
| Injuries | Current season onward, archived internally |
| Odds | Collect continuously from launch |

### 8.3 Time decay

Older data must receive less weight. Initial target weighting:

| Age | Relative weight |
|---|---:|
| Current season | 100% |
| One season old | 80% |
| Two seasons old | 64% |
| Three seasons old | 51% |
| Four seasons old | 41% |
| Five seasons old | 33% |
| Six to ten seasons old | Progressively lower |

Weights will be tuned through rolling backtests.

---

## 9. Modeling Architecture

### 9.1 Architecture principle

Use one shared feature and training pipeline with:

- One global football model
- One league-specific model per supported league
- One probability calibrator per league
- One goals model per league

Do not build five unrelated codebases.

### 9.2 Global model

The global model trains across all five leagues and includes league identity and league-specific interactions. It learns shared football relationships and provides stability when local samples are small.

### 9.3 League models

Train independent model instances for:

- Premier League
- La Liga
- Serie A
- Bundesliga
- MLS

League models learn local:

- Home advantage
- Baseline goal rate
- Draw frequency
- Tactical patterns
- Schedule characteristics
- Feature importance

### 9.4 Initial ensemble

Initial final probability:

```text
60% league-specific model
40% global model
```

The blend must be selected through validation. It is not a permanent hardcoded assumption.

### 9.5 Outcome model

Predict:

- Home win
- Draw
- Away win

Required baselines:

- League historical frequency
- Elo-only model
- Multinomial logistic regression

Candidate production algorithms:

- CatBoost
- LightGBM
- Calibrated multinomial models

### 9.6 Goals model

Predict:

- Expected home goals
- Expected away goals
- Score probability matrix
- Most likely score
- Over/under probabilities
- Both-teams-to-score probability

Required baseline:

- Poisson model

Candidate production model:

- Dixon–Coles
- Gradient-boosted expected-goals model
- Ensemble of statistical and boosted models

### 9.7 Probability calibration

Each league must receive a separate calibrator using Platt scaling, isotonic regression, or another validated method.

Calibration is required before comparing model probabilities with bookmaker probabilities.

---

## 10. Model Features

### 10.1 Team strength

- Club Elo
- Elo change
- Opponent-adjusted results
- League position
- Points per game
- Goal difference
- Promoted-team prior
- Expansion-team prior for MLS

### 10.2 Recent form

- Last 5 matches
- Last 10 matches
- Home-only form
- Away-only form
- Goals scored and conceded
- Shots and shots on target
- Opponent-strength-adjusted form
- Exponentially weighted form

### 10.3 Attack and defence

- Goals per match
- Goals conceded per match
- Shots
- Shots on target
- Shot conversion
- Save rate
- Clean-sheet rate
- Failed-to-score rate
- Possession
- Corners
- Player scoring depth
- Penalty dependence

### 10.4 Squad and player availability

- Injuries
- Suspensions
- Missing starters
- Confirmed lineup strength
- Bench strength
- Player minutes
- Player ratings
- Goals and assists
- Top-scorer availability
- Squad turnover

### 10.5 Match context

- Home advantage
- Rest days
- Fixture congestion
- Domestic cup congestion
- European competition congestion
- Manager tenure and change
- Travel distance
- Time-zone changes
- Season stage
- Relegation or title-race context if validated

### 10.6 Head-to-head

- Previous meetings
- Venue-adjusted results
- Goals per meeting

Head-to-head receives low weight and must be regularized toward neutral when the sample is small or the matches are old.

### 10.7 MLS-specific features

- Conference
- Regular season versus playoff
- Expansion-team status
- Travel distance
- Time-zone change
- Surface where reliably available
- International call-up impact
- Schedule imbalance

### 10.8 Odds

Bookmaker odds are not API-Football predictions. They are market prices.

Odds will initially be used for:

- External benchmarking
- Probability calibration analysis
- Market movement tracking
- Potential value indicators

Odds must not be included as a primary model feature during initial development. This keeps the model independent and allows honest comparison against the market.

### 10.9 API-Football predictions

API-Football predictions will:

- Not train the model
- Not become labels
- Not affect initial forecasts
- Appear only in internal benchmark reports

They may be considered as a small ensemble component only after independent backtesting proves incremental value.

---

## 11. Odds Collection

Because complete historical odds are not available, the platform must archive odds from launch onward.

Target snapshots:

- Seven days before kickoff
- Twenty-four hours before kickoff
- Six hours before kickoff
- One hour before kickoff
- After confirmed lineups
- Closing snapshot

Store:

- Bookmaker
- Market
- Outcome
- Decimal odds
- Implied probability
- Normalized implied probability
- Collection timestamp

The system will remove bookmaker margin before comparing market probability with model probability.

Potential value:

```text
model_probability - normalized_market_probability
```

Value indicators must be presented as probability differences, not guaranteed bets.

---

## 12. Training and Evaluation

### 12.1 Split strategy

Never randomly split matches. Use chronological rolling validation.

Example:

```text
Train: seasons 1–7
Validate: season 8
Calibrate: season 9
Test: season 10
```

Repeat with rolling windows.

### 12.2 2026/27 launch strategy

- Train through 2024/25
- Validate and calibrate on 2025/26
- Test final frozen configuration on 2025/26
- Retrain with approved data for 2026/27
- Update ratings after each completed match
- Refit full models on a controlled schedule

### 12.3 Evaluation metrics

Outcome model:

- Multiclass log loss
- Brier score
- Ranked probability score
- Accuracy
- Calibration error
- Reliability plots

Goals model:

- Poisson deviance
- Mean absolute goal error
- Exact-score accuracy
- Over/under calibration
- Both-teams-to-score calibration

Market comparison:

- Log loss versus normalized closing odds
- Brier score versus closing odds
- Probability-edge performance by bucket
- Closing-line comparison

### 12.4 Required reporting

Report metrics:

- Globally
- Per league
- Per season
- By home/draw/away outcome
- By confidence band
- Before and after lineups
- By model version

---

## 13. Prediction Lifecycle

### 13.1 Initial prediction

Published 12–24 hours before kickoff using:

- Current team ratings
- Recent form
- Expected availability
- Rest and congestion
- Current odds benchmark

### 13.2 Injury update

Regenerate when important injury or suspension information changes.

### 13.3 Final prediction

Regenerate approximately 30–60 minutes before kickoff after confirmed lineups.

### 13.4 Locking

At kickoff:

- Lock the final prediction
- Save all component probabilities
- Save model version
- Save feature snapshot
- Save odds snapshot
- Prevent edits

### 13.5 Settlement

After full time:

- Attach actual result
- Calculate model metrics
- Update public performance
- Update team ratings
- Preserve original predictions

---

## 14. Web Application

### 14.1 Technology and UI

- Responsive web application
- ShadCN UI components
- Mobile-first match browsing
- Accessible probability displays
- Server-side provider integration

### 14.2 Core pages

#### Home

- Today’s predictions
- Next matches
- Recent model performance
- Supported leagues
- Upgrade prompt

#### League page

- Fixtures
- Predictions
- Standings
- League model performance
- League-specific filters

#### Match page

- Home/draw/away probabilities
- Likely score
- Expected goals proxy
- Over/under and both-teams-to-score
- Recent form
- Team strength
- Injuries and suspensions
- Confirmed lineups
- Head-to-head
- Model explanation
- Market comparison
- Prediction update timeline

#### Performance page

- All historical predictions
- No deleted losses
- Calibration results
- Performance by league
- Performance by confidence
- Model version history

#### Account page

- Access status
- Purchase record
- Telegram connection
- Alert preferences
- Responsible-use settings

#### Admin page

- Ingestion health
- API quota
- Missing coverage
- Prediction generation status
- Failed fixtures
- Model version deployment
- User access

---

## 15. Telegram Bot

### 15.1 Role

Telegram is an alert and retention channel. The web application remains the source of truth.

### 15.2 Commands

```text
/today
/premierleague
/laliga
/seriea
/bundesliga
/mls
/match
/results
/performance
/account
/alerts
```

### 15.3 Alerts

- Daily prediction digest
- High-confidence forecast
- Material probability change
- Injury update
- Confirmed-lineup update
- Final prediction
- Match result and model settlement

Users must be able to select leagues and notification types.

---

## 16. Access and Monetization

### 16.1 Free access

- Limited daily predictions
- Basic home/draw/away probabilities
- Delayed or partial match explanations
- Public historical performance
- Selected Telegram previews

### 16.2 Lifetime access

- All five leagues
- Every match prediction
- Score and totals projections
- Full explanations
- Injury and lineup updates
- Telegram alerts
- Market comparison
- Historical filters
- Future improvements included, subject to product terms

### 16.3 Launch offer

Recommended structure:

- Limited founding-member lifetime access
- Quantity cap
- One-time purchase
- Clearly defined product-lifetime terms
- Pricing finalized after data and infrastructure costs are confirmed

Possible test range:

```text
Founding lifetime: $49–$79
Standard lifetime: $129–$199
```

Pricing is a hypothesis and must be validated.

### 16.4 Payments

Web:

- Stripe or another approved processor

Telegram:

- Telegram Stars for digital access purchased inside Telegram

One user account must map web identity, payment identity, and Telegram identity securely.

### 16.5 Additional future revenue

- League-specific passes
- Developer prediction API
- White-label widgets
- Affiliate partnerships where lawful
- Sponsored content
- Premium data exports

---

## 17. Functional Requirements

### 17.1 Data ingestion

- Scheduled API ingestion
- Idempotent writes
- Stable provider ID mapping
- Coverage-aware endpoint calls
- Retry with backoff
- Quota monitoring
- Raw-response archival where permitted
- Data validation and anomaly alerts

### 17.2 Feature pipeline

- Point-in-time correct features
- No post-kickoff data in pre-match features
- Reproducible feature snapshots
- Shared definitions across training and inference
- League-specific transformations where required

### 17.3 Model registry

Each model release stores:

- Version
- Training window
- Features
- Parameters
- Calibration method
- Validation metrics
- Deployment date
- Artifact checksum

### 17.4 Prediction records

Each prediction stores:

- Fixture ID
- League
- Publication timestamp
- Model version
- Home/draw/away probabilities
- Goal expectations
- Score matrix
- Feature snapshot
- Market snapshot
- Update reason
- Final locked state
- Actual result

### 17.5 Entitlements

- Free versus lifetime access
- Server-side authorization
- Payment verification
- Telegram identity linking
- Refund and revocation support

---

## 18. Non-Functional Requirements

### 18.1 Performance

- Cached dashboard responses
- Match pages load without direct provider calls
- Prediction refresh completes before publishing deadlines

### 18.2 Reliability

- Provider outages do not remove existing predictions
- Last successful data timestamp is visible internally
- Missing features degrade gracefully
- Predictions are not regenerated silently after kickoff

### 18.3 Security

- API keys remain server-side
- Secrets stored in environment variables or a secret manager
- Payment webhooks verified
- Telegram payments verified
- Admin routes protected
- Rate limiting on public APIs

### 18.4 Auditability

- Immutable prediction history
- Logged model deployments
- Logged manual interventions
- Timestamped odds snapshots

---

## 19. Legal and Compliance

### 19.1 Data rights

API-Football’s subscription does not automatically grant commercial publication rights for league data, logos, images, or trademarks.

Before monetization:

- Contact API-Football support.
- Describe the paid derived-prediction product.
- Confirm permitted storage and display.
- Confirm whether displaying fixtures, statistics, odds, and team names is allowed.
- Obtain necessary permissions from relevant rights holders.
- Avoid league, club, and player images until rights are confirmed.

### 19.2 Betting-related compliance

- Do not guarantee profits.
- Include responsible-use notices.
- Consider age gating.
- Review laws in every launch market.
- Review whether affiliate activity requires licensing.
- Avoid automated betting in the initial release.
- Present probabilities and historical performance honestly.

### 19.3 Product terms

Lifetime access must define:

- Lifetime of the product
- Included leagues and features
- Provider-dependent availability
- Refund policy
- Service termination rights
- Prohibited account sharing

---

## 20. Success Metrics

### 20.1 Model metrics

- Log loss improvement over league-frequency baseline
- Brier score improvement over Elo baseline
- Calibration error
- Performance versus normalized closing odds
- Stability across leagues and seasons

### 20.2 Product metrics

- Weekly active users
- Prediction page views
- Telegram connection rate
- Alert open rate
- Free-to-paid conversion
- Founding-member sales
- Thirty-day retention
- Refund rate

### 20.3 Operational metrics

- Successful ingestion rate
- Missing-feature rate
- Prediction publication punctuality
- API requests per day
- API quota utilization
- Failed lineup updates

---

## 21. Delivery Phases

### Phase 0: Data and legal validation

- Confirm commercial data rights.
- Audit 2026 season coverage for all five leagues.
- Verify historical season access.
- Test response completeness.
- Estimate daily API usage.
- Select subscription.

### Phase 1: Premier League model

- Ingest ten seasons.
- Add Championship history for promoted clubs.
- Build Elo, outcome, and goals baselines.
- Build chronological backtests.
- Add probability calibration.
- Create internal evaluation report.

### Phase 2: Five-league platform

- Add La Liga, Serie A, Bundesliga, and MLS.
- Add supporting second divisions.
- Train global and league models.
- Add odds collection.
- Add injuries and lineup updates.
- Create model registry.

### Phase 3: Web MVP

- Build ShadCN dashboard.
- Add league and match pages.
- Add performance reporting.
- Add authentication and entitlements.
- Add one-time payment.
- Add admin health page.

### Phase 4: Telegram

- Add account linking.
- Add commands.
- Add Telegram Stars payment.
- Add customizable alerts.

### Phase 5: Paid launch

- Launch limited founding-lifetime offer.
- Publish methodology and backtests.
- Monitor conversion and data costs.
- Collect feedback.
- Tune pricing and limits.

---

## 22. Launch Criteria

The paid product cannot launch until:

- Commercial use has been reviewed.
- All five league-season coverage responses are audited.
- Historical data ingestion succeeds.
- No material point-in-time leakage exists.
- Every league beats basic baselines on held-out data.
- Probabilities are calibrated.
- Predictions lock at kickoff.
- Public history cannot be edited or deleted.
- Payments and entitlements are verified.
- Telegram alerts respect user preferences.
- Responsible-use messaging is visible.

---

## 23. Risks

| Risk | Mitigation |
|---|---|
| API lacks true xG | Use transparent attack proxy; add provider later |
| Historical deep stats unavailable | Train long-term ratings on results and recent models on richer data |
| Historical odds unavailable | Begin snapshot collection immediately |
| Injuries are incomplete | Display source freshness; avoid false completeness |
| Model overfits one league | Rolling tests, global model, regularization |
| Promoted clubs have no top-flight history | Ingest second divisions and apply promoted-team priors |
| MLS differs structurally | Add MLS-specific features and calibration |
| Lifetime revenue is exhausted by recurring costs | Limit founding memberships and maintain cost reserve |
| Data publication rights are unclear | Obtain written confirmation and legal review |
| Users interpret forecasts as guarantees | Use probability-first UX and responsible-use messaging |

---

## 24. Open Decisions

- Final product name and brand
- Launch countries
- Founding-member quantity and price
- Exact payment processor
- Authentication provider
- Database and hosting platform
- Whether odds are visible to all premium users
- Whether API-Football predictions appear publicly or only internally
- Whether a second provider is required for xG
- Whether lifetime access includes future leagues
- Legal interpretation of derived predictions and displayed sports data

---

## 25. Recommended Immediate Next Steps

1. Configure the API-Football key securely.
2. Run a coverage audit for all five 2026 seasons.
3. Check which ten historical seasons are available on the free plan.
4. Estimate the paid-plan request volume.
5. Contact API-Football about commercial usage.
6. Build the ten-season Premier League ingestion pipeline.
7. Pull Championship data for promoted teams.
8. Establish Elo, logistic, Poisson, and Dixon–Coles baselines.
9. Backtest chronologically against 2025/26.
10. Begin collecting upcoming-match odds immediately.
