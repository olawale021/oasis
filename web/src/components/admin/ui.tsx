import { cn } from "@/lib/utils";

/** Shared chrome for the admin console.
 *
 * Type scale — the one rule that keeps this readable: structure is sans,
 * data is mono. Labels, headings and prose use Instrument Sans; anything
 * you'd compare, scan or copy (numbers, ids, timestamps, log lines) uses
 * JetBrains Mono. The old console set everything in mono at one size,
 * which is why label and value read as the same thing. */

export const TEXT = {
  /** Section eyebrow inside a card header. */
  eyebrow: "font-sans text-[11px] font-semibold uppercase tracking-[0.07em] text-[var(--oasis-text-dim)]",
  /** Key in a key/value row. */
  label: "font-sans text-[12.5px] text-[var(--oasis-text-muted)]",
  /** Value in a key/value row. */
  value: "font-mono text-[12.5px] text-[var(--oasis-text)]",
  /** Supporting prose. */
  body: "font-sans text-[12.5px] text-[var(--oasis-text-muted)]",
  /** Smallest annotations — ids, counts under a step. */
  micro: "font-mono text-[10.5px] text-[var(--oasis-text-dim)]",
} as const;

export const TABLE = {
  th: "px-2 py-[7px] text-left font-sans text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]",
  td: "px-2 py-[7px] align-middle font-mono text-[12px]",
  /** Cells holding names rather than data. */
  tdText: "px-2 py-[7px] align-middle font-sans text-[12.5px]",
} as const;

export function Card({
  title, right, children, className, bodyClassName,
}: {
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("min-w-0 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)]", className)}>
      {title && (
        <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[var(--oasis-border)] px-4 py-[10px]">
          <h2 className={TEXT.eyebrow}>{title}</h2>
          {right && <div className="ml-auto flex items-center gap-2">{right}</div>}
        </header>
      )}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Row({ k, v, warn }: { k: string; v: React.ReactNode; warn?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-[var(--oasis-border-row)] py-[7px] last:border-0">
      <span className={TEXT.label}>{k}</span>
      <span className={cn(TEXT.value, "min-w-0 break-words text-right", warn && "text-[var(--oasis-warn)]")}>{v}</span>
    </div>
  );
}

/** Headline number. `tone` colours the figure when it carries a verdict. */
export function Stat({
  k, v, sub, tone = "plain",
}: {
  k: string;
  v: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "plain" | "good" | "warn" | "bad";
}) {
  const toneCls = {
    plain: "text-[var(--oasis-text)]",
    good: "text-[var(--oasis-positive)]",
    warn: "text-[var(--oasis-warn)]",
    bad: "text-[var(--oasis-away)]",
  }[tone];
  return (
    <div className="min-w-0 rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-bg)] px-[13px] py-[11px]">
      <div className="font-sans text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]">{k}</div>
      <div className={cn("mt-[3px] font-mono text-[23px] font-bold leading-none tracking-[-0.02em]", toneCls)}>{v}</div>
      {sub && <div className="mt-[5px] truncate font-sans text-[11px] text-[var(--oasis-text-muted)]">{sub}</div>}
    </div>
  );
}

export function Pill({
  children, tone = "muted",
}: {
  children: React.ReactNode;
  tone?: "muted" | "good" | "warn" | "bad" | "info";
}) {
  const cls = {
    muted: "border-[var(--oasis-border-strong)] text-[var(--oasis-text-muted)]",
    good: "border-[var(--oasis-positive)] text-[var(--oasis-positive)]",
    warn: "border-[var(--oasis-warn)] text-[var(--oasis-warn)]",
    bad: "border-[var(--oasis-away)] text-[var(--oasis-away)]",
    info: "border-[var(--oasis-home)] text-[var(--oasis-home)]",
  }[tone];
  return (
    <span className={cn("whitespace-nowrap rounded-[4px] border px-[6px] py-[1px] font-mono text-[10.5px]", cls)}>
      {children}
    </span>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className={TEXT.body}>{children}</p>;
}
