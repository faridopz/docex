/**
 * Presentation helpers for the requisition flow.
 *
 * Colour carries meaning here and nowhere else: red is a check that blocks
 * payment, amber is one that only informs, emerald is clear. An overridden
 * FAIL keeps a distinct treatment — it is neither clean nor still blocking,
 * and an auditor must be able to spot it at a glance.
 */
import type { CheckResult, ReqStatus } from "@/types/requisition";

export const REQ_STATUS_LABEL: Record<ReqStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  in_review: "In review",
  approved: "Approved — awaiting payment",
  paid: "Paid",
  declined: "Declined",
  returned: "Returned for fixes",
};

export const REQ_STATUS_STYLE: Record<ReqStatus, string> = {
  draft: "bg-gray-50 text-gray-600 ring-gray-200",
  submitted: "bg-blue-50 text-blue-700 ring-blue-200",
  in_review: "bg-amber-50 text-amber-700 ring-amber-200",
  approved: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  paid: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  declined: "bg-red-50 text-red-700 ring-red-200",
  returned: "bg-orange-50 text-orange-700 ring-orange-200",
};

export const CHECK_LABEL: Record<CheckResult, string> = {
  pass: "Pass",
  warning: "Warning",
  fail: "Blocks payment",
};

export const CHECK_STYLE: Record<CheckResult, string> = {
  pass: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  warning: "bg-amber-50 text-amber-700 ring-amber-200",
  fail: "bg-red-50 text-red-700 ring-red-200",
};

/** Overridden FAILs are their own category — released, but on the record. */
export const OVERRIDDEN_STYLE = "bg-purple-50 text-purple-700 ring-purple-200";

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

export function shortDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function dateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return shortDate(iso);
}

/**
 * How long something has been sitting unactioned. Surfaced so bottlenecks are
 * visible without anyone running a report: three days is where a finance team
 * starts getting chased by a vendor.
 */
export function agingLabel(iso?: string | null): { label: string; tone: string } | null {
  if (!iso) return null;
  const days = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (Number.isNaN(days)) return null;
  if (days >= 3) return { label: `${Math.floor(days)}d waiting`, tone: "text-red-600" };
  if (days >= 1) return { label: `${Math.floor(days)}d waiting`, tone: "text-amber-600" };
  return null;
}

/** "compliance_review" → "Compliance review". Steps are org-defined, so we
 *  can't hard-code labels; this makes an arbitrary key readable. */
export function humanise(key?: string | null): string {
  if (!key) return "—";
  const s = key.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
