import { PerformanceLedger } from "@/components/performance/performance-ledger";
import { CALIBRATION_BARS, CONFIDENCE_BANDS, HEADLINE, LEAGUE_CODES, LEAGUE_LOG_LOSS, LEAGUE_NAMES } from "@/lib/data";

export default function PerformancePage() {
  const liveCodes = new Set(LEAGUE_LOG_LOSS.map((r) => r.code));
  const pendingLeagues = LEAGUE_CODES.filter((c) => !liveCodes.has(c));

  return (
    <div className="flex w-full flex-col gap-[14px] p-5">
      <div className="flex flex-wrap items-baseline gap-4 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <span className="text-[20px] font-extrabold leading-none tracking-[-0.02em]">Performance record</span>
        <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
          {HEADLINE.n_test} scored matches · {HEADLINE.season} · nothing edited, nothing deleted
        </span>
        <span className="ml-auto font-mono text-[11px] font-medium text-[var(--oasis-text-dim)]">
          live locked predictions begin with the 2026/27 season
        </span>
      </div>

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
              {CALIBRATION_BARS.map((h, i) => (
                <div key={i} className="w-3 rounded-t-[3px]" style={{ height: `${h}%`, background: "var(--oasis-home)" }} />
              ))}
            </div>
            <div className="absolute right-[10px] top-[10px] font-mono text-[10px] font-medium text-[var(--oasis-text-dim)]">
              diagonal = perfect
            </div>
          </div>
          <div className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">
            ECE {HEADLINE.ece.toFixed(3)} · observed win rate by predicted-probability band · pre-lineup predictions
          </div>
        </div>

        <div className="flex flex-col gap-[10px]">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            BY LEAGUE — LOG LOSS vs BASELINE
          </div>
          <div className="flex flex-col gap-[11px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 font-mono text-[11.5px] font-medium">
            {LEAGUE_LOG_LOSS.map((row) => (
              <div key={row.code} className="flex items-center gap-[10px]">
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
              model log loss / league-frequency baseline · remaining leagues arrive in Phase 2
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
            {CONFIDENCE_BANDS.map((row) => (
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
            <div className="font-mono text-[12px] font-medium text-[var(--oasis-text-muted)]">
              no odds archive yet
            </div>
            <div className="font-mono text-[10.5px] font-medium leading-[1.5] text-[var(--oasis-text-dim)]">
              historical odds cannot be backfilled — snapshot collection starts at launch, and this comparison
              appears once closing odds have been archived
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <PerformanceLedger />
      </div>
    </div>
  );
}
