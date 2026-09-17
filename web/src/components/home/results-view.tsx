"use client";

import { useEffect, useRef, useState } from "react";
import { TwinBar } from "@/components/probability-bar";
import { TeamSide } from "@/components/team-logo";
import { UnlockCta } from "@/components/unlock-cta";
import { LEAGUE_CODES, LEAGUE_NAMES, utcDayLabel } from "@/lib/data";
import { cn } from "@/lib/utils";
import type { LiveData } from "@/lib/data";
import type { LeagueCode } from "@/lib/types";
import type { RecentResult } from "@/lib/types";
import type { Tier } from "@/lib/viewer";
import { IconCheck, IconCross } from "@/components/icons";

export type ResultsFilter = "all" | "closer" | "market" | "hit";
export const TASTER_PER_DAY = 2;

const OUTCOME_LABEL = ["home win", "draw", "away win"];
const OUTCOME_COLOR = ["var(--oasis-home)", "var(--oasis-text-soft)", "var(--oasis-away)"];

/** Rows are the public record: locked before kickoff, settled, never
 * edited. Retro reconstructions are excluded upstream. */
export function resultsSummary(rows: RecentResult[]) {
  let n = 0, closer = 0, compared = 0, hits = 0, draws = 0, ll = 0, mll = 0, expDraws = 0, mktExpDraws = 0;
  for (const r of rows) {
    const l = r.locked;
    if (!l || l.correct === null) continue;
    n += 1;
    if (l.correct) hits += 1;
    if (l.outcome === 1) draws += 1;
    expDraws += l.d / 100;
    if (l.md != null) mktExpDraws += l.md / 100;
    if (l.closer != null && l.logLoss != null && l.marketLogLoss != null) {
      compared += 1; ll += l.logLoss; mll += l.marketLogLoss;
      if (l.closer) closer += 1;
    }
  }
  return { n, closer, compared, hits, draws, expDraws, mktExpDraws, ll: compared ? ll / compared : null, mll: compared ? mll / compared : null };
}

/** Plain-language read on the week's draws, computed from the data so it
 * updates itself. "Unusual" means observed draws exceed what the forecasts
 * summed to by more than about two matches' worth of noise. */
function drawNote(s: ReturnType<typeof resultsSummary>): { v: string; sub: string; tone?: string } {
  if (!s.n) return { v: "—", sub: "no settled forecasts yet" };
  const exp = Math.round(s.expDraws);
  const sd = Math.sqrt(Math.max(1, s.expDraws * (1 - s.expDraws / s.n)));
  const excess = s.draws - s.expDraws;
  if (excess > 1.5 * sd) {
    return {
      v: `${s.draws} of ${s.n}`,
      sub: `a draw-heavy week: our forecasts expected about ${exp}. Draws are the hardest result to call and every forecaster, us and the bookmakers, misses in a week like this`,
      tone: "var(--oasis-warn)",
    };
  }
  if (excess < -1.5 * sd) {
    return { v: `${s.draws} of ${s.n}`, sub: `fewer draws than usual: our forecasts expected about ${exp}, which flatters everyone's accuracy this week` };
  }
  return { v: `${s.draws} of ${s.n}`, sub: `in line with the ${exp} our forecasts expected, so this week's accuracy is a fair read` };
}

/** Swipeable accuracy cards: overall first, then one per league that has
 * settled results this week, each naming the model that made the calls.
 * Scroll-snap on touch, dots and arrows on desktop. */
