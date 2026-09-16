import { Card, Empty, TEXT } from "@/components/admin/ui";
import type { OpsData } from "@/lib/ops";

export function TabLogs({ ops }: { ops: OpsData }) {
  return (
    <Card
      title="matchday.log"
      right={<span className={TEXT.micro}>last {ops.log_tail.length} lines</span>}
      bodyClassName={ops.log_tail.length === 0 ? "p-4" : "p-3"}
    >
      {ops.log_tail.length === 0 ? (
        <Empty>Log is empty until the first cron run.</Empty>
      ) : (
        <pre className="max-h-[70vh] overflow-auto rounded-[6px] bg-[var(--oasis-bg)] p-3 font-mono text-[11.5px] leading-[1.6] text-[var(--oasis-text-soft)]">
          {ops.log_tail.join("\n")}
        </pre>
      )}
    </Card>
  );
}
