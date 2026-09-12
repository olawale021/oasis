"use client";

import { TwinBar } from "@/components/probability-bar";
import { TeamSide } from "@/components/team-logo";
import { UnlockCta } from "@/components/unlock-cta";
import { LEAGUE_NAMES, utcDayLabel } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import type { RecentResult } from "@/lib/types";
import type { Tier } from "@/lib/viewer";

export type ResultsFilter = "all" | "closer" | "market" | "hit";
export const TASTER_PER_DAY = 2;

const OUTCOME_LABEL = ["home win", "draw", "away win"];
const OUTCOME_COLOR = ["var(--oasis-home)", "var(--oasis-text-soft)", "var(--oasis-away)"];

/** Rows are the public record: locked before kickoff, settled, never
 * edited. Retro reconstructions are excluded upstream. */
export function resultsSummary(rows: RecentResult[]) {
  let n = 0, closer = 0, compared = 0, hits = 0, draws = 0, ll = 0, mll = 0;
  for (const r of rows) {
    const l = r.locked;
    if (!l || l.correct === null) continue;
    n += 1;
    if (l.correct) hits += 1;
    if (l.outcome === 1) draws += 1;
    if (l.closer != null && l.logLoss != null && l.marketLogLoss != null) {
      compared += 1; ll += l.logLoss; mll += l.marketLogLoss;
      if (l.closer) closer += 1;
    }
  }
  return { n, closer, compared, hits, draws, ll: compared ? ll / compared : null, mll: compared ? mll / compared : null };
}

export function ResultsHero({ rows, live, bookmakerCount }: { rows: RecentResult[]; live: LiveData; bookmakerCount: number }) {
  const s = resultsSummary(rows);
  const tiles = [
    {
      k: "CLOSER THAN THE BOOKMAKERS",
      v: s.compared ? `${s.closer} of ${s.compared}` : "—",
      sub: s.compared ? "results this week where our forecast gave the real outcome more chance than the odds did" : "fills in as locked forecasts settle",
      color: s.compared ? "var(--oasis-positive)" : undefined,
    },
    {
      k: "FORECAST ERROR · LOG LOSS",
      v: s.ll != null && s.mll != null ? <>{s.ll.toFixed(3)} <span className="text-[14px] text-[var(--oasis-text-dim)]">v</span> {s.mll.toFixed(3)}</> : "—",
      sub: "us v market · lower is better · one weekend moves this a lot, one season settles it",
    },
    {
      k: "TOP PICK CORRECT",
      v: s.n ? `${s.hits} of ${s.n}` : "—",
      sub: s.n ? `${s.draws} of ${s.n} finished as draws` : "no settled forecasts yet",
    },
  ];
  return (
    <div className="flex flex-col gap-[14px]">
      <div className="flex max-w-[760px] flex-col gap-2">
        <span className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">SCORED AGAINST THE BOOKMAKERS</span>
        <h1 className="m-0 text-[21px] font-extrabold leading-[1.18] tracking-[-0.02em] sm:text-[27px]" style={{ textWrap: "pretty" }}>
          Every forecast is locked before kickoff, then scored against the bookmakers on what actually happened.
        </h1>
        <p className="m-0 text-[12.5px] leading-[1.65] text-[var(--oasis-text-muted)] sm:text-[13.5px]" style={{ textWrap: "pretty" }}>
          The bar is our forecast. The thin line beneath it is what {bookmakerCount || "the"} bookmakers implied at the same moment, with their margin
          removed. After the final whistle, the one that gave more chance to the real result was closer.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:gap-[10px]">
        {tiles.map((t, i) => (
          <div
            key={t.k}
            className="rs-rise flex min-w-0 flex-col gap-[3px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[10px] sm:gap-1 sm:p-[13px] sm:px-[14px]"
            style={{ animationDelay: `${i * 70}ms` }}
          >
            <span className="font-mono text-[9px] font-semibold leading-[1.3] tracking-[0.08em] text-[var(--oasis-text-dim)] sm:text-[10px] sm:tracking-[0.1em]">{t.k}</span>
            <span className="whitespace-nowrap font-mono text-[16px] font-bold leading-[1.1] sm:text-[22px]" style={{ color: t.color }}>{t.v}</span>
            <span className="hidden text-[12px] font-medium leading-[1.45] text-[var(--oasis-text-muted)] sm:block">{t.sub}</span>
          </div>
        ))}
      </div>
      <p className="m-0 flex flex-col gap-[6px] text-[12.5px] font-medium leading-[1.45] text-[var(--oasis-text-muted)] sm:hidden">
        Whoever gave the real result more chance was closer. Nothing here was edited after kickoff.
      </p>
      {live.live_record.settled > s.n && (
        <span className="font-mono text-[10.5px] text-[var(--oasis-text-faint)]">
          Season record: {live.live_record.closer_n ?? "—"} of {live.live_record.market_n} closer than the market across {live.live_record.settled} settled forecasts.
        </span>
      )}
    </div>
  );
}

