export type LeagueCode = "EPL" | "LAL" | "SEA" | "BUN" | "MLS";
export type LeagueFilter = "ALL" | LeagueCode;
export type Confidence = "HIGH" | "MED" | "LOW";

export interface ScoreMatrix {
  grid: number[][];
  peakRow: number;
  peakCol: number;
  /** Probability (%) of the modal scoreline — typically only 10–13%. */
  peakPct: number;
  over15: number;
  over25: number;
  over35: number;
  btts: number;
}

export interface FactorWeight {
  label: string;
  weight: number;
}

export interface MatchRecord {
  id: number;
  lg: LeagueCode;
  home: string;
  away: string;
  homeId: number;
  awayId: number;
  ko: string;
  h: number;
  d: number;
  a: number;
  /** Market-implied probabilities (median across bookmakers, margin removed,
   * latest archived snapshot). Null until a snapshot exists for the fixture. */
  mh: number | null;
  md: number | null;
  ma: number | null;
  marketSnapshot: string | null;
  marketBookmakers: number | null;
  score: string;
  conf: Confidence;
  st: string;
  why: string;
  kickoffUtc: string;
  round: string | null;
  muHome: number;
  muAway: number;
  matrix: ScoreMatrix;
  /** Most likely scoreline consistent with the model's top outcome, and its
   * probability (%) — more informative than the unconditional mode, which is
   * 1–1 for almost every realistic pair of goal rates. */
  condScore: string;
  condPct: number;
  pick: "home" | "draw" | "away";
  missingHome: number;
  missingAway: number;
  factors: FactorWeight[];
  stage: string;
  /** True when the server stripped the prediction fields for this viewer
   * (see lib/gate.ts). Probabilities, score, matrix, factors, market and
   * explanation are then zero/empty and must not be rendered as data. */
  gated?: boolean;
}

export interface DerivedMatch extends MatchRecord {
  leagueName: string;
  probsLabel: string;
  marketLabel: string | null;
  edge: number | null;
  edgeLabel: string;
  hot: boolean;
  statusConfirmed: boolean;
  metaLabel: string;
}

export interface StandingsRow {
  team: string;
  teamId: number;
  played: number;
  goalDiff: string;
  points: number;
  elo: number;
}

export interface LeaguePerf {
  ll: string;
  base: string;
  mkt: string;
}

export interface LedgerRow {
  date: string;
  lg: LeagueCode;
  fixture: string;
  published: string;
  final: string;
  result: string;
  won: boolean;
  logLoss: number;
  modelVersion: string;
}

export interface ConfidenceBand {
  band: string;
  n: number;
  pred: number;
  actual: number;
}

export interface LeagueLogLossRow {
  code: string;
  label: string;
  value: number;
  detail: string;
  modelLl?: number;
  freqLl?: number;
  harnessLl?: number | null;
  harnessEloLl?: number | null;
  harnessFreqLl?: number | null;
  belowBaseline: boolean;
}

export interface ReleaseHistoryEntry {
  version: string;
  registered_at: string;
  deployed: boolean;
  test_log_loss: number | null;
  test_accuracy: number | null;
  test_rps: number | null;
  features: number;
  /** 5-fold walk-forward mean for this version, when the league's latest
   * harness report evaluated it. Null for versions the harness never ran. */
  harness_ll?: number | null;
}

export interface ModelRelease {
  lg: LeagueCode;
  version: string;
  deployed_at: string;
  /** When the serving release is a *_live refold, the evaluation-track
   * version whose harness-frozen methodology it refits. */
  methodology_version?: string | null;
  test_log_loss: number | null;
  n_releases: number;
  /** 5-fold walk-forward mean — the selection metric and honest headline. */
  harness_ll?: number;
  harness_elo_ll?: number | null;
  harness_freq_ll?: number | null;
  harness_folds?: number;
  /** Chronological (oldest first). */
  history: ReleaseHistoryEntry[];
}

export interface RecentResult {
  id: number;
  lg: LeagueCode;
  home: string;
  away: string;
  homeId: number;
  awayId: number;
  kickoffUtc: string;
  ko: string;
  score: string;
  /** The immutable pre-kickoff prediction — null for fixtures played before
   * the lock lifecycle went live (2026-08-20). */
  locked: {
    h: number;
    d: number;
    a: number;
    /** Bookmaker consensus at lock time (median, margin removed). Null when
     * no odds snapshot existed, or on payloads older than 2026-09-12. */
    mh?: number | null;
    md?: number | null;
    ma?: number | null;
    marketBookmakers?: number | null;
    /** 0 home, 1 draw, 2 away; null until settled. */
    outcome?: 0 | 1 | 2 | null;
    correct: boolean | null;
    logLoss: number | null;
    marketLogLoss?: number | null;
    /** True when the model gave the real result more probability than the
     * market did; null when either side is missing. */
    closer?: boolean | null;
    modelVersion: string;
    stage: string;
  } | null;
  /** Point-in-time reconstruction by the serving model (pre-match features,
   * no leakage) for fixtures that were never locked. Display-only — clearly
   * labeled, never part of the live record. */
  retro: {
    h: number;
    d: number;
    a: number;
    correct: boolean;
    modelVersion: string;
  } | null;
}

export interface Headline {
  n_test: number;
  log_loss: number;
  rps: number;
  accuracy: number;
  ece: number;
  season: string;
}

export interface ExperimentRow {
  lg: string;
  label?: string;
  before: number;
  after: number;
  delta: number;
  folds: number;
  folds_won: number | null;
  shipped: boolean;
  detail?: string;
  ran_at: string;
}

export interface Experiment {
  key: string;
  label: string;
  blurb: string;
  metric: string;
  rows: ExperimentRow[];
}

// --- Betting tab (Betting PRD 4, 5, 16) -----------------------------------

export type BettingMarket = "1X2" | "OU25" | "BTTS";
export type BettingLevel = "PASS" | "WATCH" | "VALUE" | "STRONG_VALUE";

export interface BettingReason {
  code: string;
  detail: string;
}

/** One selection of one market on one upcoming fixture. Percentages, not
 * fractions: p/mp/edge/ev are already x100. `locked` rows come from the
 * ledger (graded as of lock, reproducible); the rest are previews graded
 * now with the same rulebook. */
export interface BettingRow {
  id: number;
  market: BettingMarket;
  sel: string;
  p: number;
  mp: number | null;
  edge: number | null;
  odds: number | null;
  book: string | null;
  ev: number | null;
  books: number | null;
  snap: string | null;
  level: BettingLevel;
  reasons: BettingReason[];
  locked: boolean;
}

export interface TeamTrend {
  n: number;
  btts: number;
  over25: number;
  gf: number;
  ga: number;
}

export interface H2HSummary {
  n: number;
  hw: number;
  d: number;
  aw: number;
  hg: number;
  ag: number;
  btts: number;
  over25: number;
  avg: number | null;
  last: string | null;
}

export interface BettingContext {
  h2h: H2HSummary | null;
  home: TeamTrend | null;
  away: TeamTrend | null;
}

export interface BettingBlock {
  thresholds_version: string;
  markets: Record<BettingMarket, string[]>;
  generated_at: string;
  rows: BettingRow[];
  /** Keyed by fixture id as a string (JSON object keys). */
  context: Record<string, BettingContext>;
}
