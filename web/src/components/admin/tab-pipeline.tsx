import { Card, Row, TEXT } from "@/components/admin/ui";
import { cn } from "@/lib/utils";
import { ago, clock, stamp, uptime, type OpsData } from "@/lib/ops";

export function TabPipeline({ ops, now }: { ops: OpsData; now: number }) {
  const host = ops.host;
  const memUsed = host.mem_total_mb != null && host.mem_available_mb != null ? host.mem_total_mb - host.mem_available_mb : null;
  const diskPct = host.disk_total_gb ? Math.round((host.disk_used_gb! / host.disk_total_gb) * 100) : null;
  const errored = ops.steps.filter((s) => s.error);

  return (
    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <Card
        title="Pipeline steps"
        right={<span className={TEXT.micro}>{ops.steps.filter((s) => s.ok).length}/{ops.steps.length} ok</span>}
      >
        <div className="divide-y divide-[var(--oasis-border-row)]">
          {ops.steps.map((s) => {
            const counts = Object.entries(s.counts).filter((e): e is [string, number] => typeof e[1] === "number");
            return (
              <div key={s.key} className="py-[9px] first:pt-0 last:pb-0">
                <div className="flex items-center gap-[10px]">
                  <span
                    className={cn(
                      "h-[7px] w-[7px] shrink-0 rounded-full",
                      s.ok == null ? "bg-[var(--oasis-border-strong)]" : s.ok ? "bg-[var(--oasis-positive)]" : "bg-[var(--oasis-away)]",
                    )}
                  />
                  <span className="min-w-0 flex-1 truncate font-sans text-[12.5px] font-semibold">{s.label}</span>
                  <span className="flex shrink-0 items-center gap-[10px] font-mono text-[11px] text-[var(--oasis-text-muted)]">
                    {s.ok === false && <span className="font-bold text-[var(--oasis-away)]">fail</span>}
                    <span>{clock(s.refreshed_at)}</span>
                    <span className="w-[34px] text-right text-[var(--oasis-text-dim)]">
                      {s.duration_ms != null ? `${(s.duration_ms / 1000).toFixed(0)}s` : "—"}
                    </span>
                  </span>
                </div>
                {counts.length > 0 && (
                  <div className="mt-[6px] flex flex-wrap gap-x-[10px] gap-y-[3px] pl-[17px]">
                    {counts.map(([k, v]) => (
                      <span key={k} className={cn(TEXT.micro, "whitespace-nowrap")}>
                        <span className="font-sans">{k.replace(/_/g, " ")}</span>{" "}
                        <span className="text-[var(--oasis-text-muted)]">{v.toLocaleString()}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {errored.length > 0 && (
          <pre className="mt-3 overflow-x-auto rounded-[6px] bg-[var(--oasis-bg)] p-3 font-mono text-[11px] leading-[1.5] text-[var(--oasis-away)]">
            {errored.map((s) => `${s.key}: ${s.error}`).join("\n")}
          </pre>
        )}
      </Card>

      <div className="space-y-4">
        <Card title="Server">
          <Row k="host" v={host.hostname} />
          <Row k="os" v={host.os} />
          <Row k="uptime" v={uptime(host.uptime_s)} />
          <Row k="load (1m)" v={host.load_1m ?? "—"} warn={(host.load_1m ?? 0) > 1.5} />
          <Row k="memory" v={memUsed != null ? `${memUsed} / ${host.mem_total_mb} MB` : "—"} warn={memUsed != null && memUsed > 800} />
          <Row k="disk" v={diskPct != null ? `${host.disk_used_gb} / ${host.disk_total_gb} GB (${diskPct}%)` : "—"} warn={(diskPct ?? 0) > 80} />
          <Row k="runtime" v={`py ${host.python} · node ${host.node ?? "?"}`} />
          <Row k="commit" v={host.git_commit ?? "—"} />
          <Row k="cron" v={host.cron ? host.cron.split(" ").slice(0, 5).join(" ") : "not installed"} warn={!host.cron} />
        </Card>

        <Card title="Data freshness">
          <Row
            k="odds last fetched"
            v={ago(ops.freshness.odds_last_fetched, now)}
            warn={now - Date.parse(ops.freshness.odds_last_fetched ?? "0") > 3 * 3600e3}
          />
          <Row k="odds rows (24h)" v={`${ops.freshness.odds_rows_24h.toLocaleString()} · ${ops.freshness.odds_fixtures_24h} fixtures`} />
          <Row k="last result" v={stamp(ops.freshness.last_result_kickoff)} />
          <Row k="results pending" v={ops.freshness.results_pending} warn={ops.freshness.results_pending > 0} />
          <Row k="fixtures next 8d" v={ops.freshness.fixtures_next_8d} />
          <Row k="predictions" v={ago(ops.freshness.predictions_generated_at, now)} />
          <Row k="live.json" v={ago(ops.freshness.live_json_generated_at, now)} />
        </Card>
      </div>
    </div>
  );
}