export function SignInStrip({ tier }: { tier: Tier }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-3 sm:flex-row sm:items-center sm:gap-4 sm:px-[14px]">
      <div className="flex-1 text-[12.5px] leading-[1.6] text-[var(--oasis-text-muted)]">
        <span className="font-bold text-[var(--oasis-text)]">Upcoming matches are under Today, Tomorrow and Week.</span>{" "}
        {tier === "anon"
          ? `A free account unlocks the ${TASTER_PER_DAY} highest-confidence forecasts each day.`
          : "Lifetime access unlocks every upcoming forecast."}
      </div>
      <UnlockCta tier={tier} />
    </div>
  );
}

function Verdict({ r, compact = false }: { r: RecentResult; compact?: boolean }) {
  const l = r.locked!;
  if (l.correct === null || l.outcome == null) {
    return <span className="font-mono text-[11.5px] text-[var(--oasis-text-dim)]">awaiting settlement</span>;
  }
  const us = Math.round([l.h, l.d, l.a][l.outcome]);
  const mk = l.mh != null && l.md != null && l.ma != null ? Math.round([l.mh, l.md, l.ma][l.outcome]) : null;
  const chip =
    l.closer === true ? (
      <span className="whitespace-nowrap rounded-full border border-[rgba(47,207,154,.35)] bg-[var(--oasis-positive-tint)] px-[9px] py-[3px] font-mono text-[10px] font-bold tracking-[0.06em] text-[var(--oasis-positive)]">CLOSER THAN MARKET</span>
    ) : l.closer === false ? (
      <span className="whitespace-nowrap rounded-full border border-[var(--oasis-border-strong)] px-[9px] py-[3px] font-mono text-[10px] font-bold tracking-[0.06em] text-[var(--oasis-text-dim)]">MARKET CLOSER</span>
    ) : (
      <span className="whitespace-nowrap rounded-full border border-dashed border-[var(--oasis-border-strong)] px-[9px] py-[3px] font-mono text-[10px] font-bold tracking-[0.06em] text-[var(--oasis-text-dim)]">NO ODDS AT LOCK</span>
    );
  const nums = (
    <span className="whitespace-nowrap font-mono text-[12px] leading-[1.2]">
      <span className="font-bold">us {us}%</span>
      {mk != null && <span className="text-[var(--oasis-text-muted)]"> · market {mk}%</span>}
    </span>
  );
  if (compact) return <>{nums}{chip}</>;
  return <span className="rs-rise flex flex-col items-end gap-[6px]" style={{ animationDelay: "520ms" }}>{nums}{chip}</span>;
}

function Meta({ r }: { r: RecentResult }) {
  const o = r.locked?.outcome;
  return (
    <span className="whitespace-nowrap font-mono text-[10.5px] font-medium text-[var(--oasis-text-muted)] sm:text-[11.5px]">
      {LEAGUE_NAMES[r.lg]} · {r.ko} UTC
      {o != null && (
        <>
          {" · "}
          <span className="font-bold" style={{ color: OUTCOME_COLOR[o] }}>result: {OUTCOME_LABEL[o]}</span>
        </>
      )}
    </span>
  );
}

