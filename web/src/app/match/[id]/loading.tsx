import { Bone, BoneStats } from "@/components/skeleton";

export default function MatchLoading() {
  return (
    <div className="flex w-full flex-col gap-6 p-4 sm:p-6" aria-busy aria-label="Loading match">
      <div className="flex flex-wrap items-center gap-4 border-b border-[var(--oasis-border)] pb-4">
        <Bone className="h-[11px] w-[54px]" />
        <Bone className="h-[26px] w-[300px] max-w-full" />
        <Bone className="h-[11px] w-[180px]" />
        <Bone className="ml-auto h-[20px] w-[120px] rounded-[6px]" />
      </div>
      <div className="flex flex-col gap-4">
        <Bone className="h-11 w-full rounded-[9px]" />
        <div className="grid grid-cols-2 gap-[8px] sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex flex-col gap-2 rounded-[8px] border border-[var(--oasis-border)] px-3 py-[10px]">
              <Bone className="h-[9px] w-[70px]" />
              <Bone className="h-[22px] w-[64px]" />
              <Bone className="h-[10px] w-[90px]" />
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_1fr_320px]">
        <div className="flex flex-col gap-3">
          <Bone className="h-[10px] w-[150px]" />
          <Bone className="h-[200px] w-full rounded-[8px]" />
        </div>
        <BoneStats rows={7} />
        <div className="flex flex-col gap-6"><BoneStats rows={3} /><BoneStats rows={2} /></div>
      </div>
    </div>
  );
}
