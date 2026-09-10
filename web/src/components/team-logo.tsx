import { cn } from "@/lib/utils";

/** Club crest served from /public/logos/{team_id}.png (API-Football ids,
 * downscaled to 96px and committed, so nothing is hotlinked). */
export function TeamLogo({ id, size = 20, className }: { id: number; size?: number; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static asset, sized inline, no optimisation needed
    <img
      src={`/logos/${id}.png`}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      className={cn("inline-block shrink-0 object-contain align-[-0.2em]", className)}
      style={{ width: size, height: size }}
    />
  );
}

/** "⟨crest⟩ Home v Away ⟨crest⟩" on one line. Text styling comes from the
 * parent span so each page keeps its existing type scale. */
export function MatchName({
  home, away, homeId, awayId, size = 20,
}: { home: string; away: string; homeId: number; awayId: number; size?: number }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-[7px]">
      <TeamLogo id={homeId} size={size} />
      <span>{home}</span>
      <span className="font-medium text-[var(--oasis-text-faint)]">v</span>
      <TeamLogo id={awayId} size={size} />
      <span>{away}</span>
    </span>
  );
}

/** One side of a fixture for the home | gauge | away layout: crest hugging
 * the gauge, name truncating away from it. */
export function TeamSide({
  id, name, side, size = 22, className,
}: { id: number; name: string; side: "home" | "away"; size?: number; className?: string }) {
  return (
    <span
      className={cn(
        "flex min-w-0 shrink-0 items-center gap-[8px]",
        side === "home" ? "flex-row-reverse text-right" : "flex-row text-left",
        className,
      )}
    >
      <TeamLogo id={id} size={size} />
      <span className="min-w-0 truncate">{name}</span>
    </span>
  );
}
