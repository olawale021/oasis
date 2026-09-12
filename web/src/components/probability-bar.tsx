interface ProbabilityBarProps {
  home: number;
  draw: number;
  away: number;
  height?: number;
  /** Render the percentage inside each segment (when wide enough to fit). */
  labeled?: boolean;
  className?: string;
}

/** Stacked home/draw/away probability gauge. Give it a width via className
 * (e.g. flex-1 or w-full) — the inner segments are percentage-sized, so the
 * bar has no intrinsic width of its own. */
export function ProbabilityBar({ home, draw, away, height = 9, labeled = false, className = "" }: ProbabilityBarProps) {
  const segment = (value: number, background: string, color: string, label: string) => (
    <span
      className="flex items-center justify-center overflow-hidden whitespace-nowrap font-mono text-[11px] font-bold sm:text-[12.5px]"
      style={{ width: `${value}%`, background, color }}
      title={`${label} ${value.toFixed(1)}%`}
    >
      {labeled && value >= 12 ? `${Math.round(value)}%` : ""}
    </span>
  );

  return (
    <span className={`flex min-w-0 overflow-hidden rounded-[5px] bg-[var(--oasis-border-row)] ${className}`} style={{ height }}>
      {segment(home, "var(--oasis-home)", "var(--oasis-home-ink)", "home win")}
      {segment(draw, "var(--oasis-draw)", "var(--oasis-text)", "draw")}
      {segment(away, "var(--oasis-away)", "#1a1206", "away win")}
    </span>
  );
}

/** Legend for the gauge colors — use once above a list of bars. */
export function ProbabilityLegend() {
  return (
    <span className="flex items-center gap-[14px]">
      {(
        [
          ["HOME", "var(--oasis-home)"],
          ["DRAW", "var(--oasis-draw)"],
          ["AWAY", "var(--oasis-away)"],
        ] as const
      ).map(([label, color]) => (
        <span key={label} className="flex items-center gap-[5px]">
          <span className="h-[8px] w-[8px] rounded-[2px]" style={{ background: color }} />
          {label}
        </span>
      ))}
    </span>
  );
}

/** Placeholder rendered in place of a gauge the viewer is not entitled to
 * see. Same footprint as ProbabilityBar so rows keep their layout. */
export function LockedBar({ height = 9, className = "", label = "locked" }: { height?: number; className?: string; label?: string }) {
  return (
    <span
      className={`flex min-w-0 items-center justify-center overflow-hidden rounded-[5px] font-mono text-[10.5px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)] ${className}`}
      style={{
        height,
        background:
          "repeating-linear-gradient(135deg, var(--oasis-border-row) 0 6px, var(--oasis-surface-raised) 6px 12px)",
        border: "1px solid var(--oasis-border)",
      }}
      title="Prediction locked for your access level"
    >
      {height >= 18 ? `🔒 ${label.toUpperCase()}` : ""}
    </span>
  );
}
