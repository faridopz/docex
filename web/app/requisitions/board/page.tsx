"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Banknote,
  CheckCircle2,
  Clock,
  Loader2,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  listRequisitions,
} from "@/lib/requisitionApi";
import { agingLabel, money } from "@/lib/requisitionFormat";
import { useDepartmentNames } from "@/lib/orgNames";
import { ViewSwitch } from "@/components/erp/ViewSwitch";
import type { RequisitionSummary } from "@/types/requisition";

/**
 * Payment pipeline — every payment request and exactly where it sits.
 *
 * This board used to be fed by compliance checks (`listChecks`), which meant
 * the one screen titled "every payment" could not see a single requisition:
 * a request raised through the approval engine never appeared on it, and its
 * "Requisition" column was really a lifecycle stage of a compliance check.
 * Two systems, one name. It now reads the requisition engine — the actual
 * payment spine, the thing with the approval chain, the hash-chained audit
 * log and the frozen transaction record — so the board and the requisition
 * list can never disagree about where a payment is.
 *
 * Columns map 1:1 onto the engine's own statuses, so every requisition has
 * exactly one home and nothing is silently dropped:
 *
 *   Needs attention  draft / returned / on hold — not moving until someone
 *                    acts on it outside the normal chain
 *   With approvers   in review, including requests with a blocking check:
 *                    those are still with an approver (who must return or
 *                    release them), so they sort first and say so in red.
 *                    Filing them under Needs attention left "With
 *                    approvers" reading 0 while Finance had four on its desk.
 *   Approved         cleared every step, waiting to be paid
 *   Paid             terminal, transaction frozen
 *   Declined         terminal, rejected
 *
 * Money, not just counts. A finance officer opening this wants to know how
 * much is stuck, not how many things are stuck, so every column totals.
 */

type ColumnKey = "needs_attention" | "in_approval" | "approved" | "paid" | "declined";

const COLUMNS: {
  key: ColumnKey;
  title: string;
  hint: string;
  icon: typeof Clock;
  accent: string;
}[] = [
  {
    key: "needs_attention",
    title: "Needs attention",
    hint: "Returned, on hold, or not yet sent",
    icon: ShieldAlert,
    accent: "text-rose-600",
  },
  {
    key: "in_approval",
    title: "With approvers",
    hint: "Moving through the approval chain",
    icon: Clock,
    accent: "text-amber-600",
  },
  {
    key: "approved",
    title: "Approved",
    hint: "Signed off — ready for payment",
    icon: CheckCircle2,
    accent: "text-emerald-600",
  },
  {
    key: "paid",
    title: "Paid",
    hint: "Payment recorded, transaction frozen",
    icon: Banknote,
    accent: "text-brand-600",
  },
  {
    key: "declined",
    title: "Declined",
    hint: "Rejected by an approver",
    icon: XCircle,
    accent: "text-gray-400",
  },
];

/** Which column a requisition belongs in — by who has it, not by whether a
 * check failed (see the header comment). */
function columnFor(r: RequisitionSummary): ColumnKey {
  if (r.status === "paid") return "paid";
  if (r.status === "declined") return "declined";
  if (r.status === "approved") return "approved";
  if (r.status === "draft" || r.status === "returned" || r.status === "on_hold") {
    return "needs_attention";
  }
  return "in_approval";
}

/** The one line that says why this card is where it is. */
function stageLabel(r: RequisitionSummary, deptNameFor: (key?: string | null) => string): string {
  if (r.status === "on_hold") return "On hold";
  if (r.status === "returned") return `Returned to ${r.submitted_by_name || r.submitted_by}`;
  if (r.status === "draft") return "Draft — not submitted";
  if (r.status === "paid") return "Paid";
  if (r.status === "declined") return "Declined";
  if (r.status === "approved") return "Ready for payment";
  const withWho = r.current_department ? `With ${deptNameFor(r.current_department)}` : "In review";
  if (r.blocking_count > 0) {
    return `${withWho} · ${r.blocking_count} blocking check${r.blocking_count === 1 ? "" : "s"}`;
  }
  return withWho;
}

