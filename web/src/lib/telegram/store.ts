import "server-only";
import { clerkClient } from "@clerk/nextjs/server";
import type { KVLike } from "./env";
import { LEAGUE_CODES } from "@/lib/data";
import type { LeagueCode } from "@/lib/types";

/** Where a Telegram link lives: the user's Clerk private metadata (the
 * record: chat id, preferences, 18+ confirmation) plus two small KV keys
 * so inbound commands and outbound dispatch can find users without
 * scanning Clerk: tg:chat:<chat_id> -> userId, and tg:subs -> {userId: chat_id}. */

export interface TelegramPrefs {
  leagues: LeagueCode[];
  digest: boolean;
  final: boolean;
  results: boolean;
  high_conf: boolean;
  /** Betting grades. Off by default; premium only; needs adult_confirmed_at. */
  betting: boolean;
}

export interface TelegramRecord {
  chat_id: number;
  username: string | null;
  linked_at: string;
  adult_confirmed_at: string | null;
  prefs: TelegramPrefs;
}

export const DEFAULT_PREFS: TelegramPrefs = {
  leagues: [...LEAGUE_CODES],
  digest: true,
  final: true,
  results: true,
  high_conf: true,
  betting: false,
};

export interface Subscriber {
  userId: string;
  premium: boolean;
  record: TelegramRecord;
}

const CHAT_KEY = (id: number) => `tg:chat:${id}`;
const SUBS_KEY = "tg:subs";

function readRecord(priv: unknown): TelegramRecord | null {
  const t = (priv as { telegram?: TelegramRecord } | null)?.telegram;
  if (!t || typeof t.chat_id !== "number") return null;
  return { ...t, prefs: { ...DEFAULT_PREFS, ...(t.prefs ?? {}) } };
}

async function subsMap(kv: KVLike): Promise<Record<string, number>> {
  return ((await kv.get(SUBS_KEY, { type: "json" })) as Record<string, number> | null) ?? {};
}

export async function linkChat(kv: KVLike, userId: string, chat_id: number, username: string | null): Promise<TelegramRecord> {
  const client = await clerkClient();
  const user = await client.users.getUser(userId);
  const existing = readRecord(user.privateMetadata);
  const record: TelegramRecord = {
    chat_id,
    username,
    linked_at: new Date().toISOString(),
    adult_confirmed_at: existing?.adult_confirmed_at ?? null,
    prefs: existing?.prefs ?? DEFAULT_PREFS,
  };
  await client.users.updateUserMetadata(userId, { privateMetadata: { telegram: record } });
  await kv.put(CHAT_KEY(chat_id), JSON.stringify({ userId }));
  const subs = await subsMap(kv);
  subs[userId] = chat_id;
  await kv.put(SUBS_KEY, JSON.stringify(subs));
  return record;
}

export async function unlinkChat(kv: KVLike, chat_id: number): Promise<boolean> {
  const hit = (await kv.get(CHAT_KEY(chat_id), { type: "json" })) as { userId: string } | null;
  if (!hit) return false;
  const client = await clerkClient();
  // Replace semantics for the sub-object: updateUserMetadata deep-merges, so
  // null the key explicitly.
  await client.users.updateUserMetadata(hit.userId, { privateMetadata: { telegram: null } });
  await kv.delete(CHAT_KEY(chat_id));
  const subs = await subsMap(kv);
  delete subs[hit.userId];
  await kv.put(SUBS_KEY, JSON.stringify(subs));
  return true;
}

export async function userForChat(kv: KVLike, chat_id: number): Promise<Subscriber | null> {
  const hit = (await kv.get(CHAT_KEY(chat_id), { type: "json" })) as { userId: string } | null;
  if (!hit) return null;
  const client = await clerkClient();
  const user = await client.users.getUser(hit.userId);
  const record = readRecord(user.privateMetadata);
  if (!record) return null;
  return { userId: hit.userId, premium: (user.publicMetadata as { premium?: boolean } | null)?.premium === true, record };
}

export async function updateRecord(userId: string, patch: Partial<TelegramRecord>): Promise<void> {
  const client = await clerkClient();
  await client.users.updateUserMetadata(userId, { privateMetadata: { telegram: patch } });
}

/** Every linked user with tier and record, in batches of 100 Clerk ids. */
export async function subscribers(kv: KVLike): Promise<Subscriber[]> {
  const subs = await subsMap(kv);
  const ids = Object.keys(subs);
  if (ids.length === 0) return [];
  const client = await clerkClient();
  const out: Subscriber[] = [];
  for (let i = 0; i < ids.length; i += 100) {
    const { data } = await client.users.getUserList({ userId: ids.slice(i, i + 100), limit: 100 });
    for (const u of data) {
      const record = readRecord(u.privateMetadata);
      if (!record) continue;
      out.push({ userId: u.id, premium: (u.publicMetadata as { premium?: boolean } | null)?.premium === true, record });
    }
  }
  return out;
}
