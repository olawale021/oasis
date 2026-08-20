"use client";

import { useState } from "react";
import { Switch } from "@/components/ui/switch";

export function AlertToggle() {
  const [enabled, setEnabled] = useState(true);

  return (
    <div className="flex items-center gap-[10px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
      <div className="flex-1">
        <div className="text-[12.5px] font-bold">Alert me if this changes</div>
        <div className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">
          Telegram · lineup &amp; probability moves
        </div>
      </div>
      <Switch checked={enabled} onCheckedChange={setEnabled} />
    </div>
  );
}
