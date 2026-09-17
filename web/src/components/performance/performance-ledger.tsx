"use client";

import { useMemo, useState } from "react";
import { LEAGUE_CODES, LEAGUE_NAMES } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import type { LedgerRow, LeagueFilter } from "@/lib/types";
import { IconCheck, IconCross } from "@/components/icons";

/** The ledger mixes two tracks and the row itself is the only place that
 * says which: the matchday chain tags live rows "<model> · live" and
 * replayed ones "<model> · backtest". They mean very different things — a
 * live row was locked before kickoff and can never be revised — so they are
 * labelled per row and filterable, never silently merged. */
type Track = "live" | "backtest";
type TrackFilter = Track | "all";

function trackOf(r: LedgerRow): Track {
  return /·\s*live\s*$/.test(r.modelVersion) ? "live" : "backtest";
}

export function PerformanceLedger({ live }: { live: LiveData }) {
  const [league, setLeague] = useState<LeagueFilter>("ALL");
  const counts = useMemo(() => {
    let liveN = 0;
    for (const r of live.ledger) if (trackOf(r) === "live") liveN += 1;
    return { live: liveN, backtest: live.ledger.length - liveN };
  }, [live.ledger]);
  // Land on the live record when there is one: it is the honest track, and
  // the backtest is the thing that needs the caveat, not the default.
  const [track, setTrack] = useState<TrackFilter>(counts.live > 0 ? "live" : "all");

  const rows = useMemo(
    () => live.ledger.filter((r) => (league === "ALL" || r.lg === league) && (track === "all" || trackOf(r) === track)),
    [league, track, live.ledger],
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-[9px]">
        {(["ALL", ...LEAGUE_CODES] as LeagueFilter[]).map((code) => {
          const active = league === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => setLeague(code)}
              className="rounded-[6px] px-[11px] py-[6px] text-[12px] font-semibold"
              style={{
                background: active ? "var(--oasis-surface-raised)" : "transparent",
                border: active ? "1px solid var(--oasis-border-strong)" : "1px solid var(--oasis-border)",
                color: active ? "var(--oasis-text)" : "var(--oasis-text-muted)",
              }}
            >
              {LEAGUE_NAMES[code]}
            </button>
          );
        })}
        <span className="rounded-[6px] border border-[var(--oasis-border)] px-[11px] py-[6px] text-[12px] font-semibold text-[var(--oasis-text-muted)]">
          {live.headline.season}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-[9px]">
        {([
          { key: "live" as const, label: "Live record", n: counts.live },
          { key: "backtest" as const, label: "Backtest", n: counts.backtest },
          { key: "all" as const, label: "Both", n: live.ledger.length },
        ]).map((t) => {
          const active = track === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTrack(t.key)}
              disabled={t.n === 0}
              className="rounded-[6px] px-[11px] py-[6px] text-[12px] font-semibold disabled:cursor-not-allowed disabled:opacity-40"
              style={{
                background: active ? "var(--oasis-home-tint)" : "transparent",
                border: `1px solid ${active ? "var(--oasis-home)" : "var(--oasis-border)"}`,
                color: active ? "var(--oasis-home)" : "var(--oasis-text-muted)",
              }}
            >
              {t.label} <span className="font-mono text-[11px] opacity-70">{t.n}</span>
            </button>
          );
        })}
      </div>

      <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
        {track === "live"
          ? "PREDICTION LEDGER — LIVE, LOCKED BEFORE KICKOFF"
          : track === "backtest"
            ? "PREDICTION LEDGER — BACKTEST REPLAY"
            : "PREDICTION LEDGER — LIVE AND BACKTEST"}
      </div>
      <div className="-mx-1 overflow-x-auto px-1">
      <div className="min-w-[840px]">
      <div className="flex border-b border-[var(--oasis-border)] px-1 py-[10px] font-mono text-[10px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)]">
        <span className="w-24">DATE</span>
        <span className="w-[42px]">LG</span>
        <span className="flex-1">FIXTURE</span>
        <span className="w-[98px]">PUBLISHED</span>
        <span className="w-[98px]">FINAL</span>
        <span className="w-[76px]">RESULT</span>
        <span className="w-[74px] text-right">LOG LOSS</span>
        <span className="w-[74px] text-right">TRACK</span>
        <span className="w-16 text-right">MODEL</span>
      </div>
      {rows.map((r) => (
        <div
          key={`${r.date}-${r.fixture}`}
          className="flex border-b border-[var(--oasis-border-row)] px-1 py-3 font-mono text-[12px] font-medium last:border-b-0"
        >
          <span className="w-24 text-[var(--oasis-text-muted)]">{r.date}</span>
          <span className="w-[42px] text-[var(--oasis-text-muted)]">{r.lg}</span>
          <span className="flex-1 text-[13.5px] font-bold">{r.fixture}</span>
          <span className="w-[98px]">{r.published}</span>
          <span className="w-[98px]">{r.final}</span>
          <span className="flex w-[76px] items-center gap-[4px]" style={{ color: r.won ? "var(--oasis-positive)" : "var(--oasis-warn)" }}>
            {r.result} {r.won ? <IconCheck size={11} strokeWidth={2.2} /> : <IconCross size={10} strokeWidth={2.2} />}
          </span>
          <span className="w-[74px] text-right">{r.logLoss.toFixed(2)}</span>
          <span className="w-[74px] text-right">
            <span
              className="rounded-[4px] border px-[5px] py-[1px] font-mono text-[9.5px] font-bold tracking-[0.05em]"
              style={
                trackOf(r) === "live"
                  ? { borderColor: "var(--oasis-positive)", color: "var(--oasis-positive)" }
                  : { borderColor: "var(--oasis-border-strong)", color: "var(--oasis-text-dim)" }
              }
            >
              {trackOf(r) === "live" ? "LIVE" : "BACKTEST"}
            </span>
          </span>
          <span className="w-16 text-right text-[var(--oasis-text-muted)]" title={r.modelVersion}>
            {r.modelVersion.split(" ")[0]}
          </span>
        </div>
      ))}
      </div>
      </div>
      {rows.length === 0 && (
        <div className="rounded-[10px] border border-dashed border-[var(--oasis-border-strong)] p-5 text-center text-[13px] font-semibold text-[var(--oasis-text-muted)]">
          {track === "live"
            ? "No settled live predictions for this league yet."
            : "No settled predictions for this league yet."}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-[14px] font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
        <span>
          {track === "backtest"
            ? `latest ${rows.length} of ${live.headline.n_test} scored backtest matches`
            : track === "live"
              ? `latest ${rows.length} of ${live.live_record.settled} settled live predictions`
              : `latest ${rows.length} rows · ${counts.live} live, ${counts.backtest} backtest`}
        </span>
        <span className="ml-auto text-[var(--oasis-text-faint)]">
          losses are shown in full — records cannot be removed
        </span>
      </div>
    </div>
  );
}
