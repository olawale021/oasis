// Static configuration + pure derivation over the live data payload.
//
// The payload (produced by src/export_web.py) lives in Cloudflare KV in
// production — the matchday chain uploads it with `wrangler kv key put`, so
// data updates never require a redeploy. Server components fetch it via
// lib/live-server.ts and pass it (or slices of it) down as props; the JSON
// bundled at build time is only the dev/cold-start fallback.
import type {
  BettingBlock,
  ConfidenceBand,
  GoalsSkill,
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
  Experiment,
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
    market_n: number;
    market_log_loss: number | null;
    model_log_loss_on_market: number | null;
    /** Settled rows where the model beat the market on the real result. */
    closer_n?: number;
  };
  /** Bookmakers behind the market line (last 30 days of snapshots). */
  bookmakers?: string[];
  recent_results: RecentResult[];
  experiments: Experiment[];
  factor_glossary: Record<string, string>;
  /** Free-tier taster, pinned per UTC day by the matchday chain:
   * {"2026-09-12": [fixtureId, fixtureId]}. Only today's entry is used. */
  taster?: Record<string, number[]>;
  /** Per-selection grades and H2H/form context for the Betting tab. Absent
   * on payloads exported before the betting layer existed. */
  betting?: BettingBlock;
  /** Goals-model skill receipts for the Performance page; null until the
   * diagnostic has run on the exporting machine. */
  goals_skill?: GoalsSkill | null;
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

export interface MarketTotal {
  /** Bookmaker consensus probability, %, margin removed. */
  mp: number;
  books: number | null;
  snap: string | null;
}

/** Bookmaker consensus for Over 2.5 and BTTS on one fixture, from the
 * betting block (already gated per viewer). The match page leads with these
 * because the goals model has no validated skill on totals. */
export function marketTotals(live: LiveData, id: number): { over25: MarketTotal | null; btts: MarketTotal | null } {
  const rows = live.betting?.rows ?? [];
  const pick = (market: string, sel: string): MarketTotal | null => {
    const r = rows.find((x) => x.id === id && x.market === market && x.sel === sel);
    return r && r.mp !== null ? { mp: r.mp, books: r.books, snap: r.snap } : null;
  };
  return { over25: pick("OU25", "over"), btts: pick("BTTS", "yes") };
}
