"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Download, Inbox, Loader2, Plus } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Page } from "@/components/layout/Page";
import { ViewSwitch } from "@/components/erp/ViewSwitch";
import { useAuth } from "@/lib/auth";
import { useDepartmentNames } from "@/lib/orgNames";
import { WHERE_TONE, whereItIs } from "@/lib/whereItIs";
import {
  downloadRequisitionLog,
  getDocumentPermissions,
  listPendingForMe,
  listRequisitions,
  triggerBlobDownload,
} from "@/lib/requisitionApi";
import { agingLabel, humanise, money, relativeTime } from "@/lib/requisitionFormat";
import type { RequisitionSummary, ReqStatus } from "@/types/requisition";

/**
 * Payment requests — one list, three questions.
 *
 *   Waiting on me   what my department must decide (approvers' default)
 *   Raised by me    where my own requests are (everyone else's default —
 *                   a programme officer's "waiting on me" is always empty,
 *                   so that default showed them an empty page every time)
 *   All / My department   everything this person may see (WO-59 scoping)
 *
 * Each row says where the request is in plain words ("With Finance / Audit —
 * needs something from you") instead of a status pill and a step key.
 */

type Tab = "waiting" | "raised" | "all";

const STATUS_FILTERS: { value: ReqStatus | ""; label: string }[] = [
  { value: "", label: "Any status" },
  { value: "in_review", label: "With approvers" },
  { value: "on_hold", label: "On hold" },
  { value: "approved", label: "Approved" },
  { value: "returned", label: "Returned" },
  { value: "paid", label: "Paid" },
  { value: "declined", label: "Declined" },
];

export default function RequisitionsPage() {
  const { user } = useAuth();
  const deptName = useDepartmentNames();
  const [tab, setTab] = useState<Tab | null>(null);
  const [ownsAStep, setOwnsAStep] = useState(false);
  const [seesEverything, setSeesEverything] = useState(false);
  const [status, setStatus] = useState<ReqStatus | "">("");
  const [rows, setRows] = useState<RequisitionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"" | "week" | "month">("");
  const [exportError, setExportError] = useState<string | null>(null);

  // Which view to open on: approvers land on their queue, everyone else on
  // their own requests. A ?tab= link (from the dashboard) wins.
  useEffect(() => {
    let live = true;
    (async () => {
      const [pending, perms] = await Promise.all([
        listPendingForMe().catch(() => null),
        getDocumentPermissions().catch(() => null),
      ]);
      if (!live) return;
      const owns = Boolean(pending && pending.steps.length > 0);
      setOwnsAStep(owns);
      setSeesEverything(Boolean(perms?.sees_everything));
      let wanted: Tab | null = null;
      try {
        const q = new URLSearchParams(window.location.search).get("tab");
        if (q === "waiting" || q === "raised" || q === "all") wanted = q;
      } catch {
        /* no window */
      }
      setTab(wanted ?? (owns ? "waiting" : "raised"));
    })();
    return () => {
      live = false;
    };
  }, []);

  /** The weekly/monthly audit log. Week starts Monday, matching how a
   *  payment run is actually scheduled, not the calendar's Sunday. */
  async function handleExport(period: "week" | "month") {
    setExporting(period);
    setExportError(null);
    try {
      const now = new Date();
      let start: Date;
      if (period === "week") {
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
      setExportError(e instanceof Error ? e.message : "Could not export the log.");
    } finally {
      setExporting("");
    }
  }

  const load = useCallback(async () => {
    if (tab === null) return;
    setLoading(true);
    setError(null);
    try {
      if (tab === "waiting") {
        setRows((await listPendingForMe()).requisitions);
      } else {
        const all = await listRequisitions(status ? { status } : {});
        const me = (user?.email || "").toLowerCase();
        setRows(tab === "raised" ? all.filter((r) => r.submitted_by.toLowerCase() === me) : all);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load payment requests.");
    } finally {
      setLoading(false);
    }
  }, [tab, status, user?.email]);

  useEffect(() => {
    void load();
  }, [load]);

  const value = rows.reduce((sum, r) => sum + r.amount, 0);
  const needsFix = rows.filter((r) => r.blocking_count > 0).length;
  const allLabel = seesEverything ? "All" : "My department";

  const subtitle =
    tab === "waiting"
      ? "Requests your department must decide, oldest first."
      : tab === "raised"
        ? "Every request you have raised, and where each one is."
        : seesEverything
          ? "Every payment request in the organisation."
          : "Requests raised in your department.";

  return (
    <AppShell
      actions={
        <Link
          href="/requisitions/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          New payment request
        </Link>
      }
    >
      <Page
        width="wide"
        title="Payment requests"
        subtitle={subtitle}
        aside={seesEverything ? <ViewSwitch current="list" /> : null}
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-gray-300 bg-white p-0.5">
            {ownsAStep ? (
              <TabButton active={tab === "waiting"} onClick={() => setTab("waiting")}>
                Waiting on me
              </TabButton>
            ) : null}
            <TabButton active={tab === "raised"} onClick={() => setTab("raised")}>
              Raised by me
            </TabButton>
            <TabButton active={tab === "all"} onClick={() => setTab("all")}>
              {allLabel}
            </TabButton>
          </div>

          {tab === "all" || tab === "raised" ? (
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as ReqStatus | "")}
              aria-label="Filter by status"
              className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          ) : null}

          <p className="text-sm text-gray-500">
            {rows.length} request{rows.length === 1 ? "" : "s"} · {money(value)}
            {needsFix ? (
              <span className="ml-2 font-medium text-red-700">
                · {needsFix} blocked by a check
              </span>
            ) : null}
          </p>

          {/* The weekly/monthly log NEEM asked for, where the requests are.
              Org-wide, so only for the approval chain — the server agrees. */}
          {seesEverything ? (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-gray-500">Download log:</span>
              <ExportButton busy={exporting === "week"} disabled={exporting !== ""} onClick={() => handleExport("week")}>
                This week
              </ExportButton>
              <ExportButton busy={exporting === "month"} disabled={exporting !== ""} onClick={() => handleExport("month")}>
                This month
              </ExportButton>
            </div>
          ) : null}
        </div>

        {exportError ? <p className="text-xs text-red-700">{exportError}</p> : null}

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>
        ) : null}

        {loading || tab === null ? (
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-8 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center">
            <Inbox className="mx-auto h-8 w-8 text-gray-300" />
            <p className="mt-3 text-sm font-medium text-gray-900">
              {tab === "waiting"
                ? "Nothing waiting on you"
                : tab === "raised"
                  ? "You haven't raised a payment request yet"
                  : "No payment requests yet"}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              {tab === "waiting" ? (
                "When a request reaches your department it appears here, and you get an alert."
              ) : (
                <>
                  <Link href="/requisitions/new" className="font-medium text-brand-700 underline">
                    Raise one
                  </Link>{" "}
                  and it goes through your approval chain automatically.
                </>
              )}
            </p>
          </div>
        ) : (
          <RequisitionTable rows={rows} deptName={deptName} me={user?.email} showRaisedBy={tab !== "raised"} />
        )}
      </Page>
    </AppShell>
  );
}

