import Link from "next/link";

export function LegalPage({ title, updated, intro, children }: { title: string; updated: string; intro: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-[860px] flex-col gap-[14px] p-3 sm:p-5">
      <div className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 sm:p-5">
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] sm:text-[24px]">{title}</h1>
        <p className="mt-1 font-mono text-[11px] text-[var(--oasis-text-dim)]">Last updated {updated}</p>
        <p className="mt-3 text-[13.5px] leading-[1.7] text-[var(--oasis-text-muted)]">{intro}</p>
      </div>
      {children}
      <div className="flex gap-4 px-1 font-mono text-[11px] text-[var(--oasis-text-dim)]">
        <Link href="/privacy" className="hover:text-[var(--oasis-text)]">Privacy policy</Link>
        <Link href="/terms" className="hover:text-[var(--oasis-text)]">Terms and conditions</Link>
        <Link href="/method" className="hover:text-[var(--oasis-text)]">Method</Link>
      </div>
    </div>
  );
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 sm:p-5">
      <h2 className="mb-3 font-mono text-[10.5px] font-semibold uppercase tracking-[0.1em] text-[var(--oasis-text-dim)]">{title}</h2>
      <div className="flex flex-col gap-3 text-[13.5px] leading-[1.7] text-[var(--oasis-text-soft)] [&_li]:ml-4 [&_li]:list-disc [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-1">{children}</div>
    </section>
  );
}

/** Facts the operator must fill before launch. Rendered visibly so a
 * placeholder can never pass for the real thing. */
export function Fill({ what }: { what: string }) {
  return <span className="rounded-[4px] border border-dashed border-[var(--oasis-warn)] px-1 font-mono text-[12px] text-[var(--oasis-warn)]">[{what}]</span>;
}
