// Static configuration + pure derivation over the live data payload.
//
// The payload (produced by src/export_web.py) lives in Cloudflare KV in
// production — the matchday chain uploads it with `wrangler kv key put`, so
// data updates never require a redeploy. Server components fetch it via
// lib/live-server.ts and pass it (or slices of it) down as props; the JSON
// bundled at build time is only the dev/cold-start fallback.
import type {
  ConfidenceBand,
  Headline,
  LeagueCode,
  LeagueFilter,
  LeagueLogLossRow,
  LeaguePerf,
  LedgerRow,
  MatchRecord,
  ModelRelease,
  RecentResult,
  StandingsRow,
} from "./types";

export interface LiveData {
  generated_at: string;
  predictions_generated_at: string;
  live_leagues: LeagueCode[];
  model_versions: Record<LeagueCode, string>;
  model_releases: ModelRelease[];
  freshness: Record<string, string | null>;
  matches: MatchRecord[];
  standings: Record<LeagueCode, StandingsRow[]>;
  league_perf: Record<LeagueCode, LeaguePerf>;
  ledger: LedgerRow[];
  confidence_bands: ConfidenceBand[];
  calibration_bars: number[];
  league_log_loss: LeagueLogLossRow[];
  headline: Headline;
  live_record: {
    locked: number;
    settled: number;
    log_loss: number | null;
    brier: number | null;
    accuracy: number | null;
  };
  recent_results: RecentResult[];
}

export const LEAGUE_CODES: LeagueCode[] = ["EPL", "LAL", "SEA", "BUN", "MLS"];

export const LEAGUE_NAMES: Record<LeagueFilter, string> = {
  ALL: "All leagues",
  EPL: "Premier League",
  LAL: "La Liga",
  SEA: "Serie A",
  BUN: "Bundesliga",
  MLS: "MLS",
};

export function getMatchById(live: LiveData, id: number): MatchRecord | undefined {
  return live.matches.find((m) => m.id === id);
}

export function matchesByLeague(live: LiveData, lg: LeagueCode): MatchRecord[] {
  return live.matches.filter((m) => m.lg === lg);
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
