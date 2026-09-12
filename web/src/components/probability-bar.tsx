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
      className={`rs-locked flex min-w-0 items-center justify-center overflow-hidden rounded-[5px] font-mono text-[10.5px] font-semibold tracking-[0.08em] text-[var(--oasis-text-dim)] ${className}`}
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

const OUTCOME_BG = ["var(--oasis-home)", "var(--oasis-draw)", "var(--oasis-away)"];
const OUTCOME_INK = ["var(--oasis-home-ink)", "var(--oasis-text)", "#1a1206"];

/** Settled-result gauge: the model's locked forecast as the main bar, the
 * bookmaker consensus as a thin line beneath it, and the outcome that
 * actually happened outlined on the bar and lit on the line. `delayMs`
 * staggers the load-in down a list. */
export function TwinBar({
  model, market, outcome, height = 26, line = 7, delayMs = 0, className = "",
}: {
  model: [number, number, number];
  market: [number, number, number] | null;
  outcome: 0 | 1 | 2 | null;
  height?: number;
  line?: number;
  delayMs?: number;
  className?: string;
}) {
  const labels = ["home win", "draw", "away win"];
  return (
    <span className={`flex min-w-0 flex-col gap-[3px] ${className}`}>
      <span
        className="rs-fill flex w-full min-w-0 overflow-hidden rounded-[5px] bg-[var(--oasis-border-row)]"
        style={{ height, animationDelay: `${delayMs}ms` }}
      >
        {model.map((v, i) => (
          <span
            key={i}
            className="flex items-center justify-center overflow-hidden whitespace-nowrap font-mono text-[11px] font-bold sm:text-[12.5px]"
            style={{
              width: `${v}%`, background: OUTCOME_BG[i], color: OUTCOME_INK[i],
              boxShadow: outcome === i ? "inset 0 0 0 2px var(--oasis-text)" : undefined,
            }}
            title={`our forecast · ${labels[i]} ${v.toFixed(1)}%`}
          >
            {v >= 12 ? `${Math.round(v)}%` : ""}
          </span>
        ))}
      </span>
      {market ? (
        <span
          className="rs-fill flex w-full min-w-0 overflow-hidden rounded-[3px] bg-[var(--oasis-border-row)]"
          style={{ height: line, animationDelay: `${delayMs + 160}ms` }}
          title="bookmaker consensus at lock time · margin removed"
        >
          {market.map((v, i) => (
            <span
              key={i}
              className="rs-mkt block"
              style={{ width: `${v}%`, height: line, background: OUTCOME_BG[i], opacity: outcome === i ? 1 : 0.45 }}
              title={`market · ${labels[i]} ${v.toFixed(1)}%`}
            />
          ))}
        </span>
      ) : (
        <span className="flex w-full rounded-[3px] border border-dashed border-[var(--oasis-border)]" style={{ height: line }} title="no odds snapshot at lock time" />
      )}
    </span>
  );
}
