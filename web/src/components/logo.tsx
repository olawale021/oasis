/** RealscoreAI mark "2E · Edge bars": three ascending bars (dim, muted,
 * edge-green) beside a weight-split wordmark. Reproduced from the approved
 * design file; header sizes are the design's dark-row values. */
export function EdgeBars({ size = 18, className = "" }: { size?: number; className?: string }) {
  // Design ratios at 18px tall: bars 3px wide, 2px gap, heights 7/12/18.
  const w = Math.max(2, Math.round(size / 6));
  const gap = Math.max(1, Math.round(size / 9));
  const hs = [7 / 18, 12 / 18, 1].map((f) => Math.round(size * f));
  return (
    <span className={`flex items-end ${className}`} style={{ gap, height: size }} aria-hidden="true">
      <span style={{ width: w, height: hs[0], background: "var(--oasis-draw)" }} />
      <span style={{ width: w, height: hs[1], background: "var(--oasis-text-muted)" }} />
      <span style={{ width: w, height: hs[2], background: "var(--oasis-positive)" }} />
    </span>
  );
}

export function Wordmark({ size = 19, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`flex items-baseline leading-none ${className}`} style={{ fontSize: size, letterSpacing: "-0.045em" }}>
      <span className="font-semibold">Realscore</span>
      <span className="font-normal">AI</span>
    </span>
  );
}

export function Logo({ size = 19, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`flex items-end gap-[8px] ${className}`}>
      <EdgeBars size={Math.round(size * (18 / 19))} className="mb-[3px]" />
      <Wordmark size={size} />
    </span>
  );
}
