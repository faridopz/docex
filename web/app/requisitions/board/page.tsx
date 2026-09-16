"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Banknote,
  CheckCircle2,
  Clock,
  Download,
  Loader2,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  downloadRequisitionLog,
  listRequisitions,
  triggerBlobDownload,
} from "@/lib/requisitionApi";
import { agingLabel, money } from "@/lib/requisitionFormat";
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
 *   Needs attention  draft / returned / on hold, or a blocking check nobody
 *                    has released — in every case the ball is with the
 *                    requester, not an approver
 *   With approvers   submitted / in review
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
    hint: "Blocked, on hold, returned, or not yet submitted",
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

/** Which column a requisition belongs in.
 *
 * An unreleased blocking check outranks the workflow status on purpose: a
 * requisition can sit in "in_review" with a FAIL nobody has released, and on
 * a board whose job is to show what needs a human, that belongs under Needs
 * attention rather than looking like it is progressing normally. */
function columnFor(r: RequisitionSummary): ColumnKey {
  if (r.status === "paid") return "paid";
  if (r.status === "declined") return "declined";
  if (r.status === "approved") return "approved";
  if (r.status === "draft" || r.status === "returned" || r.status === "on_hold") {
    return "needs_attention";
  }
  if (r.blocking_count > 0) return "needs_attention";
  return "in_approval";
}

/** The one line that says why this card is where it is. */
function stageLabel(r: RequisitionSummary): string {
  if (r.status === "on_hold") return "On hold";
  if (r.status === "returned") return "Returned to submitter";
  if (r.status === "draft") return "Draft — not submitted";
  if (r.status === "paid") return "Paid";
  if (r.status === "declined") return "Declined";
  if (r.blocking_count > 0) {
    return `${r.blocking_count} check${r.blocking_count === 1 ? "" : "s"} blocking`;
  }
  if (r.status === "approved") return "Ready for payment";
  return r.current_step ? `With ${r.current_step.replace(/_/g, " ")}` : "In review";
}

export default function PaymentPipelinePage() {
  const [rows, setRows] = useState<RequisitionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"" | "week" | "month">("");
  const [exportError, setExportError] = useState<string | null>(null);

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
    return g;
  }, [rows]);

  const currency = rows?.[0]?.currency ?? "NGN";

  /** Export the log for the current week or month — the audit sweep, from
   *  the same screen that shows the pipeline, rather than a separate page. */
  async function handleExport(period: "week" | "month") {
    setExporting(period);
    setExportError(null);
    try {
      const now = new Date();
      let start: Date;
      if (period === "week") {
        // Monday of the current week — NEEM's payment run is weekly and
        // memos are due Monday/Tuesday, so the week starts Monday, not Sunday.
        const day = (now.getDay() + 6) % 7;
        start = new Date(now);
        start.setDate(now.getDate() - day);
      } else {
        start = new Date(now.getFullYear(), now.getMonth(), 1);
      }
      const iso = (d: Date) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
          d.getDate(),
        ).padStart(2, "0")}`;
      const blob = await downloadRequisitionLog(iso(start), iso(now));
      triggerBlobDownload(blob, `requisition-log-${iso(start)}-to-${iso(now)}.xlsx`);
    } catch (e) {
      setExportError(
        e instanceof Error ? e.message : "Could not export the log.",
      );
    } finally {
      setExporting("");
    }
  }

  return (
    <AppShell active="pipeline">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              Payment pipeline
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-gray-600">
              Every payment request and exactly where it sits — from raised, through
              approval, to paid. No chasing an email thread to find a payment&rsquo;s
              status.
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => handleExport("week")}
                disabled={exporting !== ""}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
              >
                {exporting === "week" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                This week
              </button>
              <button
                type="button"
                onClick={() => handleExport("month")}
                disabled={exporting !== ""}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
              >
                {exporting === "month" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                This month
              </button>
            </div>
            <p className="text-[11px] text-gray-400">Export the log for audit</p>
            {exportError ? (
              <p className="text-[11px] text-red-700">{exportError}</p>
            ) : null}
          </div>
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
                              <span className="truncate text-[11px] font-medium capitalize text-gray-600">
                                {stageLabel(r)}
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