export function ResultsList({ rows, filter }: { rows: RecentResult[]; filter: ResultsFilter }) {
  const shown = rows.filter((r) => {
    const l = r.locked!;
    if (filter === "closer") return l.closer === true;
    if (filter === "market") return l.closer === false;
    if (filter === "hit") return l.correct === true;
    return true;
  });
  const dayCount: Record<string, number> = {};
  for (const r of shown) dayCount[r.kickoffUtc.slice(0, 10)] = (dayCount[r.kickoffUtc.slice(0, 10)] ?? 0) + 1;

  return (
    <>
      <div className="flex items-center border-b border-[var(--oasis-border)] px-1 pb-[9px] font-mono text-[10px] font-semibold tracking-[0.09em] text-[var(--oasis-text-dim)] sm:text-[10.5px]">
        <span className="flex flex-1 items-center gap-[14px] md:pr-[18px]">
          <span className="hidden text-right md:block md:w-[160px]">HOME</span>
          <span className="flex flex-1 items-center gap-[16px] md:justify-center">
            <span>OUR FORECAST</span>
            <span className="flex items-center gap-[6px] text-[var(--oasis-text-faint)]">
              <span className="block h-[4px] w-[18px] rounded-[2px] bg-[var(--oasis-home)] opacity-50" />
              MARKET LINE
            </span>
          </span>
          <span className="hidden md:block md:w-[160px]">AWAY</span>
        </span>
        <span className="hidden w-[80px] text-right md:block">FINAL</span>
        <span className="hidden w-[170px] text-right md:block">ON THE RESULT</span>
      </div>

      {shown.map((r, i) => {
        const l = r.locked!;
        const day = r.kickoffUtc.slice(0, 10);
        const showDay = i === 0 || shown[i - 1].kickoffUtc.slice(0, 10) !== day;
        const market = l.mh != null && l.md != null && l.ma != null ? ([l.mh, l.md, l.ma] as [number, number, number]) : null;
        return (
          <div key={r.id}>
            {showDay && (
              <div className="pb-[6px] pt-3 font-mono text-[12px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)] sm:text-[12.5px]">
                {utcDayLabel(r.kickoffUtc).toUpperCase()} · <span className="text-[var(--oasis-text-muted)]">{dayCount[day]} {dayCount[day] === 1 ? "result" : "results"}</span>
              </div>
            )}
            {/* Desktop row */}
            <div className="rs-row hidden items-center border-b border-[var(--oasis-border-row)] px-1 py-[14px] md:flex">
              <span className="flex min-w-0 flex-1 items-center gap-[14px] pr-[18px]">
                <TeamSide id={r.homeId} name={r.home} side="home" size={24} className="w-[160px] text-[15px] font-bold tracking-[-0.01em]" />
                <span className="flex min-w-0 flex-1 flex-col items-center gap-[5px]">
                  <TwinBar model={[l.h, l.d, l.a]} market={market} outcome={l.outcome ?? null} delayMs={Math.min(i, 24) * 60} className="w-full" />
                  <Meta r={r} />
                </span>
                <TeamSide id={r.awayId} name={r.away} side="away" size={24} className="w-[160px] text-[15px] font-bold tracking-[-0.01em]" />
              </span>
              <span className="w-[80px] text-right font-mono text-[16.5px] font-bold">{r.score}</span>
              <span className="flex w-[170px] justify-end"><Verdict r={r} /></span>
            </div>
            {/* Phone row */}
            <div className="rs-row flex flex-col gap-2 border-b border-[var(--oasis-border-row)] py-3 md:hidden">
              <span className="flex items-center justify-between gap-[10px]">
                <TeamSide id={r.homeId} name={r.home} side="away" size={20} className="min-w-0 flex-1 text-[14px] font-bold tracking-[-0.01em]" />
                <span className="shrink-0 font-mono text-[15px] font-bold">{r.score}</span>
                <TeamSide id={r.awayId} name={r.away} side="home" size={20} className="min-w-0 flex-1 justify-end text-[14px] font-bold tracking-[-0.01em]" />
              </span>
              <TwinBar model={[l.h, l.d, l.a]} market={market} outcome={l.outcome ?? null} height={22} line={6} delayMs={Math.min(i, 24) * 60} className="w-full" />
              <Meta r={r} />
              <span className="flex items-center justify-between gap-2"><Verdict r={r} compact /></span>
            </div>
          </div>
        );
      })}

      {shown.length === 0 && (
        <div className="rounded-[9px] border border-dashed border-[var(--oasis-border-strong)] p-[22px] text-center text-[13px] font-semibold text-[var(--oasis-text-muted)]">
          {rows.length === 0
            ? "No locked forecasts have settled in the last 7 days for this selection. Forecasts lock at kickoff and appear here once the match finishes."
            : "No results match this filter."}
        </div>
      )}
    </>
  );
}

