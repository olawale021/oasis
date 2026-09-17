"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { MatchName } from "@/components/team-logo";
import { UnlockCta } from "@/components/unlock-cta";
import { LEAGUE_CODES, LEAGUE_NAMES, utcClock } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import {
  MARKET_CHIPS, applyFilters, buildItems, defaultsFor, sortItems,
  type BettingItem, type ConfFilter, type DateRange, type Filters, type Mode, type SortKey,
} from "@/lib/betting-derive";
import type { BettingLevel } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { Tier } from "@/lib/viewer";

const LEVEL: Record<BettingLevel, { label: string; cls: string }> = {
  PASS:         { label: "PASS",   cls: "border-[var(--oasis-border-strong)] text-[var(--oasis-text-dim)]" },
  WATCH:        { label: "WATCH",  cls: "border-[var(--oasis-warn)] text-[var(--oasis-warn)]" },
  VALUE:        { label: "VALUE",  cls: "border-[var(--oasis-positive)] text-[var(--oasis-positive)]" },
  STRONG_VALUE: { label: "STRONG", cls: "border-[var(--oasis-home)] text-[var(--oasis-home)]" },
};

const chip = (active: boolean) =>
  cn(
    "cursor-pointer rounded-[7px] px-[10px] py-[6px] text-[11.5px] font-semibold",
    active
      ? "border border-[rgba(47,207,154,.35)] bg-[var(--oasis-positive-tint)] text-[var(--oasis-positive)]"
      : "border border-[var(--oasis-border)] text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]",
  );

const selectCls =
  "rounded-[7px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] px-[8px] py-[6px] font-mono text-[11.5px] text-[var(--oasis-text)] outline-none focus:border-[var(--oasis-home)]";

const th = "px-2 py-[8px] text-left font-sans text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]";
const td = "px-2 py-[9px] align-middle font-mono text-[12px]";

function pp(x: number | null, signed = true): string {
  if (x === null) return "—";
  return `${signed && x > 0 ? "+" : ""}${x.toFixed(1)}`;
}

