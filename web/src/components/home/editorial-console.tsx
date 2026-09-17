"use client";

import { Logo } from "@/components/logo";

import Link from "next/link";
import { LEAGUE_NAMES, utcClock } from "@/lib/data";
import type { LiveData } from "@/lib/data";
import { deriveMatch, sortByKickoff } from "@/lib/derive";
import { MatchName } from "@/components/team-logo";

export function EditorialConsole({ live }: { live: LiveData }) {
  // Highest-conviction forecast first: largest gap between best and worst outcome.
  const rows = sortByKickoff(live.matches.map(deriveMatch));
  const featured =
    [...rows].sort(
      (x, y) => Math.max(y.h, y.a) - Math.min(y.h, y.a) - (Math.max(x.h, x.a) - Math.min(x.h, x.a)),
    )[0] ?? null;
  const secondary = rows.filter((m) => m.id !== featured?.id).slice(0, 2);

  return (
    <div className="w-full">
      <div className="flex items-center gap-[22px] border-b border-[var(--oasis-border)] bg-[var(--oasis-surface)] px-5 py-[14px]">
        <div className="flex items-center gap-[9px]">
          <Logo size={17} />
        </div>
        <div className="flex gap-[18px] text-[13px] font-semibold">
          <span>Today</span>
          <span className="text-[var(--oasis-text-muted)]">Leagues</span>
          <span className="text-[var(--oasis-text-muted)]">Record</span>
        </div>
        <span className="ml-auto rounded-[7px] border border-[var(--oasis-border-strong)] px-3 py-[6px] text-[12px] font-bold">
          Sign in
        </span>
      </div>

      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-baseline justify-between">
          <span className="text-[21px] font-extrabold leading-none tracking-[-0.02em]">Upcoming forecasts</span>
          <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
            {LEAGUE_NAMES.ALL} · {rows.length} {rows.length === 1 ? "match" : "matches"} · published{" "}
            {utcClock(live.predictions_generated_at)} UTC
          </span>
        </div>

        {featured && (
          <div className="flex flex-col gap-[14px] rounded-[12px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-surface)] p-[18px]">
            <div className="flex items-baseline gap-3">
              <span className="text-[18px] font-extrabold leading-none tracking-[-0.02em]">
                {featured.home} <span className="font-medium text-[var(--oasis-text-faint)]">v</span> {featured.away}
              </span>
              <span className="font-mono text-[11px] font-medium text-[var(--oasis-text-muted)]">{featured.metaLabel}</span>
              <span className="ml-auto rounded-[5px] bg-[var(--oasis-positive-tint)] px-2 py-1 font-mono text-[11px] font-bold text-[var(--oasis-positive)]">
                {featured.conf} confidence
              </span>
            </div>

            <div className="flex flex-col gap-[9px]">
              <ProbabilityRow label={featured.home} value={featured.h} color="var(--oasis-home)" />
              <ProbabilityRow label="Draw" value={featured.d} color="var(--oasis-draw)" />
              <ProbabilityRow label={featured.away} value={featured.a} color="var(--oasis-away)" />
            </div>

            <div className="flex flex-wrap gap-2 font-mono text-[11px] font-medium text-[var(--oasis-text-muted)]">
              <span className="rounded-[6px] border border-[var(--oasis-border)] px-[9px] py-1">
                likely {featured.score}
              </span>
              <span className="rounded-[6px] border border-[var(--oasis-border)] px-[9px] py-1">
                {featured.marketLabel ? `market ${featured.marketLabel}` : "market — no odds yet"}
              </span>
            </div>

            <div className="border-t border-[var(--oasis-border)] pt-3 text-[13px] font-medium leading-[1.7] text-[var(--oasis-text-soft)]">
              {featured.why}
            </div>
          </div>
        )}

        {secondary.map((m) => (
          <Link
            key={m.id}
            href={`/match/${m.id}`}
            className="flex items-center gap-4 rounded-[11px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[15px] transition-colors hover:border-[var(--oasis-border-strong)]"
          >
            <span className="flex flex-1 flex-col gap-[3px]">
              <span className="text-[15px] font-bold tracking-[-0.01em]">
                <MatchName home={m.home} away={m.away} homeId={m.homeId} awayId={m.awayId} size={20} />
              </span>
              <span
                className="font-mono text-[10.5px] font-medium"
                style={{ color: m.statusConfirmed ? "var(--oasis-positive)" : "var(--oasis-text-muted)" }}
              >
                {m.metaLabel}
              </span>
            </span>
            <span className="w-[200px]">
              <span className="flex h-[9px] overflow-hidden rounded-[5px] bg-[var(--oasis-border-row)]">
                <span style={{ width: `${m.h}%`, background: "var(--oasis-home)" }} />
                <span style={{ width: `${m.d}%`, background: "var(--oasis-draw)" }} />
                <span style={{ width: `${m.a}%`, background: "var(--oasis-away)" }} />
              </span>
            </span>
            <span className="w-[78px] text-right font-mono text-[12px] font-medium">{m.probsLabel}</span>
            <span className="w-12 text-right font-mono text-[12.5px] font-medium">{m.score}</span>
          </Link>
        ))}

        <div
          className="flex items-center gap-4 rounded-[11px] p-4"
          style={{
            border: "1px solid var(--oasis-border-strong)",
            background: "linear-gradient(120deg,rgba(77,156,246,.1),rgba(47,207,154,.06))",
          }}
        >
          <div className="flex-1">
            <div className="text-[15px] font-bold">Every match, full explanations</div>
            <div className="mt-[3px] font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
              founding lifetime · one-time purchase · opens at paid launch
            </div>
          </div>
          <span className="rounded-[7px] bg-[var(--oasis-home)] px-[15px] py-[9px] text-[12.5px] font-bold text-[var(--oasis-home-ink)]">
            See pricing
          </span>
        </div>

        <div className="flex gap-3">
          <div className="flex-1 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px]">
            <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
              BACKTEST RECORD
            </div>
            <div className="mt-1 font-mono text-[12.5px] font-medium leading-[1.7] text-[var(--oasis-text-muted)]">
              log loss {live.headline.log_loss.toFixed(3)}
              <br />
              {live.headline.n_test} matches · {live.headline.season.replace(" (backtest)", "")}
            </div>
          </div>
          <div className="flex-1 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px]">
            <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
              TELEGRAM
            </div>
            <div className="mt-1 font-mono text-[12.5px] font-medium leading-[1.7] text-[var(--oasis-text-muted)]">
              daily digest
              <br />
              lineup-change alerts
            </div>
          </div>
        </div>

        <div className="font-mono text-[10px] font-medium leading-[1.6] text-[var(--oasis-text-faint)]">
          Probabilistic forecasts, not guarantees and not betting advice. 18+ · responsible use.
        </div>
      </div>
    </div>
  );
}

function ProbabilityRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-3 font-mono text-[12px] font-medium">
      <span className="w-24 text-[var(--oasis-text-muted)]">{label}</span>
      <span className="h-[11px] flex-1 rounded-[6px] bg-[var(--oasis-border-row)]">
        <span className="block h-full rounded-[6px]" style={{ width: `${value}%`, background: color }} />
      </span>
      <span className="w-11 text-right">{value.toFixed(0)}%</span>
    </div>
  );
}
