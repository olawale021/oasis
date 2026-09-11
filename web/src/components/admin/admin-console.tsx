import { logoutAction } from "@/app/admin/actions";
import { cn } from "@/lib/utils";
import {
  ago, clock, duration, heartbeat, stamp, uptime,
  type Heartbeat, type LockState, type OpsData,
} from "@/lib/ops";

const HB: Record<Heartbeat, { label: string; dot: string; text: string; blurb: string }> = {
  ok:     { label: "Server reporting", dot: "bg-[var(--oasis-positive)]", text: "text-[var(--oasis-positive)]", blurb: "Last hourly run succeeded." },
  failed: { label: "Last run failed",  dot: "bg-[var(--oasis-away)]",     text: "text-[var(--oasis-away)]",     blurb: "The server is up but the chain stopped at a step. See the log below." },
  stale:  { label: "Missed a run",     dot: "bg-[var(--oasis-warn)]",     text: "text-[var(--oasis-warn)]",     blurb: "No report for over 75 minutes. Cron may have skipped or the run is hanging." },
  down:   { label: "Server silent",    dot: "bg-[var(--oasis-away)]",     text: "text-[var(--oasis-away)]",     blurb: "No report for over 3 hours. Check the droplet: ssh oasis@143.110.170.181" },
};

const LOCK: Record<LockState, { label: string; cls: string }> = {
  final:   { label: "final",   cls: "text-[var(--oasis-home)] border-[var(--oasis-home)]" },
  locked:  { label: "locked",  cls: "text-[var(--oasis-positive)] border-[var(--oasis-positive)]" },
  pending: { label: "pending", cls: "text-[var(--oasis-text-muted)] border-[var(--oasis-border-strong)]" },
  due:     { label: "due",     cls: "text-[var(--oasis-warn)] border-[var(--oasis-warn)]" },
  missed:  { label: "missed",  cls: "text-[var(--oasis-away)] border-[var(--oasis-away)]" },
};

function Card({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)]", className)}>
      <h2 className="border-b border-[var(--oasis-border)] px-4 py-[10px] font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--oasis-text-dim)]">
        {title}
      </h2>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Row({ k, v, warn }: { k: string; v: React.ReactNode; warn?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-[var(--oasis-border-row)] py-[6px] text-[12.5px] last:border-0">
      <span className="text-[var(--oasis-text-muted)]">{k}</span>
      <span className={cn("font-mono text-right", warn ? "text-[var(--oasis-warn)]" : "text-[var(--oasis-text)]")}>{v}</span>
    </div>
  );
}

function Tile({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="rounded-[8px] border border-[var(--oasis-border)] bg-[var(--oasis-bg)] px-3 py-2">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]">{k}</div>
      <div className="mt-[2px] font-mono text-[18px] font-bold leading-tight">{v}</div>
    </div>
  );
}

const th = "px-2 py-[6px] text-left font-mono text-[10.5px] font-medium uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]";
const td = "px-2 py-[6px] text-[12px] whitespace-nowrap";

