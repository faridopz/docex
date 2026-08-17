/**
 * Presentation helpers for the ERP workflow UI — human labels, status colours
 * (traffic-light prioritisation), money + relative-time formatting. Kept in one
 * place so every screen speaks the same visual language.
 */
import type { Department, TxnState } from "@/types/erp";

export const STATE_LABEL: Record<TxnState, string> = {
  submitted: "Submitted",
  intake: "Intake",
  compliance_review: "Compliance review",
  finance_review: "Finance review",
  approval: "Awaiting approval",
  paid: "Paid",
  returned: "Returned for fixes",
};

/** Tailwind classes for a status pill. Green = done, red = needs attention,
 *  amber/blue/violet = in-flight stages, gray = not started. */
export const STATE_STYLE: Record<TxnState, string> = {
  submitted: "bg-gray-100 text-gray-700 ring-gray-200",
  intake: "bg-gray-100 text-gray-700 ring-gray-200",
  compliance_review: "bg-amber-50 text-amber-700 ring-amber-200",
  finance_review: "bg-blue-50 text-blue-700 ring-blue-200",
  approval: "bg-violet-50 text-violet-700 ring-violet-200",
  paid: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  returned: "bg-red-50 text-red-700 ring-red-200",
};

export const DEPT_LABEL: Record<Department, string> = {
  compliance: "Compliance",
  finance: "Finance",
  program: "Program / M&E",
  management: "Management",
};

/** The happy-path order, for rendering a progress stepper. */
export const PIPELINE: TxnState[] = [
  "submitted",
  "compliance_review",
  "finance_review",
  "approval",
  "paid",
];

export function money(amount?: number | null, currency = "NGN"): string {
  if (amount == null) return "—";
  try {
    return new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency} ${Math.round(amount).toLocaleString()}`;
  }
}

export function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Date.now() - then;
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

/** Aging bucket for a queue row — surfaces bottlenecks at a glance. */
export function agingLabel(iso?: string | null): { label: string; tone: string } | null {
  if (!iso) return null;
  const days = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (Number.isNaN(days)) return null;
  if (days >= 3) return { label: `${Math.floor(days)}d waiting`, tone: "text-red-600" };
  if (days >= 1) return { label: `${Math.floor(days)}d waiting`, tone: "text-amber-600" };
  return null;
}
