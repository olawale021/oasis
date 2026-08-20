// Real pipeline data, exported by src/export_web.py (run it after predict.py
// to refresh). Nothing in this module is fabricated: fields the pipeline
// cannot supply yet (odds, non-EPL leagues, live locked predictions) are
// null / empty and the UI renders honest placeholder states for them.
import live from "@/data/live.json";
import type {
  ConfidenceBand,
  Headline,
  LeagueCode,
  LeagueFilter,
  LeagueLogLossRow,
  LeaguePerf,
  LedgerRow,
  MatchRecord,
  StandingsRow,
} from "./types";

export const LEAGUE_CODES: LeagueCode[] = ["EPL", "LAL", "SEA", "BUN", "MLS"];

export const LEAGUE_NAMES: Record<LeagueFilter, string> = {
  ALL: "All leagues",
  EPL: "Premier League",
  LAL: "La Liga",
  SEA: "Serie A",
  BUN: "Bundesliga",
  MLS: "MLS",
};

/** Leagues the model actually covers today (PRD Phase 2 adds the rest). */
export const LIVE_LEAGUES: LeagueCode[] = ["EPL"];

export const MATCHES = live.matches as MatchRecord[];
export const STANDINGS = live.standings as Record<LeagueCode, StandingsRow[]>;
export const LEAGUE_PERF = live.league_perf as Record<LeagueCode, LeaguePerf>;
export const LEDGER = live.ledger as LedgerRow[];
export const CONFIDENCE_BANDS = live.confidence_bands as ConfidenceBand[];
export const CALIBRATION_BARS = live.calibration_bars as number[];
export const LEAGUE_LOG_LOSS = live.league_log_loss as LeagueLogLossRow[];
export const HEADLINE = live.headline as Headline;
export const MODEL_VERSION = live.model_version as string;
export const GENERATED_AT = live.generated_at as string;
export const PREDICTIONS_GENERATED_AT = live.predictions_generated_at as string;
export const FRESHNESS = live.freshness as Record<string, string | null>;

export function getMatchById(id: number): MatchRecord | undefined {
  return MATCHES.find((m) => m.id === id);
}

export function matchesByLeague(lg: LeagueCode): MatchRecord[] {
  return MATCHES.filter((m) => m.lg === lg);
}

export function utcClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export function utcDayLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}
