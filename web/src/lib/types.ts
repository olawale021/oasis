export type LeagueCode = "EPL" | "LAL" | "SEA" | "BUN" | "MLS";
export type LeagueFilter = "ALL" | LeagueCode;
export type Confidence = "HIGH" | "MED" | "LOW";

export interface ScoreMatrix {
  grid: number[][];
  peakRow: number;
  peakCol: number;
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
  missingHome: number;
  missingAway: number;
  factors: FactorWeight[];
  stage: string;
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
  belowBaseline: boolean;
}

export interface Headline {
  n_test: number;
  log_loss: number;
  rps: number;
  accuracy: number;
  ece: number;
  season: string;
}
