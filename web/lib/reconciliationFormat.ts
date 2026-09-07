/**
 * Presentation rules for reconciliation.
 *
 * Colour means one thing on this screen: red is money nobody has explained.
 * Everything else is calmer than red. The point of the screen is that a
 * finance officer's eye lands on unexplained money first, so nothing else is
 * allowed to compete with it.
 */
import type { ExceptionCode, MatchMethod, Severity } from "@/types/reconciliation";

/** Plain-English titles. "NOT_IN_SYSTEM" means nothing to a finance officer. */
export const EXCEPTION_TITLE: Record<ExceptionCode, string> = {
  NOT_IN_SYSTEM: "Money left the account with no approved request",
  NOT_IN_BANK: "Recorded as paid, but the bank has no record",
  AMOUNT_MISMATCH: "Paid a different amount than approved",
  AMBIGUOUS: "Several bank lines could be this payment",
  DUPLICATE_BANK_LINE: "The same debit appears twice",
};

/** What to actually do about it. */
export const EXCEPTION_ACTION: Record<ExceptionCode, string> = {
  NOT_IN_SYSTEM:
    "Find out who authorised this and record it, or raise it with the bank.",
  NOT_IN_BANK:
    "Check whether the transfer failed, or was marked paid before it was sent.",
  AMOUNT_MISMATCH: "Confirm which figure is right before the month closes.",
  AMBIGUOUS: "Match it to the right line yourself — the system will not guess.",
  DUPLICATE_BANK_LINE:
    "Confirm with the bank whether the account was debited twice.",
};

export const SEVERITY_STYLE: Record<Severity, string> = {
  high: "bg-red-50 text-red-700 ring-red-200",
  medium: "bg-amber-50 text-amber-700 ring-amber-200",
  low: "bg-gray-50 text-gray-600 ring-gray-200",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: "Unexplained",
  medium: "Needs a look",
  low: "Explained",
};

/** How a pair was made. An auditor should be able to see this at a glance. */
export const METHOD_LABEL: Record<MatchMethod, string> = {
  reference: "Bank reference",
  exact: "Amount + date",
  vendor: "Amount + vendor name",
  manual: "Matched by hand",
};

export const METHOD_STYLE: Record<MatchMethod, string> = {
  reference: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  exact: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  vendor: "bg-teal-50 text-teal-700 ring-teal-200",
  // A human decided this one. It is correct, but it is not the same kind of
  // fact as the engine matching a reference, so it does not look the same.
  manual: "bg-purple-50 text-purple-700 ring-purple-200",
};

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

/** "2026-08" → "August 2026". */
export function periodLabel(period: string): string {
  const [y, m] = (period || "").split("-").map(Number);
  if (!y || !m) return period || "—";
  const label = new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
  // Say so plainly. A partial month that reconciles is not a closed month.
  return isCurrentMonth(period) ? `${label} (so far)` : label;
}

/**
 * Months available to reconcile, newest first.
 *
 * The current month is included and listed first. Month END is the named
 * exercise, but finance teams reconcile part-way through precisely to catch a
 * debit nobody authorised while there is still time to do something about it —
 * and waiting for the month to end to discover it is how the money is already
 * gone. `periodLabel` marks it so nobody mistakes a partial month for a closed
 * one.
 */
export function recentPeriods(count = 6): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = 0; i < count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

/** True when `period` is the month we are currently living in. */
export function isCurrentMonth(period: string): boolean {
  const now = new Date();
  return period === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}
