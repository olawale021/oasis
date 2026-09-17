"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

/** Keeps server-rendered content in step with the Clerk session.
 *
 * Tier is resolved on the server (`getViewer()`), so what a viewer may see
 * is baked into the RSC payload. Clerk's sign-in and sign-out happen
 * entirely client-side: the session goes away, but Next's router cache
 * still holds the payload rendered for the old session, so the page keeps
 * showing signed-in content until a manual reload.
 *
 * Watching the user id covers sign-out, sign-in and switching accounts in
 * one place — no per-button callbacks to keep in sync. The first settled
 * value is recorded, not acted on, so the initial load never refetches. */
export function AuthSync() {
  const { isLoaded, userId } = useAuth();
  const router = useRouter();
  const seen = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (!isLoaded) return;
    const current = userId ?? null;
    if (seen.current === undefined) {
      seen.current = current;
      return;
    }
    if (seen.current !== current) {
      seen.current = current;
      router.refresh();
    }
  }, [isLoaded, userId, router]);

  return null;
}
