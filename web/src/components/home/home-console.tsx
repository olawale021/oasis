"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { LockedBar, ProbabilityBar, ProbabilityLegend } from "@/components/probability-bar";
import { UnlockCta } from "@/components/unlock-cta";
import type { Tier } from "@/lib/viewer";
import { LEAGUE_CODES, LEAGUE_NAMES, utcClock, utcDayLabel } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import { deriveMatch, sortByKickoff } from "@/lib/derive";
import type { DerivedMatch, LeagueFilter } from "@/lib/types";
import { TeamSide } from "@/components/team-logo";
import { HowToReadCard, LiveRecordCard, MarketCard, ResultsHero, ResultsList, SignInStrip, type ResultsFilter } from "@/components/home/results-view";
import { NextKickoff } from "@/components/home/next-kickoff";

const DAY_TABS = ["Today", "Tomorrow", "Week", "Results"] as const;
const TASTER_PER_DAY = 2;
const RESULT_FILTERS: { key: ResultsFilter; label: string }[] = [
  { key: "all", label: "All results" },
  { key: "closer", label: "Closer than market" },
  { key: "market", label: "Market closer" },
  { key: "hit", label: "Top pick correct" },
];
type DayTab = (typeof DAY_TABS)[number];

function utcDayStamp(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function HomeConsole({ live, tier }: { live: LiveData; tier: Tier }) {
  const premium = tier === "premium";
  const [league, setLeague] = useState<LeagueFilter>("ALL");
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [highConfOnly, setHighConfOnly] = useState(false);
  const [edgeOnly, setEdgeOnly] = useState(false);
  const [showEdgeInfo, setShowEdgeInfo] = useState(false);
  // Signed-out visitors land on settled predictions (the public track
  // record); signed-in viewers land on the upcoming board. Neither default
  // depends on the clock, so SSR and hydration agree; Today/Tomorrow filter
  // on click.
  const [dayTab, setDayTab] = useState<DayTab>(tier === "anon" ? "Results" : "Week");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [resultFilter, setResultFilter] = useState<ResultsFilter>("all");
  const isResults = dayTab === "Results";

  const derived = useMemo(() => sortByKickoff(live.matches.map(deriveMatch)), []);

  const rows = useMemo(() => {
    let out = derived.filter(
      (m) =>
        (league === "ALL" || m.lg === league) &&
        (!confirmedOnly || m.statusConfirmed) &&
        (!highConfOnly || m.conf === "HIGH") &&
        (!edgeOnly || m.hot),
    );
    if (dayTab !== "Week") {
      const target = new Date();
      if (dayTab === "Tomorrow") target.setUTCDate(target.getUTCDate() + 1);
      const stamp = utcDayStamp(target);
      out = out.filter((m) => m.kickoffUtc.slice(0, 10) === stamp);
    }
    // Day, then league in the site's fixed order, then kickoff: the board
    // reads as short per-league lists under each day, like Results.
    const rank = (lg: string) => LEAGUE_CODES.indexOf(lg as (typeof LEAGUE_CODES)[number]);
    return [...out].sort(
      (a, b) =>
        a.kickoffUtc.slice(0, 10).localeCompare(b.kickoffUtc.slice(0, 10)) ||
        rank(a.lg) - rank(b.lg) ||
        a.kickoffUtc.localeCompare(b.kickoffUtc),
    );
  }, [derived, league, confirmedOnly, highConfOnly, edgeOnly, dayTab]);

  const leagueCounts = useMemo(() => {
    const counts: Record<LeagueFilter, number> = { ALL: 0, EPL: 0, LAL: 0, SEA: 0, BUN: 0, MLS: 0 };
    if (isResults) {
      for (const r of live.recent_results) if (r.locked) { counts.ALL += 1; counts[r.lg] += 1; }
    } else {
      counts.ALL = derived.length;
      for (const m of derived) counts[m.lg] += 1;
    }
    return counts;
  }, [derived, isResults, live.recent_results]);

  // Public record = predictions locked before kickoff only. Retrospective
  // reconstructions for matches played before lock automation ran are
  // still in the payload for the ledger, but never shown as results here.
  const resultRows = useMemo(
    () => live.recent_results.filter((r) => r.locked !== null && (league === "ALL" || r.lg === league)),
    [league, live.recent_results],
  );

  const resultCounts = useMemo(() => {
    const c = { all: 0, closer: 0, market: 0, hit: 0 };
    for (const r of live.recent_results) {
      const l = r.locked;
      if (!l) continue;
      c.all += 1;
      if (l.closer === true) c.closer += 1;
      if (l.closer === false) c.market += 1;
      if (l.correct === true) c.hit += 1;
    }
    return c;
  }, [live.recent_results]);

  const heading = useMemo(() => {
    if (dayTab === "Results") return "Results";
    if (rows.length === 0) return dayTab === "Week" ? "Upcoming fixtures" : dayTab;
    const first = utcDayLabel(rows[0].kickoffUtc);
    const last = utcDayLabel(rows[rows.length - 1].kickoffUtc);
    return first === last ? first : `${first} – ${last}`;
  }, [rows, dayTab]);

  return (
    <div className="grid w-full grid-cols-1 lg:h-full lg:grid-cols-[212px_1fr_268px] lg:overflow-hidden">
      {/* Left rail */}
      <div className="flex min-w-0 flex-col gap-[14px] border-b border-[var(--oasis-border)] bg-[var(--oasis-bg-rail)] px-3 py-2 lg:min-h-0 lg:gap-[22px] lg:overflow-y-auto lg:border-b-0 lg:border-r lg:p-4">
        <div className="flex flex-col gap-2">
          <div className="hidden font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)] lg:block">
            LEAGUES
          </div>
          <div className="rs-noscroll flex gap-[6px] overflow-x-auto lg:flex-col lg:gap-2 lg:overflow-visible">
            {(["ALL", ...LEAGUE_CODES] as LeagueFilter[]).map((code) => {
              const active = league === code;
              return (
                <button
                  key={code}
                  type="button"
                  onClick={() => {
                    setLeague(code);
                    setExpanded(null);
                  }}
                  className="flex flex-none items-center gap-[7px] whitespace-nowrap rounded-full border px-[11px] py-[6px] text-left text-[12.5px] font-semibold transition-colors lg:justify-between lg:gap-0 lg:rounded-[7px] lg:border-transparent lg:px-[9px] lg:py-[7px] lg:text-[14px]"
                  style={{
                    color: active ? "var(--oasis-text)" : "var(--oasis-text-muted)",
                    background: active ? "var(--oasis-surface-raised)" : "transparent",
                    borderColor: active ? "var(--oasis-border-strong)" : "var(--oasis-border)",
                  }}
                >
                  <span>{LEAGUE_NAMES[code]}</span>
                  <span className="font-mono text-[11px] font-medium text-[var(--oasis-text-dim)]">
                    {leagueCounts[code]}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="lg:hidden"><NextKickoff matches={live.matches} compact /></div>

        {isResults && (
          <div className="hidden flex-col gap-[9px] lg:flex">
            <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">SHOW</div>
            <div className="flex flex-wrap gap-2 lg:flex-col lg:gap-[9px]">
              {RESULT_FILTERS.map((f) => {
                const active = resultFilter === f.key;
                return (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => setResultFilter(f.key)}
                    className="rs-tab cursor-pointer rounded-[7px] px-[10px] py-[6px] text-left text-[11.5px] font-semibold lg:py-[7px] lg:text-[12px]"
                    style={
                      active
                        ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                        : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
                    }
                  >
                    {f.label} · {resultCounts[f.key]}
                  </button>
                );
              })}
            </div>
          </div>
        )}
        {!isResults && (
        <div className="hidden flex-col gap-[9px] lg:flex">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            FILTERS
          </div>
          <div className="flex flex-wrap gap-2 lg:flex-col lg:gap-[9px]">
          <button
            type="button"
            onClick={() => setConfirmedOnly((v) => !v)}
            className="cursor-pointer rounded-[7px] px-[10px] py-[6px] text-left text-[11.5px] font-semibold lg:py-[7px] lg:text-[12px]"
            style={
              confirmedOnly
                ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
            }
          >
            {confirmedOnly ? "Lineups confirmed ✓" : "Lineups confirmed"}
          </button>
          <button
            type="button"
            disabled={!premium}
            title={premium ? undefined : "Confidence filters are part of lifetime access"}
            onClick={() => setHighConfOnly((v) => !v)}
            className="cursor-pointer rounded-[7px] px-[10px] py-[6px] text-left text-[11.5px] font-semibold lg:py-[7px] lg:text-[12px]"
            style={
              highConfOnly
                ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
            }
          >
            {highConfOnly ? "High confidence ✓" : premium ? "High confidence" : "High confidence 🔒"}
          </button>
          {premium && derived.some((m) => m.edge !== null) ? (
            <button
              type="button"
              onClick={() => setEdgeOnly((v) => !v)}
              className="cursor-pointer rounded-[7px] px-[10px] py-[6px] text-left text-[11.5px] font-semibold lg:py-[7px] lg:text-[12px]"
              style={
                edgeOnly
                  ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                  : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
              }
            >
              {edgeOnly ? "Edge ≥ 3% ✓" : "Edge ≥ 3%"}
            </button>
          ) : (
            <div
              className="rounded-[7px] border border-dashed border-[var(--oasis-border)] px-[10px] py-[6px] text-[11.5px] font-semibold text-[var(--oasis-text-dim)] lg:py-[7px] lg:text-[12px]"
              title={premium ? "No odds snapshots archived yet for these fixtures" : "Edge filter is part of lifetime access"}
            >
              {premium ? "Edge ≥ 3% — needs odds" : "Edge ≥ 3% 🔒"}
            </div>
          )}
          </div>
        </div>
        )}

        <div className="hidden rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[11px] lg:block">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            DATA FRESHNESS (UTC)
          </div>
          <div className="mt-1 flex flex-wrap gap-x-[14px] font-mono text-[11px] font-medium leading-[1.6] text-[var(--oasis-text-muted)] lg:flex-col lg:gap-0 lg:text-[11.5px]">
            <span>fixtures {utcClock(live.freshness.fixtures)}</span>
            <span>injuries {utcClock(live.freshness.injuries)}</span>
            <span>lineups {utcClock(live.freshness.lineups)}</span>
            <span>odds {utcClock(live.freshness.odds)}</span>
          </div>
        </div>
      </div>

      {/* Centre column: the only thing that scrolls on desktop */}
      <div className="flex min-w-0 flex-col gap-[14px] p-3 sm:p-[18px] sm:px-5 lg:min-h-0 lg:overflow-y-auto">
        {isResults && <ResultsHero rows={resultRows} bookmakerCount={live.bookmakers?.length ?? 0} versions={live.model_versions} />}
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
          <span className="text-[19px] font-extrabold leading-none tracking-[-0.02em] sm:text-[22px]">{heading}</span>
          <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)] sm:text-[12.5px]">
            {LEAGUE_NAMES[league]} ·{" "}
            {dayTab === "Results"
              ? `${resultRows.length} settled · last 7 days`
              : `${rows.length} ${rows.length === 1 ? "match" : "matches"}`}
          </span>
          {tier !== "anon" && (
          <span className="ml-auto flex flex-wrap gap-[6px] text-[11.5px] font-semibold">
            {DAY_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setDayTab(tab)}
                className="rs-tab cursor-pointer rounded-[6px] px-[10px] py-[5px]"
                style={
                  tab === dayTab
                    ? { background: "var(--oasis-surface-raised)", border: "1px solid var(--oasis-border-strong)" }
                    : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
                }
              >
                {tab}
              </button>
            ))}
          </span>
          )}
        </div>

        {/* Phone: the rail filters live here as a scrolling chip row */}
        <div className="rs-noscroll -mx-3 flex gap-[6px] overflow-x-auto px-3 lg:hidden">
          {isResults
            ? RESULT_FILTERS.map((f) => {
                const active = resultFilter === f.key;
                return (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => setResultFilter(f.key)}
                    className="rs-tab flex-none whitespace-nowrap rounded-full px-[11px] py-[6px] text-[11.5px] font-semibold"
                    style={
                      active
                        ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                        : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
                    }
                  >
                    {f.label} · {resultCounts[f.key]}
                  </button>
                );
              })
            : (
              <>
                <button
                  type="button"
                  onClick={() => setConfirmedOnly((v) => !v)}
                  className="rs-tab flex-none whitespace-nowrap rounded-full px-[11px] py-[6px] text-[11.5px] font-semibold"
                  style={
                    confirmedOnly
                      ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                      : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
                  }
                >
                  {confirmedOnly ? "Lineups confirmed ✓" : "Lineups confirmed"}
                </button>
                <button
                  type="button"
                  disabled={!premium}
                  onClick={() => setHighConfOnly((v) => !v)}
                  className="rs-tab flex-none whitespace-nowrap rounded-full px-[11px] py-[6px] text-[11.5px] font-semibold"
                  style={
                    highConfOnly
                      ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                      : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
                  }
                >
                  {highConfOnly ? "High confidence ✓" : premium ? "High confidence" : "High confidence 🔒"}
                </button>
              </>
            )}
        </div>
        {isResults && tier !== "premium" && <SignInStrip tier={tier} />}
        {isResults && <ResultsList rows={resultRows} filter={resultFilter} />}

        {dayTab !== "Results" && (<>
        <div className="flex items-center border-b border-[var(--oasis-border)] px-1 pb-[9px] font-mono text-[10px] font-semibold tracking-[0.09em] text-[var(--oasis-text-dim)] sm:text-[10.5px]">
          <span className="flex flex-1 items-center gap-[14px] md:pr-[18px]">
            <span className="hidden text-right md:block md:w-[160px]">HOME</span>
            <span className="flex flex-1 items-center gap-[14px] md:justify-center">
              <span className="hidden md:inline">WIN PROBABILITY</span>
              <ProbabilityLegend />
            </span>
            <span className="hidden md:block md:w-[160px]">AWAY</span>
          </span>
          <span className="hidden w-[100px] text-right md:block">LIKELY SCORE</span>
          <span className="relative flex w-[70px] items-center justify-end gap-[5px]">
            EDGE
            <button
              type="button"
              aria-label="What does edge mean?"
              aria-expanded={showEdgeInfo}
              onClick={() => setShowEdgeInfo((v) => !v)}
              className="flex h-[15px] w-[15px] cursor-pointer items-center justify-center rounded-full border text-[9.5px] font-bold normal-case leading-none tracking-normal"
              style={{
                borderColor: showEdgeInfo ? "var(--oasis-home)" : "var(--oasis-border-strong)",
                color: showEdgeInfo ? "var(--oasis-home)" : "var(--oasis-text-muted)",
                background: showEdgeInfo ? "var(--oasis-home-tint)" : "transparent",
              }}
            >
              i
            </button>
            {showEdgeInfo && <EdgeInfoPopover matches={derived} onClose={() => setShowEdgeInfo(false)} />}
          </span>
        </div>

        {rows.map((m, idx) => {
          const isOpen = expanded === m.id;
          const day = m.kickoffUtc.slice(0, 10);
          const newDay = idx === 0 || rows[idx - 1].kickoffUtc.slice(0, 10) !== day;
          const showDay = dayTab === "Week" && newDay;
          const showLeague = newDay || rows[idx - 1].lg !== m.lg;
          const groupN = rows.filter((r) => r.kickoffUtc.slice(0, 10) === day && r.lg === m.lg).length;
          return (
            <div key={m.id}>
              {showDay && (
                <div className="pb-[2px] pt-3 font-mono text-[12.5px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)]">
                  {utcDayLabel(m.kickoffUtc).toUpperCase()}
                </div>
              )}
              {showLeague && (
                <div className="flex items-center gap-2 pb-[2px] pt-[10px]">
                  <span className="text-[12.5px] font-bold tracking-[-0.01em] text-[var(--oasis-text-soft)]">{LEAGUE_NAMES[m.lg]}</span>
                  <span className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">{groupN}</span>
                  <span className="h-px flex-1 bg-[var(--oasis-border)]" />
                </div>
              )}
              <div className="rs-row cursor-pointer border-b border-[var(--oasis-border-row)]">
                <button
                  type="button"
                  onClick={() => setExpanded(isOpen ? null : m.id)}
                  className="flex w-full flex-col gap-[10px] px-1 py-3 text-left md:flex-row md:items-center md:gap-0 md:py-[14px]"
                >
                  <span className="flex w-full min-w-0 items-center gap-[10px] md:w-auto md:flex-1 md:gap-[14px] md:pr-[18px]">
                    <TeamSide
                      id={m.homeId} name={m.home} side="home" size={24}
                      className="w-[29%] text-[13px] font-bold tracking-[-0.01em] md:w-[160px] md:text-[15px]"
                    />
                    <span className="flex min-w-0 flex-1 flex-col gap-[4px]">
                      {m.gated ? (
                        <LockedBar height={26} className="w-full" label={tier === "anon" ? "sign in to unlock" : "lifetime access"} delayMs={Math.min(idx, 24) * 70} />
                      ) : (
                        <ProbabilityBar home={m.h} draw={m.d} away={m.a} height={26} labeled className="w-full" delayMs={Math.min(idx, 24) * 90} />
                      )}
                      <span
                        className="w-full text-center font-mono text-[10.5px] font-medium leading-[1.35] md:text-[11.5px]"
                        style={{ color: m.statusConfirmed ? "var(--oasis-positive)" : "var(--oasis-text-muted)" }}
                      >
                        {m.ko} UTC{m.statusConfirmed ? " · lineups confirmed" : ""}
                      </span>
                    </span>
                    <TeamSide
                      id={m.awayId} name={m.away} side="away" size={24}
                      className="w-[29%] text-[13px] font-bold tracking-[-0.01em] md:w-[160px] md:text-[15px]"
                    />
                  </span>
                  <span className="flex w-full items-center justify-between md:contents">
                    <span
                      className="rs-rise flex flex-col md:w-[100px] md:items-end"
                      style={{ animationDelay: `${Math.min(idx, 24) * 90 + 400}ms` }}
                      title={m.gated ? "locked" : `most likely ${m.pick === "draw" ? "scoreline" : `${m.pick}-win scoreline`} (overall mode ${m.score}, ${m.matrix.peakPct}%)`}
                    >
                      <span className="font-mono text-[14px] font-medium md:text-[15.5px]">{m.gated ? "—" : m.condScore}</span>
                      <span className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)] md:text-[11.5px]">
                        {m.gated ? "locked" : `${Math.round(m.condPct)}% chance`}
                      </span>
                    </span>
                    <span
                      className="flex flex-col items-end md:w-[70px]"
                      title={
                        m.edge === null
                          ? "no odds collected yet"
                          : "model home-win probability minus market consensus (margin removed)"
                      }
                    >
                      <span className="font-mono text-[9.5px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)] md:hidden">
                        EDGE
                      </span>
                      <span
                        className="font-mono text-[12px] md:text-[12.5px]"
                        style={{
                          color: m.hot ? "var(--oasis-positive)" : "var(--oasis-text-dim)",
                          fontWeight: m.hot ? 700 : 500,
                        }}
                      >
                        {m.edgeLabel}
                      </span>
                    </span>
                  </span>
                </button>

                {isOpen && m.gated && (
                  <div className="mx-1 mb-[14px] flex flex-col items-start gap-3 rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 sm:flex-row sm:items-center">
                    <div className="flex-1">
                      <div className="text-[13.5px] font-bold">This prediction is locked</div>
                      <div className="mt-[3px] text-[12.5px] leading-[1.6] text-[var(--oasis-text-muted)]">
                        {tier === "anon"
                          ? `A free account shows the ${TASTER_PER_DAY} highest-confidence predictions each day. Lifetime access shows every match.`
                          : "Lifetime access shows every upcoming match, with likely scores, factors and market comparison."}
                        {" "}Finished matches are always public under Results.
                      </div>
                    </div>
                    <UnlockCta tier={tier} />
                  </div>
                )}
                {isOpen && !m.gated && (
                  <div className="mx-1 mb-[14px] flex flex-col gap-4 rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-3 sm:flex-row sm:items-start sm:gap-6">
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
                        WHY THIS FORECAST
                      </div>
                      <div className="mt-[6px] text-[13.5px] font-medium leading-[1.7] text-[var(--oasis-text-soft)]">
                        {m.why}
                      </div>
                      <Link href={`/match/${m.id}`} className="mt-3 inline-block font-mono text-[12.5px] font-bold text-[var(--oasis-home)]">
                        Open full match page →
                      </Link>
                    </div>
                    <div className="flex shrink-0 flex-col gap-[6px] font-mono text-[12.5px] font-medium sm:w-[320px] sm:border-l sm:border-[var(--oasis-border)] sm:pl-6">
                      <div className="flex justify-between gap-4">
                        <span className="text-[var(--oasis-text-muted)]">confidence</span>
                        <span>{m.conf}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-[var(--oasis-text-muted)]">
                          likely score{m.pick !== "draw" ? ` (${m.pick} win)` : ""}
                        </span>
                        <span className="whitespace-nowrap">
                          {m.condScore} · {Math.round(m.condPct)}%
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-[var(--oasis-text-muted)]">most likely overall</span>
                        <span className="whitespace-nowrap text-[var(--oasis-text-muted)]">
                          {m.score} · {Math.round(m.matrix.peakPct)}%
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-[var(--oasis-text-muted)]">market (no vig)</span>
                        <span className="text-[var(--oasis-text-muted)]">{m.marketLabel ?? "no odds yet"}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {rows.length === 0 && (
          <div className="rounded-[9px] border border-dashed border-[var(--oasis-border-strong)] p-[22px] text-center text-[13px] font-semibold text-[var(--oasis-text-muted)]">
            No fixtures match these filters {dayTab === "Week" ? "in the current horizon" : dayTab.toLowerCase()}.
          </div>
        )}
        </>)}

        <div
          className="rs-shift flex flex-col items-start gap-3 rounded-[10px] p-4 sm:flex-row sm:items-center sm:gap-4 sm:p-[15px] sm:px-[17px]"
          style={{
            border: "1px solid var(--oasis-border-strong)",
            background: "linear-gradient(120deg,rgba(77,156,246,.14),rgba(47,207,154,.05),rgba(77,156,246,.14))",
          }}
        >
          <div className="flex-1">
            <div className="text-[13.5px] font-bold sm:text-[14.5px]">Founding-member lifetime access</div>
            <div className="mt-[3px] font-mono text-[11px] font-medium text-[var(--oasis-text-muted)] sm:text-[11.5px]">
              one-time purchase · quantity capped · opens at paid launch
            </div>
          </div>
          {premium ? (
            <span className="font-mono text-[11.5px] font-bold text-[var(--oasis-positive)]">you&rsquo;re in ✓</span>
          ) : (
            <UnlockCta tier={tier} />
          )}
        </div>
      </div>

      {/* Right rail */}
      <div className="flex min-w-0 flex-col gap-[14px] border-t border-[var(--oasis-border)] bg-[var(--oasis-bg-rail)] p-4 lg:min-h-0 lg:overflow-y-auto lg:border-t-0 lg:border-l">
        <div className="hidden lg:block"><NextKickoff matches={live.matches} /></div>
        {isResults && <HowToReadCard />}
        <MarketCard bookmakers={live.bookmakers ?? []} />
        {/* The live record is the honest track record, so it shows on every
            tab once anything has settled — not just Results, where it used to
            hide behind the day filter and left the backtest card looking like
            the only record we had. */}
        {live.live_record.settled > 0 && <LiveRecordCard live={live} />}
        <div className="flex flex-col gap-[9px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px]">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            2025/26 BACKTEST · {live.headline.n_test} MATCHES
          </div>
          <div className="flex justify-between font-mono text-[12.5px] font-medium">
            <span className="text-[var(--oasis-text-muted)]">log loss</span>
            <span>{live.headline.log_loss.toFixed(3)}</span>
          </div>
          <div className="flex justify-between font-mono text-[12.5px] font-medium">
            <span className="text-[var(--oasis-text-muted)]">accuracy</span>
            <span>{live.headline.accuracy.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between font-mono text-[12.5px] font-medium">
            <span className="text-[var(--oasis-text-muted)]">calibration (ECE)</span>
            <span>{live.headline.ece.toFixed(3)}</span>
          </div>
          <div className="flex justify-between font-mono text-[12.5px] font-medium">
            <span className="text-[var(--oasis-text-muted)]">vs market (live)</span>
            {live.live_record.market_log_loss != null && live.live_record.model_log_loss_on_market != null ? (
              <span
                title={`${live.live_record.market_n} settled locked predictions: model log loss vs bookmaker consensus at lock time`}
                style={{ color: live.live_record.model_log_loss_on_market < live.live_record.market_log_loss ? "var(--oasis-positive)" : "var(--oasis-warn)" }}
              >
                {live.live_record.model_log_loss_on_market.toFixed(3)} v {live.live_record.market_log_loss.toFixed(3)}
              </span>
            ) : (
              <span title="fills in once locked predictions settle; the backtest season has no archived odds">—</span>
            )}
          </div>
          <div className="mt-[2px] flex h-[44px] items-end gap-[3px]" title="observed win rate by predicted-probability band">
            {live.calibration_bars.map((h, i) => (
              <span
                key={i}
                className="flex-1 rounded-[2px]"
                style={{ height: `${Math.max(4, h)}%`, background: i === live.calibration_bars.length - 1 ? "var(--oasis-home)" : "var(--oasis-border-strong)" }}
              />
            ))}
          </div>
          <Link href="/performance" className="text-[11.5px] font-bold text-[var(--oasis-home)]">
            See full record →
          </Link>
        </div>

        {!isResults && (
        <div className="flex flex-col gap-2 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px]">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            TELEGRAM
          </div>
          <div className="text-[13px] font-semibold">Daily digest + lineup alerts</div>
          <div className="font-mono text-[11px] font-medium text-[var(--oasis-text-dim)]">
            /today · /performance · /alerts
          </div>
          <div className="rounded-[7px] border border-[var(--oasis-border-strong)] py-2 text-center text-[12px] font-bold">
            Connect account
          </div>
        </div>
        )}

        <div className="font-mono text-[10px] font-medium leading-[1.6] text-[var(--oasis-text-faint)]">
          Probabilistic forecasts, not guarantees and not betting advice. 18+ · responsible use.
          <span className="mt-1 flex gap-3">
            <Link href="/privacy" className="text-[var(--oasis-text-dim)] hover:text-[var(--oasis-text)]">Privacy</Link>
            <Link href="/terms" className="text-[var(--oasis-text-dim)] hover:text-[var(--oasis-text)]">Terms</Link>
          </span>
        </div>
      </div>
    </div>
  );
}

function EdgeInfoPopover({ matches, onClose }: { matches: DerivedMatch[]; onClose: () => void }) {
  const withEdge = matches.filter((m) => m.edge !== null);
  const positive = [...withEdge].sort((a, b) => (b.edge as number) - (a.edge as number))[0];
  const negative = [...withEdge].sort((a, b) => (a.edge as number) - (b.edge as number))[0];
  const showPositive = positive && (positive.edge as number) > 1;
  const showNegative = negative && (negative.edge as number) < -1 && negative.id !== positive?.id;

  return (
    <div
      className="fixed inset-x-3 top-[72px] z-30 max-h-[70vh] cursor-default overflow-y-auto rounded-[10px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-surface)] p-4 text-left font-sans normal-case tracking-normal shadow-[0_12px_32px_rgba(0,0,0,.5)] md:absolute md:inset-x-auto md:right-0 md:top-[24px] md:z-20 md:w-[400px]"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-baseline justify-between">
        <span className="text-[14px] font-bold text-[var(--oasis-text)]">What does &ldquo;edge&rdquo; mean?</span>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="cursor-pointer text-[13px] font-bold text-[var(--oasis-text-muted)]"
        >
          ✕
        </button>
      </div>

      <div className="mt-[10px] flex flex-col gap-[10px] text-[13px] font-medium leading-[1.7] text-[var(--oasis-text-soft)]">
        <p>For every match there are two opinions about the home team winning:</p>
        <div className="flex flex-col gap-[6px] rounded-[8px] border border-[var(--oasis-border)] p-[10px] text-[12.5px]">
          <div>
            <span className="font-bold text-[var(--oasis-text)]">1. Our model&rsquo;s number</span> — calculated from
            data: team strength, recent form, injuries, rest days.
          </div>
          <div>
            <span className="font-bold text-[var(--oasis-text)]">2. The bookmakers&rsquo; number</span> — the win
            probability hidden inside their odds (we average many bookmakers and strip out their built-in profit
            margin).
          </div>
        </div>
        <p>
          <span className="font-bold text-[var(--oasis-text)]">Edge is simply: our number minus theirs.</span> It
          answers one question — <em>where do we see this match differently from the bookmakers?</em>
        </p>

        {showPositive && (
          <div className="rounded-[8px] border border-[rgba(47,207,154,.35)] bg-[var(--oasis-positive-tint)] p-[10px]">
            <div className="text-[11px] font-bold tracking-[0.06em] text-[var(--oasis-positive)]">
              EXAMPLE — POSITIVE EDGE (green)
            </div>
            <div className="mt-[4px] text-[12.5px]">
              <span className="font-bold">{positive.home} v {positive.away}</span>: our model gives{" "}
              {positive.home} a <span className="font-bold">{Math.round(positive.h)}%</span> chance to win. The
              bookmakers only give them <span className="font-bold">{Math.round(positive.mh as number)}%</span>.
            </div>
            <div className="mt-[6px] rounded-[6px] bg-[var(--oasis-surface)] px-[8px] py-[5px] font-mono text-[11.5px]">
              {Math.round(positive.h)}% (ours) − {Math.round(positive.mh as number)}% (bookmakers) ={" "}
              <span className="font-bold text-[var(--oasis-positive)]">{positive.edgeLabel}</span>
            </div>
            <div className="mt-[5px] text-[12px] text-[var(--oasis-text-muted)]">
              We believe in {positive.home} more than the odds do. Rows turn green from +3%.
            </div>
          </div>
        )}

        {showNegative && (
          <div className="rounded-[8px] border border-[rgba(224,134,60,.35)] bg-[rgba(224,134,60,.08)] p-[10px]">
            <div className="text-[11px] font-bold tracking-[0.06em] text-[var(--oasis-away)]">
              EXAMPLE — NEGATIVE EDGE
            </div>
            <div className="mt-[4px] text-[12.5px]">
              <span className="font-bold">{negative.home} v {negative.away}</span>: our model gives{" "}
              {negative.home} <span className="font-bold">{Math.round(negative.h)}%</span>, but the bookmakers give
              them <span className="font-bold">{Math.round(negative.mh as number)}%</span>.
            </div>
            <div className="mt-[6px] rounded-[6px] bg-[var(--oasis-surface)] px-[8px] py-[5px] font-mono text-[11.5px]">
              {Math.round(negative.h)}% (ours) − {Math.round(negative.mh as number)}% (bookmakers) ={" "}
              <span className="font-bold text-[var(--oasis-away)]">{negative.edgeLabel}</span>
            </div>
            <div className="mt-[5px] text-[12px] text-[var(--oasis-text-muted)]">
              The market believes in {negative.home} more than we do — which also means we rate the draw or{" "}
              {negative.away} higher than the odds suggest.
            </div>
          </div>
        )}

        <p>
          An edge near <span className="font-mono">0%</span> means we and the bookmakers roughly agree — that&rsquo;s
          the case for most matches.
        </p>

        <div className="rounded-[8px] border border-[var(--oasis-border)] p-[10px] text-[12.5px]">
          <span className="font-bold text-[var(--oasis-text)]">Does a big edge mean &ldquo;bet on it&rdquo;? No.</span>{" "}
          Bookmakers are usually very accurate. A big gap often means our model is missing something the market knows —
          a new signing, or a newly promoted team it has little data on. Read edge as{" "}
          <em>&ldquo;here&rsquo;s where our model disagrees&rdquo;</em>, then open the match page to see why.
        </div>

        <p className="border-t border-[var(--oasis-border)] pt-[8px] font-mono text-[10.5px] leading-[1.6] text-[var(--oasis-text-dim)]">
          Odds are a benchmark only — never an input to our model. Probabilistic forecasts, not betting advice. 18+ ·
          responsible use.
        </p>
      </div>
    </div>
  );
}
