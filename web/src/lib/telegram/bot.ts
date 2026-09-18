import "server-only";
import { LEAGUE_CODES } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import { redactLive } from "@/lib/gate";
import type { LeagueCode } from "@/lib/types";
import type { Sender } from "./api";
import type { TelegramEnv } from "./env";
import {
  HELP, bettingMessage, bettingView, digestMessage, esc, finalMessage, highConfMessage, performanceMessage,
  resultsView, settledMessage, todayView, type View,
} from "./format";
import { verifyLinkToken } from "./link";
import { ADULT_KEYBOARD, ADULT_PROMPT, alertsKeyboard, alertsText, toggleLeague } from "./prefs";
import { linkChat, subscribers, unlinkChat, updateRecord, userForChat, type Subscriber } from "./store";

/** Inbound (webhook) and outbound (dispatch) logic, kept free of HTTP so
 * both routes stay thin and the dry sender can exercise everything.
 *
 * Access: a linked chat is the account it linked, so the same redaction as
 * the site applies -- redactLive() with that account's tier. A chat that
 * is not linked is an anonymous viewer. */

interface Ctx {
  env: TelegramEnv;
  sender: Sender;
  live: LiveData;
}

const viewerFor = (sub: Subscriber | null) => ({ tier: (sub ? (sub.premium ? "premium" : "free") : "anon") as "anon" | "free" | "premium", userId: sub?.userId ?? null });

function parseCommand(text: string): { cmd: string; arg: string } | null {
  const m = text.trim().match(/^\/([a-z_]+)(?:@\w+)?(?:\s+(.*))?$/i);
  if (m) return { cmd: m[1].toLowerCase(), arg: (m[2] ?? "").trim() };
  // Button labels arrive as plain text: "📅 Today" -> today.
  const word = text.replace(/[^a-z ]/gi, "").trim().toLowerCase();
  const cmd = BUTTON_COMMANDS[word];
  return cmd ? { cmd, arg: "" } : null;
}

function asLeague(arg: string): LeagueCode | undefined {
  const up = arg.toUpperCase();
  return (LEAGUE_CODES as string[]).includes(up) ? (up as LeagueCode) : undefined;
}

// --- keyboards ---------------------------------------------------------------

const SITE = "https://realscores.app";

/** The button bar under the composer. Labels are what the client sends as
 * text, so they map straight back to commands. */
const MAIN_KEYBOARD = {
  keyboard: [
    [{ text: "📅 Today" }, { text: "✅ Results" }, { text: "📈 Record" }],
    [{ text: "🎯 Betting" }, { text: "🔔 Alerts" }, { text: "👤 Account" }],
  ],
  resize_keyboard: true,
  is_persistent: true,
};

const BUTTON_COMMANDS: Record<string, string> = {
  today: "today", results: "results", record: "performance", performance: "performance",
  betting: "betting", alerts: "alerts", account: "account", help: "help",
};

const CONNECT_BUTTON = { inline_keyboard: [[{ text: "Connect your account", url: `${SITE}/account` }]] };
const UNLOCK_BUTTON = { inline_keyboard: [[{ text: "Lifetime access", url: `${SITE}/pricing` }]] };

/** Inline picker under a list: league chips, confidence for betting, and
 * "more" paging. Callback data `v:<view>:<league>:<conf>:<offset>`. */
function pickerFor(view: "today" | "results" | "betting", league: string, conf: string, offset: number, v: View) {
  const chip = (text: string, lg: string, c = conf, off = 0) => ({ text, callback_data: `v:${view}:${lg}:${c}:${off}` });
  const rows: { text: string; callback_data: string }[][] = [];
  rows.push([chip(league === "ALL" ? "• All" : "All", "ALL"), ...LEAGUE_CODES.map((lg) => chip(league === lg ? `• ${lg}` : lg, lg))]);
  if (view === "betting") {
    rows.push([chip(conf === "ALL" ? "• any confidence" : "any confidence", league, "ALL"), chip(conf === "MED" ? "• med+" : "med+", league, "MED"), chip(conf === "HIGH" ? "• high" : "high", league, "HIGH")]);
  }
  const nav: { text: string; callback_data: string }[] = [];
  if (offset > 0) nav.push(chip("◂ back", league, conf, 0));
  if (v.hasMore) nav.push(chip("more ▸", league, conf, offset + (view === "results" ? 2 : view === "betting" ? 8 : 12)));
  if (nav.length) rows.push(nav);
  return { inline_keyboard: rows };
}

