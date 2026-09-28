import type { RequisitionSummary } from "@/types/requisition";

/**
 * Where a payment request is, in the words a programme officer would use.
 *
 * The list used to show a status pill ("In review") and a step key
 * ("Finance") in two columns and leave the reader to combine them; the
 * question people actually ask is "who has it, and is it waiting on me?".
 */
export type Where = { text: string; tone: "gray" | "blue" | "amber" | "green" | "red" };

export function whereItIs(
  r: Pick<RequisitionSummary, "status" | "blocking_count" | "submitted_by" | "submitted_by_name" | "current_department">,
  deptName: (key?: string | null) => string,
  me?: string | null,
): Where {
  const mine = Boolean(me && r.submitted_by.toLowerCase() === me.toLowerCase());
  const withWho = r.current_department ? deptName(r.current_department) : "the approvers";
  switch (r.status) {
    case "draft":
      return { text: "Draft — not sent yet", tone: "gray" };
    case "returned":
      return mine
        ? { text: "Returned to you — fix and send again", tone: "amber" }
        : { text: `Returned to ${r.submitted_by_name || r.submitted_by}`, tone: "amber" };
    case "on_hold":
      return { text: `On hold with ${withWho}`, tone: "amber" };
    case "approved":
      return { text: "Approved — waiting to be paid", tone: "green" };
    case "paid":
      return { text: "Paid", tone: "green" };
    case "declined":
      return { text: "Declined", tone: "red" };
    default:
      if (mine && r.blocking_count > 0) return { text: `With ${withWho} — needs something from you`, tone: "amber" };
      return { text: `With ${withWho}`, tone: "blue" };
  }
}

export const WHERE_TONE: Record<Where["tone"], string> = {
  gray: "bg-gray-100 text-gray-700",
  blue: "bg-blue-50 text-blue-800",
  amber: "bg-amber-50 text-amber-900",
  green: "bg-emerald-50 text-emerald-800",
  red: "bg-red-50 text-red-800",
};
