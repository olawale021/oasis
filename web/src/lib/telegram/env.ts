import "server-only";

/** Runtime configuration for the bot. Secrets come from the Worker
 * (`wrangler secret put`) or process.env under `next dev`. The bot never
 * runs on the droplet: it only ever holds a dispatch secret.
 *
 *   TELEGRAM_BOT_TOKEN        from @BotFather
 *   TELEGRAM_WEBHOOK_SECRET   sent by Telegram on every webhook call
 *   TELEGRAM_DISPATCH_SECRET  bearer the matchday chain uses to trigger alerts
 *   TELEGRAM_BOT_USERNAME     public, for the t.me deep link (wrangler vars)
 */

export interface KVLike {
  get(key: string, opts: { type: "json" }): Promise<unknown>;
  put(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
}

// `next dev` has no KV binding; an in-memory store keeps the flows testable
// and forgets everything on restart, which is what you want in dev.
const devStore = new Map<string, string>();
const devKV: KVLike = {
  async get(key) {
    const v = devStore.get(key);
    return v == null ? null : JSON.parse(v);
  },
  async put(key, value) {
    devStore.set(key, value);
  },
  async delete(key) {
    devStore.delete(key);
  },
};

export interface TelegramEnv {
  token: string | null;
  webhookSecret: string | null;
  dispatchSecret: string | null;
  botUsername: string | null;
  kv: KVLike;
}

export async function tgEnv(): Promise<TelegramEnv> {
  let env: Record<string, unknown> = {};
  try {
    const { getCloudflareContext } = await import("@opennextjs/cloudflare");
    env = getCloudflareContext().env as Record<string, unknown>;
  } catch {
    // next dev without the Workers runtime.
  }
  const pick = (k: string): string | null => {
    const v = env[k];
    if (typeof v === "string" && v.length > 0) return v;
    const p = process.env[k];
    return p && p.length > 0 ? p : null;
  };
  return {
    token: pick("TELEGRAM_BOT_TOKEN"),
    webhookSecret: pick("TELEGRAM_WEBHOOK_SECRET"),
    dispatchSecret: pick("TELEGRAM_DISPATCH_SECRET"),
    botUsername: pick("TELEGRAM_BOT_USERNAME"),
    kv: (env.LIVE_KV as KVLike | undefined) ?? devKV,
  };
}
