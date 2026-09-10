import { cookies } from "next/headers";

/** Single-operator admin gate. The password lives in the Worker secret
 * ADMIN_PASSWORD (`wrangler secret put`), or process.env for `next dev`.
 * A successful login sets an HttpOnly cookie holding HMAC(secret, tag), so
 * the cookie cannot be forged without the secret and rotating the secret
 * invalidates every session. */

export const ADMIN_COOKIE = "oasis_admin";
const TAG = "oasis-admin-v1";
const MAX_AGE_S = 60 * 60 * 24 * 30;

export async function getAdminSecret(): Promise<string | null> {
  try {
    const { getCloudflareContext } = await import("@opennextjs/cloudflare");
    const { env } = getCloudflareContext();
    const v = (env as Record<string, unknown>).ADMIN_PASSWORD;
    if (typeof v === "string" && v.length > 0) return v;
  } catch {
    // next dev without the Workers runtime.
  }
  const v = process.env.ADMIN_PASSWORD;
  return v && v.length > 0 ? v : null;
}

async function hmacHex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function sessionToken(secret: string): Promise<string> {
  return hmacHex(secret, TAG);
}

export async function isAdmin(): Promise<boolean> {
  const secret = await getAdminSecret();
  if (!secret) return false;
  const cookie = (await cookies()).get(ADMIN_COOKIE)?.value;
  if (!cookie) return false;
  return constantTimeEqual(cookie, await sessionToken(secret));
}

/** Returns true and sets the session cookie if the password matches. */
export async function tryLogin(password: string): Promise<boolean> {
  const secret = await getAdminSecret();
  if (!secret) return false;
  // Compare HMACs rather than raw strings so length is not leaked either.
  const ok = constantTimeEqual(await hmacHex(secret, password), await hmacHex(secret, secret));
  if (!ok) return false;
  (await cookies()).set(ADMIN_COOKIE, await sessionToken(secret), {
    httpOnly: true, secure: true, sameSite: "lax", path: "/admin", maxAge: MAX_AGE_S,
  });
  return true;
}

export async function clearSession(): Promise<void> {
  (await cookies()).delete({ name: ADMIN_COOKIE, path: "/admin" });
}
