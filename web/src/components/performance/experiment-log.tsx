import type { Experiment, ExperimentRow } from "@/lib/types";
import { LEAGUE_NAMES } from "@/lib/data";
import type { LeagueFilter } from "@/lib/types";

const FLOOR = 0.001;

function deltaTone(r: ExperimentRow): string {
  if (r.delta <= -FLOOR) return "text-[var(--oasis-positive)]";
  if (r.delta >= FLOOR) return "text-[var(--oasis-away)]";
  return "text-[var(--oasis-text-dim)]";
}

function leagueLabel(lg: string): string {
  if (lg === "ALL") return "All leagues";
  return LEAGUE_NAMES[lg as LeagueFilter] ?? lg;
}

const th = "px-2 py-[6px] text-left font-mono text-[10.5px] font-medium uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]";
const td = "px-2 py-[7px] text-[12.5px] whitespace-nowrap";

export function ExperimentLog({ experiments }: { experiments: Experiment[] }) {
  if (!experiments.length) {
    return <p className="text-[12.5px] text-[var(--oasis-text-muted)]">No experiment reports exported yet.</p>;
  }
  const shippedCount = experiments.flatMap((e) => e.rows).filter((r) => r.shipped).length;
  return (
    <div className="flex flex-col gap-[14px]">
      <div className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4 text-[12.5px] leading-[1.6] text-[var(--oasis-text-soft)]">
        Every candidate is judged on the walk-forward harness: mean log loss across held-out seasons 2021 to 2025, refit each time on
        earlier seasons only. A candidate ships in a league only if it improves that mean by at least {FLOOR}. Single-season wins
        do not count. Negative change is better. {shippedCount} league-level results below have shipped; the rest are recorded so
        the same idea is not retried without new data.
      </div>
      {experiments.map((e) => (
        <section key={e.key} className="rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)]">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-[var(--oasis-border)] px-4 py-[10px]">
            <span className="text-[14px] font-extrabold">{e.label}</span>
            <span className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]">{e.metric}</span>
            <span className="ml-auto font-mono text-[10.5px] text-[var(--oasis-text-dim)]">{e.rows[0]?.ran_at}</span>
          </div>
          <p className="px-4 pt-3 text-[12.5px] leading-[1.6] text-[var(--oasis-text-muted)]">{e.blurb}</p>
          <div className="overflow-x-auto px-2 pb-2 pt-1">
            <table className="w-full">
              <thead>
                <tr>
                  <th className={th}>{e.rows.some((r) => r.label) ? "candidate" : "league"}</th>
                  <th className={th}>before</th>
                  <th className={th}>after</th>
                  <th className={th}>change</th>
                  <th className={th}>folds won</th>
                  <th className={th}>status</th>
                </tr>
              </thead>
              <tbody>
                {e.rows.map((r, i) => (
                  <tr key={`${r.lg}-${r.label ?? i}`} className="border-t border-[var(--oasis-border-row)]">
                    <td className={`${td} font-semibold`}>
                      {r.label ?? leagueLabel(r.lg)}
                      {r.detail && <span className="ml-2 font-mono text-[10.5px] font-normal text-[var(--oasis-text-dim)]">{r.detail}</span>}
                    </td>
                    <td className={`${td} font-mono text-[var(--oasis-text-muted)]`}>{r.before.toFixed(4)}</td>
                    <td className={`${td} font-mono`}>{r.after.toFixed(4)}</td>
                    <td className={`${td} font-mono font-bold ${deltaTone(r)}`}>
                      {r.delta > 0 ? "+" : ""}
                      {r.delta.toFixed(4)}
                    </td>
                    <td className={`${td} font-mono text-[var(--oasis-text-muted)]`}>
                      {r.folds_won === null ? "—" : `${r.folds_won} / ${r.folds}`}
                    </td>
                    <td className={td}>
                      <span
                        className="rounded-[4px] border px-[6px] py-[1px] font-mono text-[10.5px]"
                        style={
                          r.shipped
                            ? { color: "var(--oasis-positive)", borderColor: "var(--oasis-positive)" }
                            : { color: "var(--oasis-text-dim)", borderColor: "var(--oasis-border-strong)" }
                        }
                      >
                        {r.shipped ? "shipped" : "not shipped"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