export function BettingConsole({ live, tier }: { live: LiveData; tier: Tier }) {
  const [mode, setModeState] = useState<Mode>("likely");
  const [f, setF] = useState<Filters>(defaultsFor("likely"));
  const [open, setOpen] = useState<string | null>(null);
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setF((prev) => ({ ...prev, [k]: v }));
  const setMode = (m: Mode) => { setModeState(m); setF(defaultsFor(m)); };

  const items = useMemo(() => buildItems(live), [live]);
  // Today is derived from the payload, not the client clock, so the server
  // and the browser filter the same way on first paint.
  const todayUtc = live.generated_at.slice(0, 10);
  const shown = useMemo(() => sortItems(applyFilters(items, f, todayUtc), f.sort), [items, f, todayUtc]);
  const lockedFixtures = live.matches.filter((m) => m.gated).length;
  const block = live.betting;

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-[14px] p-3 sm:p-5">
      {/* Title + mode */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <div className="min-w-0">
          <h1 className="text-[19px] font-extrabold leading-none tracking-[-0.02em] sm:text-[21px]">Betting</h1>
          <p className="mt-[6px] font-sans text-[12.5px] text-[var(--oasis-text-muted)]">
            {mode === "likely"
              ? "What the model thinks is most likely to happen. High probability is not the same as value."
              : "Where the model disagrees most with the bookmakers. Disagreement is a candidate, not a tip."}
          </p>
        </div>
        <div className="flex items-center gap-[6px] sm:ml-auto">
          {(["likely", "value"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className="cursor-pointer rounded-[6px] px-[12px] py-[6px] text-[12px] font-semibold"
              style={
                m === mode
                  ? { background: "var(--oasis-surface-raised)", border: "1px solid var(--oasis-border-strong)" }
                  : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
              }
            >
              {m === "likely" ? "Most likely" : "Best value"}
            </button>
          ))}
        </div>
        {block && (
          <span
            className="w-full font-mono text-[10.5px] text-[var(--oasis-text-faint)]"
            title="VALUE and STRONG VALUE are withheld until the point-in-time backtest validates thresholds."
          >
            rulebook {block.thresholds_version} · grades only PASS or WATCH until backtested · odds as of {utcClock(block.generated_at)} UTC
          </span>
        )}
      </div>

      {tier !== "premium" && lockedFixtures > 0 && (
        <div className="flex flex-col items-start gap-3 rounded-[9px] border border-[var(--oasis-home)] bg-[var(--oasis-surface)] p-3 sm:flex-row sm:items-center sm:gap-4 sm:px-[14px]">
          <div className="flex-1 text-[12.5px] leading-[1.6] text-[var(--oasis-text-muted)]">
            <span className="font-bold text-[var(--oasis-text)]">
              {lockedFixtures} upcoming {lockedFixtures === 1 ? "fixture is" : "fixtures are"} locked.
            </span>{" "}
            {tier === "anon"
              ? "A free account unlocks the two highest-confidence fixtures each day; lifetime access unlocks every market on every fixture."
              : "Lifetime access unlocks every market on every upcoming fixture."}
          </div>
          <UnlockCta tier={tier} />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-3 sm:p-4">
        <div className="flex flex-wrap gap-[6px]">
          {MARKET_CHIPS.map((c) => (
            <button key={c.key} type="button" onClick={() => set("market", c.key)} className={chip(f.market === c.key)}>
              {c.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <label className="flex items-center gap-[6px] font-sans text-[11.5px] text-[var(--oasis-text-muted)]">
            Oasis ≥
            <select className={selectCls} value={f.minP} onChange={(e) => set("minP", Number(e.target.value))}>
              {[0, 50, 55, 60, 65, 70, 75].map((v) => <option key={v} value={v}>{v === 0 ? "any" : `${v}%`}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-[6px] font-sans text-[11.5px] text-[var(--oasis-text-muted)]">
            Edge ≥
            <select className={selectCls} value={f.minEdge} onChange={(e) => set("minEdge", Number(e.target.value))}>
              {[0, 2, 3, 5, 8, 10].map((v) => <option key={v} value={v}>{v === 0 ? "any" : `+${v}pp`}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-[6px] font-sans text-[11.5px] text-[var(--oasis-text-muted)]">
            Confidence
            <select className={selectCls} value={f.conf} onChange={(e) => set("conf", e.target.value as ConfFilter)}>
              <option value="ALL">all</option><option value="MED">medium+</option><option value="HIGH">high</option>
            </select>
          </label>
          <label className="flex items-center gap-[6px] font-sans text-[11.5px] text-[var(--oasis-text-muted)]">
            H2H ≥
            <select className={selectCls} value={f.h2hMin} onChange={(e) => set("h2hMin", Number(e.target.value))}>
              {[0, 3, 4, 5].map((v) => <option key={v} value={v}>{v === 0 ? "any" : `${v}/5`}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-[6px] font-sans text-[11.5px] text-[var(--oasis-text-muted)]">
            When
            <select className={selectCls} value={f.date} onChange={(e) => set("date", e.target.value as DateRange)}>
              <option value="today">today</option><option value="tomorrow">tomorrow</option>
              <option value="3d">next 3 days</option><option value="7d">next 7 days</option>
            </select>
          </label>
          <label className="flex items-center gap-[6px] font-sans text-[11.5px] text-[var(--oasis-text-muted)]">
            Sort
            <select className={selectCls} value={f.sort} onChange={(e) => set("sort", e.target.value as SortKey)}>
              <option value="prob">highest probability</option><option value="edge">highest edge</option>
              <option value="conf">highest confidence</option><option value="kickoff">kickoff time</option>
              <option value="h2h">strongest H2H</option>
            </select>
          </label>
          <button type="button" onClick={() => set("showPass", !f.showPass)} className={chip(f.showPass)}>
            {f.showPass ? "Showing PASS ✓" : "Show PASS"}
          </button>
        </div>
        <div className="flex flex-wrap gap-[6px]">
          {LEAGUE_CODES.map((lg) => {
            const on = f.leagues.includes(lg);
            return (
              <button
                key={lg}
                type="button"
                onClick={() => set("leagues", on ? f.leagues.filter((x) => x !== lg) : [...f.leagues, lg])}
                className={chip(on)}
              >
                {LEAGUE_NAMES[lg]}
              </button>
            );
          })}
          {f.leagues.length > 0 && (
            <button type="button" onClick={() => set("leagues", [])} className="font-sans text-[11.5px] text-[var(--oasis-text-dim)] hover:text-[var(--oasis-text)]">
              clear
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)]">
        <div className="flex flex-wrap items-baseline gap-x-3 border-b border-[var(--oasis-border)] px-4 py-[10px]">
          <span className="font-sans text-[11px] font-semibold uppercase tracking-[0.07em] text-[var(--oasis-text-dim)]">
            {mode === "likely" ? "Most likely" : "Best value"}
          </span>
          <span className="font-mono text-[11px] text-[var(--oasis-text-muted)]">
            {shown.length} of {items.length} selections
          </span>
        </div>
        {!block ? (
          <p className="p-4 font-sans text-[12.5px] text-[var(--oasis-text-muted)]">Betting data arrives with the next pipeline run.</p>
        ) : shown.length === 0 ? (
          <p className="p-4 font-sans text-[12.5px] text-[var(--oasis-text-muted)]">
            {items.length === 0
              ? tier === "premium" ? "No upcoming fixtures in the window." : "Sign in or unlock to see upcoming selections."
              : "Nothing matches these filters. PASS rows are hidden unless you show them."}
          </p>
        ) : (
          <div className="overflow-x-auto"><div className="min-w-[980px]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--oasis-border)]">
                  <th className={th}>kickoff</th><th className={th}>fixture</th><th className={th}>selection</th>
                  <th className={cn(th, "text-right")}>oasis</th><th className={cn(th, "text-right")}>market</th>
                  <th className={cn(th, "text-right")}>edge</th><th className={cn(th, "text-right")}>best odds</th>
                  <th className={cn(th, "text-right")}>ev</th><th className={cn(th, "text-right")}>h2h</th>
                  <th className={th}>form</th><th className={th}>conf</th><th className={th}>grade</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((it) => <Row key={`${it.id}:${it.market}:${it.sel}`} it={it} open={open} setOpen={setOpen} />)}
              </tbody>
            </table>
          </div></div>
        )}
      </div>

      <p className="font-sans text-[11.5px] leading-[1.6] text-[var(--oasis-text-dim)]">
        These are probabilities and prices, not predictions of what will happen. A 70% forecast is expected to fail about
        three times in ten when the model is well calibrated. Edge is the model&rsquo;s disagreement with the bookmaker
        consensus in percentage points; EV is the return per unit at the best archived price if the model&rsquo;s probability
        is right. Nothing on this page is advice to place a bet.
      </p>
    </div>
  );
}

function Row({ it, open, setOpen }: { it: BettingItem; open: string | null; setOpen: (k: string | null) => void }) {
  const key = `${it.id}:${it.market}:${it.sel}`;
  const isOpen = open === key;
  const m = it.match;
  const edgeCls = it.edge === null ? "text-[var(--oasis-text-dim)]" : it.edge >= 3 ? "text-[var(--oasis-positive)]" : it.edge <= -3 ? "text-[var(--oasis-away)]" : "text-[var(--oasis-text-muted)]";
  const lvl = LEVEL[it.level];
  const form = it.ctx?.home && it.ctx?.away ? formLabel(it, it.ctx.home, it.ctx.away) : "—";
  return (
    <>
      <tr
        onClick={() => setOpen(isOpen ? null : key)}
        className={cn("cursor-pointer border-t border-[var(--oasis-border-row)] hover:bg-[var(--oasis-hover-row)]", it.level === "PASS" && "opacity-70")}
      >
        <td className={cn(td, "whitespace-nowrap text-[var(--oasis-text-muted)]")}>
          {new Date(m.kickoffUtc).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })} {m.ko}
        </td>
        <td className="px-2 py-[9px] align-middle font-sans text-[12.5px] font-semibold">
          <MatchName home={m.home} away={m.away} homeId={m.homeId} awayId={m.awayId} size={16} />
          <span className="ml-[6px] font-mono text-[10.5px] font-normal text-[var(--oasis-text-dim)]">{m.lg}</span>
        </td>
        <td className="px-2 py-[9px] align-middle font-sans text-[12.5px]">{it.label}</td>
        <td className={cn(td, "text-right font-bold")}>{it.p.toFixed(0)}%</td>
        <td className={cn(td, "text-right text-[var(--oasis-text-muted)]")}>{it.mp === null ? "—" : `${it.mp.toFixed(0)}%`}</td>
        <td className={cn(td, "text-right font-bold", edgeCls)}>{it.edge === null ? "—" : `${pp(it.edge)}pp`}</td>
        <td className={cn(td, "text-right")} title={it.book ?? undefined}>{it.odds === null ? "—" : it.odds.toFixed(2)}</td>
        <td className={cn(td, "text-right", it.ev !== null && it.ev > 0 ? "text-[var(--oasis-positive)]" : "text-[var(--oasis-text-muted)]")}>
          {it.ev === null ? "—" : `${pp(it.ev)}%`}
        </td>
        <td className={cn(td, "text-right text-[var(--oasis-text-muted)]")}>{it.h2h ? `${it.h2h.k}/${it.h2h.n}` : "—"}</td>
        <td className={cn(td, "whitespace-nowrap text-[var(--oasis-text-muted)]")}>{form}</td>
        <td className={cn(td, "text-[var(--oasis-text-dim)]")}>{m.conf}</td>
        <td className={td}>
          <span className={cn("rounded-[4px] border px-[6px] py-[1px] font-mono text-[10.5px]", lvl.cls)} title={it.locked ? "graded at lock" : "provisional until lock"}>
            {lvl.label}{!it.locked && <span className="opacity-60">·pre</span>}
          </span>
        </td>
      </tr>
      {isOpen && (
        <tr className="border-t border-[var(--oasis-border-row)] bg-[var(--oasis-bg)]">
          <td colSpan={12} className="px-4 py-3">
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <div className="font-sans text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]">Why this grade</div>
                <ul className="mt-[6px] space-y-[3px] font-sans text-[12px] text-[var(--oasis-text-muted)]">
                  {it.reasons.map((r) => <li key={r.code}>• {r.detail}</li>)}
                  {it.books !== null && <li>• {it.books} bookmakers in the {it.snap} window{it.book ? `; best price at ${it.book}` : ""}.</li>}
                </ul>
              </div>
              <div>
                <div className="font-sans text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]">Head to head</div>
                {it.ctx?.h2h && it.ctx.h2h.n > 0 ? (
                  <div className="mt-[6px] font-mono text-[12px] text-[var(--oasis-text-muted)]">
                    last {it.ctx.h2h.n}: {m.home} {it.ctx.h2h.hw} · draws {it.ctx.h2h.d} · {m.away} {it.ctx.h2h.aw}<br />
                    goals {it.ctx.h2h.hg}–{it.ctx.h2h.ag} · avg {it.ctx.h2h.avg ?? "—"}<br />
                    over 2.5 {it.ctx.h2h.over25}/{it.ctx.h2h.n} · btts {it.ctx.h2h.btts}/{it.ctx.h2h.n}
                    {it.ctx.h2h.last && <><br /><span className="text-[var(--oasis-text-dim)]">last met {it.ctx.h2h.last.slice(0, 10)}</span></>}
                  </div>
                ) : <div className="mt-[6px] font-sans text-[12px] text-[var(--oasis-text-dim)]">No previous meetings on record.</div>}
              </div>
              <div>
                <div className="font-sans text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]">Recent form · last 10, any competition</div>
                {it.ctx?.home && it.ctx?.away ? (
                  <div className="mt-[6px] font-mono text-[12px] text-[var(--oasis-text-muted)]">
                    {m.home}: over 2.5 {it.ctx.home.over25}/{it.ctx.home.n} · btts {it.ctx.home.btts}/{it.ctx.home.n} · {it.ctx.home.gf}–{it.ctx.home.ga}<br />
                    {m.away}: over 2.5 {it.ctx.away.over25}/{it.ctx.away.n} · btts {it.ctx.away.btts}/{it.ctx.away.n} · {it.ctx.away.gf}–{it.ctx.away.ga}
                  </div>
                ) : <div className="mt-[6px] font-sans text-[12px] text-[var(--oasis-text-dim)]">Form not computed yet.</div>}
                <Link href={`/match/${m.id}`} className="mt-[8px] inline-block font-sans text-[11.5px] font-bold text-[var(--oasis-home)]">Match detail →</Link>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/** The form column shows the stat that matters for this selection. */
function formLabel(it: BettingItem, home: { n: number; btts: number; over25: number }, away: { n: number; btts: number; over25: number }): string {
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
  return "—";
}
