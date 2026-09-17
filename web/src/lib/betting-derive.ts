// Pure derivation for the Betting tab: join grades to fixtures, filter,
// sort. No React, no clock -- the caller passes today's UTC date so SSR and
// hydration agree.
import { LEAGUE_NAMES } from "./data";
import type { LiveData } from "./data";
import type {
  BettingContext, BettingMarket, BettingRow, Confidence, LeagueCode, MatchRecord,
} from "./types";

export type Mode = "likely" | "edge";
export type SortKey = "prob" | "edge" | "conf" | "kickoff" | "h2h";
export type DateRange = "today" | "tomorrow" | "3d" | "7d";
export type ConfFilter = "ALL" | "MED" | "HIGH";

export interface Filters {
  /** "ALL", a market ("OU25"), or one selection ("OU25:over"). */
  market: string;
  minP: number;
  minEdge: number;
  conf: ConfFilter;
  h2hMin: number;
  /** Empty means every league. */
  leagues: LeagueCode[];
  date: DateRange;
  showPass: boolean;
  sort: SortKey;
}

export interface BettingItem extends BettingRow {
  match: MatchRecord;
  ctx: BettingContext | null;
  label: string;
  /** How many of the last-n meetings went this selection's way. */
  h2h: { k: number; n: number } | null;
}

export const MARKET_CHIPS: { key: string; label: string }[] = [
  { key: "ALL", label: "All markets" },
  { key: "1X2:home", label: "Home win" },
  { key: "1X2:draw", label: "Draw" },
  { key: "1X2:away", label: "Away win" },
  { key: "OU25:over", label: "Over 2.5" },
  { key: "OU25:under", label: "Under 2.5" },
  { key: "BTTS:yes", label: "BTTS yes" },
  { key: "BTTS:no", label: "BTTS no" },
];

const CONF_RANK: Record<Confidence, number> = { HIGH: 2, MED: 1, LOW: 0 };

/** "edge" ranks by model-vs-market disagreement. It is deliberately not
 * called value: a big edge is a candidate to investigate, and the first
 * week of the ledger showed the largest edges losing hardest. */
export function defaultsFor(mode: Mode): Filters {
  return mode === "likely"
    ? { market: "ALL", minP: 0, minEdge: 0, conf: "ALL", h2hMin: 0, leagues: [], date: "7d", showPass: true, sort: "prob" }
    : { market: "ALL", minP: 0, minEdge: 3, conf: "ALL", h2hMin: 0, leagues: [], date: "7d", showPass: false, sort: "edge" };
}

export function selectionLabel(row: BettingRow, m: MatchRecord): string {
  switch (`${row.market}:${row.sel}`) {
    case "1X2:home": return `${m.home} win`;
    case "1X2:draw": return "Draw";
    case "1X2:away": return `${m.away} win`;
    case "OU25:over": return "Over 2.5 goals";
    case "OU25:under": return "Under 2.5 goals";
    case "BTTS:yes": return "Both teams score";
    case "BTTS:no": return "Not both teams score";
    default: return `${row.market} ${row.sel}`;
  }
}

/** Meetings that went this selection's way, out of those considered. */
export function h2hSupport(row: BettingRow, ctx: BettingContext | null): { k: number; n: number } | null {
  const h = ctx?.h2h;
  if (!h || h.n === 0) return null;
  const k: Record<BettingMarket, Record<string, number>> = {
    "1X2": { home: h.hw, draw: h.d, away: h.aw },
    OU25: { over: h.over25, under: h.n - h.over25 },
    BTTS: { yes: h.btts, no: h.n - h.btts },
  };
  const v = k[row.market]?.[row.sel];
  return v === undefined ? null : { k: v, n: h.n };
}

export function buildItems(live: LiveData): BettingItem[] {
  const block = live.betting;
  if (!block) return [];
  const byId = new Map(live.matches.filter((m) => !m.gated).map((m) => [m.id, m]));
  const out: BettingItem[] = [];
  for (const row of block.rows) {
    const match = byId.get(row.id);
    if (!match) continue;
    const ctx = block.context[String(row.id)] ?? null;
    out.push({ ...row, match, ctx, label: selectionLabel(row, match), h2h: h2hSupport(row, ctx) });
  }
  return out;
}

function addDays(utcDay: string, n: number): string {
  const d = new Date(`${utcDay}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function applyFilters(items: BettingItem[], f: Filters, todayUtc: string): BettingItem[] {
  const [mkt, sel] = f.market === "ALL" ? [null, null] : f.market.split(":");
  const dayFrom = f.date === "tomorrow" ? addDays(todayUtc, 1) : todayUtc;
  const dayTo = f.date === "today" ? todayUtc : f.date === "tomorrow" ? dayFrom : addDays(todayUtc, f.date === "3d" ? 2 : 6);
  return items.filter((it) => {
    if (mkt && it.market !== mkt) return false;
    if (sel && it.sel !== sel) return false;
    if (it.p < f.minP) return false;
    if (f.minEdge > 0 && (it.edge === null || it.edge < f.minEdge)) return false;
    if (f.conf === "HIGH" && it.match.conf !== "HIGH") return false;
    if (f.conf === "MED" && it.match.conf === "LOW") return false;
    if (f.h2hMin > 0 && (it.h2h === null || it.h2h.k < f.h2hMin)) return false;
    if (f.leagues.length && !f.leagues.includes(it.match.lg)) return false;
    if (!f.showPass && it.level === "PASS") return false;
    const day = it.match.kickoffUtc.slice(0, 10);
    if (day < dayFrom || day > dayTo) return false;
    return true;
  });
}

export function sortItems(items: BettingItem[], sort: SortKey): BettingItem[] {
  const by: Record<SortKey, (a: BettingItem, b: BettingItem) => number> = {
    prob: (a, b) => b.p - a.p,
    edge: (a, b) => (b.edge ?? -Infinity) - (a.edge ?? -Infinity),
    conf: (a, b) => CONF_RANK[b.match.conf] - CONF_RANK[a.match.conf] || b.p - a.p,
    kickoff: (a, b) => a.match.kickoffUtc.localeCompare(b.match.kickoffUtc),
    h2h: (a, b) => (b.h2h ? b.h2h.k / b.h2h.n : -1) - (a.h2h ? a.h2h.k / a.h2h.n : -1) || b.p - a.p,
  };
  return [...items].sort(by[sort]);
}

export function leagueName(lg: LeagueCode): string {
  return LEAGUE_NAMES[lg];
}
