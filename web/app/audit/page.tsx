"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Download, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  downloadRequisitionLog,
  getAuditSummary,
  triggerBlobDownload,
} from "@/lib/requisitionApi";
import { getClientConfig, hasFeature } from "@/lib/orgConfig";
import { dateTime, humanise, money } from "@/lib/requisitionFormat";
import type { AuditSummary } from "@/types/requisition";

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/**
 * The auditor's first screen.
 *
 * One question is answered above everything else: is there any payment whose
 * policy exception has no written explanation? If the answer is no, the org is
 * audit-ready and the verdict says so plainly. If the answer is yes, those
 * exceptions are listed first and named, because that is the finding the
 * auditor would otherwise write themselves.
 *
 * Every number here is counted from stored records. Nothing is estimated.
 */
export default function AuditPage() {
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [exportEnabled, setExportEnabled] = useState(false);
  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 6);
  const [logStart, setLogStart] = useState(isoDate(weekAgo));
  const [logEnd, setLogEnd] = useState(isoDate(today));
  const [logBusy, setLogBusy] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await getAuditSummary();
        if (!cancelled) setSummary(s);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load the audit summary.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await getClientConfig();
        if (!cancelled) setExportEnabled(hasFeature(cfg, "requisition_export"));
      } catch {
        /* stays hidden — matches what the server would refuse anyway */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function downloadLog() {
    setLogBusy(true);
    setLogError(null);
    try {
      const blob = await downloadRequisitionLog(logStart, logEnd);
      triggerBlobDownload(blob, `requisition-log_${logStart}_to_${logEnd}.xlsx`);
    } catch (e) {
      setLogError(e instanceof Error ? e.message : "Could not export the log.");
    } finally {
      setLogBusy(false);
    }
  }

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center gap-2 p-8 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      </AppShell>
    );
  }

  if (error || !summary) {
    return (
      <AppShell>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error ?? "No audit summary available."}
        </div>
      </AppShell>
    );
  }

  const unexplained = summary.exceptions.filter((e) => !(e.reason ?? "").trim());
  const explained = summary.exceptions.filter((e) => (e.reason ?? "").trim());

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Audit</h1>
          <p className="mt-1 text-sm text-gray-600">
            Every policy exception on record, with the reason given and the authority relied on.
            Generated {dateTime(summary.generated_at)}.
          </p>
        </div>

        {exportEnabled ? (
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-gray-900">Export a period log</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Every requisition raised in this range, one row each — for a weekly or monthly
              audit sweep.
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <label className="text-sm">
                <span className="mb-1 block text-xs font-medium text-gray-700">From</span>
                <input
                  type="date"
                  value={logStart}
                  onChange={(e) => setLogStart(e.target.value)}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm"
                />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-xs font-medium text-gray-700">To</span>
                <input
                  type="date"
                  value={logEnd}
                  onChange={(e) => setLogEnd(e.target.value)}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm"
                />
              </label>
              <button
                type="button"
                onClick={downloadLog}
                disabled={logBusy || !logStart || !logEnd}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {logBusy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                Download .xlsx
              </button>
            </div>
            {logError ? <p className="mt-2 text-xs text-red-700">{logError}</p> : null}
          </section>
        ) : null}

        {/* The verdict, stated before any detail. */}
        {summary.audit_ready ? (
          <div className="flex gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
            <div>
              <p className="text-sm font-semibold text-emerald-900">Audit ready</p>
              <p className="mt-0.5 text-sm text-emerald-800">
                {summary.exceptions_total === 0
                  ? "No policy exception has been released. Every payment cleared on its own."
                  : `All ${summary.exceptions_total} exceptions carry a written reason and a named authority.`}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex gap-3 rounded-lg border border-red-300 bg-red-50 p-4">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
            <div>
              <p className="text-sm font-semibold text-red-900">
                {summary.exceptions_unexplained} unexplained{" "}
                {summary.exceptions_unexplained === 1 ? "exception" : "exceptions"}
              </p>
              <p className="mt-0.5 text-sm text-red-800">
                These payments went out over a failing policy check with no reason recorded. This is
                exactly what an external auditor writes up as a finding.
              </p>
            </div>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi label="Requisitions" value={String(summary.requisitions_total)} />
          <Kpi label="Payments" value={String(summary.transactions_total)} />
          <Kpi label="Value paid" value={money(summary.value_paid)} />
          <Kpi
            label="Exceptions"
            value={String(summary.exceptions_total)}
            tone={summary.exceptions_unexplained > 0 ? "bad" : summary.exceptions_total > 0 ? "warn" : undefined}
          />
        </div>

        {Object.keys(summary.requisitions_by_status).length ? (
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-gray-900">Requisitions by status</h2>
            <div className="flex flex-wrap gap-x-8 gap-y-2">
              {Object.entries(summary.requisitions_by_status).map(([status, count]) => (
                <div key={status}>
                  <p className="text-xs uppercase tracking-wide text-gray-500">
                    {humanise(status)}
                  </p>
                  <p className="text-lg font-semibold tabular-nums text-gray-900">{count}</p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {unexplained.length > 0 ? (
          <ExceptionTable
            title="Unexplained exceptions"
            subtitle="A failing check was released with no written reason. Fix these first."
            rows={unexplained}
            tone="bad"
          />
        ) : null}

        {explained.length > 0 ? (
          <ExceptionTable
            title="Explained exceptions"
            subtitle="Each one names who released it, why, and under what authority."
            rows={explained}
          />
        ) : null}

        {summary.exceptions_total === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-300" />
            <p className="mt-3 text-sm font-medium text-gray-900">No exceptions on record</p>
            <p className="mt-1 text-sm text-gray-500">
              Every payment made so far passed policy without an override.
            </p>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

// ─── pieces ─────────────────────────────────────────────────────────────────

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "warn" | "bad" }) {
  const colour =
    tone === "bad" ? "text-red-600" : tone === "warn" ? "text-purple-700" : "text-gray-900";
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tracking-tight ${colour}`}>{value}</p>
    </div>
  );
}

function ExceptionTable({
  title,
  subtitle,
  rows,
  tone,
}: {
  title: string;
  subtitle: string;
  rows: AuditSummary["exceptions"];
  tone?: "bad";
}) {
  return (
    <section
      className={
        tone === "bad"
          ? "overflow-hidden rounded-lg border border-red-200 bg-white"
          : "overflow-hidden rounded-lg border border-gray-200 bg-white"
      }
    >
      <div className={tone === "bad" ? "border-b border-red-200 bg-red-50 p-4" : "border-b border-gray-200 p-4"}>
        <h2 className={tone === "bad" ? "text-sm font-semibold text-red-900" : "text-sm font-semibold text-gray-900"}>
          {title} ({rows.length})
        </h2>
        <p className={tone === "bad" ? "mt-0.5 text-xs text-red-800" : "mt-0.5 text-xs text-gray-500"}>
          {subtitle}
        </p>
      </div>
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <Th>Payment</Th>
            <Th>Check released</Th>
            <Th>Policy vs actual</Th>
            <Th>Reason</Th>
            <Th>Authority</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((e, i) => (
            <tr key={`${e.transaction_id}-${e.check}-${i}`} className="align-top">
              <td className="whitespace-nowrap px-4 py-3">
                <Link
                  href={`/payments/${encodeURIComponent(e.transaction_id)}`}
                  className="font-medium text-brand-600 hover:text-brand-700"
                >
                  {e.requisition_ref}
                </Link>
              </td>
              <td className="px-4 py-3 text-gray-900">{humanise(e.check)}</td>
              <td className="px-4 py-3 text-xs text-gray-600">
                {e.policy_value ? <span className="block">Policy: {e.policy_value}</span> : null}
                {e.actual_value ? <span className="block">Actual: {e.actual_value}</span> : null}
                {!e.policy_value && !e.actual_value ? "—" : null}
              </td>
              <td className="px-4 py-3 text-gray-700">
                {(e.reason ?? "").trim() ? (
                  <>
                    &ldquo;{e.reason}&rdquo;
                    {e.approved_by ? (
                      <span className="mt-0.5 block text-xs text-gray-500">— {e.approved_by}</span>
                    ) : null}
                  </>
                ) : (
                  <span className="font-medium text-red-700">No reason recorded</span>
                )}
              </td>
              <td className="px-4 py-3 text-gray-700">
                {(e.authority ?? "").trim() || (
                  <span className="font-medium text-red-700">Not named</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      scope="col"
      className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
    >
      {children}
    </th>
  );
}
