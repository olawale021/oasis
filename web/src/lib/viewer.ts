import { cache } from "react";
import { auth, currentUser } from "@clerk/nextjs/server";

/** Access tiers. `anon` sees no upcoming probabilities; `free` sees the
 * daily taster; `premium` sees everything. Premium is a flag in Clerk
 * public metadata (set from /admin or the payment webhook).
 *
 * The fast path reads it off the session claims, which needs the Clerk
 * instance's session token customised with
 *   { "metadata": "{{user.public_metadata}}" }
 * (Dashboard -> Sessions -> Customize session token), on BOTH the dev and
 * production instances. When that claim is absent entirely -- not
 * configured, rather than configured and false -- we fetch the user
 * instead of silently downgrading a paying customer to free. That costs
 * one Clerk API call per request for signed-in viewers, so configure the
 * claim; the fallback is a safety net, not the design. */
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
    if (meta !== undefined) return { tier: meta?.premium ? "premium" : "free", userId };
    const user = await currentUser();
    const premium = (user?.publicMetadata as { premium?: boolean } | null)?.premium === true;
    return { tier: premium ? "premium" : "free", userId };
  } catch {
    // Rendered outside a request scope (or Clerk not configured).
    return { tier: "anon", userId: null };
  }
});
