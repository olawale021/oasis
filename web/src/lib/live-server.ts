import { cache } from "react";
import fallback from "@/data/live.json";
import type { LiveData } from "./data";

/** Fetch the live data payload. Production: Cloudflare KV (key "live",
 * uploaded by the matchday chain — no redeploy needed for data updates),
 * with a 60s edge cache. Dev / cold start: the JSON bundled at build time.
 * `cache()` dedupes within a request. */
export const getLive = cache(async (): Promise<LiveData> => {
  try {
    const { getCloudflareContext } = await import("@opennextjs/cloudflare");
    const { env } = getCloudflareContext();
    const kv = (env as Record<string, unknown>).LIVE_KV as
      | { get: (key: string, opts: { type: "json"; cacheTtl?: number }) => Promise<LiveData | null> }
      | undefined;
    if (kv) {
      const data = await kv.get("live", { type: "json", cacheTtl: 60 });
      if (data) return data;
    }
  } catch {
    // next dev without the Workers runtime, or KV unavailable -- fall back.
  }
  return fallback as unknown as LiveData;
});

import opsFallback from "@/data/ops.json";
import type { OpsData } from "./ops";

/** Ops snapshot for /admin: KV key "ops", pushed by the matchday chain's
 * EXIT trap. Short cache so a failed run shows within a minute. Falls back
 * to the JSON bundled at build time (dev / KV empty). */
export const getOps = cache(async (): Promise<OpsData> => {
  try {
    const { getCloudflareContext } = await import("@opennextjs/cloudflare");
    const { env } = getCloudflareContext();
    const kv = (env as Record<string, unknown>).LIVE_KV as
      | { get: (key: string, opts: { type: "json"; cacheTtl?: number }) => Promise<OpsData | null> }
      | undefined;
    if (kv) {
      const data = await kv.get("ops", { type: "json", cacheTtl: 60 });
      if (data) return data;
    }
  } catch {
    // fall through
  }
  return opsFallback as unknown as OpsData;
});
