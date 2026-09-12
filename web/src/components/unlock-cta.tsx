"use client";

import Link from "next/link";
import { SignInButton } from "@clerk/nextjs";
import type { Tier } from "@/lib/viewer";

/** The one call-to-action behind every lock. Anonymous viewers are asked to
 * sign in (free account unlocks the daily taster); free viewers are sent to
 * pricing. Client component so it can open Clerk's modal from server pages. */
export function UnlockCta({ tier, compact = false }: { tier: Tier; compact?: boolean }) {
  const cls = compact
    ? "whitespace-nowrap rounded-[6px] bg-[var(--oasis-home)] px-[9px] py-[4px] font-mono text-[10.5px] font-bold text-[var(--oasis-home-ink)]"
    : "whitespace-nowrap rounded-[7px] bg-[var(--oasis-home)] px-[13px] py-[7px] text-[12.5px] font-bold text-[var(--oasis-home-ink)]";
  if (tier === "anon") {
    return (
      <SignInButton mode="modal">
        <button type="button" className={cls}>
          {compact ? "Sign in" : "Sign in to unlock"}
        </button>
      </SignInButton>
    );
  }
  return (
    <Link href="/pricing" className={cls}>
      {compact ? "Unlock" : "Get lifetime access"}
    </Link>
  );
}