export function AdminConsole({ ops, liveGeneratedAt, now }: { ops: OpsData; liveGeneratedAt: string; now: number }) {
  const hb = heartbeat(ops, now);
  const h = HB[hb.state];
  const host = ops.host;
  const memUsed = host.mem_total_mb != null && host.mem_available_mb != null ? host.mem_total_mb - host.mem_available_mb : null;
  const diskPct = host.disk_total_gb ? Math.round((host.disk_used_gb! / host.disk_total_gb) * 100) : null;
  const upcoming = ops.upcoming_locks;
  const dueOrMissed = upcoming.filter((u) => u.state === "due" || u.state === "missed").length;
  const fmtPct = (x: number | null) => (x == null ? "—" : `${Math.round(x)}%`);

  return (
    <div className="mx-auto w-full max-w-[1280px] px-4 py-5 sm:px-[22px]">
      {/* Status strip */}
      <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] px-4 py-3">
        <div className="flex items-center gap-[9px]">
          <span className={cn("h-[9px] w-[9px] rounded-full", h.dot)} />
          <span className={cn("font-sans text-[15px] font-extrabold", h.text)}>{h.label}</span>
        </div>
        <span className="text-[12.5px] text-[var(--oasis-text-muted)]">{h.blurb}</span>
        <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[11.5px] text-[var(--oasis-text-dim)]">
          <span>report {ago(ops.generated_at, now)}</span>
          <span>run {ops.last_run.ok === false ? `failed at ${ops.last_run.failed_step}` : duration(ops.last_run.duration_s)}</span>
          <span>site data {ago(liveGeneratedAt, now)}</span>
          <form action={logoutAction}>
            <button type="submit" className="rounded-[6px] border border-[var(--oasis-border-strong)] px-2 py-[3px] text-[11px] text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]">
              sign out
            </button>
          </form>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Server">
          <Row k="host" v={`${host.hostname} · ${host.os}`} />
          <Row k="uptime" v={uptime(host.uptime_s)} />
          <Row k="load (1m)" v={host.load_1m ?? "—"} warn={(host.load_1m ?? 0) > 1.5} />
          <Row k="memory" v={memUsed != null ? `${memUsed} / ${host.mem_total_mb} MB` : "—"} warn={memUsed != null && memUsed > 800} />
          <Row k="disk" v={diskPct != null ? `${host.disk_used_gb} / ${host.disk_total_gb} GB (${diskPct}%)` : "—"} warn={(diskPct ?? 0) > 80} />
          <Row k="runtime" v={`py ${host.python} · node ${host.node ?? "?"}`} />
          <Row k="commit" v={host.git_commit ?? "—"} />
          <Row k="cron" v={host.cron ? host.cron.split(" ").slice(0, 5).join(" ") : "not installed"} warn={!host.cron} />
        </Card>

        <Card title="Pipeline steps">
          <table className="w-full">
            <thead><tr><th className={th}>step</th><th className={th}>ok</th><th className={th}>at</th><th className={th}>took</th><th className={th}>counts</th></tr></thead>
            <tbody>
              {ops.steps.map((s) => (
                <tr key={s.key} className="border-t border-[var(--oasis-border-row)]">
                  <td className={td}>{s.label}</td>
                  <td className={cn(td, "font-mono", s.ok === false ? "text-[var(--oasis-away)]" : "text-[var(--oasis-positive)]")}>{s.ok == null ? "—" : s.ok ? "ok" : "fail"}</td>
                  <td className={cn(td, "font-mono text-[var(--oasis-text-muted)]")}>{clock(s.refreshed_at)}</td>
                  <td className={cn(td, "font-mono text-[var(--oasis-text-muted)]")}>{s.duration_ms != null ? `${(s.duration_ms / 1000).toFixed(0)}s` : "—"}</td>
                  <td className={cn(td, "font-mono text-[11px] text-[var(--oasis-text-dim)] whitespace-normal")}>
                    {Object.entries(s.counts).filter(([, v]) => typeof v === "number").map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {ops.steps.some((s) => s.error) && (
            <pre className="mt-3 overflow-x-auto rounded-[6px] bg-[var(--oasis-bg)] p-2 font-mono text-[11px] text-[var(--oasis-away)]">
              {ops.steps.filter((s) => s.error).map((s) => `${s.key}: ${s.error}`).join("\n")}
            </pre>
          )}
        </Card>

        <Card title={`Run history · last ${ops.runs.length || 0}`}>
          {ops.runs.length === 0 ? (
            <p className="text-[12.5px] text-[var(--oasis-text-muted)]">No runs recorded yet. History starts with the first cron run after this deploy.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-[4px]">
                {ops.runs.map((r) => (
                  <span
                    key={r.ts}
                    title={`${stamp(r.ts)} · ${r.ok ? `ok ${duration(r.duration_s)}` : `failed at ${r.failed_step}`}`}
                    className={cn("h-[14px] w-[14px] rounded-[3px]", r.ok ? "bg-[var(--oasis-positive)]" : "bg-[var(--oasis-away)]")}
                  />
                ))}
              </div>
              <div className="mt-3 space-y-[2px] font-mono text-[11.5px] text-[var(--oasis-text-muted)]">
                {ops.runs.slice(-6).reverse().map((r) => (
                  <div key={r.ts} className="flex justify-between">
                    <span>{stamp(r.ts)}</span>
                    <span className={r.ok ? "text-[var(--oasis-positive)]" : "text-[var(--oasis-away)]"}>{r.ok ? duration(r.duration_s) : `fail: ${r.failed_step}`}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_2fr]">
        <div className="space-y-4">
          <Card title="Live ledger">
            <div className="grid grid-cols-3 gap-2">
              <Tile k="locked" v={ops.ledger_summary.locked} />
              <Tile k="awaiting" v={ops.ledger_summary.awaiting_result} />
              <Tile k="settled" v={ops.ledger_summary.settled} />
            </div>
            <div className="mt-3">
              <Row k="log loss" v={ops.ledger_summary.log_loss?.toFixed(3) ?? "—"} />
              <Row k="brier" v={ops.ledger_summary.brier?.toFixed(3) ?? "—"} />
              <Row k="accuracy" v={ops.ledger_summary.accuracy != null ? `${Math.round(ops.ledger_summary.accuracy * 100)}%` : "—"} />
            </div>
          </Card>
          <Card title="Data freshness">
            <Row k="odds last fetched" v={ago(ops.freshness.odds_last_fetched, now)} warn={now - Date.parse(ops.freshness.odds_last_fetched ?? "0") > 3 * 3600e3} />
            <Row k="odds rows (24h)" v={`${ops.freshness.odds_rows_24h.toLocaleString()} · ${ops.freshness.odds_fixtures_24h} fixtures`} />
            <Row k="last result" v={stamp(ops.freshness.last_result_kickoff)} />
            <Row k="results pending" v={ops.freshness.results_pending} warn={ops.freshness.results_pending > 0} />
            <Row k="fixtures next 8d" v={ops.freshness.fixtures_next_8d} />
            <Row k="predictions" v={ago(ops.freshness.predictions_generated_at, now)} />
            <Row k="live.json" v={ago(ops.freshness.live_json_generated_at, now)} />
          </Card>
        </div>

        <Card title={`Lock schedule · next 72h · window ${ops.lock_window_minutes} min${dueOrMissed ? ` · ${dueOrMissed} need attention` : ""}`}>
          {upcoming.length === 0 ? (
            <p className="text-[12.5px] text-[var(--oasis-text-muted)]">No predicted fixtures in the next 72 hours.</p>
          ) : (
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full">
                <thead><tr><th className={th}>kickoff</th><th className={th}>lg</th><th className={th}>match</th><th className={th}>lock by</th><th className={th}>run</th><th className={th}>state</th></tr></thead>
                <tbody>
                  {upcoming.map((u) => (
                    <tr key={u.fixture_id} className="border-t border-[var(--oasis-border-row)]">
                      <td className={cn(td, "font-mono")}>{stamp(u.kickoff_utc)}</td>
                      <td className={cn(td, "font-mono text-[var(--oasis-text-dim)]")}>{u.league}</td>
                      <td className={cn(td, "whitespace-normal")}>{u.home} <span className="text-[var(--oasis-text-dim)]">v</span> {u.away}</td>
                      <td className={cn(td, "font-mono text-[var(--oasis-text-muted)]")}>{clock(u.lock_by)}</td>
                      <td className={cn(td, "font-mono text-[var(--oasis-text-muted)]")}>{clock(u.expected_run)}</td>
                      <td className={td}><span className={cn("rounded-[4px] border px-[6px] py-[1px] font-mono text-[10.5px]", LOCK[u.state].cls)}>{LOCK[u.state].label}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Card title={`Locked predictions · latest ${ops.ledger.length}`} className="mt-4">
        {ops.ledger.length === 0 ? (
          <p className="text-[12.5px] text-[var(--oasis-text-muted)]">Nothing locked yet. Rows appear when a cron run lands inside the lock window before kickoff.</p>
        ) : (
          <div className="max-h-[480px] overflow-auto">
            <table className="w-full">
              <thead><tr>
                <th className={th}>kickoff</th><th className={th}>lg</th><th className={th}>match</th><th className={th}>h / d / a</th><th className={th}>market</th><th className={th}>conf</th><th className={th}>locked</th><th className={th}>result</th><th className={th}>ll</th><th className={th}>hit</th>
              </tr></thead>
              <tbody>
                {ops.ledger.map((r) => (
                  <tr key={r.fixture_id} className="border-t border-[var(--oasis-border-row)]">
                    <td className={cn(td, "font-mono")}>{stamp(r.kickoff_utc)}</td>
                    <td className={cn(td, "font-mono text-[var(--oasis-text-dim)]")}>{r.league_code}</td>
                    <td className={cn(td, "whitespace-normal")}>{r.home} <span className="text-[var(--oasis-text-dim)]">v</span> {r.away}</td>
                    <td className={cn(td, "font-mono")}>{fmtPct(r.p_home)} / {fmtPct(r.p_draw)} / {fmtPct(r.p_away)}</td>
                    <td className={cn(td, "font-mono text-[var(--oasis-text-muted)]")}>{r.market_p_home != null ? `${fmtPct(r.market_p_home)} / ${fmtPct(r.market_p_draw)} / ${fmtPct(r.market_p_away)}` : "—"}</td>
                    <td className={cn(td, "font-mono text-[var(--oasis-text-dim)]")}>{r.confidence}</td>
                    <td className={cn(td, "font-mono text-[var(--oasis-text-muted)]")}>{clock(r.locked_at)}</td>
                    <td className={cn(td, "font-mono")}>{r.settled_at ? `${r.result_home}-${r.result_away}` : <span className="text-[var(--oasis-text-dim)]">awaiting</span>}</td>
                    <td className={cn(td, "font-mono text-[var(--oasis-text-muted)]")}>{r.log_loss?.toFixed(2) ?? "—"}</td>
                    <td className={cn(td, "font-mono", r.correct === 1 ? "text-[var(--oasis-positive)]" : r.correct === 0 ? "text-[var(--oasis-away)]" : "")}>{r.correct == null ? "—" : r.correct ? "✓" : "✗"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`matchday.log · last ${ops.log_tail.length} lines`} className="mt-4">
        {ops.log_tail.length === 0 ? (
          <p className="text-[12.5px] text-[var(--oasis-text-muted)]">Log is empty until the first cron run.</p>
        ) : (
          <pre className="max-h-[360px] overflow-auto rounded-[6px] bg-[var(--oasis-bg)] p-3 font-mono text-[11px] leading-[1.5] text-[var(--oasis-text-soft)]">
            {ops.log_tail.join("\n")}
          </pre>
        )}
      </Card>

      <p className="mt-4 font-mono text-[10.5px] text-[var(--oasis-text-faint)]">
        Snapshot generated {stamp(ops.generated_at)} UTC on the server and pushed to KV. The site cannot reach the droplet; a silent server shows as stale here.
      </p>
    </div>
  );
}
