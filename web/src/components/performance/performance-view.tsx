"use client";

import { useState } from "react";
import { ModelComparison } from "@/components/performance/model-comparison";
import { PerformanceLedger } from "@/components/performance/performance-ledger";
import { LEAGUE_CODES, LEAGUE_NAMES, utcClock } from "@/lib/data";
import type { LiveData } from "@/lib/data";

const TABS = ["Record", "Model comparison"] as const;
type Tab = (typeof TABS)[number];

export function PerformanceView({ live }: { live: LiveData }) {
  const [tab, setTab] = useState<Tab>("Record");

  return (
    <div className="flex w-full flex-col gap-[14px] p-3 sm:p-5">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <span className="text-[18px] font-extrabold leading-none tracking-[-0.02em] sm:text-[20px]">Performance record</span>
        <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
          {live.live_record.settled > 0 ? (
            <>
              <span className="font-bold text-[var(--oasis-positive)]">
                LIVE: {live.live_record.settled} settled · log loss {live.live_record.log_loss?.toFixed(3)} · accuracy{" "}
                {live.live_record.accuracy?.toFixed(1)}%
              </span>{" "}
              · {live.headline.n_test} backtest matches · nothing edited, nothing deleted
            </>
          ) : (
            <>
              {live.headline.n_test} scored matches · {live.headline.season} · nothing edited, nothing deleted
              {live.live_record.locked > 0 && ` · ${live.live_record.locked} locked, awaiting results`}
            </>
          )}
        </span>
        <span className="ml-auto flex gap-[6px]">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className="cursor-pointer rounded-[6px] px-[12px] py-[6px] text-[12px] font-semibold"
              style={
                t === tab
                  ? { background: "var(--oasis-surface-raised)", border: "1px solid var(--oasis-border-strong)" }
                  : { color: "var(--oasis-text-muted)", border: "1px solid var(--oasis-border)" }
              }
            >
              {t}
            </button>
          ))}
        </span>
      </div>

      {tab === "Record" ? <RecordView live={live} /> : <ModelComparison live={live} />}
    </div>
  );
}