/** Right-rail cards for the Results view. */
export function HowToReadCard() {
  const rows = [
    {
      sw: <span className="flex h-[12px] w-[34px] overflow-hidden rounded-[3px]"><span className="w-1/2 bg-[var(--oasis-home)]" /><span className="w-1/4 bg-[var(--oasis-draw)]" /><span className="w-1/4 bg-[var(--oasis-away)]" /></span>,
      t: "The bar is our forecast",
      b: "Home win, draw and away win, as percentages that add to 100.",
    },
    {
      sw: <span className="mt-1 flex h-[5px] w-[34px] overflow-hidden rounded-[2px]"><span className="w-[60%] bg-[var(--oasis-home)] opacity-40" /><span className="w-[20%] bg-[var(--oasis-draw)]" /><span className="w-[20%] bg-[var(--oasis-away)] opacity-40" /></span>,
      t: "The thin line is the market",
      b: "The same split implied by the bookmakers at lock time. It lights up where the result landed.",
    },
    {
      sw: <span className="block h-[12px] w-[34px] rounded-[3px] bg-[var(--oasis-draw)]" style={{ boxShadow: "inset 0 0 0 2px var(--oasis-text)" }} />,
      t: "The outlined segment is what happened",
      b: "So you can see at a glance how much chance we gave it.",
    },
    {
      sw: <span className="rounded-full border border-[rgba(47,207,154,.35)] bg-[var(--oasis-positive-tint)] px-[7px] py-[2px] font-mono text-[9px] font-bold tracking-[0.06em] text-[var(--oasis-positive)]">CLOSER</span>,
      t: "Closer means we beat the odds on that match",
      b: "Whoever gave the real result the higher number was closer. No hindsight edits: every row was locked before kickoff.",
    },
  ];
  return (
    <div className="flex flex-col gap-3 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px]">
      <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">HOW TO READ A ROW</div>
      {rows.map((x) => (
        <div key={x.t} className="flex items-start gap-[10px]">
          <span className="mt-[3px] shrink-0">{x.sw}</span>
          <span className="flex flex-col gap-[2px]">
            <span className="text-[12.5px] font-bold">{x.t}</span>
            <span className="text-[12px] leading-[1.55] text-[var(--oasis-text-muted)]">{x.b}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

export function MarketCard({ bookmakers }: { bookmakers: string[] }) {
  return (
    <div className="flex flex-col gap-[9px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px]">
      <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
        THE MARKET{bookmakers.length ? ` · ${bookmakers.length} BOOKMAKERS` : ""}
      </div>
      <span className="text-[12px] leading-[1.55] text-[var(--oasis-text-muted)]">
        The market line is the median of these bookmakers&rsquo; odds at lock time, each with its own margin removed first. It is a benchmark only, never an input to our model.
      </span>
      {bookmakers.length > 0 && (
        <div className="flex flex-wrap gap-[5px]">
          {bookmakers.map((b) => (
            <span key={b} className="whitespace-nowrap rounded-full border border-[var(--oasis-border)] px-2 py-[3px] font-mono text-[10.5px] font-medium text-[var(--oasis-text-soft)]">{b}</span>
          ))}
        </div>
      )}
      <span className="font-mono text-[10px] leading-[1.6] text-[var(--oasis-text-faint)]">Snapshots at 7d, 24h, 6h, 1h and closing. Append-only, never edited.</span>
    </div>
  );
}

export function LiveRecordCard({ live }: { live: LiveData }) {
  const lr = live.live_record;
  const closerPct = lr.market_n && lr.closer_n != null ? Math.round((100 * lr.closer_n) / lr.market_n) : null;
  return (
    <div className="flex flex-col gap-[9px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px]">
      <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">SEASON SO FAR · LIVE RECORD</div>
      <Row k="matches scored" v={lr.settled} />
      <Row k="closer than market" v={lr.closer_n != null && lr.market_n ? `${lr.closer_n} · ${closerPct}%` : "—"} color="var(--oasis-positive)" />
      <Row k="log loss v market" v={lr.model_log_loss_on_market != null && lr.market_log_loss != null ? `${lr.model_log_loss_on_market.toFixed(3)} v ${lr.market_log_loss.toFixed(3)}` : "—"} />
      <Row k="top pick correct" v={lr.accuracy != null ? `${Math.round(lr.accuracy)}%` : "—"} />
      <span className="font-mono text-[10px] leading-[1.6] text-[var(--oasis-text-faint)]">Locking started 11 Sep 2026. Every settled forecast is counted, none removed.</span>
      <a href="/performance" className="text-[11.5px] font-bold text-[var(--oasis-home)]">See full record →</a>
    </div>
  );
}

function Row({ k, v, color }: { k: string; v: React.ReactNode; color?: string }) {
  return (
    <span className="flex justify-between gap-3 font-mono text-[12.5px] font-medium">
      <span className="text-[var(--oasis-text-muted)]">{k}</span>
      <span className="whitespace-nowrap" style={{ color: v === "—" ? undefined : color }}>{v}</span>
    </span>
  );
}
