import type { Metadata } from "next";
import Link from "next/link";
import { IconCheck, IconCross, IconArrowRight } from "@/components/icons";
import { UnlockCta } from "@/components/unlock-cta";
import { getLive } from "@/lib/live-server";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "RealscoresAI — Lifetime access",
  description: "One payment for every upcoming forecast across six leagues. Founding-member pricing, quantity capped.",
};

/** Set when Stripe checkout opens. Until then the page says so instead of
 * showing a number that could be wrong. */
const FOUNDING_PRICE: string | null = null;

const ROWS: { feature: string; free: boolean | string; lifetime: boolean | string }[] = [
  { feature: "Finished matches, with the locked forecast and verdict", free: true, lifetime: true },
  { feature: "Performance record and method, in full", free: true, lifetime: true },
  { feature: "Upcoming predictions", free: "2 per day", lifetime: "every fixture" },
  { feature: "Likely score and full score matrix", free: "taster only", lifetime: true },
  { feature: "What moved the forecast, factor by factor", free: "taster only", lifetime: true },
  { feature: "Market comparison and edge", free: false, lifetime: true },
  { feature: "High-confidence and edge filters", free: false, lifetime: true },
  { feature: "Every betting market, graded", free: false, lifetime: true },
];

function Cell({ v }: { v: boolean | string }) {
  if (v === true) return <span className="flex items-center justify-center text-[var(--oasis-positive)]"><IconCheck size={14} strokeWidth={2} aria-label="included" /></span>;
  if (v === false) return <span className="flex items-center justify-center text-[var(--oasis-text-faint)]"><IconCross size={12} strokeWidth={2} aria-label="not included" /></span>;
  return <span className="block text-center font-mono text-meta text-[var(--oasis-text-muted)]">{v}</span>;
}

function Stat({ k, v, accent = false }: { k: string; v: string; accent?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-[var(--oasis-border-row)] py-[10px] first:border-t-0">
      <span className="text-ui text-[var(--oasis-text-muted)]">{k}</span>
      <span className={`whitespace-nowrap font-mono text-lead font-semibold ${accent ? "text-[var(--oasis-positive)]" : ""}`}>{v}</span>
    </div>
  );
}