function AccuracyCards({ rows, versions }: { rows: RecentResult[]; versions: Record<string, string> }) {
  const groups: { key: string; label: string; s: ReturnType<typeof resultsSummary>; version?: string }[] = [
    { key: "ALL", label: "All leagues", s: resultsSummary(rows) },
    ...LEAGUE_CODES.map((lg: LeagueCode) => ({ key: lg, label: LEAGUE_NAMES[lg], s: resultsSummary(rows.filter((r) => r.lg === lg)), version: versions[lg] })).filter((g) => g.s.n > 0),
  ];
  const ref = useRef<HTMLDivElement>(null);
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => setIdx(Math.round(el.scrollLeft / el.clientWidth));
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);
  const go = (i: number) => {
    const el = ref.current;
    if (!el) return;
    const n = (i + groups.length) % groups.length;
    el.scrollTo({ left: n * el.clientWidth, behavior: "smooth" });
  };
  return (
    <div className="rs-rise group relative flex min-w-0 flex-col rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)]">
      <div ref={ref} className="rs-noscroll flex snap-x snap-mandatory overflow-x-auto">
        {groups.map((g) => {
          const pct = g.s.n ? Math.round((100 * g.s.hits) / g.s.n) : null;
          return (
            <div key={g.key} className="flex w-full shrink-0 snap-start flex-col gap-[3px] p-[10px] sm:gap-1 sm:p-[12px] sm:px-[13px]">
              <span className="truncate font-mono text-[9px] font-semibold leading-[1.3] tracking-[0.08em] text-[var(--oasis-text-dim)] sm:text-[10px] sm:tracking-[0.1em]">
                ACCURACY · {g.label.toUpperCase()}
              </span>
              <span className="whitespace-nowrap font-mono text-[17px] font-bold leading-[1.1] sm:text-[21px]">{pct != null ? `${pct}%` : "—"}</span>
              <span className="hidden text-[11.5px] font-medium leading-[1.45] text-[var(--oasis-text-muted)] sm:block">
                {g.s.hits} of {g.s.n} top picks right this week
                {g.s.compared ? ` · closer than the bookmakers on ${g.s.closer} of ${g.s.compared}` : ""}
                {g.version ? <span className="block truncate font-mono text-[10px] text-[var(--oasis-text-dim)]">model {g.version}</span> : <span className="block font-mono text-[10px] text-[var(--oasis-text-dim)]">a coin would score about 33%</span>}
              </span>
              <span className="text-[10.5px] text-[var(--oasis-text-muted)] sm:hidden">{g.s.hits} of {g.s.n} right</span>
            </div>
          );
        })}
      </div>
      {groups.length > 1 && (
        <>
          <div className="flex items-center justify-center gap-[5px] pb-[8px]">
            {groups.map((g, i) => (
              <button
                key={g.key}
                type="button"
                aria-label={`Show ${g.label}`}
                onClick={() => go(i)}
                className="h-[5px] rounded-full transition-all"
                style={{ width: i === idx ? 14 : 5, background: i === idx ? "var(--oasis-home)" : "var(--oasis-border-strong)" }}
              />
            ))}
          </div>
          <button type="button" aria-label="Previous league" onClick={() => go(idx - 1)} className="absolute left-1 top-1/2 hidden h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full border border-[var(--oasis-border-strong)] bg-[var(--oasis-surface)] text-[var(--oasis-text-muted)] opacity-0 transition-opacity group-hover:opacity-100 sm:flex">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 3L5 8l5 5" /></svg>
          </button>
          <button type="button" aria-label="Next league" onClick={() => go(idx + 1)} className="absolute right-1 top-1/2 hidden h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full border border-[var(--oasis-border-strong)] bg-[var(--oasis-surface)] text-[var(--oasis-text-muted)] opacity-0 transition-opacity group-hover:opacity-100 sm:flex">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3l5 5-5 5" /></svg>
          </button>
        </>
      )}
    </div>
  );
}

export function ResultsHero({ rows, bookmakerCount, versions }: { rows: RecentResult[]; bookmakerCount: number; versions: Record<string, string> }) {
  const s = resultsSummary(rows);
  const d = drawNote(s);
  const tiles = [
    {
      k: "BEAT THE BOOKMAKERS",
      v: s.compared ? `${s.closer} of ${s.compared}` : "—",
      sub: s.compared && s.ll != null && s.mll != null
        ? `results where we gave the real outcome more chance than ${bookmakerCount || "the"} bookmakers did · forecast error ${s.ll.toFixed(3)} v ${s.mll.toFixed(3)}, lower is better`
        : "needs odds at lock time",
      color: s.compared ? (s.closer * 2 >= s.compared ? "var(--oasis-positive)" : "var(--oasis-warn)") : undefined,
    },
    { k: "DRAWS THIS WEEK", v: d.v, sub: d.sub, color: d.tone },
  ];
  return (
    <div className="flex flex-col gap-[10px]">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">SCORED AGAINST THE BOOKMAKERS</span>
        <span className="text-[13px] font-semibold text-[var(--oasis-text-soft)] sm:text-[14px]">
          Every forecast is locked before kickoff, then scored on what actually happened.
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:gap-[10px]">
        <AccuracyCards rows={rows} versions={versions} />
        {tiles.map((t, i) => (
          <div
            key={t.k}
            className="rs-rise flex min-w-0 flex-col gap-[3px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[10px] sm:p-[12px] sm:px-[13px]"
            style={{ animationDelay: `${(i + 1) * 120}ms` }}
          >
            <span className="font-mono text-[9px] font-semibold leading-[1.3] tracking-[0.08em] text-[var(--oasis-text-dim)] sm:text-[10px] sm:tracking-[0.1em]">{t.k}</span>
            <span className="whitespace-nowrap font-mono text-[17px] font-bold leading-[1.1] sm:text-[21px]" style={{ color: t.color }}>{t.v}</span>
            <span className="hidden text-[11.5px] font-medium leading-[1.45] text-[var(--oasis-text-muted)] sm:block">{t.sub}</span>
          </div>
        ))}
      </div>
      <p className="m-0 text-[11.5px] font-medium leading-[1.5] text-[var(--oasis-text-muted)] sm:hidden">{d.sub}.</p>
    </div>
  );
}

