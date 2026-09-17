import "server-only";
import { LEAGUE_CODES, LEAGUE_NAMES } from "@/lib/data";
import type { LeagueCode } from "@/lib/types";
import type { TelegramPrefs, TelegramRecord } from "./store";

/** Inline keyboard for /alerts. Callback data is tiny by design (64 bytes
 * max): p:<pref> toggles an alert type, l:<code> a league, adult:yes
 * records the 18+ confirmation that betting alerts require. */

const PREF_LABELS: Record<keyof Omit<TelegramPrefs, "leagues">, string> = {
  digest: "Daily digest 08:00 UTC",
  final: "Lineups confirmed → final forecast",
  results: "Results as they settle",
  high_conf: "High-confidence forecasts",
  betting: "Betting grades (lifetime · 18+)",
};

export function alertsKeyboard(record: TelegramRecord, premium: boolean) {
  const p = record.prefs;
  const mark = (on: boolean) => (on ? "✅" : "▫️");
  const rows: { text: string; callback_data: string }[][] = [];
  for (const key of Object.keys(PREF_LABELS) as (keyof typeof PREF_LABELS)[]) {
    const locked = key === "betting" && !premium;
    rows.push([{ text: `${locked ? "🔒" : mark(p[key])} ${PREF_LABELS[key]}`, callback_data: `p:${key}` }]);
  }
  rows.push(LEAGUE_CODES.map((lg) => ({ text: `${p.leagues.includes(lg) ? "✅" : "▫️"} ${lg}`, callback_data: `l:${lg}` })));
  return { inline_keyboard: rows };
}

export function alertsText(record: TelegramRecord, premium: boolean): string {
  const leagues = record.prefs.leagues.map((l) => LEAGUE_NAMES[l]).join(", ") || "none";
  const betting = !premium
    ? "Betting grades need lifetime access."
    : record.adult_confirmed_at
      ? "Betting grades are available; they are off until you switch them on."
      : "Betting grades need an 18+ confirmation first — tap the button and you will be asked.";
  return `<b>Alerts</b>\nLeagues: ${leagues}\n${betting}\n\nTap to toggle:`;
}

export function toggleLeague(prefs: TelegramPrefs, lg: LeagueCode): TelegramPrefs {
  const leagues = prefs.leagues.includes(lg) ? prefs.leagues.filter((x) => x !== lg) : [...prefs.leagues, lg];
  return { ...prefs, leagues };
}

export const ADULT_PROMPT =
  "Betting grades are for adults only. By tapping below you confirm you are 18 or over (or the legal age where you live) and that viewing betting information is lawful where you are. Grades are classifications, not advice.";
export const ADULT_KEYBOARD = { inline_keyboard: [[{ text: "I'm 18 or over — turn betting grades on", callback_data: "adult:yes" }]] };
