import "server-only";
import { LEAGUE_CODES } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import { redactLive } from "@/lib/gate";
import type { LeagueCode } from "@/lib/types";
import type { Sender } from "./api";
import type { TelegramEnv } from "./env";
import {
  HELP, bettingMessage, digestMessage, esc, finalMessage, highConfMessage, performanceMessage,
  resultsMessage, settledMessage, todayMessage,
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
  return m ? { cmd: m[1].toLowerCase(), arg: (m[2] ?? "").trim() } : null;
}

function asLeague(arg: string): LeagueCode | undefined {
  const up = arg.toUpperCase();
  return (LEAGUE_CODES as string[]).includes(up) ? (up as LeagueCode) : undefined;
}

// --- inbound ------------------------------------------------------------------

export async function handleUpdate(update: Record<string, unknown>, ctx: Ctx): Promise<void> {
  const cb = update.callback_query as { id: string; data?: string; message?: { chat: { id: number }; message_id: number } } | undefined;
  if (cb) return handleCallback(cb, ctx);
  const msg = update.message as { chat: { id: number; type: string }; from?: { username?: string }; text?: string } | undefined;
  if (!msg?.text) return;
  const parsed = parseCommand(msg.text);
  if (!parsed) return;
  const chat_id = msg.chat.id;
  const { env, sender } = ctx;
  const say = (text: string, reply_markup?: unknown) => sender.send({ chat_id, text, reply_markup });

  if (parsed.cmd === "start") {
    if (!parsed.arg) {
      return say(`Connect this chat from your account page: realscores.app/account → <b>Connect Telegram</b>.\n\n${HELP}`);
    }
    if (!env.token) return say("Linking is not configured on this deployment.");
    const userId = await verifyLinkToken(parsed.arg, env.token);
    if (!userId) return say("That link has expired or is not valid. Open realscores.app/account and tap <b>Connect Telegram</b> again.");
    const record = await linkChat(env.kv, userId, chat_id, msg.from?.username ?? null);
    return say(`Connected. You will get the daily digest at 08:00 UTC and alerts for ${record.prefs.leagues.join(", ")}.\n\n${HELP}`);
  }

  const sub = await userForChat(env.kv, chat_id);
  const live = redactLive(ctx.live, viewerFor(sub));
  const leagues = sub?.record.prefs.leagues ?? [...LEAGUE_CODES];

  switch (parsed.cmd) {
    case "today":
      return say(todayMessage(live, leagues, asLeague(parsed.arg)));
    case "results": {
      const since = new Date(Date.parse(live.generated_at) - 7 * 86400e3).toISOString().slice(0, 10);
      return say(resultsMessage(live, leagues, since, asLeague(parsed.arg)));
    }
    case "performance":
      return say(performanceMessage(live));
    case "account":
      if (!sub) return say("This chat is not connected. realscores.app/account → <b>Connect Telegram</b>.");
      return say(`Connected to your ${sub.premium ? "<b>lifetime</b>" : "free"} account${sub.record.username ? ` as @${esc(sub.record.username)}` : ""}.\nAlerts: /alerts · Disconnect: /stop`);
    case "alerts":
      if (!sub) return say("Connect first: realscores.app/account → <b>Connect Telegram</b>.");
      return say(alertsText(sub.record, sub.premium), alertsKeyboard(sub.record, sub.premium));
    case "betting": {
      if (!sub) return say("Betting grades need a connected lifetime account.");
      if (!sub.premium) return say("Betting grades are part of lifetime access: realscores.app/pricing");
      if (!sub.record.adult_confirmed_at) return say(ADULT_PROMPT, ADULT_KEYBOARD);
      const text = bettingMessage(live, (live.betting?.rows ?? []).filter((r) => leagues.includes(live.matches.find((m) => m.id === r.id)?.lg as LeagueCode)));
      return say(text ?? "Nothing graded above PASS right now — the engine is passing on everything, out loud.");
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
  if (!sub) return sender.answerCallback(cb.id, "Not connected. Use /start from your account page.");

  if (data === "adult:yes") {
    const at = new Date().toISOString();
    await updateRecord(sub.userId, { adult_confirmed_at: at, prefs: { ...sub.record.prefs, betting: sub.premium } });
    await sender.answerCallback(cb.id, "Confirmed.");
    return sender.send({ chat_id, text: sub.premium ? "Betting grades are on. /betting shows what is graded now; /alerts to turn them off." : "Confirmed. Betting grades also need lifetime access." });
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
          push(bettingMessage(view, (view.betting?.rows ?? []).filter((r) => ids.has(r.id) && r.locked)));
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