function renderView(view: "today" | "results" | "betting", live: LiveData, sub: Subscriber | null, league: string, conf: string, offset: number): { text: string; reply_markup: unknown } {
  const leagues = sub?.record.prefs.leagues ?? [...LEAGUE_CODES];
  const lg = asLeague(league);
  let v: View;
  if (view === "today") {
    v = todayView(live, leagues, lg, { offset });
  } else if (view === "results") {
    const since = new Date(Date.parse(live.generated_at) - 7 * 86400e3).toISOString().slice(0, 10);
    v = resultsView(live, leagues, since, lg, { offset });
  } else {
    const minConf = conf === "HIGH" ? "HIGH" : conf === "MED" ? "MED" : undefined;
    const rows = (live.betting?.rows ?? []).filter((r) => leagues.includes(live.matches.find((m) => m.id === r.id)?.lg as LeagueCode));
    v = bettingView(live, rows, { league: lg, minConf }, { offset });
  }
  return { text: v.text, reply_markup: pickerFor(view, lg ?? "ALL", conf, offset, v) };
}

// --- inbound ------------------------------------------------------------------

export async function handleUpdate(update: Record<string, unknown>, ctx: Ctx): Promise<void> {
  const cb = update.callback_query as { id: string; data?: string; message?: { chat: { id: number }; message_id: number } } | undefined;
  if (cb) return handleCallback(cb, ctx);
  const msg = update.message as { chat: { id: number; type: string }; from?: { username?: string }; text?: string } | undefined;
  if (!msg?.text) return;
  const parsed = parseCommand(msg.text);
  const chat_id = msg.chat.id;
  const { env, sender } = ctx;
  const say = (text: string, reply_markup: unknown = MAIN_KEYBOARD) => sender.send({ chat_id, text, reply_markup });
  if (!parsed) return say("Tap a button below, or /help.", MAIN_KEYBOARD);

  if (parsed.cmd === "start") {
    if (!parsed.arg) {
      const sub = await userForChat(env.kv, chat_id);
      if (sub) return say(`Welcome back. ${HELP}`);
      await say("<b>RealscoresAI</b> — pre-match probabilities for six leagues, scored in public.\n\nYou can browse right away with the buttons below. Connect your account to unlock forecasts and get alerts.", MAIN_KEYBOARD);
      return say("Connect from your account page — the button there opens this chat and links it in one tap.", CONNECT_BUTTON);
    }
    if (!env.token) return say("Linking is not configured on this deployment.");
    const userId = await verifyLinkToken(parsed.arg, env.token);
    if (!userId) return say("That link has expired. Open your account page and tap <b>Connect Telegram</b> again.", CONNECT_BUTTON);
    const record = await linkChat(env.kv, userId, chat_id, msg.from?.username ?? null);
    return say(`✅ Connected. Daily digest at 08:00 UTC, alerts for ${record.prefs.leagues.join(", ")}. Change any of it under 🔔 Alerts.\n\n${HELP}`);
  }

  const sub = await userForChat(env.kv, chat_id);
  const live = redactLive(ctx.live, viewerFor(sub));

  switch (parsed.cmd) {
    case "today": {
      const v = renderView("today", live, sub, parsed.arg || "ALL", "ALL", 0);
      return sender.send({ chat_id, ...v });
    }
    case "results": {
      const v = renderView("results", live, sub, parsed.arg || "ALL", "ALL", 0);
      return sender.send({ chat_id, ...v });
    }
    case "performance":
      return say(performanceMessage(live), { inline_keyboard: [[{ text: "Full record on the site", url: `${SITE}/performance` }]] });
    case "account":
      if (!sub) return say("This chat is not connected yet.", CONNECT_BUTTON);
      return say(
        `Connected to your ${sub.premium ? "<b>lifetime</b>" : "free"} account${sub.record.username ? ` as @${esc(sub.record.username)}` : ""}.\n🔔 Alerts to change what you get · /stop to disconnect.`,
        sub.premium ? MAIN_KEYBOARD : UNLOCK_BUTTON,
      );
    case "alerts":
      if (!sub) return say("Connect first — then you can choose leagues and alert types here.", CONNECT_BUTTON);
      return say(alertsText(sub.record, sub.premium), alertsKeyboard(sub.record, sub.premium));
    case "betting": {
      if (!sub) return say("Betting grades need a connected lifetime account.", CONNECT_BUTTON);
      if (!sub.premium) return say("Betting grades are part of lifetime access.", UNLOCK_BUTTON);
      if (!sub.record.adult_confirmed_at) return say(ADULT_PROMPT, ADULT_KEYBOARD);
      const words = parsed.arg.split(/\s+/).filter(Boolean);
      const league = words.map(asLeague).find(Boolean) ?? "ALL";
      const conf = words.some((w) => /^high$/i.test(w)) ? "HIGH" : words.some((w) => /^med(ium)?$/i.test(w)) ? "MED" : "ALL";
      const v = renderView("betting", live, sub, league, conf, 0);
      return sender.send({ chat_id, ...v });
    }
    case "stop":
      return say((await unlinkChat(env.kv, chat_id)) ? "Disconnected. Nothing more will be sent here." : "This chat was not connected.");
    case "help":
    default:
      return say(HELP);
  }
}

