"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { IconArrowRight, IconCheck, IconChevronDown, IconSliders } from "@/components/icons";
import { MatchName } from "@/components/team-logo";
import { UnlockCta } from "@/components/unlock-cta";
import { LEAGUE_CODES, LEAGUE_NAMES, utcClock, utcDayLabel } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import {
  MARKET_CHIPS, applyFilters, buildItems, defaultsFor, sortItems,
  type BettingItem, type ConfFilter, type DateRange, type Filters, type Mode, type SortKey,
} from "@/lib/betting-derive";
import type { BettingLevel } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { Tier } from "@/lib/viewer";

/* ------------------------------------------------------------------ */
/* Tokens for this page. One accent (the brand blue) for the model, the
   text colour for the market, grades on the existing semantic colours.  */

const LEVEL: Record<BettingLevel, { label: string; cls: string }> = {
  PASS:         { label: "PASS",   cls: "border-[var(--oasis-border-strong)] text-[var(--oasis-text-dim)]" },
  WATCH:        { label: "WATCH",  cls: "border-[var(--oasis-warn)] text-[var(--oasis-warn)]" },
  VALUE:        { label: "VALUE",  cls: "border-[var(--oasis-positive)] text-[var(--oasis-positive)]" },
  STRONG_VALUE: { label: "STRONG", cls: "border-[var(--oasis-home)] text-[var(--oasis-home)]" },
};

const COPY: Record<Mode, { title: string; lede: string; short: string }> = {
  likely: {
    title: "What the model expects",
    short: "Most likely",
    lede: "Every selection ranked by the model's own probability. A high number is a strong opinion, not a price worth taking.",
  },
  edge: {
    title: "Where the model disagrees",
    short: "Biggest edge",
    lede: "Selections where the model and the bookmaker consensus are furthest apart. Disagreement is a candidate to investigate, not a tip.",
  },
};

const chip = (active: boolean) =>
  cn(
    "rs-tab flex-none cursor-pointer whitespace-nowrap rounded-full border px-[11px] py-[6px] text-meta font-semibold active:scale-[0.98]",
    active
      ? "border-[var(--oasis-positive)]/45 bg-[var(--oasis-positive-tint)] text-[var(--oasis-positive)]"
      : "border-[var(--oasis-border)] text-[var(--oasis-text-muted)] hover:border-[var(--oasis-border-strong)] hover:text-[var(--oasis-text)]",
  );

const selectCls =
  "cursor-pointer rounded-[7px] border border-[var(--oasis-border)] bg-transparent px-[8px] py-[5px] font-mono text-meta text-[var(--oasis-text)] outline-none hover:border-[var(--oasis-border-strong)] focus-visible:border-[var(--oasis-home)]";

function pp(x: number | null): string {
  if (x === null) return "—";
  return `${x > 0 ? "+" : ""}${x.toFixed(1)}`;
}

function kickoffLabel(iso: string): string {
  return `${new Date(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })} ${utcClock(iso)}`;
}

/* ------------------------------------------------------------------ */

