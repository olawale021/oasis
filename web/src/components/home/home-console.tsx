"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ProbabilityBar, ProbabilityLegend } from "@/components/probability-bar";
import { LEAGUE_CODES, LEAGUE_NAMES, utcClock, utcDayLabel } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import { deriveMatch, sortByKickoff } from "@/lib/derive";
import type { DerivedMatch, LeagueFilter } from "@/lib/types";
import { MatchName } from "@/components/team-logo";

const DAY_TABS = ["Today", "Tomorrow", "Week", "Results"] as const;
type DayTab = (typeof DAY_TABS)[number];

function utcDayStamp(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function HomeConsole({ live }: { live: LiveData }) {
  const [league, setLeague] = useState<LeagueFilter>("ALL");
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [highConfOnly, setHighConfOnly] = useState(false);
  const [edgeOnly, setEdgeOnly] = useState(false);
  const [showEdgeInfo, setShowEdgeInfo] = useState(false);
  // Default to the full horizon so the first render never depends on the
  // clock (avoids SSR/client hydration drift); Today/Tomorrow filter on click.
  const [dayTab, setDayTab] = useState<DayTab>("Week");
  const [expanded, setExpanded] = useState<number | null>(null);

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
    return out;
  }, [derived, league, confirmedOnly, highConfOnly, edgeOnly, dayTab]);

  const leagueCounts = useMemo(() => {
    const counts: Record<LeagueFilter, number> = { ALL: derived.length, EPL: 0, LAL: 0, SEA: 0, BUN: 0, MLS: 0 };
    for (const m of derived) counts[m.lg] += 1;
    return counts;
  }, [derived]);

  const resultRows = useMemo(
    () => live.recent_results.filter((r) => league === "ALL" || r.lg === league),
    [league, live.recent_results],
  );

  const heading = useMemo(() => {
    if (dayTab === "Results") return "Recent results";
    if (rows.length === 0) return dayTab === "Week" ? "Upcoming fixtures" : dayTab;
    const first = utcDayLabel(rows[0].kickoffUtc);
    const last = utcDayLabel(rows[rows.length - 1].kickoffUtc);
    return first === last ? first : `${first} – ${last}`;
  }, [rows, dayTab]);

  let lastDay = "";

  return (
    <div className="grid w-full grid-cols-1 lg:grid-cols-[212px_1fr_268px]">
      {/* Left rail */}
      <div className="flex flex-col gap-[14px] border-b border-[var(--oasis-border)] bg-[var(--oasis-bg-rail)] p-3 lg:gap-[22px] lg:border-b-0 lg:border-r lg:p-4">
        <div className="flex flex-col gap-2">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            LEAGUES
          </div>
          <div className="flex gap-[6px] overflow-x-auto pb-1 lg:flex-col lg:gap-2 lg:overflow-visible lg:pb-0">
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

        <div className="flex flex-col gap-[9px]">
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
            onClick={() => setHighConfOnly((v) => !v)}
            className="cursor-pointer rounded-[7px] px-[10px] py-[6px] text-left text-[11.5px] font-semibold lg:py-[7px] lg:text-[12px]"
            style={
              highConfOnly
                ? { color: "var(--oasis-positive)", background: "var(--oasis-positive-tint)", border: "1px solid rgba(47,207,154,.35)" }
                : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
            }
          >
            {highConfOnly ? "High confidence ✓" : "High confidence"}
          </button>
          {derived.some((m) => m.edge !== null) ? (
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
              title="No odds snapshots archived yet for these fixtures"
            >
              Edge ≥ 3% — needs odds
            </div>
          )}
          </div>
        </div>

        <div className="rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[11px]">
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

      {/* Centre column */}
      <div className="flex min-w-0 flex-col gap-[14px] p-3 sm:p-[18px] sm:px-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
          <span className="text-[19px] font-extrabold leading-none tracking-[-0.02em] sm:text-[22px]">{heading}</span>
          <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)] sm:text-[12.5px]">
            {LEAGUE_NAMES[league]} ·{" "}
            {dayTab === "Results"
              ? `${resultRows.length} played (last 7 days)`
              : `${rows.length} ${rows.length === 1 ? "match" : "matches"}`}
          </span>
          <span className="ml-auto flex flex-wrap gap-[6px] text-[11.5px] font-semibold">
            {DAY_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setDayTab(tab)}
                className="cursor-pointer rounded-[6px] px-[10px] py-[5px]"
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
        </div>

        {dayTab === "Results" && <ResultsList rows={resultRows} />}

        {dayTab !== "Results" && (<>
        <div className="flex items-center border-b border-[var(--oasis-border)] px-1 pb-[9px] font-mono text-[10px] font-semibold tracking-[0.09em] text-[var(--oasis-text-dim)] sm:text-[10.5px]">
          <span className="hidden md:block md:w-[270px]">MATCH</span>
          <span className="flex flex-1 items-center gap-[14px]">
            <span className="hidden md:inline">WIN PROBABILITY</span>
            <ProbabilityLegend />
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

        {rows.map((m) => {
          const isOpen = expanded === m.id;
          const day = m.kickoffUtc.slice(0, 10);
          const showDay = dayTab === "Week" && day !== lastDay;
          lastDay = day;
          return (
            <div key={m.id}>
              {showDay && (
                <div className="pb-[6px] pt-2 font-mono text-[12.5px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)]">
                  {utcDayLabel(m.kickoffUtc).toUpperCase()}
                </div>
              )}
              <div
                className="cursor-pointer border-b border-[var(--oasis-border-row)] transition-colors"
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--oasis-hover-row)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <button
                  type="button"
                  onClick={() => setExpanded(isOpen ? null : m.id)}
                  className="flex w-full flex-col gap-[10px] px-1 py-3 text-left md:flex-row md:items-center md:gap-0 md:py-[14px]"
                >
                  <span className="flex flex-col gap-[3px] md:w-[270px] md:gap-[4px] md:pr-4">
                    <span className="text-[15px] font-bold tracking-[-0.01em] md:text-[17.5px]">
                      <MatchName home={m.home} away={m.away} homeId={m.homeId} awayId={m.awayId} size={22} />
                    </span>
                    <span
                      className="font-mono text-[11px] font-medium md:text-[12.5px]"
                      style={{ color: m.statusConfirmed ? "var(--oasis-positive)" : "var(--oasis-text-muted)" }}
                    >
                      {m.metaLabel}
                    </span>
                  </span>
                  <span className="flex w-full items-center md:w-auto md:flex-1 md:pr-[18px]">
                    <ProbabilityBar home={m.h} draw={m.d} away={m.a} height={26} labeled className="w-full md:max-w-[440px]" />
                  </span>
                  <span className="flex w-full items-center justify-between md:contents">
                    <span
                      className="flex flex-col md:w-[100px] md:items-end"
                      title={`most likely ${m.pick === "draw" ? "scoreline" : `${m.pick}-win scoreline`} (overall mode ${m.score}, ${m.matrix.peakPct}%)`}
                    >
                      <span className="font-mono text-[14px] font-medium md:text-[15.5px]">{m.condScore}</span>
                      <span className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)] md:text-[11.5px]">
                        {Math.round(m.condPct)}% chance
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

                {isOpen && (
                  <div className="grid grid-cols-1 gap-4 px-1 pb-[14px] sm:grid-cols-[1.4fr_1fr]">
                    <div className="rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-3">
                      <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
                        WHY THIS FORECAST
                      </div>
                      <div className="mt-[6px] text-[13.5px] font-medium leading-[1.7] text-[var(--oasis-text-soft)]">
                        {m.why}
                      </div>
                    </div>
                    <div className="flex flex-col gap-[7px] rounded-[9px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-3 font-mono text-[12.5px] font-medium">
                      <div className="flex justify-between">
                        <span className="flex items-center gap-[6px] text-[var(--oasis-text-muted)]">
                          <span className="h-[8px] w-[8px] rounded-[2px]" style={{ background: "var(--oasis-home)" }} />
                          {m.home} win
                        </span>
                        <span>{Math.round(m.h)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="flex items-center gap-[6px] text-[var(--oasis-text-muted)]">
                          <span className="h-[8px] w-[8px] rounded-[2px]" style={{ background: "var(--oasis-draw)" }} />
                          Draw
                        </span>
                        <span>{Math.round(m.d)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="flex items-center gap-[6px] text-[var(--oasis-text-muted)]">
                          <span className="h-[8px] w-[8px] rounded-[2px]" style={{ background: "var(--oasis-away)" }} />
                          {m.away} win
                        </span>
                        <span>{Math.round(m.a)}%</span>
                      </div>
                      <div className="flex justify-between border-t border-[var(--oasis-border)] pt-[7px]">
                        <span className="text-[var(--oasis-text-muted)]">confidence</span>
                        <span>{m.conf}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--oasis-text-muted)]">
                          likely score{m.pick !== "draw" ? ` (if ${m.pick} win)` : ""}
                        </span>
                        <span>
                          {m.condScore} · {Math.round(m.condPct)}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--oasis-text-muted)]">most likely overall</span>
                        <span className="text-[var(--oasis-text-muted)]">
                          {m.score} · {Math.round(m.matrix.peakPct)}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--oasis-text-muted)]">market (no vig)</span>
                        <span className="text-[var(--oasis-text-muted)]">{m.marketLabel ?? "no odds yet"}</span>
                      </div>
                      <Link href={`/match/${m.id}`} className="mt-[2px] text-[12.5px] font-bold text-[var(--oasis-home)]">
                        Open full match page →
                      </Link>
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
          className="flex flex-col items-start gap-3 rounded-[10px] p-4 sm:flex-row sm:items-center sm:gap-4 sm:p-[15px] sm:px-[17px]"
          style={{
            border: "1px solid var(--oasis-border-strong)",
            background: "linear-gradient(120deg,rgba(77,156,246,.1),rgba(47,207,154,.06))",
          }}
        >
          <div className="flex-1">
            <div className="text-[13.5px] font-bold sm:text-[14.5px]">Founding-member lifetime access</div>
            <div className="mt-[3px] font-mono text-[11px] font-medium text-[var(--oasis-text-muted)] sm:text-[11.5px]">
              one-time purchase · quantity capped · opens at paid launch
            </div>
          </div>
          <button
            type="button"
            className="rounded-[7px] bg-[var(--oasis-home)] px-[15px] py-[9px] text-[12.5px] font-bold text-[var(--oasis-home-ink)]"
          >
            Get notified
          </button>
        </div>
      </div>

      {/* Right rail */}
      <div className="flex min-w-0 flex-col gap-[14px] border-t border-[var(--oasis-border)] bg-[var(--oasis-bg-rail)] p-4 lg:border-t-0 lg:border-l">
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
            <span className="text-[var(--oasis-text-muted)]">vs market</span>
            <span title="odds collection starts at launch">—</span>
          </div>
          <div className="mt-[2px] flex h-[44px] items-end gap-[3px]" title="observed win rate by predicted-probability band">
            {live.calibration_bars.map((h, i) => (
              <span
                key={i}
                className="flex-1 rounded-[2px]"
                style={{ height: `${Math.max(4, h)}%`, background: i === live.calibration_bars.length - 1 ? "var(--oasis-home)" : "#2b3a52" }}
              />
            ))}
          </div>
          <Link href="/performance" className="text-[11.5px] font-bold text-[var(--oasis-home)]">
            See full record →
          </Link>
        </div>

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

        <div className="font-mono text-[10px] font-medium leading-[1.6] text-[var(--oasis-text-faint)]">
          Probabilistic forecasts, not guarantees and not betting advice. 18+ · responsible use.
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

function ResultsList({ rows }: { rows: import("@/lib/types").RecentResult[] }) {
  let lastDay = "";
  return (
    <>
      <div className="flex items-center border-b border-[var(--oasis-border)] px-1 pb-[9px] font-mono text-[10px] font-semibold tracking-[0.09em] text-[var(--oasis-text-dim)] sm:text-[10.5px]">
        <span className="hidden md:block md:w-[270px]">MATCH</span>
        <span className="flex flex-1 items-center gap-[14px]">
          <span className="hidden md:inline">LOCKED PRE-KICKOFF PREDICTION</span>
          <ProbabilityLegend />
        </span>
        <span className="hidden w-[80px] text-right md:block">FINAL</span>
        <span className="hidden w-[110px] text-right md:block">VERDICT</span>
      </div>
      {rows.map((r) => {
        const day = r.kickoffUtc.slice(0, 10);
        const showDay = day !== lastDay;
        lastDay = day;
        return (
          <div key={r.id}>
            {showDay && (
              <div className="pb-[6px] pt-2 font-mono text-[12.5px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)]">
                {utcDayLabel(r.kickoffUtc).toUpperCase()}
              </div>
            )}
            <div className="flex flex-col gap-[10px] border-b border-[var(--oasis-border-row)] px-1 py-3 md:flex-row md:items-center md:gap-0 md:py-[14px]">
              <span className="flex flex-col gap-[3px] md:w-[270px] md:gap-[4px] md:pr-4">
                <span className="text-[15px] font-bold tracking-[-0.01em] md:text-[17.5px]">
                  <MatchName home={r.home} away={r.away} homeId={r.homeId} awayId={r.awayId} size={22} />
                </span>
                <span className="font-mono text-[11px] font-medium text-[var(--oasis-text-muted)] md:text-[12.5px]">
                  {LEAGUE_NAMES[r.lg]} · {r.ko} UTC{r.locked ? ` · ${r.locked.modelVersion}` : ""}
                </span>
              </span>
              <span className="flex w-full flex-col gap-[3px] md:w-auto md:flex-1 md:pr-[18px]">
                {r.locked ? (
                  <ProbabilityBar home={r.locked.h} draw={r.locked.d} away={r.locked.a} height={26} labeled className="w-full max-w-[440px]" />
                ) : r.retro ? (
                  <>
                    <span className="opacity-70">
                      <ProbabilityBar home={r.retro.h} draw={r.retro.d} away={r.retro.a} height={22} labeled className="flex w-full max-w-[440px]" />
                    </span>
                    <span className="font-mono text-[10px] font-medium text-[var(--oasis-text-dim)]">
                      retrospective ({r.retro.modelVersion}, pre-match data only) — not locked before kickoff
                    </span>
                  </>
                ) : (
                  <span className="rounded-[6px] border border-dashed border-[var(--oasis-border)] px-3 py-[5px] font-mono text-[11px] font-medium text-[var(--oasis-text-dim)]">
                    no locked prediction — played before lock automation ran (locking live from 21 Aug 2026)
                  </span>
                )}
              </span>
              <span className="flex w-full items-center justify-between md:contents">
              <span className="font-mono text-[15px] font-bold md:w-[80px] md:text-right md:text-[16.5px]">
                <span className="mr-[6px] font-sans text-[9.5px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)] md:hidden">FINAL</span>
                {r.score}
              </span>
              <span className="text-right font-mono text-[11.5px] font-medium md:w-[110px] md:text-[12px]">
                {r.locked && r.locked.correct !== null ? (
                  <span style={{ color: r.locked.correct ? "var(--oasis-positive)" : "var(--oasis-away)" }}>
                    {r.locked.correct ? "✓ top pick" : "✗ missed"}
                    {r.locked.logLoss !== null && (
                      <span className="block text-[10.5px] text-[var(--oasis-text-dim)]">ll {r.locked.logLoss.toFixed(2)}</span>
                    )}
                  </span>
                ) : r.retro ? (
                  <span className="opacity-75" style={{ color: r.retro.correct ? "var(--oasis-positive)" : "var(--oasis-away)" }}>
                    {r.retro.correct ? "✓ retro" : "✗ retro"}
                  </span>
                ) : (
                  <span className="text-[var(--oasis-text-dim)]">—</span>
                )}
              </span>
              </span>
            </div>
          </div>
        );
      })}
      {rows.length === 0 && (
        <div className="rounded-[9px] border border-dashed border-[var(--oasis-border-strong)] p-[22px] text-center text-[13px] font-semibold text-[var(--oasis-text-muted)]">
          No finished matches in the last 7 days for this selection.
        </div>
      )}
    </>
  );
}