export function SignInStrip({ tier }: { tier: Tier }) {
  /** Anonymous visitors have no day tabs at all (the upcoming board is
   * hidden for them), so they need telling both what they are looking at
   * and that an upcoming board exists. Free viewers can already see the
   * tabs, so for them this is only a nudge toward the rest. */
  const anon = tier === "anon";
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-3 rounded-[9px] border bg-[var(--oasis-surface)] p-3 sm:flex-row sm:items-center sm:gap-4 sm:px-[14px]",
        anon ? "border-[var(--oasis-home)]" : "border-[var(--oasis-border)]",
      )}
    >
      {anon && (
        <span className="whitespace-nowrap rounded-full border border-[var(--oasis-home)] bg-[var(--oasis-home-tint)] px-[9px] py-[3px] font-mono text-[10px] font-bold tracking-[0.06em] text-[var(--oasis-home)]">
          PAST RESULTS
        </span>
      )}
      <div className="flex-1 text-[12.5px] leading-[1.6] text-[var(--oasis-text-muted)]">
        {anon ? (
          <>
            <span className="font-bold text-[var(--oasis-text)]">
              You&rsquo;re looking at matches that have already been played
            </span>{" "}
            — predictions locked before kickoff, then scored against the result. Predictions for{" "}
            <span className="font-bold text-[var(--oasis-text)]">upcoming</span> matches need an account: a free one
            unlocks the {TASTER_PER_DAY} highest-confidence forecasts every day.
          </>
        ) : (
          <>
            <span className="font-bold text-[var(--oasis-text)]">Upcoming matches are under Today, Tomorrow and Week.</span>{" "}
            Lifetime access unlocks every upcoming forecast.
          </>
        )}
      </div>
      <UnlockCta tier={tier} />
    </div>
  );
}

function Verdict({ r, compact = false, delayMs = 0 }: { r: RecentResult; compact?: boolean; delayMs?: number }) {
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
  if (compact) return <>{nums}<span className="rs-pop rs-chip" style={{ animationDelay: `${delayMs + 700}ms` }}>{chip}</span></>;
  return (
    <span className="flex flex-col items-end gap-[6px]">
      <span className="rs-rise" style={{ animationDelay: `${delayMs + 500}ms` }}>{nums}</span>
      <span className="rs-pop rs-chip" style={{ animationDelay: `${delayMs + 700}ms` }}>{chip}</span>
    </span>
  );
}

const PICK_LABEL = ["home win", "draw", "away win"];

/** Hit or miss on the top pick, in words: "[check] picked home win". */
function PickMark({ r, align = "end" }: { r: RecentResult; align?: "end" | "start" }) {
  const l = r.locked!;
  if (l.correct === null) return null;
  const pick = [l.h, l.d, l.a].indexOf(Math.max(l.h, l.d, l.a));
  const ok = l.correct === true;
  return (
    <span
      className={`flex items-center gap-[5px] whitespace-nowrap font-mono text-[10.5px] font-bold tracking-[0.04em] ${align === "end" ? "justify-end" : ""}`}
      style={{ color: ok ? "var(--oasis-positive)" : "var(--oasis-away)" }}
      title={ok ? "our top pick was right" : "our top pick was wrong"}
    >
      <span
        className="flex h-[15px] w-[15px] items-center justify-center rounded-full text-[10px] leading-none"
        style={{ background: ok ? "var(--oasis-positive)" : "var(--oasis-away)", color: ok ? "var(--oasis-home-ink)" : "#1a1206" }}
      >
        {ok ? <IconCheck size={10} strokeWidth={2.6} /> : <IconCross size={9} strokeWidth={2.6} />}
      </span>
      {ok ? "picked" : "picked"} {PICK_LABEL[pick]}
    </span>
  );
}

function Meta({ r }: { r: RecentResult }) {
  const o = r.locked?.outcome;
  return (
    <span className="whitespace-nowrap font-mono text-[10.5px] font-medium text-[var(--oasis-text-muted)] sm:text-[11.5px]">
      {r.ko} UTC
      {o != null && (
        <>
          {" · "}
          <span className="font-bold" style={{ color: OUTCOME_COLOR[o] }}>{OUTCOME_LABEL[o]}</span>
        </>
      )}
    </span>
  );
}