export default function PaymentPipelinePage() {
  const deptName = useDepartmentNames();
  const [rows, setRows] = useState<RequisitionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listRequisitions();
        if (!cancelled) setRows(list);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load the pipeline.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => {
    const g: Record<ColumnKey, RequisitionSummary[]> = {
      needs_attention: [],
      in_approval: [],
      approved: [],
      paid: [],
      declined: [],
    };
    for (const r of rows ?? []) g[columnFor(r)].push(r);
    // Within "With approvers", anything a check is blocking comes first.
    g.in_approval.sort((a, b) => Number(b.blocking_count > 0) - Number(a.blocking_count > 0));
    return g;
  }, [rows]);

  const currency = rows?.[0]?.currency ?? "NGN";

  return (
    <AppShell active="requisitions">
      <div className="mx-auto max-w-7xl py-6 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">Payment requests</h1>
            <p className="mt-1 max-w-2xl text-sm text-gray-600">
              Every request and who has it — from raised, through approval, to paid.
            </p>
          </div>
          {/* The log download lives on the list (and in Audit); the board
              is the same requests seen by who has them. */}
          <ViewSwitch current="board" />
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {rows === null && !error ? (
          <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading pipeline…
          </div>
        ) : null}

        {rows !== null ? (
          <div className="grid gap-4 lg:grid-cols-5">
            {COLUMNS.map((col) => {
              const items = grouped[col.key];
              const total = items.reduce((sum, r) => sum + r.amount, 0);
              const Icon = col.icon;
              return (
                <div key={col.key} className="flex flex-col">
                  <div className="mb-1 flex items-center gap-2 px-1">
                    <Icon className={`h-4 w-4 shrink-0 ${col.accent}`} />
                    <h2 className="text-sm font-semibold text-gray-900">{col.title}</h2>
                    <span className="ml-auto inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-gray-100 px-1.5 text-xs font-semibold tabular-nums text-gray-600">
                      {items.length}
                    </span>
                  </div>
                  {/* The money, not just the count — "₦4.2m is stuck waiting on
                      the AED" is the sentence finance actually needs. */}
                  <p className="mb-0.5 px-1 text-xs font-semibold tabular-nums text-gray-700">
                    {items.length ? money(total, currency) : "—"}
                  </p>
                  <p className="mb-3 px-1 text-[11px] leading-tight text-gray-400">
                    {col.hint}
                  </p>

                  <div className="flex-1 space-y-2 rounded-xl bg-gray-50/70 p-2">
                    {items.length === 0 ? (
                      <p className="px-2 py-6 text-center text-xs text-gray-400">
                        Nothing here
                      </p>
                    ) : (
                      items.map((r) => {
                        const aging = agingLabel(r.submitted_at);
                        return (
                          <Link
                            key={r.id}
                            href={`/requisitions/${encodeURIComponent(r.id)}`}
                            className="group block rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition hover:border-brand-300 hover:shadow"
                          >
                            <div className="flex items-baseline justify-between gap-2">
                              <span className="text-xs font-semibold text-gray-500 group-hover:text-brand-700">
                                {r.ref}
                              </span>
                              <span className="shrink-0 text-xs font-semibold tabular-nums text-gray-900">
                                {money(r.amount, r.currency)}
                              </span>
                            </div>
                            <p className="mt-0.5 truncate text-sm font-medium text-gray-900">
                              {r.vendor_name}
                            </p>
                            <div className="mt-2 flex items-center justify-between gap-2">
                              <span
                                className={`text-[11px] font-medium leading-snug ${
                                  r.status === "in_review" && r.blocking_count > 0 ? "text-rose-700" : "text-gray-600"
                                }`}
                              >
                                {stageLabel(r, deptName)}
                              </span>
                              {aging ? (
                                <span className={`shrink-0 text-[10px] font-semibold ${aging.tone}`}>
                                  {aging.label}
                                </span>
                              ) : null}
                            </div>
                          </Link>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}

        {rows !== null ? (
          <div className="mt-6">
            <Link
              href="/requisitions"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-700"
            >
              View all as a list
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
