"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Inbox, Loader2, Plus } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ReqStatusBadge } from "@/components/erp/PolicyChecks";
import { listPendingForMe, listRequisitions } from "@/lib/requisitionApi";
import { agingLabel, humanise, money, relativeTime } from "@/lib/requisitionFormat";
import type { RequisitionSummary, ReqStatus } from "@/types/requisition";

/**
 * The approver's queue.
 *
 * "Waiting on me" is the default view because that is the only question an
 * approver opens this page to answer. Everything else is a filter away. Rows
 * are dense and scannable — amount, who it pays, how long it has been sitting,
 * and whether anything blocks it — so triage happens without opening records.
 */

type Tab = "mine" | "all";

const STATUS_FILTERS: { value: ReqStatus | ""; label: string }[] = [
  { value: "", label: "Any status" },
  { value: "in_review", label: "In review" },
  { value: "approved", label: "Approved" },
  { value: "returned", label: "Returned" },
  { value: "paid", label: "Paid" },
  { value: "declined", label: "Declined" },
];

export default function RequisitionsPage() {
  const [tab, setTab] = useState<Tab>("mine");
  const [status, setStatus] = useState<ReqStatus | "">("");
  const [rows, setRows] = useState<RequisitionSummary[]>([]);
  const [department, setDepartment] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === "mine") {
        const r = await listPendingForMe();
        setRows(r.requisitions);
        setDepartment(r.department);
      } else {
        setRows(await listRequisitions(status ? { status } : {}));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load requisitions.");
    } finally {
      setLoading(false);
    }
  }, [tab, status]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!cancelled) await load();
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const pendingValue = rows.reduce((sum, r) => sum + r.amount, 0);
  const blockedCount = rows.filter((r) => r.blocking_count > 0).length;

  return (
    <AppShell
      actions={
        <Link
          href="/requisitions/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          New requisition
        </Link>
      }
    >
      <div className="space-y-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Requisitions</h1>
          <p className="mt-1 text-sm text-gray-600">
            {tab === "mine"
              ? `Everything waiting on ${department ? humanise(department) : "your department"}.`
              : "Every requisition in the organisation."}
          </p>
        </div>

        {/* KPIs first: how much is held up, and how much of it is stuck. */}
        <div className="grid gap-3 sm:grid-cols-3">
          <Kpi label="Requisitions" value={String(rows.length)} />
          <Kpi label="Value" value={money(pendingValue)} />
          <Kpi
            label="With blocking checks"
            value={String(blockedCount)}
            tone={blockedCount > 0 ? "warn" : undefined}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-gray-300 bg-white p-0.5">
            <TabButton active={tab === "mine"} onClick={() => setTab("mine")}>
              Waiting on me
            </TabButton>
            <TabButton active={tab === "all"} onClick={() => setTab("all")}>
              All
            </TabButton>
          </div>

          {tab === "all" ? (
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as ReqStatus | "")}
              className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-8 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center">
            <Inbox className="mx-auto h-8 w-8 text-gray-300" />
            <p className="mt-3 text-sm font-medium text-gray-900">
              {tab === "mine" ? "Nothing waiting on you" : "No requisitions yet"}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              {tab === "mine"
                ? "When a requisition reaches your step it appears here."
                : "Raise one and it will route through your approval chain."}
            </p>
          </div>
        ) : (
          <RequisitionTable rows={rows} />
        )}
      </div>
    </AppShell>
  );
}

// ─── pieces ─────────────────────────────────────────────────────────────────

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p
        className={
          tone === "warn"
            ? "mt-1 text-2xl font-bold tracking-tight text-red-600"
            : "mt-1 text-2xl font-bold tracking-tight text-gray-900"
        }
      >
        {value}
      </p>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-md bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white"
          : "rounded-md px-3 py-1.5 text-sm font-medium text-gray-600 transition hover:text-gray-900"
      }
    >
      {children}
    </button>
  );
}

function RequisitionTable({ rows }: { rows: RequisitionSummary[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <Th>Reference</Th>
            <Th>Payee</Th>
            <Th className="text-right">Amount</Th>
            <Th>Status</Th>
            <Th>Step</Th>
            <Th>Raised</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((r) => {
            const aging = agingLabel(r.updated_at ?? r.submitted_at);
            return (
              <tr key={r.id} className="transition hover:bg-gray-50">
                <td className="whitespace-nowrap px-4 py-3">
                  <Link
                    href={`/requisitions/${encodeURIComponent(r.id)}`}
                    className="font-medium text-brand-600 hover:text-brand-700"
                  >
                    {r.ref}
                  </Link>
                  {r.blocking_count > 0 ? (
                    <span className="mt-0.5 flex items-center gap-1 text-xs font-medium text-red-600">
                      <AlertTriangle className="h-3 w-3" />
                      {r.blocking_count} blocking
                    </span>
                  ) : r.warning_count > 0 ? (
                    <span className="mt-0.5 block text-xs text-amber-600">
                      {r.warning_count} warning{r.warning_count === 1 ? "" : "s"}
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <span className="font-medium text-gray-900">{r.vendor_name || "—"}</span>
                  {r.category || r.project_code ? (
                    <span className="mt-0.5 block text-xs text-gray-500">
                      {[humanise(r.category), r.project_code].filter(Boolean).join(" · ")}
                    </span>
                  ) : null}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-medium tabular-nums text-gray-900">
                  {money(r.amount, r.currency)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <ReqStatusBadge status={r.status} />
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                  {humanise(r.current_step)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                  {relativeTime(r.submitted_at)}
                  {aging ? (
                    <span className={`mt-0.5 block text-xs font-medium ${aging.tone}`}>
                      {aging.label}
                    </span>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={`px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 ${className}`}
    >
      {children}
    </th>
  );
}
