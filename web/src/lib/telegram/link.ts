import "server-only";

/** Account linking tokens for the t.me deep link (`/start <token>`).
 * `userId-timestamp-signature`, HMAC-keyed by the bot token so no extra
 * secret is needed, valid 15 minutes. Telegram allows [A-Za-z0-9_-] up to
 * 64 chars in the start parameter; Clerk ids are `user_` + base62, so `-`
 * is a safe separator. */

const TTL_MS = 15 * 60 * 1000;
const SIG_CHARS = 20;

async function hmacHex(key: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, enc.encode(message));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function signLinkToken(userId: string, key: string, now = Date.now()): Promise<string> {
  const ts = Math.floor(now / 1000).toString(36);
  const sig = (await hmacHex(key, `${userId}|${ts}`)).slice(0, SIG_CHARS);
  return `${userId}-${ts}-${sig}`;
}

export async function verifyLinkToken(token: string, key: string, now = Date.now()): Promise<string | null> {
  const last = token.lastIndexOf("-");
  const mid = token.lastIndexOf("-", last - 1);
  if (last < 0 || mid < 0) return null;
  const userId = token.slice(0, mid);
  const ts = token.slice(mid + 1, last);
  const sig = token.slice(last + 1);
  const expected = (await hmacHex(key, `${userId}|${ts}`)).slice(0, SIG_CHARS);
  if (sig.length !== expected.length) return null;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  if (diff !== 0) return null;
  const issued = parseInt(ts, 36) * 1000;
  if (!Number.isFinite(issued) || now - issued > TTL_MS || issued > now + 60_000) return null;
  return userId;
}