function RecordView({ live }: { live: LiveData }) {
  const liveCodes = new Set(live.league_log_loss.map((r) => r.code));
  const pendingLeagues = LEAGUE_CODES.filter((c) => !liveCodes.has(c));

  return (
    <>
      <div className="grid grid-cols-1 gap-[18px] md:grid-cols-3">
        <div className="flex flex-col gap-[10px]">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            CALIBRATION — PREDICTED vs OBSERVED
          </div>
          <div className="relative h-[186px] overflow-hidden rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)]">
            <div
              className="absolute inset-0"
              style={{
                background:
                  "linear-gradient(to bottom right, transparent calc(50% - 1px), var(--oasis-border-strong) 50%, transparent calc(50% + 1px))",
              }}
            />
            <div className="absolute inset-0 flex items-end justify-around px-3">
              {live.calibration_bars.map((h, i) => (
                <div key={i} className="w-3 rounded-t-[3px]" style={{ height: `${h}%`, background: "var(--oasis-home)" }} />
              ))}
            </div>
            <div className="absolute right-[10px] top-[10px] font-mono text-[10px] font-medium text-[var(--oasis-text-dim)]">
              diagonal = perfect
            </div>
          </div>
          <div className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">
            ECE {live.headline.ece.toFixed(3)} · observed win rate by predicted-probability band · pre-lineup predictions
          </div>
        </div>

        <div className="flex flex-col gap-[10px]">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            BY LEAGUE — LOG LOSS vs BASELINE
          </div>
          <div className="flex flex-col gap-[11px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 font-mono text-[11.5px] font-medium">
            {live.league_log_loss.map((row) => (
              <div
                key={row.code}
                className="flex items-center gap-[10px]"
                title={
                  row.harnessLl
                    ? `5-fold walk-forward mean ${row.harnessLl.toFixed(4)} (vs elo-only ${row.harnessEloLl?.toFixed(4) ?? "—"}) · single 2025/26 test season ${row.modelLl?.toFixed(4)}`
                    : undefined
                }
              >
                <span className="w-[78px] text-[var(--oasis-text-muted)]">{row.label}</span>
                <span className="h-[9px] flex-1 rounded-[5px] bg-[var(--oasis-border-row)]">
                  <span
                    className="block h-full rounded-[5px]"
                    style={{ width: `${row.value}%`, background: row.belowBaseline ? "var(--oasis-positive)" : "var(--oasis-away)" }}
                  />
                </span>
                <span className="w-[76px] text-right">{row.detail}</span>
              </div>
            ))}
            {pendingLeagues.map((code) => (
              <div key={code} className="flex items-center gap-[10px] opacity-60">
                <span className="w-[78px] text-[var(--oasis-text-muted)]">{LEAGUE_NAMES[code]}</span>
                <span className="h-[9px] flex-1 rounded-[5px] border border-dashed border-[var(--oasis-border-strong)]" />
                <span className="w-[76px] text-right text-[var(--oasis-text-dim)]">not live</span>
              </div>
            ))}
            <div className="border-t border-[var(--oasis-border)] pt-[10px] text-[10.5px] text-[var(--oasis-text-dim)]">
              5-season walk-forward mean log loss / frequency baseline — the metric models are selected on (hover a
              row for the single-test-season number)
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-[10px]">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            BY CONFIDENCE BAND
          </div>
          <div className="flex flex-col gap-[9px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 font-mono text-[12px] font-medium">
            <div className="flex text-[10px] tracking-[0.06em] text-[var(--oasis-text-dim)]">
              <span className="flex-1">BAND</span>
              <span className="w-[46px] text-right">N</span>
              <span className="w-[60px] text-right">PRED</span>
              <span className="w-[60px] text-right">ACTUAL</span>
            </div>
            {live.confidence_bands.map((row) => (
              <div key={row.band} className="flex">
                <span className="flex-1">{row.band}</span>
                <span className="w-[46px] text-right text-[var(--oasis-text-muted)]">{row.n}</span>
                <span className="w-[60px] text-right">{row.pred}</span>
                <span className="w-[60px] text-right">{row.actual}</span>
              </div>
            ))}
          </div>
          <div className="flex flex-col gap-[6px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
            <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
              VS CLOSING ODDS
            </div>
            <div className="font-mono text-[12px] font-medium text-[var(--oasis-text-muted)]">no odds archive yet</div>
            <div className="font-mono text-[10.5px] font-medium leading-[1.5] text-[var(--oasis-text-dim)]">
              historical odds cannot be backfilled — snapshot collection started 2026-08-20, and this comparison appears
              once closing odds have been archived and fixtures settle
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-[10px]">
        <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
          DEPLOYED MODEL VERSIONS — REGISTRY
        </div>
        <div className="grid grid-cols-1 gap-[10px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 sm:grid-cols-2 lg:grid-cols-5">
          {live.model_releases.map((r) => (
            <div key={r.lg} className="flex flex-col gap-[4px] rounded-[8px] border border-[var(--oasis-border)] p-[10px]">
              <div className="flex items-baseline justify-between">
                <span className="text-[12.5px] font-bold">{LEAGUE_NAMES[r.lg]}</span>
                <span className="font-mono text-[10px] text-[var(--oasis-text-dim)]">{r.n_releases} releases</span>
              </div>
              <div className="font-mono text-[12.5px] font-semibold text-[var(--oasis-home)]">{r.version}</div>
              <div className="font-mono text-[10.5px] font-medium leading-[1.6] text-[var(--oasis-text-muted)]">
                deployed {r.deployed_at.slice(0, 10)} {utcClock(r.deployed_at)} UTC
                {r.methodology_version && (
                  <>
                    <br />
                    <span className="text-[var(--oasis-text-dim)]">methodology: {r.methodology_version}</span>
                  </>
                )}
                {r.harness_ll != null && (
                  <>
                    <br />
                    {r.harness_folds ?? 5}-fold mean {r.harness_ll.toFixed(4)}
                  </>
                )}
                {r.test_log_loss !== null && (
                  <>
                    <br />
                    <span className="text-[var(--oasis-text-dim)]">test 25/26: {r.test_log_loss.toFixed(4)}</span>
                  </>
                )}
              </div>
              {r.history.length > 1 && (
                <div
                  className="font-mono text-[10px] font-medium text-[var(--oasis-text-faint)]"
                  title={r.history.map((h) => `${h.version} · ${h.registered_at.slice(0, 16).replace("T", " ")}`).join("\n")}
                >
                  prev:{" "}
                  {[...r.history]
                    .reverse()
                    .filter((h) => !h.deployed)
                    .slice(0, 2)
                    .map((h) => h.version)
                    .join(", ") || "—"}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <PerformanceLedger live={live} />
      </div>
    </>
  );
}