export function ResultsList({ rows, filter }: { rows: RecentResult[]; filter: ResultsFilter }) {
  // Newest day first; inside a day, leagues in the site's fixed order, then
  // latest kickoff first. Rows are grouped under a day header and a league
  // sub-header so a Saturday with five leagues reads as five short lists.
  const leagueRank = (lg: string) => LEAGUE_CODES.indexOf(lg as (typeof LEAGUE_CODES)[number]);
  const shown = rows
    .filter((r) => {
      const l = r.locked!;
      if (filter === "closer") return l.closer === true;
      if (filter === "market") return l.closer === false;
      if (filter === "hit") return l.correct === true;
      return true;
    })
    .sort((a, b) =>
      b.kickoffUtc.slice(0, 10).localeCompare(a.kickoffUtc.slice(0, 10)) ||
      leagueRank(a.lg) - leagueRank(b.lg) ||
      b.kickoffUtc.localeCompare(a.kickoffUtc),
    );
  const dayCount: Record<string, number> = {};
  const groupCount: Record<string, number> = {};
  for (const r of shown) {
    const day = r.kickoffUtc.slice(0, 10);
    dayCount[day] = (dayCount[day] ?? 0) + 1;
    groupCount[`${day}|${r.lg}`] = (groupCount[`${day}|${r.lg}`] ?? 0) + 1;
  }

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
        <span className="hidden w-[128px] text-right md:block">FINAL · OUR PICK</span>
        <span className="hidden w-[170px] text-right md:block">ON THE RESULT</span>
      </div>

      {shown.map((r, i) => {
        const l = r.locked!;
        const day = r.kickoffUtc.slice(0, 10);
        const showDay = i === 0 || shown[i - 1].kickoffUtc.slice(0, 10) !== day;
        const showLeague = showDay || shown[i - 1].lg !== r.lg;
        const market = l.mh != null && l.md != null && l.ma != null ? ([l.mh, l.md, l.ma] as [number, number, number]) : null;
        return (
          <div key={r.id}>
            {showDay && (
              <div className="pb-[2px] pt-4 font-mono text-[12px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)] sm:text-[12.5px]">
                {utcDayLabel(r.kickoffUtc).toUpperCase()} · <span className="text-[var(--oasis-text-muted)]">{dayCount[day]} {dayCount[day] === 1 ? "result" : "results"}</span>
              </div>
            )}
            {showLeague && (
              <div className="flex items-center gap-2 pb-[2px] pt-[10px]">
                <span className="text-[12.5px] font-bold tracking-[-0.01em] text-[var(--oasis-text-soft)]">{LEAGUE_NAMES[r.lg]}</span>
                <span className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">{groupCount[`${day}|${r.lg}`]}</span>
                <span className="h-px flex-1 bg-[var(--oasis-border)]" />
              </div>
            )}
            {/* Desktop row */}
            <div className="rs-row hidden items-center border-b border-[var(--oasis-border-row)] px-1 py-[14px] md:flex">
              <span className="flex min-w-0 flex-1 items-center gap-[14px] pr-[18px]">
                <TeamSide id={r.homeId} name={r.home} side="home" size={24} className="w-[160px] text-[15px] font-bold tracking-[-0.01em]" />
                <span className="flex min-w-0 flex-1 flex-col items-center gap-[5px]">
                  <TwinBar model={[l.h, l.d, l.a]} market={market} outcome={l.outcome ?? null} delayMs={Math.min(i, 24) * 90} className="w-full" />
                  <Meta r={r} />
                </span>
                <TeamSide id={r.awayId} name={r.away} side="away" size={24} className="w-[160px] text-[15px] font-bold tracking-[-0.01em]" />
              </span>
              <span className="flex w-[128px] flex-col items-end gap-[4px]">
                <span className="font-mono text-[16.5px] font-bold leading-none">{r.score}</span>
                <PickMark r={r} />
              </span>
              <span className="flex w-[170px] justify-end"><Verdict r={r} delayMs={Math.min(i, 24) * 90} /></span>
            </div>
            {/* Phone row */}
            <div className="rs-row flex flex-col gap-2 border-b border-[var(--oasis-border-row)] py-3 md:hidden">
              <span className="flex items-center justify-between gap-[10px]">
                <TeamSide id={r.homeId} name={r.home} side="away" size={20} className="min-w-0 flex-1 text-[14px] font-bold tracking-[-0.01em]" />
                <span className="shrink-0 font-mono text-[15px] font-bold">{r.score}</span>
                <TeamSide id={r.awayId} name={r.away} side="home" size={20} className="min-w-0 flex-1 justify-end text-[14px] font-bold tracking-[-0.01em]" />
              </span>
              <TwinBar model={[l.h, l.d, l.a]} market={market} outcome={l.outcome ?? null} height={22} line={6} delayMs={Math.min(i, 24) * 90} className="w-full" />
              <span className="flex items-center justify-between gap-2"><Meta r={r} /><PickMark r={r} /></span>
              <span className="flex items-center justify-between gap-2"><Verdict r={r} compact delayMs={Math.min(i, 24) * 90} /></span>
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