export function BettingConsole({ live, tier }: { live: LiveData; tier: Tier }) {
  const [mode, setModeState] = useState<Mode>("likely");
  const [f, setF] = useState<Filters>(defaultsFor("likely"));
  const [more, setMore] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setF((prev) => ({ ...prev, [k]: v }));
  const setMode = (m: Mode) => { setModeState(m); setF(defaultsFor(m)); setOpen(null); };

  const items = useMemo(() => buildItems(live), [live]);
  // Today is derived from the payload, not the client clock, so the server
  // and the browser filter the same way on first paint.
  const todayUtc = live.generated_at.slice(0, 10);
  const shown = useMemo(() => sortItems(applyFilters(items, f, todayUtc), f.sort), [items, f, todayUtc]);
  const hiddenPass = useMemo(
    () => (f.showPass ? 0 : applyFilters(items, { ...f, showPass: true }, todayUtc).length - shown.length),
    [items, f, todayUtc, shown.length],
  );
  const lockedFixtures = live.matches.filter((m) => m.gated).length;
  const block = live.betting;

  const figures = useMemo(() => {
    const fixtures = new Set(items.map((it) => it.id));
    const priced = new Set(items.filter((it) => it.odds !== null).map((it) => it.id));
    const flagged = items.filter((it) => it.level !== "PASS").length;
    return { fixtures: fixtures.size, priced: priced.size, flagged, graded: items.length };
  }, [items]);

  const d = defaultsFor(mode);
  const advancedDirty = f.minP !== d.minP || f.minEdge !== d.minEdge || f.conf !== d.conf || f.h2hMin !== d.h2hMin || f.showPass !== d.showPass;
  const showAdvanced = more || advancedDirty;

  // Group by day only when the list is in kickoff order; any other sort is
  // a ranking and day headers would break it up.
  const groups = useMemo(() => {
    if (f.sort !== "kickoff") return [{ day: null as string | null, rows: shown }];
    const out: { day: string | null; rows: BettingItem[] }[] = [];
    for (const it of shown) {
      const day = it.match.kickoffUtc.slice(0, 10);
      const last = out[out.length - 1];
      if (last && last.day === day) last.rows.push(it);
      else out.push({ day, rows: [it] });
    }
    return out;
  }, [shown, f.sort]);

  let rowIndex = 0;

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 p-4 pb-16 sm:p-6">
      {/* ---- Header: title left, mode + figures right -------------------- */}
      <header className="grid gap-6 border-b border-[var(--oasis-border)] pb-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div className="flex max-w-[60ch] flex-col gap-3">
          <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">
            Betting{block ? ` · rulebook ${block.thresholds_version} · odds as of ${utcClock(block.generated_at)} UTC` : ""}
          </span>
          <h1 className="text-display font-extrabold">{COPY[mode].title}</h1>
          <p className="text-body text-[var(--oasis-text-muted)]">{COPY[mode].lede}</p>
        </div>

        <div className="flex flex-col items-start gap-5 lg:items-end">
          <div role="tablist" aria-label="Ranking" className="inline-flex rounded-[9px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-surface)] p-[3px]">
            {(["likely", "edge"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={m === mode}
                onClick={() => setMode(m)}
                className={cn(
                  "rs-tab cursor-pointer rounded-[6px] px-[14px] py-[7px] text-ui font-semibold active:scale-[0.98]",
                  m === mode ? "bg-[var(--oasis-surface-raised)] text-[var(--oasis-text)]" : "text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]",
                )}
              >
                {COPY[m].short}
              </button>
            ))}
          </div>
          <dl className="flex divide-x divide-[var(--oasis-border)]">
            <Figure k="fixtures" v={figures.fixtures} />
            <Figure k="with odds" v={figures.priced} />
            <Figure k="flagged" v={figures.flagged} accent={figures.flagged > 0} />
            <Figure k="graded" v={figures.graded} />
          </dl>
        </div>
      </header>

      {tier !== "premium" && lockedFixtures > 0 && (
        <div className="flex flex-col items-start gap-3 border-l-2 border-[var(--oasis-home)] pl-4 sm:flex-row sm:items-center sm:gap-6">
          <p className="flex-1 text-ui text-[var(--oasis-text-muted)]">
            <span className="font-bold text-[var(--oasis-text)]">
              {lockedFixtures} upcoming {lockedFixtures === 1 ? "fixture is" : "fixtures are"} locked.
            </span>{" "}
            {tier === "anon"
              ? "A free account unlocks the two highest-confidence fixtures each day; lifetime access unlocks every market on every fixture."
              : "Lifetime access unlocks every market on every upcoming fixture."}
          </p>
          <UnlockCta tier={tier} />
        </div>
      )}

      {/* ---- Toolbar: sticks under the header while the list scrolls ------ */}
      <div className="sticky top-0 z-10 -mx-4 flex flex-col gap-[10px] border-b border-[var(--oasis-border)] bg-[var(--oasis-bg)] px-4 pb-3 pt-3 sm:-mx-6 sm:px-6">
        <div className="rs-noscroll -mx-4 flex gap-[6px] overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0">
          {MARKET_CHIPS.map((c) => (
            <button key={c.key} type="button" onClick={() => set("market", c.key)} className={chip(f.market === c.key)} aria-pressed={f.market === c.key}>
              {c.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-[10px]">
          <div className="rs-noscroll -mx-4 flex gap-[6px] overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0">
            {LEAGUE_CODES.map((lg) => {
              const on = f.leagues.includes(lg);
              return (
                <button
                  key={lg}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set("leagues", on ? f.leagues.filter((x) => x !== lg) : [...f.leagues, lg])}
                  className={chip(on)}
                >
                  {LEAGUE_NAMES[lg]}
                </button>
              );
            })}
            {f.leagues.length > 0 && (
              <button type="button" onClick={() => set("leagues", [])} className="px-2 text-meta font-semibold text-[var(--oasis-text-dim)] hover:text-[var(--oasis-text)]">
                clear
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 sm:ml-auto">
            <Select label="When" value={f.date} onChange={(v) => set("date", v as DateRange)}
              options={[["today", "today"], ["tomorrow", "tomorrow"], ["3d", "next 3 days"], ["7d", "next 7 days"]]} />
            <Select label="Sort" value={f.sort} onChange={(v) => set("sort", v as SortKey)}
              options={[["prob", "probability"], ["edge", "edge"], ["conf", "confidence"], ["kickoff", "kickoff"], ["h2h", "head to head"]]} />
            <button
              type="button"
              onClick={() => setMore((v) => !v)}
              aria-expanded={showAdvanced}
              className={cn(
                "rs-tab flex cursor-pointer items-center gap-[6px] rounded-[7px] border px-[10px] py-[5px] text-meta font-semibold",
                showAdvanced ? "border-[var(--oasis-border-strong)] text-[var(--oasis-text)]" : "border-[var(--oasis-border)] text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]",
              )}
            >
              <IconSliders size={13} />
              More
              {advancedDirty && <span className="h-[5px] w-[5px] rounded-full bg-[var(--oasis-positive)]" />}
            </button>
          </div>
        </div>
        {showAdvanced && (
          <div className="rs-sheet flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-[var(--oasis-border-row)] pt-[10px]">
            <Select label="Model ≥" value={String(f.minP)} onChange={(v) => set("minP", Number(v))}
              options={[0, 50, 55, 60, 65, 70, 75].map((v) => [String(v), v === 0 ? "any" : `${v}%`])} />
            <Select label="Edge ≥" value={String(f.minEdge)} onChange={(v) => set("minEdge", Number(v))}
              options={[0, 2, 3, 5, 8, 10].map((v) => [String(v), v === 0 ? "any" : `+${v}pp`])} />
            <Select label="Confidence" value={f.conf} onChange={(v) => set("conf", v as ConfFilter)}
              options={[["ALL", "all"], ["MED", "medium+"], ["HIGH", "high"]]} />
            <Select label="H2H ≥" value={String(f.h2hMin)} onChange={(v) => set("h2hMin", Number(v))}
              options={[0, 3, 4, 5].map((v) => [String(v), v === 0 ? "any" : `${v} of 5`])} />
            <button type="button" onClick={() => set("showPass", !f.showPass)} className={chip(f.showPass)} aria-pressed={f.showPass}>
              <span className="flex items-center gap-[5px]">PASS rows{f.showPass && <IconCheck size={12} strokeWidth={2} />}</span>
            </button>
            {advancedDirty && (
              <button type="button" onClick={() => setF(defaultsFor(mode))} className="px-1 text-meta font-semibold text-[var(--oasis-text-dim)] hover:text-[var(--oasis-text)]">
                reset
              </button>
            )}
          </div>
        )}
      </div>

      {/* ---- List ------------------------------------------------------- */}
      <section aria-live="polite">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pb-1">
          <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">{COPY[mode].short}</span>
          <span className="font-mono text-meta text-[var(--oasis-text-muted)]">
            {shown.length} of {items.length} selections{hiddenPass > 0 ? ` · ${hiddenPass} PASS hidden` : ""}
          </span>
        </div>

        {!block ? (
          <EmptyState title="No grades yet">Betting data arrives with the next pipeline run.</EmptyState>
        ) : items.length === 0 ? (
          tier === "premium" ? (
            <EmptyState title="Nothing in the window">No upcoming fixtures have been graded for the next seven days.</EmptyState>
          ) : (
            <EmptyState title="Selections are locked" action={<UnlockCta tier={tier} />}>
              {tier === "anon" ? "Sign in to see today's free taster, or unlock every fixture." : "Today's taster fixtures are on the board. Lifetime access grades every market on every fixture."}
            </EmptyState>
          )
        ) : shown.length === 0 ? (
          <EmptyState
            title="Nothing matches"
            action={
              <span className="flex flex-wrap gap-2">
                {hiddenPass > 0 && (
                  <button type="button" onClick={() => set("showPass", true)} className={chip(false)}>
                    Show {hiddenPass} PASS {hiddenPass === 1 ? "row" : "rows"}
                  </button>
                )}
                <button type="button" onClick={() => setF(defaultsFor(mode))} className={chip(false)}>Reset filters</button>
              </span>
            }
          >
            Loosen a filter, widen the date range, or include PASS rows.
          </EmptyState>
        ) : (
          <div className="border-t border-[var(--oasis-border)]">
            {/* Column key, desktop only. */}
            <div className="hidden grid-cols-[minmax(0,1.5fr)_188px_92px_92px_120px_96px_24px] gap-x-5 border-b border-[var(--oasis-border-row)] py-2 font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)] md:grid">
              <span>selection</span>
              <span>model v market</span>
              <span className="text-right">edge</span>
              <span className="text-right">best odds</span>
              <span>h2h · form</span>
              <span>grade</span>
              <span />
            </div>
            {groups.map((g) => (
              <div key={g.day ?? "all"}>
                {g.day && (
                  <div className="border-b border-[var(--oasis-border-row)] pb-2 pt-4 text-ui font-bold">
                    {utcDayLabel(`${g.day}T12:00:00Z`)}
                  </div>
                )}
                {g.rows.map((it) => {
                  const key = `${it.id}:${it.market}:${it.sel}`;
                  const i = rowIndex++;
                  return <Row key={key} it={it} index={i} open={open === key} onToggle={() => setOpen(open === key ? null : key)} />;
                })}
              </div>
            ))}
          </div>
        )}
      </section>

      <p className="max-w-[72ch] text-meta leading-[1.6] text-[var(--oasis-text-dim)]">
        These are probabilities and prices, not predictions of what will happen. A 70% forecast is expected to fail about
        three times in ten when the model is well calibrated. Edge is the model&rsquo;s disagreement with the bookmaker
        consensus in percentage points; EV is the return per unit at the best archived price if the model&rsquo;s probability
        is right. Nothing on this page is advice to place a bet. 18+.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Figure({ k, v, accent = false }: { k: string; v: number; accent?: boolean }) {
  return (
    <div className="flex flex-col-reverse gap-[2px] px-4 first:pl-0 last:pr-0">
      <dt className="font-mono text-label uppercase text-[var(--oasis-text-dim)]">{k}</dt>
      <dd className={cn("font-mono text-title font-semibold", accent && "text-[var(--oasis-positive)]")}>{v}</dd>
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <label className="flex items-center gap-[6px] text-meta text-[var(--oasis-text-muted)]">
      {label}
      <select className={selectCls} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

function EmptyState({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 border-t border-[var(--oasis-border)] py-10 sm:pr-[30%]">
      <span className="text-title font-bold">{title}</span>
      <p className="max-w-[52ch] text-body text-[var(--oasis-text-muted)]">{children}</p>
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}

/** Model probability as a filled track, the market's number as a tick on
 * the same track. The gap between fill end and tick is the edge, so the
 * eye reads it before the number does. */
function Gauge({ p, mp }: { p: number; mp: number | null }) {
  return (
    <span className="flex w-full flex-col gap-[5px]">
      <span className="relative block h-[7px] w-full rounded-[4px] bg-[var(--oasis-border-row)]">
        <span className="rs-fill absolute inset-y-0 left-0 rounded-[4px] bg-[var(--oasis-home)]" style={{ width: `${p}%` }} />
        {mp !== null && (
          <span
            className="absolute top-[-3px] bottom-[-3px] w-[2px] rounded-[1px] bg-[var(--oasis-text)]"
            style={{ left: `calc(${mp}% - 1px)` }}
            title={`market ${mp.toFixed(1)}%`}
          />
        )}
      </span>
      <span className="flex justify-between font-mono text-label text-[var(--oasis-text-dim)]">
        <span><span className="font-bold text-[var(--oasis-text)]">{p.toFixed(0)}%</span> model</span>
        <span>{mp === null ? "no odds" : <><span className="font-bold text-[var(--oasis-text-soft)]">{mp.toFixed(0)}%</span> market</>}</span>
      </span>
    </span>
  );
}

function Row({ it, index, open, onToggle }: { it: BettingItem; index: number; open: boolean; onToggle: () => void }) {
  const m = it.match;
  const lvl = LEVEL[it.level];
  const pass = it.level === "PASS";
  const edgeColor = it.edge === null ? "text-[var(--oasis-text-dim)]" : it.edge >= 3 ? "text-[var(--oasis-positive)]" : it.edge <= -3 ? "text-[var(--oasis-away)]" : "text-[var(--oasis-text-soft)]";
  const form = it.ctx?.home && it.ctx?.away ? formLabel(it, it.ctx.home, it.ctx.away) : null;
  const delay = `${Math.min(index, 20) * 40}ms`;

  return (
    <div className={cn("border-b border-[var(--oasis-border-row)]", open && "bg-[var(--oasis-surface)]")}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={cn(
          "rs-rise rs-row grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3 py-[13px] text-left md:grid-cols-[minmax(0,1.5fr)_188px_92px_92px_120px_96px_24px] md:gap-x-5 md:gap-y-0",
          pass && "opacity-60 hover:opacity-100",
        )}
        style={{ animationDelay: delay }}
      >
        {/* Selection + fixture */}
        <span className="flex min-w-0 flex-col gap-[3px]">
          <span className="truncate text-body font-bold leading-tight">{it.label}</span>
          <span className="flex min-w-0 flex-wrap items-center gap-x-2 text-ui font-medium text-[var(--oasis-text-muted)]">
            <MatchName home={m.home} away={m.away} homeId={m.homeId} awayId={m.awayId} size={15} />
            <span className="font-mono text-label text-[var(--oasis-text-dim)]">{m.lg} · {kickoffLabel(m.kickoffUtc)}</span>
          </span>
        </span>

        {/* Grade: top-right on mobile, sixth column on desktop */}
        <span className="flex flex-col items-end gap-[3px] md:order-6 md:items-start">
          <span className={cn("rounded-[4px] border px-[6px] py-[2px] font-mono text-label font-bold", lvl.cls)} title={it.locked ? "graded at lock" : "provisional until lock"}>
            {lvl.label}{!it.locked && <span className="opacity-60">·pre</span>}
          </span>
          <span className="font-mono text-label text-[var(--oasis-text-dim)]">{m.conf.toLowerCase()} conf</span>
        </span>

        {/* Gauge: full width on mobile */}
        <span className="col-span-2 md:order-2 md:col-span-1">
          <Gauge p={it.p} mp={it.mp} />
        </span>

        {/* Numbers: one row on mobile, three cells on desktop */}
        <span className="col-span-2 flex items-start justify-between gap-4 md:contents">
          <span className="flex flex-col md:order-3 md:items-end">
            <span className={cn("font-mono text-lead font-semibold leading-tight", edgeColor)}>{it.edge === null ? "—" : `${pp(it.edge)}pp`}</span>
            <span className="font-mono text-label text-[var(--oasis-text-dim)]">{it.ev === null ? "edge" : `ev ${pp(it.ev)}%`}</span>
          </span>
          <span className="flex flex-col md:order-4 md:items-end">
            <span className="font-mono text-lead font-semibold leading-tight">{it.odds === null ? "—" : it.odds.toFixed(2)}</span>
            <span className="max-w-[92px] truncate font-mono text-label text-[var(--oasis-text-dim)]">{it.book ?? "best odds"}</span>
          </span>
          <span className="flex flex-col md:order-5">
            <span className="font-mono text-lead font-semibold leading-tight">{it.h2h ? `${it.h2h.k}/${it.h2h.n}` : "—"}</span>
            <span className="font-mono text-label text-[var(--oasis-text-dim)]">{form ? `form ${form}` : "h2h"}</span>
          </span>
        </span>

        <span className="hidden text-[var(--oasis-text-dim)] md:order-7 md:block">
          <IconChevronDown size={14} className={cn("transition-transform duration-200", open && "rotate-180")} />
        </span>
      </button>

      {open && (
        <div className="rs-sheet grid gap-5 border-t border-[var(--oasis-border-row)] px-1 py-4 md:grid-cols-3 md:gap-8">
          <Detail label="Why this grade">
            <ul className="flex flex-col gap-[5px]">
              {it.reasons.map((r) => (
                <li key={r.code} className="flex gap-[8px]">
                  <span className="mt-[7px] h-[4px] w-[4px] flex-none rounded-full bg-[var(--oasis-text-dim)]" />
                  <span>{r.detail}</span>
                </li>
              ))}
              {it.books !== null && (
                <li className="flex gap-[8px]">
                  <span className="mt-[7px] h-[4px] w-[4px] flex-none rounded-full bg-[var(--oasis-text-dim)]" />
                  <span>{it.books} bookmakers in the {it.snap} window{it.book ? `; best price at ${it.book}` : ""}.</span>
                </li>
              )}
            </ul>
          </Detail>
          <Detail label="Head to head">
            {it.ctx?.h2h && it.ctx.h2h.n > 0 ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-[3px] font-mono text-meta">
                <dt className="text-[var(--oasis-text-dim)]">last {it.ctx.h2h.n}</dt>
                <dd>{m.home} {it.ctx.h2h.hw} · draws {it.ctx.h2h.d} · {m.away} {it.ctx.h2h.aw}</dd>
                <dt className="text-[var(--oasis-text-dim)]">goals</dt>
                <dd>{it.ctx.h2h.hg}–{it.ctx.h2h.ag} · avg {it.ctx.h2h.avg ?? "—"}</dd>
                <dt className="text-[var(--oasis-text-dim)]">over 2.5</dt>
                <dd>{it.ctx.h2h.over25}/{it.ctx.h2h.n} · btts {it.ctx.h2h.btts}/{it.ctx.h2h.n}</dd>
                {it.ctx.h2h.last && (<><dt className="text-[var(--oasis-text-dim)]">last met</dt><dd>{it.ctx.h2h.last.slice(0, 10)}</dd></>)}
              </dl>
            ) : <span className="text-[var(--oasis-text-dim)]">No previous meetings on record.</span>}
          </Detail>
          <Detail label="Recent form · last 10, any competition">
            {it.ctx?.home && it.ctx?.away ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-[3px] font-mono text-meta">
                <dt className="truncate text-[var(--oasis-text-dim)]">{m.home}</dt>
                <dd>over 2.5 {it.ctx.home.over25}/{it.ctx.home.n} · btts {it.ctx.home.btts}/{it.ctx.home.n} · {it.ctx.home.gf}–{it.ctx.home.ga}</dd>
                <dt className="truncate text-[var(--oasis-text-dim)]">{m.away}</dt>
                <dd>over 2.5 {it.ctx.away.over25}/{it.ctx.away.n} · btts {it.ctx.away.btts}/{it.ctx.away.n} · {it.ctx.away.gf}–{it.ctx.away.ga}</dd>
              </dl>
            ) : <span className="text-[var(--oasis-text-dim)]">Form not computed yet.</span>}
            <Link href={`/match/${m.id}`} className="mt-3 flex w-fit items-center gap-[6px] text-ui font-bold text-[var(--oasis-home)]">
              Match detail <IconArrowRight size={13} />
            </Link>
          </Detail>
        </div>
      )}
    </div>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 text-ui text-[var(--oasis-text-soft)]">
      <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">{label}</span>
      {children}
    </div>
  );
}

/** The form column shows the stat that matters for this selection. */
function formLabel(it: BettingItem, home: { n: number; btts: number; over25: number }, away: { n: number; btts: number; over25: number }): string | null {
  if (it.market === "OU25") {
    const h = it.sel === "over" ? home.over25 : home.n - home.over25;
    const a = it.sel === "over" ? away.over25 : away.n - away.over25;
    return `${h}/${home.n} · ${a}/${away.n}`;
  }
  if (it.market === "BTTS") {
    const h = it.sel === "yes" ? home.btts : home.n - home.btts;
    const a = it.sel === "yes" ? away.btts : away.n - away.btts;
    return `${h}/${home.n} · ${a}/${away.n}`;
  }
  return null;
}
