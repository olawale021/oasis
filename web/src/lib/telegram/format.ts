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

function fixtureLine(m: MatchRecord): string {
  const head = `${utcClock(m.kickoffUtc)} <b>${esc(m.home)}</b> v <b>${esc(m.away)}</b> <code>${m.lg}</code>`;
  if (m.gated) return `${head}\n   🔒 locked — sign in or lifetime access`;
  const probs = `${Math.round(m.h)}/${Math.round(m.d)}/${Math.round(m.a)}`;
  const conf = m.conf === "HIGH" ? " · <b>HIGH</b>" : m.conf === "MED" ? " · med" : "";
  return `${head}\n   ${probs} → ${esc(pick(m))}${conf} · likely ${esc(m.condScore)}`;
}

/** Upcoming fixtures on the payload's UTC day; if none, the next day that
 * has any. `leagues` filters; `league` is a single explicit ask. */
export function todayMessage(live: LiveData, leagues: LeagueCode[], league?: LeagueCode): string {
  const wanted = (m: MatchRecord) => (league ? m.lg === league : leagues.includes(m.lg));
  const upcoming = live.matches.filter((m) => wanted(m) && m.kickoffUtc >= live.generated_at.slice(0, 13)).sort((a, b) => a.kickoffUtc.localeCompare(b.kickoffUtc));
  if (upcoming.length === 0) return `No upcoming fixtures${league ? ` in ${LEAGUE_NAMES[league]}` : ""} in the next week.\n\n${FOOTER}`;
  const today = day(live.generated_at);
  let target = upcoming.filter((m) => day(m.kickoffUtc) === today);
  let title = "Today";
  if (target.length === 0) {
    const next = day(upcoming[0].kickoffUtc);
    target = upcoming.filter((m) => day(m.kickoffUtc) === next);
    title = dayLabel(next);
  }
  const lines = target.slice(0, 25).map(fixtureLine);
  const more = target.length > 25 ? `\n…and ${target.length - 25} more on the site.` : "";
  return `<b>${title}</b>${league ? ` · ${esc(LEAGUE_NAMES[league])}` : ""} · ${target.length} ${target.length === 1 ? "match" : "matches"} (UTC)\n\n${lines.join("\n")}${more}\n\n${FOOTER}`;
}

function resultLine(r: RecentResult): string {
  const l = r.locked;
  const verdict = !l || l.correct == null ? "" : l.correct ? " ✓" : " ✗";
  const closer = l?.closer === true ? " · closer than market" : "";
  const p = l ? ` · pick ${l.h >= l.d && l.h >= l.a ? esc(r.home) : l.a >= l.d ? esc(r.away) : "Draw"}` : "";
  return `<b>${esc(r.home)} ${esc(r.score)} ${esc(r.away)}</b> <code>${r.lg}</code>${p}${verdict}${closer}`;
}

export function resultsMessage(live: LiveData, leagues: LeagueCode[], sinceDay?: string): string {
  const rows = live.recent_results
    .filter((r) => r.locked && r.locked.correct != null && leagues.includes(r.lg) && (!sinceDay || day(r.kickoffUtc) >= sinceDay))
    .sort((a, b) => b.kickoffUtc.localeCompare(a.kickoffUtc));
  if (rows.length === 0) return "No settled forecasts in that window yet.";
  const hits = rows.filter((r) => r.locked!.correct).length;
  const compared = rows.filter((r) => r.locked!.closer != null);
  const closer = compared.filter((r) => r.locked!.closer).length;
  const head = `<b>Results</b> · ${hits} of ${rows.length} top picks right${compared.length ? ` · closer than the bookmakers on ${closer} of ${compared.length}` : ""}`;
  return `${head}\n\n${rows.slice(0, 30).map(resultLine).join("\n")}\n\n<i>Every locked forecast counted, none removed.</i>`;
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
  return `<b>High-confidence forecasts</b> · ${hc.length}\n\n${hc.map(fixtureLine).join("\n")}\n\n${FOOTER}`;
}

export function settledMessage(rows: RecentResult[]): string | null {
  const done = rows.filter((r) => r.locked && r.locked.correct != null);
  if (done.length === 0) return null;
  const hits = done.filter((r) => r.locked!.correct).length;
  return `<b>Settled</b> · ${hits} of ${done.length} right\n\n${done.map(resultLine).join("\n")}`;
}

/** WATCH/VALUE rows only -- PASS is the engine saying nothing to see. */
export function bettingMessage(live: LiveData, rows: BettingRow[]): string | null {
  const byId = new Map(live.matches.map((m) => [m.id, m]));
  const graded = rows.filter((r) => r.level !== "PASS" && byId.has(r.id) && !byId.get(r.id)!.gated);
  if (graded.length === 0) return null;
  const lines = graded.slice(0, 20).map((r) => {
    const m = byId.get(r.id)!;
    const nums = r.mp === null ? `model ${r.p.toFixed(0)}% · no odds` : `model ${r.p.toFixed(0)}% · market ${r.mp.toFixed(0)}% · edge ${r.edge! >= 0 ? "+" : ""}${r.edge!.toFixed(1)}pp${r.odds ? ` @ ${r.odds.toFixed(2)}` : ""}`;
    return `<b>${esc(m.home)} v ${esc(m.away)}</b> · ${esc(selectionLabel(r, m))}\n   ${nums}\n   <b>${r.level}</b>${r.locked ? "" : " (pre-lock)"} — ${esc(r.reasons[0]?.detail ?? "")}`;
  });
  return `<b>Betting · graded disagreements</b>\n\n${lines.join("\n\n")}\n\n${BETTING_FOOTER}`;
}

export function digestMessage(live: LiveData, prefs: TelegramPrefs): string {
  const today = day(live.generated_at);
  const yesterday = new Date(Date.parse(`${today}T00:00:00Z`) - 86400e3).toISOString().slice(0, 10);
  const parts = [`<b>RealscoresAI · ${dayLabel(today)}</b>`];
  parts.push(todayMessage(live, prefs.leagues).replace(`\n\n${FOOTER}`, ""));
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
  "<b>Commands</b>",
  "/today [EPL|LAL|SEA|BUN|MLS] — upcoming forecasts",
  "/results — settled forecasts, last 7 days",
  "/performance — the live record",
  "/betting — graded model-vs-market disagreements (lifetime, 18+)",
  "/alerts — choose leagues and alert types",
  "/account — your link and access",
  "/stop — disconnect",
].join("\n");
