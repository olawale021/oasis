import { Card, Empty, Pill, Stat, TABLE, TEXT } from "@/components/admin/ui";
import { cn } from "@/lib/utils";
import { ago, clock, duration, stamp, type LockState, type OpsData } from "@/lib/ops";

const LOCK: Record<LockState, { label: string; tone: "muted" | "good" | "warn" | "bad" | "info" }> = {
  final:   { label: "final",   tone: "info" },
  locked:  { label: "locked",  tone: "good" },
  pending: { label: "pending", tone: "muted" },
  due:     { label: "due",     tone: "warn" },
  missed:  { label: "missed",  tone: "bad" },
};

export function TabOverview({ ops, now }: { ops: OpsData; now: number }) {
  const s = ops.ledger_summary;
  const upcoming = ops.upcoming_locks;
  const needsAttention = upcoming.filter((u) => u.state === "due" || u.state === "missed").length;
  const oddsAge = ops.freshness.odds_last_fetched ? now - Date.parse(ops.freshness.odds_last_fetched) : null;
  const oddsStale = oddsAge != null && oddsAge > 3 * 3600e3;
  const failures = ops.runs.filter((r) => !r.ok).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat k="locked" v={s.locked} sub={`${s.awaiting_result} awaiting result`} />
        <Stat k="settled" v={s.settled} sub={s.log_loss != null ? `log loss ${s.log_loss.toFixed(3)}` : "no scores yet"} />
        <Stat
          k="accuracy"
          v={s.accuracy != null ? `${Math.round(s.accuracy * 100)}%` : "—"}
          sub={s.brier != null ? `brier ${s.brier.toFixed(3)}` : "—"}
          tone={s.accuracy == null ? "plain" : s.accuracy >= 0.5 ? "good" : "plain"}
        />
        <Stat
          k="needs attention"
          v={needsAttention}
          sub={`of ${upcoming.length} in next 72h`}
          tone={needsAttention > 0 ? "warn" : "good"}
        />
        <Stat
          k="odds data"
          v={oddsAge == null ? "—" : `${Math.round(oddsAge / 3600e3)}h`}
          sub={`${ops.freshness.odds_fixtures_24h} fixtures / 24h`}
          tone={oddsStale ? "warn" : "good"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.7fr]">
        <Card
          title="Run history"
          right={<span className={TEXT.micro}>{ops.runs.length} runs · {failures} failed</span>}
        >
          {ops.runs.length === 0 ? (
            <Empty>No runs recorded yet. History starts with the first cron run after this deploy.</Empty>
          ) : (
            <>
              <div className="flex flex-wrap gap-[4px]">
                {ops.runs.map((r) => (
                  <span
                    key={r.ts}
                    title={`${stamp(r.ts)} · ${r.ok ? `ok ${duration(r.duration_s)}` : `failed at ${r.failed_step}`}`}
                    className={cn("h-[15px] w-[15px] rounded-[3px]", r.ok ? "bg-[var(--oasis-positive)]" : "bg-[var(--oasis-away)]")}
                  />
                ))}
              </div>
              <div className="mt-[14px] space-y-[3px]">
                {ops.runs.slice(-6).reverse().map((r) => (
                  <div key={r.ts} className="flex justify-between font-mono text-[11.5px]">
                    <span className="text-[var(--oasis-text-muted)]">{stamp(r.ts)}</span>
                    <span className={r.ok ? "text-[var(--oasis-positive)]" : "text-[var(--oasis-away)]"}>
                      {r.ok ? duration(r.duration_s) : `fail: ${r.failed_step}`}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>

        <Card
          title="Lock schedule · next 72h"
          right={
            <span className={TEXT.micro}>
              window {ops.lock_window_minutes} min{needsAttention > 0 ? ` · ${needsAttention} need attention` : ""}
            </span>
          }
          bodyClassName="p-0"
        >
          {upcoming.length === 0 ? (
            <div className="p-4"><Empty>No predicted fixtures in the next 72 hours.</Empty></div>
          ) : (
            <div className="max-h-[360px] overflow-auto"><div className="min-w-[560px]">
              <table className="w-full">
                <thead className="sticky top-0 bg-[var(--oasis-surface)]">
                  <tr className="border-b border-[var(--oasis-border)]">
                    <th className={TABLE.th}>kickoff</th><th className={TABLE.th}>lg</th>
                    <th className={TABLE.th}>match</th><th className={TABLE.th}>lock by</th>
                    <th className={TABLE.th}>run</th><th className={TABLE.th}>state</th>
                  </tr>
                </thead>
                <tbody>
                  {upcoming.map((u) => (
                    <tr key={u.fixture_id} className="border-t border-[var(--oasis-border-row)] hover:bg-[var(--oasis-hover-row)]">
                      <td className={cn(TABLE.td, "whitespace-nowrap")}>{stamp(u.kickoff_utc)}</td>
                      <td className={cn(TABLE.td, "text-[var(--oasis-text-dim)]")}>{u.league}</td>
                      <td className={TABLE.tdText}>{u.home} <span className="text-[var(--oasis-text-dim)]">v</span> {u.away}</td>
                      <td className={cn(TABLE.td, "text-[var(--oasis-text-muted)]")}>{clock(u.lock_by)}</td>
                      <td className={cn(TABLE.td, "text-[var(--oasis-text-muted)]")}>{clock(u.expected_run)}</td>
                      <td className={TABLE.td}><Pill tone={LOCK[u.state].tone}>{LOCK[u.state].label}</Pill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div></div>
          )}
        </Card>
      </div>

      <p className={cn(TEXT.micro, "text-[var(--oasis-text-faint)]")}>
        Snapshot generated {stamp(ops.generated_at)} UTC on the server and pushed to KV ({ago(ops.generated_at, now)}).
        The site cannot reach the droplet; a silent server shows as stale here.
      </p>
    </div>
  );
}
