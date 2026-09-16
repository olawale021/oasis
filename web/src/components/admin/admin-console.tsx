import Link from "next/link";
import { logoutAction } from "@/app/admin/actions";
import { TABS, type TabId } from "@/lib/admin-tabs";
import { ago, duration, heartbeat, type Heartbeat, type OpsData } from "@/lib/ops";
import { cn } from "@/lib/utils";

const HB: Record<Heartbeat, { label: string; dot: string; text: string; blurb: string }> = {
  ok:     { label: "Server reporting", dot: "bg-[var(--oasis-positive)]", text: "text-[var(--oasis-positive)]", blurb: "Last hourly run succeeded." },
  failed: { label: "Last run failed",  dot: "bg-[var(--oasis-away)]",     text: "text-[var(--oasis-away)]",     blurb: "The server is up but the chain stopped at a step. See Pipeline." },
  stale:  { label: "Missed a run",     dot: "bg-[var(--oasis-warn)]",     text: "text-[var(--oasis-warn)]",     blurb: "No report for over 75 minutes. Cron may have skipped or the run is hanging." },
  down:   { label: "Server silent",    dot: "bg-[var(--oasis-away)]",     text: "text-[var(--oasis-away)]",     blurb: "No report for over 3 hours. Check the droplet: ssh oasis@143.110.170.181" },
};

/** The console frame: a health banner that never leaves the screen, and a
 * tab bar. Health is the one thing you open this page for, so it outranks
 * everything else in the type scale and sits above the tabs rather than
 * competing with them. Tabs are links, so the page stays server-rendered. */
export function AdminShell({
  ops, liveGeneratedAt, now, tab, children,
}: {
  ops: OpsData;
  liveGeneratedAt: string;
  now: number;
  tab: TabId;
  children: React.ReactNode;
}) {
  const h = HB[heartbeat(ops, now).state];
  const failed = ops.last_run.ok === false;

  return (
    <div className="mx-auto w-full max-w-[1280px] px-4 py-5 sm:px-[22px]">
      <header className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)]">
        <div className="flex flex-wrap items-start gap-x-6 gap-y-3 px-4 py-[14px]">
          <div className="min-w-0">
            <div className="flex items-center gap-[10px]">
              <span className={cn("h-[10px] w-[10px] shrink-0 rounded-full", h.dot)} />
              <h1 className={cn("font-sans text-[19px] font-extrabold leading-none tracking-[-0.02em]", h.text)}>{h.label}</h1>
            </div>
            <p className="mt-[7px] font-sans text-[12.5px] text-[var(--oasis-text-muted)]">{h.blurb}</p>
          </div>

          <dl className="flex flex-wrap items-center gap-x-6 gap-y-2 sm:ml-auto">
            {[
              { k: "report", v: ago(ops.generated_at, now) },
              { k: "last run", v: failed ? `failed at ${ops.last_run.failed_step}` : duration(ops.last_run.duration_s), bad: failed },
              { k: "site data", v: ago(liveGeneratedAt, now) },
            ].map((m) => (
              <div key={m.k}>
                <dt className="font-sans text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--oasis-text-dim)]">{m.k}</dt>
                <dd className={cn("mt-[2px] font-mono text-[12.5px]", m.bad ? "text-[var(--oasis-away)]" : "text-[var(--oasis-text)]")}>{m.v}</dd>
              </div>
            ))}
            <form action={logoutAction}>
              <button
                type="submit"
                className="rounded-[6px] border border-[var(--oasis-border-strong)] px-[10px] py-[5px] font-sans text-[11.5px] text-[var(--oasis-text-muted)] transition-colors hover:border-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]"
              >
                Sign out
              </button>
            </form>
          </dl>
        </div>

        <nav className="flex gap-[2px] overflow-x-auto border-t border-[var(--oasis-border)] px-2">
          {TABS.map((t) => {
            const active = t.id === tab;
            return (
              <Link
                key={t.id}
                href={t.id === "overview" ? "/admin" : `/admin?tab=${t.id}`}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "-mb-px whitespace-nowrap border-b-2 px-[13px] py-[10px] font-sans text-[12.5px] transition-colors",
                  active
                    ? "border-[var(--oasis-home)] font-semibold text-[var(--oasis-text)]"
                    : "border-transparent text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]",
                )}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
      </header>

      <div className="mt-4">{children}</div>
    </div>
  );
}
