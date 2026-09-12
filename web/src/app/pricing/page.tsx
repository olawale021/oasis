import Link from "next/link";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export default async function PricingPage() {
  const viewer = await getViewer();
  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-col gap-[14px] p-3 sm:p-5">
      <h1 className="text-[21px] font-bold tracking-[-0.02em]">Lifetime access</h1>
      <p className="text-[13.5px] text-[var(--oasis-text-muted)]">
        One payment. Every upcoming prediction across the Premier League, La Liga, Serie A, Bundesliga and MLS,
        with likely scores, score matrices, model factors and market comparison. Finished matches stay public for everyone.
      </p>
      <section className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 text-[13px]">
        {viewer.tier === "premium" ? (
          <span>You already have lifetime access. <Link href="/account" className="text-[var(--oasis-home)]">Account →</Link></span>
        ) : (
          <span className="text-[var(--oasis-text-muted)]">
            Founding-member checkout opens soon. {viewer.tier === "anon" && "Sign in to be first in line."}
          </span>
        )}
      </section>
    </div>
  );
}
