import { cache } from "react";
import { auth } from "@clerk/nextjs/server";

/** Access tiers. `anon` sees no upcoming probabilities; `free` sees the
 * daily taster; `premium` sees everything. Premium is a flag in Clerk
 * public metadata (set by the payment webhook), exposed on the session
 * claims so no per-request lookup is needed. */
export type Tier = "anon" | "free" | "premium";

export interface Viewer {
  tier: Tier;
  userId: string | null;
}

export const getViewer = cache(async (): Promise<Viewer> => {
  try {
    const { userId, sessionClaims } = await auth();
    if (!userId) return { tier: "anon", userId: null };
    const meta = (sessionClaims as { metadata?: { premium?: boolean } } | null)?.metadata;
    return { tier: meta?.premium ? "premium" : "free", userId };
  } catch {
    // Rendered outside a request scope (or Clerk not configured).
    return { tier: "anon", userId: null };
  }
});
