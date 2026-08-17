"use client";

import { cn } from "@/lib/utils";
import { STATE_LABEL, STATE_STYLE } from "@/lib/erpFormat";
import type { TxnState } from "@/types/erp";

/** A colour-coded workflow status pill (traffic-light prioritisation). */
export function StatusBadge({ state, className }: { state: TxnState; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        STATE_STYLE[state],
        className,
      )}
    >
      {STATE_LABEL[state]}
    </span>
  );
}
