import { Bone } from "@/components/skeleton";

/** Mirrors the betting console: header with figures, sticky toolbar,
 * then grid rows with a gauge column. */
export default function BettingLoading() {
  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 p-4 sm:p-6" aria-busy aria-label="Loading betting selections">
      <div className="grid gap-6 border-b border-[var(--oasis-border)] pb-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div className="flex flex-col gap-3">
          <Bone className="h-[10px] w-[240px] max-w-full" />
          <Bone className="h-[30px] w-[340px] max-w-full" />
          <Bone className="h-[12px] w-[520px] max-w-full" />
        </div>
        <div className="flex flex-col items-start gap-5 lg:items-end">
          <Bone className="h-[36px] w-[200px] rounded-[9px]" />
          <div className="flex gap-8">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-2"><Bone className="h-[20px] w-[36px]" /><Bone className="h-[9px] w-[52px]" /></div>
            ))}
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[10px] border-b border-[var(--oasis-border)] pb-3 pt-3">
        <div className="flex flex-wrap gap-[6px]">
          {Array.from({ length: 8 }).map((_, i) => <Bone key={i} className="h-[30px] w-[84px] rounded-full" />)}
        </div>
        <div className="flex flex-wrap gap-[6px]">
          {Array.from({ length: 5 }).map((_, i) => <Bone key={i} className="h-[30px] w-[110px] rounded-full" />)}
          <Bone className="ml-auto h-[30px] w-[220px] rounded-[7px]" />
        </div>
      </div>
      <div className="border-t border-[var(--oasis-border)]">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3 border-b border-[var(--oasis-border-row)] py-[13px] md:grid-cols-[minmax(0,1.5fr)_188px_92px_92px_120px_96px_24px] md:gap-x-5 md:gap-y-0">
            <div className="flex flex-col gap-[6px]">
              <Bone className="h-[13px]" style={{ width: `${40 + ((i * 19) % 35)}%` }} />
              <Bone className="h-[11px]" style={{ width: `${55 + ((i * 13) % 30)}%` }} />
            </div>
            <Bone className="h-[18px] w-[52px] rounded-[4px] md:order-6" />
            <div className="col-span-2 flex flex-col gap-[6px] md:order-2 md:col-span-1"><Bone className="h-[7px] w-full" /><Bone className="h-[9px] w-[60%]" /></div>
            <Bone className="hidden h-[16px] w-[56px] md:order-3 md:block md:justify-self-end" />
            <Bone className="hidden h-[16px] w-[44px] md:order-4 md:block md:justify-self-end" />
            <Bone className="hidden h-[16px] w-[64px] md:order-5 md:block" />
            <span className="hidden md:order-7 md:block" />
          </div>
        ))}
      </div>
    </div>
  );
}
