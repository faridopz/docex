"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Banknote, Loader2, ShieldAlert } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { listPayments } from "@/lib/requisitionApi";
import { humanise, money, shortDate } from "@/lib/requisitionFormat";
import type { TransactionSummaryRow } from "@/types/requisition";

/**
 * Completed payments — the money that actually left the account.
 *
 * Each row is a frozen record, not a live one. The exceptions column is the
 * column that matters: it is the count of policy failures that were released
 * to let that payment through, and it is the first thing an auditor sorts by.
 */
export default function PaymentsPage() {
  const [rows, setRows] = useState<TransactionSummaryRow[]>([]);
  const [total, setTotal] = useState(0);
  const [value, setValue] = useState(0);
  const [grantFilter, setGrantFilter] = useState("");
  const [applied, setApplied] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (grant: string) => {
    setLoading(true);
    setError(null);
    try {
      const r = await listPayments(grant ? { grant_code: grant } : {});
      setRows(r.transactions);
      setTotal(r.total);
      setValue(r.value);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load payments.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(applied);
  }, [load, applied]);

  const withExceptions = rows.filter((r) => r.exceptions_count > 0).length;

  return (
    <AppShell>
      <div className="space-y-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Payments</h1>
          <p className="mt-1 text-sm text-gray-600">
            Every completed payment, frozen at the moment it was made.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Kpi label="Payments" value={String(total)} />
          <Kpi label="Total value" value={money(value)} />
          <Kpi
            label="With exceptions"
            value={String(withExceptions)}
            tone={withExceptions > 0 ? "warn" : undefined}
          />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(grantFilter.trim());
          }}
          className="flex flex-wrap items-center gap-2"
        >
          <input
            value={grantFilter}
            onChange={(e) => setGrantFilter(e.target.value)}
            placeholder="Filter by grant code"
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          <button
            type="submit"
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
          >
            Apply
          </button>
          {applied ? (
            <button
              type="button"
              onClick={() => {
                setGrantFilter("");
                setApplied("");
              }}
              className="text-sm font-medium text-gray-500 transition hover:text-gray-900"
            >
              Clear
            </button>
          ) : null}
        </form>

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
            <Banknote className="mx-auto h-8 w-8 text-gray-300" />
            <p className="mt-3 text-sm font-medium text-gray-900">No payments yet</p>
            <p className="mt-1 text-sm text-gray-500">
              Approved requisitions appear here once payment is recorded.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <Th>Requisition</Th>
                  <Th>Payee</Th>
                  <Th className="text-right">Amount</Th>
                  <Th>Charged to</Th>
                  <Th>Paid</Th>
                  <Th>Exceptions</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((t) => (
                  <tr key={t.id} className="transition hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-3">
                      <Link
                        href={`/payments/${encodeURIComponent(t.id)}`}
                        className="font-medium text-brand-600 hover:text-brand-700"
                      >
                        {t.requisition_ref}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-gray-900">{t.vendor_name || "—"}</span>
                      {t.category ? (
                        <span className="mt-0.5 block text-xs text-gray-500">
                          {humanise(t.category)}
                        </span>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-medium tabular-nums text-gray-900">
                      {money(t.amount, t.currency)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                      {[t.grant_code, t.project_code].filter(Boolean).join(" · ") || "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                      {shortDate(t.paid_at)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      {t.exceptions_count > 0 ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700 ring-1 ring-inset ring-purple-200">
                          <ShieldAlert className="h-3 w-3" />
                          {t.exceptions_count}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p
        className={
          tone === "warn"
            ? "mt-1 text-2xl font-bold tracking-tight text-purple-700"
            : "mt-1 text-2xl font-bold tracking-tight text-gray-900"
        }
      >
        {value}
      </p>
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