async function handleCallback(cb: { id: string; data?: string; message?: { chat: { id: number }; message_id: number } }, ctx: Ctx): Promise<void> {
  const { env, sender } = ctx;
  const chat_id = cb.message?.chat.id;
  const data = cb.data ?? "";
  if (chat_id === undefined) return sender.answerCallback(cb.id);
  const sub = await userForChat(env.kv, chat_id);

  if (data.startsWith("v:")) {
    const [, view, league, conf, off] = data.split(":");
    if (view === "betting" && (!sub || !sub.premium || !sub.record.adult_confirmed_at)) {
      return sender.answerCallback(cb.id, "Betting grades need a connected lifetime account and an 18+ confirmation.");
    }
    const live = redactLive(ctx.live, viewerFor(sub));
    const v = renderView(view as "today" | "results" | "betting", live, sub, league, conf, Number(off) || 0);
    await sender.answerCallback(cb.id);
    if (cb.message) await sender.editText(chat_id, cb.message.message_id, v.text, v.reply_markup);
    return;
  }
  if (!sub) return sender.answerCallback(cb.id, "Not connected. Use the button on your account page.");

  if (data === "adult:yes") {
    const at = new Date().toISOString();
    await updateRecord(sub.userId, { adult_confirmed_at: at, prefs: { ...sub.record.prefs, betting: sub.premium } });
    await sender.answerCallback(cb.id, "Confirmed.");
    return sender.send({ chat_id, text: sub.premium ? "Betting grades are on. 🎯 Betting shows what is graded now; 🔔 Alerts to turn them off." : "Confirmed. Betting grades also need lifetime access.", reply_markup: MAIN_KEYBOARD });
  }
  let prefs = sub.record.prefs;
  if (data.startsWith("l:")) {
    prefs = toggleLeague(prefs, data.slice(2) as LeagueCode);
  } else if (data.startsWith("p:")) {
    const key = data.slice(2) as keyof typeof prefs;
    if (key === "betting") {
      if (!sub.premium) return sender.answerCallback(cb.id, "Betting grades need lifetime access.");
      if (!sub.record.adult_confirmed_at && !prefs.betting) {
        await sender.answerCallback(cb.id);
        return sender.send({ chat_id, text: ADULT_PROMPT, reply_markup: ADULT_KEYBOARD });
      }
    }
    if (key !== "leagues" && key in prefs) prefs = { ...prefs, [key]: !prefs[key] };
  } else {
    return sender.answerCallback(cb.id);
  }
  await updateRecord(sub.userId, { prefs });
  await sender.answerCallback(cb.id, "Saved.");
  if (cb.message) await sender.editMarkup(chat_id, cb.message.message_id, alertsKeyboard({ ...sub.record, prefs }, sub.premium));
}

// --- outbound ------------------------------------------------------------------

export interface DispatchEvent {
  type: "digest" | "lock" | "final" | "settled";
  fixture_ids?: number[];
}

/** Every message the given events imply, per subscriber, honouring tier,
 * league preferences, alert types and the 18+ rule. Pure over the inputs;
 * the route sends a window of it and returns a cursor. */
export function buildDispatch(live: LiveData, subs: Subscriber[], events: DispatchEvent[]): { chat_id: number; text: string }[] {
  const out: { chat_id: number; text: string }[] = [];
  for (const sub of subs) {
    const prefs = sub.record.prefs;
    const view = redactLive(live, viewerFor(sub));
    const inLeagues = (lg: LeagueCode) => prefs.leagues.includes(lg);
    const push = (text: string | null) => text && out.push({ chat_id: sub.record.chat_id, text });
    for (const ev of events) {
      const ids = new Set(ev.fixture_ids ?? []);
      if (ev.type === "digest" && prefs.digest) push(digestMessage(view, prefs));
      if (ev.type === "final" && prefs.final) {
        for (const m of view.matches) if (ids.has(m.id) && inLeagues(m.lg) && !m.gated) push(finalMessage(m));
      }
      if (ev.type === "lock") {
        const locked = view.matches.filter((m) => ids.has(m.id) && inLeagues(m.lg));
        if (prefs.high_conf) push(highConfMessage(locked));
        if (prefs.betting && sub.premium && sub.record.adult_confirmed_at) {
          push(bettingMessage(view, (view.betting?.rows ?? []).filter((r) => ids.has(r.id) && r.locked),
            { minConf: prefs.betting_high_only ? "HIGH" : undefined, limit: 8 }));
        }
      }
      if (ev.type === "settled" && prefs.results) {
        push(settledMessage(view.recent_results.filter((r) => ids.has(r.id) && inLeagues(r.lg))));
      }
    }
  }
  return out;
}

export { subscribers };
