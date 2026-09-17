import { Bone, BoneRow, BoneStats } from "@/components/skeleton";

/** Board skeleton for "/": left rail of league chips, the fixture list in
 * the middle, stat panels on the right. Same three-column grid as the
 * console so the real page lands in place. */
export default function HomeLoading() {
  return (
    <div className="grid w-full grid-cols-1 lg:h-full lg:grid-cols-[212px_1fr_268px] lg:overflow-hidden" aria-busy aria-label="Loading the board">
      <div className="flex flex-col gap-[14px] border-b border-[var(--oasis-border)] bg-[var(--oasis-bg-rail)] px-3 py-2 lg:gap-[22px] lg:border-b-0 lg:border-r lg:p-4">
        <div className="flex gap-[6px] overflow-hidden lg:flex-col lg:gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Bone key={i} className="h-[30px] w-[104px] flex-none rounded-full lg:h-[34px] lg:w-full lg:rounded-[7px]" />
          ))}
        </div>
        <div className="hidden lg:block"><BoneStats rows={3} /></div>
      </div>
      <div className="flex min-w-0 flex-col p-3 sm:p-4">
        <div className="flex items-center gap-2 border-b border-[var(--oasis-border)] pb-3">
          {Array.from({ length: 4 }).map((_, i) => <Bone key={i} className="h-[30px] w-[78px] rounded-[7px]" />)}
        </div>
        <div className="flex items-baseline justify-between py-4">
          <Bone className="h-[20px] w-[160px]" />
          <Bone className="h-[11px] w-[96px]" />
        </div>
        {Array.from({ length: 9 }).map((_, i) => <BoneRow key={i} i={i} />)}
      </div>
      <div className="hidden flex-col gap-6 border-l border-[var(--oasis-border)] bg-[var(--oasis-bg-rail)] p-4 lg:flex">
        <BoneStats rows={2} />
        <BoneStats rows={4} />
        <BoneStats rows={4} />
      </div>
    </div>
  );
}
