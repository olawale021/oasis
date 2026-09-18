// Message builders: pure functions over the live payload. HTML parse mode,
// so every piece of data goes through esc(). The footer is on every
// message that carries a forecast, and betting messages carry their own.
import { LEAGUE_NAMES, utcClock } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import { selectionLabel } from "@/lib/betting-derive";
import type { BettingRow, LeagueCode, MatchRecord, RecentResult } from "@/lib/types";
import type { TelegramPrefs } from "./store";

export const FOOTER = "<i>Probabilities, not tips. A 70% forecast fails about 3 times in 10. 18+ · /alerts to change what you get.</i>";
const BETTING_FOOTER =
  "<i>Grades classify a disagreement between the model and the bookmakers under a published rulebook; they are not advice. Nothing is VALUE until the backtest says so. 18+ · never chase losses · GamCare 0808 8020 133.</i>";

export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const pick = (m: MatchRecord) => (m.pick === "home" ? m.home : m.pick === "away" ? m.away : "Draw");
const day = (iso: string) => iso.slice(0, 10);
const dayLabel = (isoDay: string) =>
  new Date(`${isoDay}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });

const shortName = (name: string) => esc(name.replace(/^(FC|SV|RB|AS|SS|US|AC|1\. FC) /, "").replace(/ (FC|CF|SC|AFC|BC|SAD)$/, ""));

function fixtureLine(m: MatchRecord): string {
  const head = `${utcClock(m.kickoffUtc)}  <b>${shortName(m.home)}</b> v <b>${shortName(m.away)}</b>`;
  if (m.gated) return `${head}  🔒`;
  const conf = m.conf === "HIGH" ? " · <b>high</b>" : "";
  return `${head}\n        ${Math.round(m.h)} · ${Math.round(m.d)} · ${Math.round(m.a)}  →  ${esc(pick(m))}${conf}`;
}

/** Group rows by league, in the site's league order, with a heading per
 * league and a blank line between groups: readable on a phone, no code
 * repeated on every row. */
function byLeague<T extends { lg: LeagueCode }>(rows: T[], line: (r: T) => string): string {
  const order: LeagueCode[] = ["EPL", "LAL", "SEA", "BUN", "MLS", "UCL"];
  const groups: string[] = [];
  for (const lg of order) {
    const rs = rows.filter((r) => r.lg === lg);
    if (rs.length) groups.push(`<b>${esc(LEAGUE_NAMES[lg])}</b>\n${rs.map(line).join("\n")}`);
  }
  return groups.join("\n\n");
}

export interface Page {
  offset?: number;
  limit?: number;
}
export interface View {
  text: string;
  hasMore: boolean;
  total: number;
}

const PAGE = 12;

/** Upcoming fixtures on the payload's UTC day; if none, the next day that
 * has any. `leagues` filters; `league` is a single explicit ask. */
export function todayMessage(live: LiveData, leagues: LeagueCode[], league?: LeagueCode): string {
  return todayView(live, leagues, league).text;
}

export function todayView(live: LiveData, leagues: LeagueCode[], league?: LeagueCode, page: Page = {}): View {
  const wanted = (m: MatchRecord) => (league ? m.lg === league : leagues.includes(m.lg));
  const upcoming = live.matches.filter((m) => wanted(m) && m.kickoffUtc >= live.generated_at.slice(0, 13)).sort((a, b) => a.kickoffUtc.localeCompare(b.kickoffUtc));
  if (upcoming.length === 0) return { text: `No upcoming fixtures${league ? ` in ${LEAGUE_NAMES[league]}` : ""} in the next week.\n\n${FOOTER}`, hasMore: false, total: 0 };
  const today = day(live.generated_at);
  let target = upcoming.filter((m) => day(m.kickoffUtc) === today);
  let title = "Today";
  if (target.length === 0) {
    const next = day(upcoming[0].kickoffUtc);
    target = upcoming.filter((m) => day(m.kickoffUtc) === next);
    title = dayLabel(next);
  }
  const offset = page.offset ?? 0;
  const limit = page.limit ?? PAGE;
  const slice = target.slice(offset, offset + limit);
  const locked = slice.filter((m) => m.gated).length;
  const lockedNote = locked ? `\n\n🔒 ${locked} locked — sign in for the daily taster, lifetime for all.` : "";
  const legend = locked < slice.length ? "<i>home · draw · away %, then the model's pick.</i>\n" : "";
  const range = target.length > limit ? ` · ${offset + 1}–${offset + slice.length} of ${target.length}` : ` · ${target.length} ${target.length === 1 ? "match" : "matches"}`;
  return {
    text: `<b>${title}</b>${league ? ` · ${esc(LEAGUE_NAMES[league])}` : ""}${range} · times UTC\n\n${byLeague(slice, fixtureLine)}${lockedNote}\n\n${legend}${FOOTER}`,
    hasMore: offset + slice.length < target.length,
    total: target.length,
  };
}

function resultLine(r: RecentResult): string {
  const l = r.locked!;
  const hit = l.correct ? "✅" : "❌";
  const beat = l.closer === true ? " ↑" : "";
  // The score says who won; only a miss needs the pick spelled out.
  const picked = l.h >= l.d && l.h >= l.a ? r.home : l.a >= l.d ? r.away : "Draw";
  const miss = l.correct ? "" : `  <i>(picked ${shortName(picked)})</i>`;
  return `${hit} ${shortName(r.home)} <b>${esc(r.score)}</b> ${shortName(r.away)}${beat}${miss}`;
}

export function resultsMessage(live: LiveData, leagues: LeagueCode[], sinceDay?: string, league?: LeagueCode): string {
  return resultsView(live, leagues, sinceDay, league).text;
}

/** Results paged by DAY (a day is the natural unit), newest first. */
export function resultsView(live: LiveData, leagues: LeagueCode[], sinceDay?: string, league?: LeagueCode, page: Page = {}): View {
  const rows = live.recent_results
    .filter((r) => r.locked && r.locked.correct != null && (league ? r.lg === league : leagues.includes(r.lg)) && (!sinceDay || day(r.kickoffUtc) >= sinceDay))
    .sort((a, b) => b.kickoffUtc.localeCompare(a.kickoffUtc));
  if (rows.length === 0) return { text: `No settled forecasts${league ? ` in ${esc(LEAGUE_NAMES[league])}` : ""} in the last week.`, hasMore: false, total: 0 };
  const hits = rows.filter((r) => r.locked!.correct).length;
  const compared = rows.filter((r) => r.locked!.closer != null);
  const closer = compared.filter((r) => r.locked!.closer).length;
  const allDays = [...new Set(rows.map((r) => day(r.kickoffUtc)))];
  const offset = page.offset ?? 0;
  const days = allDays.slice(offset, offset + (page.limit ?? 2));
  const sections = days.map((d) => `<b>${dayLabel(d)}</b>\n\n${byLeague(rows.filter((r) => day(r.kickoffUtc) === d), resultLine)}`);
  const head = offset === 0
    ? `<b>Results · last 7 days</b>${league ? ` · ${esc(LEAGUE_NAMES[league])}` : ""}\nTop pick right: <b>${hits} of ${rows.length}</b>${compared.length ? `\nCloser than the bookmakers: <b>${closer} of ${compared.length}</b>` : ""}`
    : `<b>Results</b>${league ? ` · ${esc(LEAGUE_NAMES[league])}` : ""} · earlier`;
  return {
    text: `${head}\n\n${sections.join("\n\n")}\n\n<i>↑ = the model gave the real result more probability than the bookmakers did.</i>`,
    hasMore: offset + days.length < allDays.length,
    total: rows.length,
  };
}

export function performanceMessage(live: LiveData): string {
  const lr = live.live_record;
  const h = live.headline;
  const liveLine = lr.settled > 0
    ? `<b>Live record</b> · ${lr.settled} settled · top pick right ${lr.accuracy != null ? Math.round(lr.accuracy) : "—"}% · log loss ${lr.log_loss?.toFixed(3) ?? "—"}` +
      (lr.market_log_loss != null && lr.model_log_loss_on_market != null ? ` vs market ${lr.market_log_loss.toFixed(3)}` : "")
    : "<b>Live record</b> · nothing settled yet";
  return `${liveLine}\n<b>Backtest</b> · ${h.n_test} matches · log loss ${h.log_loss.toFixed(3)} · accuracy ${h.accuracy.toFixed(1)}%\n\nFull record: realscores.app/performance\n\n${FOOTER}`;
}

export function finalMessage(m: MatchRecord): string {
  return `<b>Lineups confirmed — final forecast</b>\n${fixtureLine(m)}\n<i>${esc(m.why).slice(0, 300)}</i>\n\n${FOOTER}`;
}

export function highConfMessage(matches: MatchRecord[]): string | null {
  const hc = matches.filter((m) => !m.gated && m.conf === "HIGH");
  if (hc.length === 0) return null;
  return `<b>High-confidence forecasts</b> · ${hc.length}\n\n${byLeague(hc, fixtureLine)}\n\n${FOOTER}`;
}

export function settledMessage(rows: RecentResult[]): string | null {
  const done = rows.filter((r) => r.locked && r.locked.correct != null);
  if (done.length === 0) return null;
  const hits = done.filter((r) => r.locked!.correct).length;
  return `<b>Settled</b> · ${hits} of ${done.length} right\n\n${byLeague(done, resultLine)}`;
}

const REASON_SHORT: Record<string, string> = {
  unvalidated_edge: "edge not yet validated by the backtest",
  stale_odds: "newest price is days old",
  few_bookmakers: "too few bookmakers quoting",
  no_odds: "no odds archived yet",
};

export interface BettingFilter {
  league?: LeagueCode;
  /** Minimum fixture confidence: "HIGH" or "MED" (MED means MED or HIGH). */
  minConf?: "HIGH" | "MED";
  limit?: number;
}

/** WATCH/VALUE rows only -- PASS is the engine saying nothing to see.
 * Grouped by league, strongest edge first, capped, with the ways to
 * narrow it spelled out at the bottom. */
export function bettingMessage(live: LiveData, rows: BettingRow[], filter: BettingFilter = {}): string | null {
  const v = bettingView(live, rows, filter);
  return v.total ? v.text : null;
}

export function bettingView(live: LiveData, rows: BettingRow[], filter: BettingFilter = {}, page: Page = {}): View {
  const byId = new Map(live.matches.map((m) => [m.id, m]));
  const confOk = (c: MatchRecord["conf"]) => !filter.minConf || c === "HIGH" || (filter.minConf === "MED" && c === "MED");
  const graded = rows
    .map((r) => ({ r, m: byId.get(r.id) }))
    .filter((x): x is { r: BettingRow; m: MatchRecord } =>
      !!x.m && !x.m.gated && x.r.level !== "PASS" && (!filter.league || x.m.lg === filter.league) && confOk(x.m.conf))
    .sort((a, b) => (b.r.edge ?? -1) - (a.r.edge ?? -1));
  if (graded.length === 0) return { text: `Nothing graded above PASS${filter.league || filter.minConf ? " for that filter" : ""} right now — the engine is passing, out loud.`, hasMore: false, total: 0 };
  const offset = page.offset ?? 0;
  const limit = filter.limit ?? page.limit ?? 8;
  const shown = graded.slice(offset, offset + limit);
  const line = ({ r, m }: { r: BettingRow; m: MatchRecord }) => {
    const nums = r.mp === null
      ? `model ${r.p.toFixed(0)}% · no odds`
      : `model ${r.p.toFixed(0)}% · market ${r.mp.toFixed(0)}% · <b>${r.edge! >= 0 ? "+" : ""}${r.edge!.toFixed(1)}pp</b>${r.odds ? ` @ ${r.odds.toFixed(2)}` : ""}`;
    const why = REASON_SHORT[r.reasons[0]?.code ?? ""] ?? r.reasons[0]?.detail ?? "";
    const conf = m.conf === "HIGH" ? " · high" : m.conf === "MED" ? " · med" : " · low";
    return `${utcClock(m.kickoffUtc)}  <b>${shortName(m.home)}</b> v <b>${shortName(m.away)}</b> — ${esc(selectionLabel(r, m))}\n        ${nums}\n        ${r.level}${r.locked ? "" : " (pre-lock)"}${conf} · ${esc(why)}`;
  };
  const title = `<b>Betting · graded disagreements</b>${filter.league ? ` · ${esc(LEAGUE_NAMES[filter.league])}` : ""}${filter.minConf ? ` · ${filter.minConf === "HIGH" ? "high" : "med+"} confidence` : ""}`;
  const range = graded.length > limit ? ` · ${offset + 1}–${offset + shown.length} of ${graded.length}` : ` · ${graded.length}`;
  return {
    text: `${title}${range}\n\n${byLeague(shown.map((x) => ({ ...x, lg: x.m.lg })), line)}\n\n${BETTING_FOOTER}`,
    hasMore: offset + shown.length < graded.length,
    total: graded.length,
  };
}

export function digestMessage(live: LiveData, prefs: TelegramPrefs): string {
  const today = day(live.generated_at);
  const yesterday = new Date(Date.parse(`${today}T00:00:00Z`) - 86400e3).toISOString().slice(0, 10);
  const parts = [`<b>RealscoresAI · ${dayLabel(today)}</b>`];
  parts.push(todayMessage(live, prefs.leagues).replace(`<i>home · draw · away %, then the model's pick.</i>\n`, "").replace(`\n\n${FOOTER}`, ""));
  if (prefs.high_conf) {
    const hc = highConfMessage(live.matches.filter((m) => prefs.leagues.includes(m.lg) && day(m.kickoffUtc) === today));
    if (hc) parts.push(hc.replace(`\n\n${FOOTER}`, ""));
  }
  if (prefs.results) {
    const settled = live.recent_results.filter((r) => day(r.kickoffUtc) === yesterday && prefs.leagues.includes(r.lg));
    const s = settledMessage(settled);
    if (s) parts.push(s.replace("<b>Settled</b>", "<b>Yesterday</b>"));
  }
  return `${parts.join("\n\n")}\n\n${FOOTER}`;
}

export const HELP = [
  "Use the buttons at the bottom — or type:",
  "/today — upcoming forecasts (tap a league to narrow)",
  "/results — settled forecasts, last 7 days",
  "/performance — the live record",
  "/betting — graded model-vs-market disagreements (lifetime, 18+)",
  "/alerts — choose leagues and alert types",
  "/account — your link and access · /stop — disconnect",
].join("\n");
