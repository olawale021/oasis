import Link from "next/link";

export function LegalPage({ title, updated, intro, children }: { title: string; updated: string; intro: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-[860px] flex-col gap-6 p-4 pb-12 sm:p-6">
      <div className="flex flex-col gap-3 pb-2 sm:pr-[20%]">
        <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Last updated {updated}</span>
        <h1 className="text-display font-extrabold">{title}</h1>
        <p className="max-w-[62ch] text-lead text-[var(--oasis-text-muted)]">{intro}</p>
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
    <section className="grid gap-3 border-t border-[var(--oasis-border)] pt-5 sm:grid-cols-[160px_1fr] sm:gap-8">
      <h2 className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)] sm:pt-[3px]">{title}</h2>
      <div className="flex max-w-[68ch] flex-col gap-3 text-body text-[var(--oasis-text-soft)] [&_li]:ml-4 [&_li]:list-disc [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-1">{children}</div>
    </section>
  );
}

/** Facts the operator must fill before launch. Rendered visibly so a
 * placeholder can never pass for the real thing. */
export function Fill({ what }: { what: string }) {
  return <span className="rounded-[4px] border border-dashed border-[var(--oasis-warn)] px-1 font-mono text-[12px] text-[var(--oasis-warn)]">[{what}]</span>;
}
