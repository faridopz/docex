"use client";

import {
  Check,
  CircleDot,
  CornerUpLeft,
  Eye,
  MessageSquare,
  Plus,
  Stamp,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { DEPT_LABEL, relativeTime, STATE_LABEL } from "@/lib/erpFormat";
import type { TxnEvent, TxnEventType } from "@/types/erp";

/**
 * The always-visible audit trail — a vertical timeline of every action on a
 * transaction. Research across compliance tools is clear: the audit trail must
 * be front-and-centre, not buried in a settings menu. Newest at the top.
 */

const ICON: Record<TxnEventType, LucideIcon> = {
  created: Plus,
  state_changed: CircleDot,
  viewed: Eye,
  noted: MessageSquare,
  returned: CornerUpLeft,
  approved: Stamp,
  paid: Wallet,
  linked: Check,
};

const TONE: Record<TxnEventType, string> = {
  created: "bg-gray-100 text-gray-500",
  state_changed: "bg-blue-50 text-blue-600",
  viewed: "bg-gray-100 text-gray-400",
  noted: "bg-gray-100 text-gray-500",
  returned: "bg-red-50 text-red-600",
  approved: "bg-violet-50 text-violet-600",
  paid: "bg-emerald-50 text-emerald-600",
  linked: "bg-gray-100 text-gray-500",
};

function describe(e: TxnEvent): string {
  switch (e.type) {
    case "created":
      return "Transaction opened";
    case "linked":
      return e.note ?? "Linked to source item";
    case "viewed":
      return `Viewed${e.department ? ` by ${DEPT_LABEL[e.department]}` : ""}`;
    case "noted":
      return e.note ?? "Note added";
    case "returned":
      return `Returned for fixes${e.note ? ` — ${e.note}` : ""}`;
    case "approved":
      return "Approval stage reached";
    case "paid":
      return "Marked paid";
    default:
      return e.from_state && e.to_state
        ? `${STATE_LABEL[e.from_state]} → ${STATE_LABEL[e.to_state]}`
        : "Updated";
  }
}

export function StatusTimeline({ history }: { history: TxnEvent[] }) {
  const events = [...history].reverse();
  return (
    <ol className="space-y-4">
      {events.map((e, i) => {
        const Icon = ICON[e.type] ?? CircleDot;
        return (
          <li key={i} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className={`flex h-7 w-7 items-center justify-center rounded-full ${TONE[e.type] ?? "bg-gray-100 text-gray-500"}`}>
                <Icon className="h-3.5 w-3.5" />
              </span>
              {i < events.length - 1 && <span className="mt-1 w-px flex-1 bg-gray-200" />}
            </div>
            <div className="min-w-0 pb-1">
              <p className="text-sm text-gray-900">{describe(e)}</p>
              <p className="mt-0.5 text-xs text-gray-400">
                {e.department ? DEPT_LABEL[e.department] : "System"}
                {e.actor ? ` · ${e.actor}` : ""} · {relativeTime(e.timestamp)}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
