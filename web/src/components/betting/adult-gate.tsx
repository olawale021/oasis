import Link from "next/link";
import { confirmAdultAction } from "@/app/betting/actions";

/** Shown once per browser before the Betting section. Server-rendered so
 * there is nothing to flash past, and the numbers behind it are never sent
 * until the form has been submitted. */
export function AdultGate() {
  return (
    <div className="mx-auto flex w-full max-w-[640px] flex-col gap-5 p-4 pb-16 sm:p-6 lg:pt-12">
      <div className="flex flex-col gap-3">
        <span className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.1em] text-[var(--oasis-text-dim)]">Betting section</span>
        <h1 className="text-[24px] font-extrabold leading-[1.1] tracking-[-0.02em] sm:text-[28px]">This section is for adults.</h1>
        <p className="text-[14px] leading-[1.65] text-[var(--oasis-text-muted)]">
          It compares our model&rsquo;s probabilities with bookmaker prices and grades the difference. To open it you
          need to be <strong className="text-[var(--oasis-text)]">18 or over</strong>, or the legal age for
          gambling-related content where you live if that is higher, and it needs to be lawful for you to view betting
          information where you are.
        </p>
      </div>

      <ul className="flex flex-col gap-[10px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 text-[13px] leading-[1.6] text-[var(--oasis-text-muted)]">
        <li>• Nothing here is advice or a tip. A grade classifies a disagreement between a model and the market; it is not an instruction, and probabilities lose.</li>
        <li>• We are not a bookmaker, take no bets, and have no arrangement with any bookmaker. We do not know whether you bet.</li>
        <li>• If you bet, decide first what you can afford to lose and never chase losses. Help is free: GamCare 0808 8020 133 (UK), or your national helpline via gamblingtherapy.org.</li>
      </ul>

      <form action={confirmAdultAction} className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
        <button
          type="submit"
          className="rs-cta rounded-[8px] bg-[var(--oasis-home)] px-[16px] py-[10px] text-[13.5px] font-bold text-[var(--oasis-home-ink)]"
        >
          I&rsquo;m 18 or over — continue
        </button>
        <Link href="/" className="rounded-[8px] border border-[var(--oasis-border-strong)] px-[16px] py-[10px] text-[13.5px] font-semibold text-[var(--oasis-text-soft)]">
          Take me back
        </Link>
      </form>

      <p className="font-mono text-[10.5px] leading-[1.6] text-[var(--oasis-text-faint)]">
        Continuing records your confirmation in this browser for a year. It is your statement, not a check we run. Full
        terms: <Link href="/terms" className="text-[var(--oasis-text-muted)]">sections 2, 3 and 10</Link>.
      </p>
    </div>
  );
}
