"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Bell,
  Inbox,
  Loader2,
  Plus,
  ShieldAlert,
  Wallet,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ReqStatusBadge } from "@/components/erp/PolicyChecks";
import { StatusBadge } from "@/components/erp/StatusBadge";
import { useAuth } from "@/lib/auth";
import { getDashboard, listTransactions } from "@/lib/erpApi";
import { listPendingForMe, listRequisitions } from "@/lib/requisitionApi";
import {
  agingLabel,
  DEPT_LABEL,
  money,
  relativeTime,
  STATE_LABEL,
} from "@/lib/erpFormat";
import { humanise } from "@/lib/requisitionFormat";
import type { DashboardSummary, TransactionSummary } from "@/types/erp";
import type { RequisitionSummary } from "@/types/requisition";

/**
 * Per-department dashboard — the daily home for finance & compliance.
 *
 * The "pending on me" action queue is the centrepiece (what do I need to do
 * now), KPIs sit above it, status is colour-coded, and aging is surfaced so
 * bottlenecks are obvious.
 *
 * REQUISITION-FIRST. This screen used to read only `tx.list_all()` — the
 * legacy transaction/voucher system — which meant an org whose payments run
 * through the requisition engine (NEEM's does; it is the spine with the
 * approval chain, the policy checks and the audit trail) landed after sign-in
 * on a dashboard reading zero in every box, above a queue of nothing, under a
 * primary button pointing at a voucher screen their own nav doesn't show. The
 * first screen of the product described a system they weren't using.
 *
 * It now leads with requisitions and keeps the legacy transaction queue as a
 * secondary section, rendered only when that system actually holds something
 * — so installs still using vouchers lose nothing, and installs that aren't
 * stop being shown an empty half of a product.
 */
