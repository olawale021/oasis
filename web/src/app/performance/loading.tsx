import { Bone, BoneRow, BoneStats } from "@/components/skeleton";

export default function PerformanceLoading() {
  return (
    <div className="flex w-full flex-col gap-6 p-4 sm:p-6" aria-busy aria-label="Loading performance record">
      <div className="flex flex-wrap items-center gap-4 border-b border-[var(--oasis-border)] pb-4">
        <Bone className="h-[24px] w-[220px]" />
        <Bone className="h-[11px] w-[260px] max-w-full" />
        <div className="ml-auto flex gap-[6px]">
          {Array.from({ length: 3 }).map((_, i) => <Bone key={i} className="h-[30px] w-[100px] rounded-[6px]" />)}
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>{Array.from({ length: 8 }).map((_, i) => <BoneRow key={i} i={i} />)}</div>
        <div className="flex flex-col gap-6"><BoneStats rows={4} /><BoneStats rows={4} /></div>
      </div>
    </div>
  );
}
