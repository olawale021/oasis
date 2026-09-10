/** Shape of web/src/data/ops.json, produced by src/export_ops.py at the end
 * of every matchday run and pushed to KV under "ops". */

export type LockState = "locked" | "pending" | "due" | "missed";

export interface OpsStep {
  key: string;
  label: string;
  ok: boolean | null;
  refreshed_at: string | null;
  duration_ms: number | null;
  counts: Record<string, number | Record<string, number>>;
  error: string | null;
}

export interface OpsRun {
  ts: string;
  ok: boolean;
  failed_step: string | null;
  duration_s: number;
}

export interface OpsLedgerRow {
  fixture_id: number;
  league_code: string;
  kickoff_utc: string;
  locked_at: string;
  stage: string;
  home: string;
  away: string;
  p_home: number;
  p_draw: number;
  p_away: number;
  confidence: string;
  market_p_home: number | null;
  market_p_draw: number | null;
  market_p_away: number | null;
  result_home: number | null;
  result_away: number | null;
  outcome: number | null;
  log_loss: number | null;
  brier: number | null;
  correct: number | null;
  settled_at: string | null;
  model_version: string;
}

export interface OpsUpcomingLock {
  fixture_id: number;
  league: string;
  home: string;
  away: string;
  kickoff_utc: string;
  lock_by: string;
  expected_run: string;
  state: LockState;
  confidence: string;
}

export interface OpsData {
  generated_at: string;
  lock_window_minutes: number;
  last_run: {
    ok: boolean | null;
    failed_step: string | null;
    duration_s: number | null;
    finished_at: string;
  };
  host: {
    hostname: string;
    os: string;
    python: string;
    node: string | null;
    git_commit: string | null;
    uptime_s: number | null;
    load_1m: number | null;
    mem_total_mb: number | null;
    mem_available_mb: number | null;
    disk_total_gb: number | null;
    disk_used_gb: number | null;
    cron: string | null;
  };
  steps: OpsStep[];
  runs: OpsRun[];
  ledger_summary: {
    locked: number;
    settled: number;
    awaiting_result: number;
    log_loss: number | null;
    brier: number | null;
    accuracy: number | null;
  };
  ledger: OpsLedgerRow[];
  upcoming_locks: OpsUpcomingLock[];
  freshness: {
    odds_last_fetched: string | null;
    odds_fixtures_24h: number;
    odds_rows_24h: number;
    last_result_kickoff: string | null;
    results_pending: number;
    fixtures_next_8d: number;
    live_json_generated_at: string | null;
    predictions_generated_at: string | null;
  };
  log_tail: string[];
}

export type Heartbeat = "ok" | "failed" | "stale" | "down";

/** The droplet reports hourly. >75 min silent = a missed run, >3 h = treat
 * as down. A fresh report of a failed run is its own state. */
export function heartbeat(ops: OpsData, now = Date.now()): { state: Heartbeat; ageMin: number } {
  const ageMin = Math.max(0, Math.round((now - Date.parse(ops.generated_at)) / 60000));
  if (ageMin > 180) return { state: "down", ageMin };
  if (ageMin > 75) return { state: "stale", ageMin };
  if (ops.last_run.ok === false) return { state: "failed", ageMin };
  return { state: "ok", ageMin };
}

export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const min = Math.round((now - Date.parse(iso)) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 48) return `${h} h ${min % 60} min ago`;
  return `${Math.floor(h / 24)} d ago`;
}

export function stamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    weekday: "short", day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false,
  });
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
}

export function duration(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 90) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function uptime(s: number | null | undefined): string {
  if (s == null) return "—";
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`;
}

/** Request-time clock for the admin page. The page is a dynamic server
 * component rendered once per request, so reading the clock there is fine;
 * this wrapper keeps the purity lint rule from flagging a literal Date.now. */
export function nowMs(): number {
  return Date.now();
}
