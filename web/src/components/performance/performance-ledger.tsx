"use client";

import { useMemo, useState } from "react";
import { LEAGUE_CODES, LEAGUE_NAMES } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import type { LeagueFilter } from "@/lib/types";

export function PerformanceLedger({ live }: { live: LiveData }) {
  const [league, setLeague] = useState<LeagueFilter>("ALL");

  const rows = useMemo(() => live.ledger.filter((r) => league === "ALL" || r.lg === league), [league, live.ledger]);

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

      <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
        PREDICTION live.ledger — BACKTEST
      </div>
      <div className="-mx-1 overflow-x-auto px-1">
      <div className="min-w-[760px]">
      <div className="flex border-b border-[var(--oasis-border)] px-1 py-[10px] font-mono text-[10px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)]">
        <span className="w-24">DATE</span>
        <span className="w-[42px]">LG</span>
        <span className="flex-1">FIXTURE</span>
        <span className="w-[98px]">PUBLISHED</span>
        <span className="w-[98px]">FINAL</span>
        <span className="w-[76px]">RESULT</span>
        <span className="w-[74px] text-right">LOG LOSS</span>
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
          <span className="w-[76px]" style={{ color: r.won ? "var(--oasis-positive)" : "var(--oasis-warn)" }}>
            {r.result} {r.won ? "✓" : "✗"}
          </span>
          <span className="w-[74px] text-right">{r.logLoss.toFixed(2)}</span>
          <span className="w-16 text-right text-[var(--oasis-text-muted)]" title={r.modelVersion}>
            {r.modelVersion.split(" ")[0]}
          </span>
        </div>
      ))}
      </div>
      </div>
      {rows.length === 0 && (
        <div className="rounded-[10px] border border-dashed border-[var(--oasis-border-strong)] p-5 text-center text-[13px] font-semibold text-[var(--oasis-text-muted)]">
          No settled predictions for this league yet.
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-[14px] font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
        <span>
          latest {rows.length} of {live.headline.n_test} scored backtest matches
        </span>
        <span className="ml-auto text-[var(--oasis-text-faint)]">
          losses are shown in full — records cannot be removed
        </span>
      </div>
    </div>
  );
}
