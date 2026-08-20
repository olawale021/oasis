import { notFound } from "next/navigation";
import Link from "next/link";
import { ProbabilityBar, ProbabilityLegend } from "@/components/probability-bar";
import {
  HEADLINE,
  LEAGUE_CODES,
  LEAGUE_NAMES,
  LEAGUE_PERF,
  LIVE_LEAGUES,
  MODEL_VERSION,
  STANDINGS,
  matchesByLeague,
} from "@/lib/data";
import { deriveMatch } from "@/lib/derive";
import type { LeagueCode } from "@/lib/types";

export function generateStaticParams() {
  return LEAGUE_CODES.map((code) => ({ code }));
}

function isLeagueCode(value: string): value is LeagueCode {
  return (LEAGUE_CODES as string[]).includes(value);
}

export default async function LeaguePage({ params }: { params: Promise<{ code: string }> }) {
  const { code: rawCode } = await params;
  const code = rawCode.toUpperCase();
  if (!isLeagueCode(code)) notFound();

  const isLive = LIVE_LEAGUES.includes(code);
  const fixtures = matchesByLeague(code).map(deriveMatch);
  const standings = STANDINGS[code] ?? [];
  const perf = LEAGUE_PERF[code];
  const round = fixtures[0]?.round ?? null;

  return (
    <div className="w-full">
      <div className="flex items-center gap-[24px] border-b border-[var(--oasis-border)] bg-[var(--oasis-surface)] px-[22px] py-[14px]">
        {LEAGUE_CODES.map((c) => (
          <Link
            key={c}
            href={`/league/${c}`}
            className="pb-[3px] text-[13.5px] font-semibold"
            style={{
              color: c === code ? "var(--oasis-text)" : "var(--oasis-text-muted)",
              borderBottom: c === code ? "2px solid var(--oasis-home)" : "2px solid transparent",
            }}
          >
            {LEAGUE_NAMES[c]}
          </Link>
        ))}
        <span className="ml-auto font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
          season 2026/27
        </span>
      </div>

      {!isLive ? (
        <div className="flex flex-col items-center gap-3 p-[60px] text-center">
          <div className="text-[17px] font-bold">{LEAGUE_NAMES[code]} is not live yet</div>
          <div className="max-w-[440px] text-[13px] font-medium leading-[1.7] text-[var(--oasis-text-muted)]">
            The model currently covers the Premier League only. La Liga, Serie A, Bundesliga and MLS are next
            (Phase 2): each gets its own independently trained and calibrated model before any predictions are
            published here.
          </div>
          <Link href="/league/EPL" className="mt-1 text-[12.5px] font-bold text-[var(--oasis-home)]">
            View Premier League →
          </Link>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-[9px] border-b border-[var(--oasis-border)] px-[22px] py-[11px]">
            {round && (
              <span className="rounded-[6px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-surface-raised)] px-[11px] py-[6px] text-[12px] font-semibold">
                {round}
              </span>
            )}
            <span className="ml-auto font-mono text-[11.5px] font-medium text-[var(--oasis-text-dim)]">
              {LEAGUE_NAMES[code]} · model {MODEL_VERSION}
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr]">
            <div className="flex flex-col gap-3 border-b border-[var(--oasis-border)] p-5 px-[20px] lg:border-b-0 lg:border-r">
              <div className="flex items-center justify-between font-mono text-[10.5px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
                <span>FIXTURES &amp; PREDICTIONS — {LEAGUE_NAMES[code]}</span>
                <ProbabilityLegend />
              </div>
              {fixtures.map((m) => (
                <Link
                  key={m.id}
                  href={`/match/${m.id}`}
                  className="flex items-center gap-[14px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px] transition-colors hover:border-[var(--oasis-border-strong)]"
                >
                  <span className="flex w-[250px] flex-col gap-[3px]">
                    <span className="text-[15px] font-bold tracking-[-0.01em]">
                      {m.home} <span className="font-medium text-[var(--oasis-text-faint)]">v</span> {m.away}
                    </span>
                    <span
                      className="font-mono text-[11.5px] font-medium"
                      style={{ color: m.statusConfirmed ? "var(--oasis-positive)" : "var(--oasis-text-muted)" }}
                    >
                      {m.ko} UTC · {m.st}
                    </span>
                  </span>
                  <ProbabilityBar home={m.h} draw={m.d} away={m.a} height={22} labeled className="flex-1" />
                  <span className="w-[52px] text-right font-mono text-[13.5px] font-medium">{m.score}</span>
                </Link>
              ))}
              {fixtures.length === 0 && (
                <div className="rounded-[10px] border border-dashed border-[var(--oasis-border-strong)] p-5 text-center text-[13px] font-semibold text-[var(--oasis-text-muted)]">
                  No upcoming fixtures in the prediction horizon.
                </div>
              )}

              <div className="mt-1 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[14px]">
                <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
                  BACKTEST RECORD — {HEADLINE.season.toUpperCase()}
                </div>
                <div className="mt-[5px] font-mono text-[12px] font-medium leading-[1.8] text-[var(--oasis-text-muted)]">
                  {HEADLINE.n_test} matches · log loss {HEADLINE.log_loss.toFixed(3)} · accuracy{" "}
                  {HEADLINE.accuracy.toFixed(1)}% · RPS {HEADLINE.rps.toFixed(3)}
                </div>
                <Link href="/performance" className="mt-1 inline-block text-[11.5px] font-bold text-[var(--oasis-home)]">
                  Open full ledger →
                </Link>
              </div>
            </div>

            <div className="flex flex-col gap-3 p-5 px-[20px]">
              <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
                STANDINGS
              </div>
              <div className="overflow-hidden rounded-[10px] border border-[var(--oasis-border)]">
                <div className="flex border-b border-[var(--oasis-border)] px-3 py-[9px] font-mono text-[10px] font-semibold tracking-[0.07em] text-[var(--oasis-text-dim)]">
                  <span className="w-[26px]">#</span>
                  <span className="flex-1">TEAM</span>
                  <span className="w-7 text-right">P</span>
                  <span className="w-[38px] text-right">GD</span>
                  <span className="w-9 text-right">PTS</span>
                  <span className="w-[52px] text-right">ELO</span>
                </div>
                {standings.map((row, i) => (
                  <div
                    key={row.team}
                    className="flex items-center border-b border-[var(--oasis-border-row)] px-3 py-[10px] font-mono text-[12px] font-medium last:border-b-0"
                    style={{ background: i % 2 ? "transparent" : "rgba(255,255,255,.015)" }}
                  >
                    <span className="w-[26px] text-[var(--oasis-text-dim)]">{i + 1}</span>
                    <span className="flex-1 text-[13px] font-bold">{row.team}</span>
                    <span className="w-7 text-right text-[var(--oasis-text-muted)]">{row.played}</span>
                    <span className="w-[38px] text-right text-[var(--oasis-text-muted)]">{row.goalDiff}</span>
                    <span className="w-9 text-right">{row.points}</span>
                    <span className="w-[52px] text-right text-[var(--oasis-text-muted)]">{row.elo}</span>
                  </div>
                ))}
              </div>
              <div className="font-mono text-[10px] font-medium text-[var(--oasis-text-faint)]">
                Elo replayed over ten seasons of results, promoted teams carry adjusted second-division ratings.
              </div>

              <div className="mt-1 font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
                {LEAGUE_NAMES[code].toUpperCase()} MODEL RECORD
              </div>
              <div className="flex gap-[22px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[14px]">
                <Stat label="LOG LOSS" value={perf.ll} />
                <Stat label="vs BASELINE" value={perf.base} color="var(--oasis-positive)" />
                <Stat label="vs MARKET" value={perf.mkt} />
              </div>
              <div className="font-mono text-[10px] font-medium leading-[1.6] text-[var(--oasis-text-faint)]">
                Held-out 2025/26 backtest. Lower log loss is better; negative vs baseline means the model beats league
                frequency. Market comparison starts once odds collection begins.
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] font-semibold tracking-[0.09em] text-[var(--oasis-text-dim)]">{label}</div>
      <div className="font-mono text-[21px] font-medium" style={{ color }}>
        {value}
      </div>
    </div>
  );
}
