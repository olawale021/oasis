import { Card, Empty, Stat, TABLE, TEXT } from "@/components/admin/ui";
import { cn } from "@/lib/utils";
import { clock, stamp, type OpsData } from "@/lib/ops";
import { IconCheck, IconCross } from "@/components/icons";

const pct = (x: number | null) => (x == null ? "—" : `${Math.round(x)}%`);

export function TabLedger({ ops }: { ops: OpsData }) {
  const s = ops.ledger_summary;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat k="locked" v={s.locked} />
        <Stat k="awaiting" v={s.awaiting_result} />
        <Stat k="settled" v={s.settled} />
        <Stat k="log loss" v={s.log_loss?.toFixed(3) ?? "—"} />
        <Stat k="brier" v={s.brier?.toFixed(3) ?? "—"} />
        <Stat
          k="accuracy"
          v={s.accuracy != null ? `${Math.round(s.accuracy * 100)}%` : "—"}
          tone={s.accuracy == null ? "plain" : s.accuracy >= 0.5 ? "good" : "plain"}
        />
      </div>

      <Card
        title="Locked predictions"
        right={<span className={TEXT.micro}>latest {ops.ledger.length}</span>}
        bodyClassName={ops.ledger.length === 0 ? "p-4" : "p-0"}
      >
        {ops.ledger.length === 0 ? (
          <Empty>Nothing locked yet. Rows appear when a cron run lands inside the lock window before kickoff.</Empty>
        ) : (
          <div className="max-h-[620px] overflow-auto"><div className="min-w-[880px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-[var(--oasis-surface)]">
                <tr className="border-b border-[var(--oasis-border)]">
                  <th className={TABLE.th}>kickoff</th><th className={TABLE.th}>lg</th><th className={TABLE.th}>match</th>
                  <th className={TABLE.th}>h / d / a</th><th className={TABLE.th}>market</th><th className={TABLE.th}>conf</th>
                  <th className={TABLE.th}>locked</th><th className={TABLE.th}>result</th><th className={TABLE.th}>ll</th>
                  <th className={TABLE.th}>hit</th>
                </tr>
              </thead>
              <tbody>
                {ops.ledger.map((r) => (
                  <tr key={r.fixture_id} className="border-t border-[var(--oasis-border-row)] hover:bg-[var(--oasis-hover-row)]">
                    <td className={cn(TABLE.td, "whitespace-nowrap")}>{stamp(r.kickoff_utc)}</td>
                    <td className={cn(TABLE.td, "text-[var(--oasis-text-dim)]")}>{r.league_code}</td>
                    <td className={TABLE.tdText}>{r.home} <span className="text-[var(--oasis-text-dim)]">v</span> {r.away}</td>
                    <td className={cn(TABLE.td, "whitespace-nowrap")}>{pct(r.p_home)} / {pct(r.p_draw)} / {pct(r.p_away)}</td>
                    <td className={cn(TABLE.td, "whitespace-nowrap text-[var(--oasis-text-muted)]")}>
                      {r.market_p_home != null ? `${pct(r.market_p_home)} / ${pct(r.market_p_draw)} / ${pct(r.market_p_away)}` : "—"}
                    </td>
                    <td className={cn(TABLE.td, "text-[var(--oasis-text-dim)]")}>{r.confidence}</td>
                    <td className={cn(TABLE.td, "text-[var(--oasis-text-muted)]")}>{clock(r.locked_at)}</td>
                    <td className={cn(TABLE.td, "whitespace-nowrap")}>
                      {r.settled_at ? `${r.result_home}-${r.result_away}` : <span className="text-[var(--oasis-text-dim)]">awaiting</span>}
                    </td>
                    <td className={cn(TABLE.td, "text-[var(--oasis-text-muted)]")}>{r.log_loss?.toFixed(2) ?? "—"}</td>
                    <td className={cn(TABLE.td, r.correct === 1 ? "text-[var(--oasis-positive)]" : r.correct === 0 ? "text-[var(--oasis-away)]" : "")}>
                      {r.correct == null ? "—" : r.correct ? <IconCheck size={12} strokeWidth={2.2} /> : <IconCross size={11} strokeWidth={2.2} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div></div>
        )}
      </Card>
    </div>
  );
}