export default async function PricingPage() {
  const [viewer, live] = await Promise.all([getViewer(), getLive()]);
  const premium = viewer.tier === "premium";
  const lr = live.live_record;
  const closerPct = lr.market_n && lr.closer_n != null ? Math.round((100 * lr.closer_n) / lr.market_n) : null;

  return (
    <div className="mx-auto w-full max-w-[1100px] p-4 pb-16 sm:p-6 lg:pt-10">
      <div className="grid gap-10 lg:grid-cols-[1.25fr_1fr] lg:gap-16">
        {/* Offer */}
        <div className="flex flex-col gap-7">
          <div className="flex flex-col gap-4">
            <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Founding member · lifetime</span>
            <h1 className="max-w-[16ch] text-display font-extrabold sm:text-hero">Every upcoming forecast. One payment, never again.</h1>
            <p className="max-w-[58ch] text-lead text-[var(--oasis-text-muted)]">
              Win probabilities, likely scores, score matrices, the factors behind each forecast and the comparison
              against bookmaker odds, for every fixture in the Premier League, La Liga, Serie A, Bundesliga and MLS.
              Finished matches stay public for everyone.
            </p>
          </div>

          <div className="flex flex-wrap items-end gap-x-8 gap-y-4 border-t border-[var(--oasis-border)] pt-6">
            <div className="flex flex-col gap-1">
              <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Founding price</span>
              {FOUNDING_PRICE ? (
                <span className="font-mono text-hero font-semibold leading-none">{FOUNDING_PRICE}</span>
              ) : (
                <span className="text-title font-bold text-[var(--oasis-text-soft)]">Set at launch</span>
              )}
              <span className="font-mono text-meta text-[var(--oasis-text-muted)]">one-time · quantity capped · no renewal</span>
            </div>
            <div className="flex flex-col items-start gap-2 sm:ml-auto">
              {premium ? (
                <Link href="/account" className="rs-cta flex items-center gap-2 rounded-[7px] border border-[var(--oasis-positive)] px-[14px] py-[9px] text-ui font-bold text-[var(--oasis-positive)]">
                  You already have lifetime access <IconArrowRight size={14} />
                </Link>
              ) : viewer.tier === "anon" ? (
                <UnlockCta tier="anon" label="Sign in to be first in line" />
              ) : (
                <span className="rounded-[7px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-surface-raised)] px-[14px] py-[9px] text-ui font-bold text-[var(--oasis-text-soft)]">
                  Checkout opens at launch
                </span>
              )}
              {!premium && (
                <span className="font-mono text-meta text-[var(--oasis-text-dim)]">
                  {viewer.tier === "anon" ? "A free account already unlocks two forecasts a day." : "You are on the list. We will email when the cap opens."}
                </span>
              )}
            </div>
          </div>

          {/* What unlocks */}
          <div className="border-t border-[var(--oasis-border)] pt-2">
            <div className="grid grid-cols-[1fr_84px_84px] items-center gap-x-3 py-3 sm:grid-cols-[1fr_110px_110px]">
              <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">What unlocks</span>
              <span className="text-center font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Free</span>
              <span className="text-center font-mono text-label font-semibold uppercase text-[var(--oasis-text)]">Lifetime</span>
            </div>
            <div className="divide-y divide-[var(--oasis-border-row)] border-t border-[var(--oasis-border-row)]">
              {ROWS.map((r) => (
                <div key={r.feature} className="grid grid-cols-[1fr_84px_84px] items-center gap-x-3 py-[11px] sm:grid-cols-[1fr_110px_110px]">
                  <span className="text-body text-[var(--oasis-text-soft)]">{r.feature}</span>
                  <Cell v={r.free} />
                  <Cell v={r.lifetime} />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Proof */}
        <aside className="flex flex-col gap-8 lg:border-l lg:border-[var(--oasis-border)] lg:pl-10">
          <div className="flex flex-col gap-1">
            <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Why pay for a forecast</span>
            <p className="text-body text-[var(--oasis-text-muted)]">
              Every prediction is frozen before kickoff and scored after. The numbers below are that record, counted in full.
            </p>
          </div>

          <div>
            <div className="mb-1 font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Season so far · live record</div>
            {lr.settled > 0 ? (
              <div>
                <Stat k="matches scored" v={String(lr.settled)} />
                <Stat k="closer than the market" v={lr.closer_n != null && lr.market_n ? `${lr.closer_n} of ${lr.market_n} · ${closerPct}%` : "—"} accent />
                <Stat k="log loss v market" v={lr.model_log_loss_on_market != null && lr.market_log_loss != null ? `${lr.model_log_loss_on_market.toFixed(3)} v ${lr.market_log_loss.toFixed(3)}` : "—"} />
                <Stat k="top pick correct" v={lr.accuracy != null ? `${Math.round(lr.accuracy)}%` : "—"} />
              </div>
            ) : (
              <p className="border-t border-[var(--oasis-border-row)] pt-3 text-body text-[var(--oasis-text-dim)]">
                {lr.locked > 0 ? `${lr.locked} forecasts locked, awaiting results.` : "The first locked forecasts settle this week."}
              </p>
            )}
          </div>

          <div>
            <div className="mb-1 font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">{live.headline.season} backtest · held-out season</div>
            <Stat k="matches" v={String(live.headline.n_test)} />
            <Stat k="log loss" v={live.headline.log_loss.toFixed(3)} />
            <Stat k="top pick correct" v={`${live.headline.accuracy.toFixed(1)}%`} />
            <Stat k="calibration (ECE)" v={live.headline.ece.toFixed(3)} />
          </div>

          <div className="flex flex-col gap-2 border-t border-[var(--oasis-border)] pt-5">
            <span className="font-mono text-meta leading-[1.6] text-[var(--oasis-text-faint)]">
              Locking started 11 Sep 2026. Every settled forecast is counted, none removed. Probabilistic forecasts, not betting advice. 18+.
            </span>
            <Link href="/performance" className="flex items-center gap-[6px] text-ui font-bold text-[var(--oasis-home)]">
              See the full record <IconArrowRight size={14} />
            </Link>
          </div>
        </aside>
      </div>
    </div>
  );
}
