"use client";

import { LEAGUE_NAMES, utcClock } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import type { ReleaseHistoryEntry } from "@/lib/types";

interface Row {
  entry: ReleaseHistoryEntry;
  /** Primary value: 5-fold harness mean when the harness ran this version,
   * else the single test season (marked with *). */
  primary: number;
  isHarness: boolean;
  registrations: number;
}

/** Release-by-release model evolution per league. The primary number is the
 * 5-fold walk-forward mean — the metric releases are selected on; versions
 * the harness never evaluated fall back to the single test season, marked *.
 * Consecutive registrations of the same version collapse into one row. */
export function ModelComparison({ live }: { live: LiveData }) {
  return (
    <div className="flex flex-col gap-[14px]">
      <div className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 text-[12.5px] font-medium leading-[1.7] text-[var(--oasis-text-soft)]">
        Every registered release per league, oldest to newest. The headline number is the{" "}
        <span className="font-bold">5-fold walk-forward mean log loss (2021–2025 test seasons)</span> — the metric
        releases are selected on; the single 2025/26 test season is shown dimmed alongside (a value marked{" "}
        <span className="font-mono">*</span> means the harness never evaluated that version, so its single season
        stands in). Lower is better; longer bar = better. <span className="font-bold text-[var(--oasis-positive)]">Green</span>{" "}
        = improved on the previous release, <span className="font-bold text-[var(--oasis-away)]">amber</span> = regressed.
      </div>

      {live.model_releases.map((release) => {
        // Collapse consecutive registrations of the same version.
        const rows: Row[] = [];
        for (const h of release.history) {
          if (h.test_log_loss === null && h.harness_ll == null) continue;
          const prev = rows[rows.length - 1];
          if (prev && prev.entry.version === h.version) {
            rows[rows.length - 1] = {
              entry: h,
              primary: (h.harness_ll ?? h.test_log_loss) as number,
              isHarness: h.harness_ll != null,
              registrations: prev.registrations + 1,
            };
            continue;
          }
          rows.push({
            entry: h,
            primary: (h.harness_ll ?? h.test_log_loss) as number,
            isHarness: h.harness_ll != null,
            registrations: 1,
          });
        }

        const references: { label: string; sub: string; value: number }[] = [];
        if (release.harness_freq_ll != null)
          references.push({
            label: "frequency baseline",
            sub: "always predicts league frequencies · 5-fold mean",
            value: release.harness_freq_ll,
          });
        if (release.harness_elo_ll != null)
          references.push({
            label: "elo-only baseline",
            sub: "calibrated Elo, nothing else · 5-fold mean",
            value: release.harness_elo_ll,
          });

        const all = [...rows.map((r) => r.primary), ...references.map((r) => r.value)];
        const worst = Math.max(...all);
        const best = Math.min(...all);
        const span = Math.max(worst - best, 0.01);
        const barPct = (v: number) => 25 + 75 * ((worst - v) / span);

        const first = rows[0];
        const last = rows[rows.length - 1];
        const overall = first && last && first !== last ? first.primary - last.primary : null;

        return (
          <div key={release.lg} className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-[15px] font-bold">{LEAGUE_NAMES[release.lg]}</span>
              <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
                {release.n_releases} registrations · deployed: {release.version}
              </span>
              {overall !== null && (
                <span
                  className="ml-auto font-mono text-[11.5px] font-bold"
                  style={{ color: overall >= 0 ? "var(--oasis-positive)" : "var(--oasis-away)" }}
                  title="change in 5-fold harness mean between the first and current release"
                >
                  {overall >= 0 ? "▼" : "▲"} {Math.abs(overall).toFixed(4)} since first release
                </span>
              )}
            </div>

            <div className="mt-3 flex flex-col gap-[8px]">
              {references.map((ref) => (
                <BarRow
                  key={ref.label}
                  label={ref.label}
                  sub={ref.sub}
                  value={ref.value}
                  secondary={null}
                  pct={barPct(ref.value)}
                  color="var(--oasis-border-strong)"
                  dim
                />
              ))}
              {rows.map((r, i) => {
                const delta = i > 0 ? rows[i - 1].primary - r.primary : null;
                const h = r.entry;
                return (
                  <BarRow
                    key={`${h.version}-${h.registered_at}`}
                    label={`${h.version}${r.registrations > 1 ? ` ×${r.registrations}` : ""}`}
                    sub={`${h.registered_at.slice(0, 10)} ${utcClock(h.registered_at)} UTC${h.features > 0 ? ` · ${h.features} features` : ""}${
                      h.test_accuracy !== null ? ` · acc ${(h.test_accuracy * 100).toFixed(1)}%` : ""
                    }`}
                    value={r.primary}
                    starred={!r.isHarness}
                    secondary={r.isHarness && h.test_log_loss !== null ? h.test_log_loss : null}
                    pct={barPct(r.primary)}
                    color={h.deployed ? "var(--oasis-home)" : "#2b3a52"}
                    deployed={h.deployed}
                    delta={delta}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BarRow({
  label,
  sub,
  value,
  secondary,
  pct,
  color,
  deployed = false,
  dim = false,
  starred = false,
  delta = null,
}: {
  label: string;
  sub: string;
  value: number;
  secondary: number | null;
  pct: number;
  color: string;
  deployed?: boolean;
  dim?: boolean;
  starred?: boolean;
  delta?: number | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-[12px] gap-y-[4px] sm:flex-nowrap" style={{ opacity: dim ? 0.65 : 1 }}>
      <span className="flex w-full flex-col sm:w-[230px]">
        <span className="font-mono text-[12px] font-semibold">
          {label}
          {deployed && (
            <span className="ml-[6px] rounded-[4px] bg-[var(--oasis-positive-tint)] px-[5px] py-[1px] text-[9px] font-bold text-[var(--oasis-positive)]">
              DEPLOYED
            </span>
          )}
        </span>
        <span className="font-mono text-[10px] font-medium text-[var(--oasis-text-dim)]">{sub}</span>
      </span>
      <span className="h-[10px] min-w-[60px] flex-1 rounded-[5px] bg-[var(--oasis-border-row)]">
        <span className="block h-full rounded-[5px]" style={{ width: `${pct}%`, background: color }} />
      </span>
      <span className="w-[76px] text-right font-mono text-[12px] font-medium" title={starred ? "single 2025/26 test season — harness never ran this version" : "5-fold walk-forward mean"}>
        {value.toFixed(4)}
        {starred ? "*" : ""}
      </span>
      <span
        className="hidden w-[86px] text-right font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)] sm:block"
        title="single 2025/26 test season"
      >
        {secondary !== null ? `test ${secondary.toFixed(4)}` : ""}
      </span>
      <span
        className="w-[86px] text-right font-mono text-[11px] font-medium"
        style={{
          color:
            delta === null
              ? "var(--oasis-text-faint)"
              : delta >= 0
                ? "var(--oasis-positive)"
                : "var(--oasis-away)",
        }}
      >
        {delta === null ? "—" : `${delta >= 0 ? "▼" : "▲"} ${Math.abs(delta).toFixed(4)}`}
      </span>
    </div>
  );
}