function ExportButton({
  busy,
  disabled,
  onClick,
  children,
}: {
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

// ─── pieces ─────────────────────────────────────────────────────────────────

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

function RequisitionTable({
  rows,
  deptName,
  me,
  showRaisedBy,
}: {
  rows: RequisitionSummary[];
  deptName: (key?: string | null) => string;
  me?: string | null;
  showRaisedBy: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <Th>Reference</Th>
            <Th>Paying</Th>
            <Th className="text-right">Amount</Th>
            <Th>Where it is</Th>
            {showRaisedBy ? <Th>Raised by</Th> : null}
            <Th>Raised</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((r) => {
            const aging = r.status === "in_review" ? agingLabel(r.updated_at ?? r.submitted_at) : null;
            const where = whereItIs(r, deptName, me);
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
                      {r.blocking_count} check{r.blocking_count === 1 ? "" : "s"} blocking
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <span className="font-medium text-gray-900">{r.vendor_name || "—"}</span>
                  {r.kind === "expense_claim" && (
                    <span className="ml-2 rounded bg-teal-50 px-1.5 py-0.5 text-[11px] font-medium text-teal-700 ring-1 ring-inset ring-teal-200">
                      Claim
                    </span>
                  )}
                  {r.category || r.project_code ? (
                    <span className="mt-0.5 block text-xs text-gray-500">
                      {[humanise(r.category), r.project_code].filter(Boolean).join(" · ")}
                    </span>
                  ) : null}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-medium tabular-nums text-gray-900">
                  {money(r.amount, r.currency)}
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-medium ${WHERE_TONE[where.tone]}`}>
                    {where.text}
                  </span>
                </td>
                {showRaisedBy ? (
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700">{r.submitted_by_name || r.submitted_by}</td>
                ) : null}
                <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                  {relativeTime(r.submitted_at)}
                  {aging ? <span className={`mt-0.5 block text-xs font-medium ${aging.tone}`}>{aging.label}</span> : null}
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