export default function DashboardPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [queue, setQueue] = useState<TransactionSummary[]>([]);
  const [reqQueue, setReqQueue] = useState<RequisitionSummary[]>([]);
  const [allReqs, setAllReqs] = useState<RequisitionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || !user) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [pending, all] = await Promise.all([
          listPendingForMe(),
          listRequisitions(),
        ]);
        if (!cancelled) {
          setReqQueue(pending.requisitions);
          setAllReqs(all);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load your dashboard.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }

      // Legacy voucher/transaction system — best-effort and never fatal. An
      // org that doesn't use it should not see an error about it.
      try {
        const [s, q] = await Promise.all([
          getDashboard(),
          listTransactions({ department: user.department }),
        ]);
        if (!cancelled) {
          setSummary(s);
          setQueue(q);
        }
      } catch {
        /* silent: this half of the screen simply doesn't render */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, user]);

  const deptLabel = user ? DEPT_LABEL[user.department] : "";

  // Money still in flight — everything raised that hasn't been paid or
  // declined. This is the number a finance lead actually opens the app for.
  const openReqs = allReqs.filter((r) => r.status !== "paid" && r.status !== "declined");
  const valuePending = openReqs.reduce((sum, r) => sum + r.amount, 0);
  const reqCurrency = allReqs[0]?.currency ?? "NGN";
  const blockedCount = openReqs.filter((r) => r.blocking_count > 0).length;

  const reqCounts = allReqs.reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <AppShell
      actions={
        // Was "New voucher" → /vouchers/new, a screen hidden from the nav for
        // any org without attendance_payments. The primary action on the home
        // screen now starts the flow every org actually uses.
        <Link
          href="/requisitions/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" /> New payment request
        </Link>
      }
    >
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">
            {deptLabel} workspace
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-gray-900">
            What&apos;s waiting on you
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {user?.name ? `Signed in as ${user.name}. ` : ""}
            Items your department needs to act on, newest first.
          </p>
        </header>

        {error && (
          <p className="mb-6 rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {error}
          </p>
        )}

        {/* KPIs — now the requisition reality, not the legacy voucher one. */}
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-4">
          <KpiCard
            icon={<Inbox className="h-4 w-4" />}
            label="Waiting on you"
            value={loading ? "—" : String(reqQueue.length)}
            hint="to approve or return"
          />
          <KpiCard
            icon={<Wallet className="h-4 w-4" />}
            label="Value in flight"
            value={loading ? "—" : money(valuePending, reqCurrency)}
            hint="raised, not yet paid"
            accent
          />
          <KpiCard
            icon={<ShieldAlert className="h-4 w-4" />}
            label="Blocked"
            value={loading ? "—" : String(blockedCount)}
            hint="a check nobody released"
          />
          <KpiCard
            icon={<Bell className="h-4 w-4" />}
            label="Unread alerts"
            value={loading ? "—" : String(summary?.unread_notifications ?? 0)}
            hint="new since you looked"
          />
        </div>

        {/* Requisition queue — the centrepiece. */}
        <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Payment requests waiting on you</h2>
            <Link
              href="/requisitions/board"
              className="text-xs font-medium text-gray-500 transition hover:text-brand-700"
            >
              See the whole pipeline →
            </Link>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : reqQueue.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <p className="text-sm font-medium text-gray-900">Nothing waiting on you.</p>
              <p className="mt-1 text-xs text-gray-500">
                When a payment request reaches {deptLabel}, it shows up here and you&apos;ll get an
                alert.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-gray-50">
              {reqQueue.map((r) => {
                const aging = agingLabel(r.submitted_at);
                return (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => router.push(`/requisitions/${encodeURIComponent(r.id)}`)}
                      className="flex w-full items-center gap-4 px-5 py-3.5 text-left transition hover:bg-gray-50"
                    >
                      <span className="w-20 shrink-0 font-mono text-sm font-semibold text-brand-700">
                        {r.ref}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-gray-900">
                          {r.vendor_name}
                        </span>
                        <span className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                          <ReqStatusBadge status={r.status} />
                          <span>· {relativeTime(r.submitted_at)}</span>
                          {aging && <span className={`font-medium ${aging.tone}`}>· {aging.label}</span>}
                          {r.blocking_count > 0 && (
                            <span className="font-semibold text-rose-600">
                              · {r.blocking_count} blocking
                            </span>
                          )}
                        </span>
                      </span>
                      <span className="shrink-0 text-right text-sm font-semibold text-gray-900">
                        {money(r.amount, r.currency)}
                      </span>
                      <ArrowRight className="h-4 w-4 shrink-0 text-gray-300" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Requisition status breakdown. */}
        {Object.keys(reqCounts).length > 0 && (
          <div className="mt-6 flex flex-wrap gap-2">
            {Object.entries(reqCounts).map(([status, n]) => (
              <span
                key={status}
                className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 px-3 py-1 text-xs text-gray-600 ring-1 ring-inset ring-gray-100"
              >
                {humanise(status)}
                <span className="font-semibold text-gray-900">{n}</span>
              </span>
            ))}
          </div>
        )}

        {/* Legacy voucher/transaction queue — rendered ONLY when that system
            actually holds something for this department, so an org that has
            moved to requisitions never sees an empty second queue. */}
        {queue.length > 0 && (
        <section className="mt-8 rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Vouchers pending on you</h2>
            <span className="text-xs text-gray-400">{queue.length} item{queue.length === 1 ? "" : "s"}</span>
          </div>

          {(
            <ul className="divide-y divide-gray-50">
              {queue.map((t) => {
                const aging = agingLabel(t.updated_at);
                return (
                  <li key={t.ref}>
                    <button
                      type="button"
                      onClick={() => router.push(`/transactions/${encodeURIComponent(t.ref)}`)}
                      className="flex w-full items-center gap-4 px-5 py-3.5 text-left transition hover:bg-gray-50"
                    >
                      <span className="w-14 shrink-0 font-mono text-sm font-semibold text-brand-700">
                        {t.ref}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-gray-900">
                          {t.title}
                        </span>
                        <span className="mt-0.5 flex items-center gap-2 text-xs text-gray-400">
                          <StatusBadge state={t.state} />
                          <span>· {relativeTime(t.updated_at)}</span>
                          {aging && <span className={`font-medium ${aging.tone}`}>· {aging.label}</span>}
                        </span>
                      </span>
                      <span className="shrink-0 text-right text-sm font-semibold text-gray-900">
                        {money(t.amount, t.currency)}
                      </span>
                      <ArrowRight className="h-4 w-4 shrink-0 text-gray-300" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {summary && Object.keys(summary.counts_by_state).length > 0 && (
            <div className="flex flex-wrap gap-2 border-t border-gray-100 px-5 py-3">
              {Object.entries(summary.counts_by_state).map(([state, n]) => (
                <span
                  key={state}
                  className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 px-3 py-1 text-xs text-gray-600 ring-1 ring-inset ring-gray-100"
                >
                  {STATE_LABEL[state as keyof typeof STATE_LABEL] ?? state}
                  <span className="font-semibold text-gray-900">{n}</span>
                </span>
              ))}
            </div>
          )}
        </section>
        )}
      </div>
    </AppShell>
  );
}

function KpiCard({
  icon,
  label,
  value,
  hint,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 text-gray-400">
        <span className={accent ? "text-brand-600" : ""}>{icon}</span>
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className={`mt-2 text-2xl font-bold tracking-tight ${accent ? "text-brand-700" : "text-gray-900"}`}>
        {value}
      </p>
      <p className="mt-0.5 text-xs text-gray-400">{hint}</p>
    </div>
  );
}
