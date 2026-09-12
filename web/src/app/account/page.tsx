import { currentUser } from "@clerk/nextjs/server";
import Link from "next/link";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const [viewer, user] = await Promise.all([getViewer(), currentUser()]);
  const email = user?.primaryEmailAddress?.emailAddress ?? "—";

  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-col gap-[14px] p-3 sm:p-5">
      <h1 className="text-[21px] font-bold tracking-[-0.02em]">Account</h1>

      <section className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">ACCESS</div>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <span
            className="rounded-full px-[10px] py-[4px] font-mono text-[11px] font-bold tracking-[0.08em]"
            style={
              viewer.tier === "premium"
                ? { background: "var(--oasis-positive-tint)", color: "var(--oasis-positive)", border: "1px solid rgba(47,207,154,.35)" }
                : { background: "var(--oasis-surface-raised)", color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border-strong)" }
            }
          >
            {viewer.tier === "premium" ? "LIFETIME" : "FREE"}
          </span>
          <span className="text-[13px] text-[var(--oasis-text-muted)]">
            {viewer.tier === "premium"
              ? "All five leagues, every upcoming prediction, full explanations."
              : "Two highest-confidence predictions per day. Finished matches are always open."}
          </span>
        </div>
        {viewer.tier !== "premium" && (
          <Link
            href="/pricing"
            className="mt-4 inline-block rounded-[7px] bg-[var(--oasis-home)] px-[13px] py-[7px] text-[12.5px] font-bold text-[var(--oasis-home-ink)]"
          >
            Get lifetime access
          </Link>
        )}
      </section>

      <section className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">PROFILE</div>
        <div className="mt-2 text-[13px]">
          <span className="text-[var(--oasis-text-muted)]">Signed in as</span> {email}
        </div>
        <div className="mt-1 font-mono text-[11px] text-[var(--oasis-text-dim)]">
          Manage email, password and sessions from the avatar menu in the header.
        </div>
      </section>

      <section className="rounded-[10px] border border-dashed border-[var(--oasis-border)] p-4 text-[12.5px] text-[var(--oasis-text-dim)]">
        Telegram alerts and alert preferences arrive with the Telegram phase.
      </section>
    </div>
  );
}
