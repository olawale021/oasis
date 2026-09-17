import { cn } from "@/lib/utils";

/** A single shimmering placeholder block. Size it with className. */
export function Bone({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <span className={cn("rs-bone block", className)} style={style} aria-hidden />;
}

/** One board row: team names on the left, a probability gauge on the right.
 * Mirrors the real fixture row's footprint so the swap does not jump. */
export function BoneRow({ i = 0 }: { i?: number }) {
  return (
    <div className="flex items-center gap-4 border-b border-[var(--oasis-border-row)] py-[11px]">
      <Bone className="h-[11px] w-[46px]" />
      <div className="flex min-w-0 flex-1 flex-col gap-[6px]">
        <Bone className="h-[12px]" style={{ width: `${44 + ((i * 17) % 30)}%` }} />
        <Bone className="h-[12px]" style={{ width: `${38 + ((i * 23) % 30)}%` }} />
      </div>
      <Bone className="hidden h-[9px] w-[180px] rounded-[5px] sm:block" />
      <Bone className="h-[20px] w-[52px] rounded-[6px]" />
    </div>
  );
}

/** Stat rows for a rail panel: label on the left, value on the right. */
export function BoneStats({ rows = 4, title = true }: { rows?: number; title?: boolean }) {
  return (
    <div className="flex flex-col gap-[10px]">
      {title && <Bone className="h-[10px] w-[120px]" />}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex justify-between gap-3">
          <Bone className="h-[11px] w-[96px]" />
          <Bone className="h-[11px] w-[44px]" />
        </div>
      ))}
    </div>
  );
}

/** Page-level heading placeholder: an overline, a title, a one-line lede. */
export function BoneTitle({ wide = false }: { wide?: boolean }) {
  return (
    <div className="flex flex-col gap-3">
      <Bone className="h-[10px] w-[110px]" />
      <Bone className={cn("h-[28px]", wide ? "w-[360px] max-w-full" : "w-[220px] max-w-full")} />
      <Bone className="h-[12px] w-[520px] max-w-full" />
    </div>
  );
}

/** Document-shaped skeleton for text pages (method, legal, account). */
export function BoneDocument({ sections = 4 }: { sections?: number }) {
  return (
    <div className="mx-auto flex w-full max-w-[860px] flex-col gap-8 p-4 sm:p-6">
      <BoneTitle wide />
      {Array.from({ length: sections }).map((_, i) => (
        <div key={i} className="grid gap-3 border-t border-[var(--oasis-border)] pt-5 sm:grid-cols-[160px_1fr]">
          <Bone className="h-[10px] w-[90px]" />
          <div className="flex flex-col gap-[8px]">
            <Bone className="h-[12px] w-full" />
            <Bone className="h-[12px] w-[92%]" />
            <Bone className="h-[12px] w-[70%]" />
          </div>
        </div>
      ))}
    </div>
  );
}
