"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LEAGUE_NAMES } from "@/lib/data";
import type { MatchRecord } from "@/lib/types";
import { TeamLogo } from "@/components/team-logo";

function fmt(ms: number): string {
  if (ms <= 0) return "kicking off";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h >= 24) return `in ${Math.floor(h / 24)}d ${h % 24}h`;
  if (h > 0) return `in ${h}h ${m.toString().padStart(2, "0")}m`;
  return `in ${m}m ${sec.toString().padStart(2, "0")}s`;
}

/** Live countdown to the next kickoff in the horizon. Ticks every second;
 * the seconds only show inside the final hour so it reads calm until it
 * matters. Renders nothing before hydration so SSR and client agree. */
export function NextKickoff({ matches }: { matches: MatchRecord[] }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (now === null) return null;
  const next = matches
    .filter((m) => Date.parse(m.kickoffUtc) > now - 5 * 60 * 1000)
    .sort((a, b) => a.kickoffUtc.localeCompare(b.kickoffUtc))[0];
  if (!next) return null;
  const ms = Date.parse(next.kickoffUtc) - now;
  const lockBy = new Date(Date.parse(next.kickoffUtc) - 70 * 60 * 1000);
  const lockLabel = `${lockBy.getUTCHours().toString().padStart(2, "0")}:${lockBy.getUTCMinutes().toString().padStart(2, "0")}`;
  return (
    <Link
      href={`/match/${next.id}`}
      className="flex flex-col gap-[7px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-[13px] transition-colors hover:border-[var(--oasis-border-strong)]"
    >
      <span className="flex items-center gap-[7px] font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
        <span className="rs-pulse block h-[6px] w-[6px] rounded-full bg-[var(--oasis-home)]" />
        NEXT KICKOFF
      </span>
      <span className="flex items-center gap-[7px] text-[13px] font-bold">
        <TeamLogo id={next.homeId} size={18} />
        <span className="truncate">{next.home}</span>
        <span className="text-[var(--oasis-text-dim)]">v</span>
        <TeamLogo id={next.awayId} size={18} />
        <span className="truncate">{next.away}</span>
      </span>
      <span className="font-mono text-[18px] font-bold leading-none tabular-nums" style={{ color: ms < 3600e3 ? "var(--oasis-positive)" : "var(--oasis-text)" }}>
        {fmt(ms)}
      </span>
      <span className="font-mono text-[10.5px] text-[var(--oasis-text-muted)]">
        {LEAGUE_NAMES[next.lg]} · {next.ko} UTC · forecast locks by {lockLabel}
      </span>
    </Link>
  );
}
