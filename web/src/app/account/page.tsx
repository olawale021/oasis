import { currentUser } from "@clerk/nextjs/server";
import Link from "next/link";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

/** A labelled block in the account ledger: name on the left, content on the
 * right, a rule above. Same rhythm as the method page. */
function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-3 border-t border-[var(--oasis-border)] pt-5 sm:grid-cols-[140px_1fr] sm:gap-8">
      <h2 className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)] sm:pt-[3px]">{label}</h2>
      <div className="flex flex-col gap-3 text-body text-[var(--oasis-text-soft)]">{children}</div>
    </section>
  );
}

export default async function AccountPage() {
  const [viewer, user] = await Promise.all([getViewer(), currentUser()]);
  const email = user?.primaryEmailAddress?.emailAddress ?? "—";
  const premium = viewer.tier === "premium";

  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-6 p-4 pb-12 sm:p-6">
      <div className="flex flex-col gap-3 pb-2">
        <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Account</span>
        <h1 className="text-display font-extrabold">{premium ? "Lifetime member" : "Free account"}</h1>
      </div>

      <Block label="Access">
        <div className="flex flex-wrap items-center gap-3">
          <span
            className="rounded-full px-[10px] py-[4px] font-mono text-label font-bold"
            style={
              premium
                ? { background: "var(--oasis-positive-tint)", color: "var(--oasis-positive)", border: "1px solid var(--oasis-positive)" }
                : { background: "var(--oasis-surface-raised)", color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border-strong)" }
            }
          >
            {premium ? "LIFETIME" : "FREE"}
          </span>
          <span className="text-[var(--oasis-text-muted)]">
            {premium
              ? "All five leagues, every upcoming prediction, full explanations."
              : "Two highest-confidence predictions per day. Finished matches are always open."}
          </span>
        </div>
        {!premium && (
          <Link
            href="/pricing"
            className="rs-cta inline-block self-start rounded-[7px] bg-[var(--oasis-home)] px-[13px] py-[7px] text-ui font-bold text-[var(--oasis-home-ink)]"
          >
            Get lifetime access
          </Link>
        )}
      </Block>

      <Block label="Profile">
        <div>
          <span className="text-[var(--oasis-text-muted)]">Signed in as</span> {email}
        </div>
        <div className="font-mono text-meta text-[var(--oasis-text-dim)]">
          Manage email, password and sessions from the avatar menu in the header.
        </div>
      </Block>

      <Block label="Alerts">
        <div className="text-[var(--oasis-text-dim)]">Telegram alerts and alert preferences arrive with the Telegram phase.</div>
      </Block>
    </div>
  );
}
