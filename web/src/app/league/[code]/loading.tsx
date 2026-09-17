import { Bone, BoneRow, BoneStats } from "@/components/skeleton";

export default function LeagueLoading() {
  return (
    <div className="w-full" aria-busy aria-label="Loading league">
      <div className="flex items-center gap-[24px] border-b border-[var(--oasis-border)] bg-[var(--oasis-surface)] px-4 py-4 sm:px-[22px]">
        {Array.from({ length: 5 }).map((_, i) => <Bone key={i} className="h-[13px] w-[92px]" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr]">
        <div className="flex flex-col border-b border-[var(--oasis-border)] p-4 sm:p-5 lg:border-b-0 lg:border-r">
          {Array.from({ length: 8 }).map((_, i) => <BoneRow key={i} i={i} />)}
        </div>
        <div className="flex flex-col gap-6 p-4 sm:p-5">
          <BoneStats rows={10} />
        </div>
      </div>
    </div>
  );
}
