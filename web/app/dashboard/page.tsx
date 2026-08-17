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
  Wallet,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/erp/StatusBadge";
import { useAuth } from "@/lib/auth";
import { getDashboard, listTransactions } from "@/lib/erpApi";
import {
  agingLabel,
  DEPT_LABEL,
  money,
  relativeTime,
  STATE_LABEL,
} from "@/lib/erpFormat";
import type { DashboardSummary, TransactionSummary } from "@/types/erp";

/**
 * Per-department dashboard — the daily home for finance & compliance.
 *
 * Applying the research: the "pending on me" action queue is the centrepiece
 * (what do I need to do now), KPIs sit above it (value pending, unread, count),
 * status is colour-coded, and aging is surfaced so bottlenecks are obvious.
 */
export default function DashboardPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [queue, setQueue] = useState<TransactionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || !user) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [s, q] = await Promise.all([
          getDashboard(),
          listTransactions({ department: user.department }),
        ]);
        if (!cancelled) {
          setSummary(s);
          setQueue(q);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load your dashboard.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, user]);

  const deptLabel = user ? DEPT_LABEL[user.department] : "";

  return (
    <AppShell
      actions={
        <Link
          href="/vouchers/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" /> New voucher
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

        {/* KPIs */}
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <KpiCard
            icon={<Inbox className="h-4 w-4" />}
            label="Pending on you"
            value={loading ? "—" : String(summary?.pending_on_me ?? 0)}
            hint="items to action"
          />
          <KpiCard
            icon={<Wallet className="h-4 w-4" />}
            label="Value pending"
            value={loading ? "—" : money(summary?.total_value_pending, summary?.currency)}
            hint="not yet paid"
            accent
          />
          <KpiCard
            icon={<Bell className="h-4 w-4" />}
            label="Unread alerts"
            value={loading ? "—" : String(summary?.unread_notifications ?? 0)}
            hint="new since you looked"
          />
        </div>

        {/* Pending queue — the centrepiece */}
        <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Pending on you</h2>
            <span className="text-xs text-gray-400">{queue.length} item{queue.length === 1 ? "" : "s"}</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : queue.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <p className="text-sm font-medium text-gray-900">Nothing waiting on you.</p>
              <p className="mt-1 text-xs text-gray-500">
                When an item reaches {deptLabel}, it shows up here and you&apos;ll get an alert.
              </p>
            </div>
          ) : (
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
        </section>

        {/* State breakdown chips */}
        {summary && Object.keys(summary.counts_by_state).length > 0 && (
          <div className="mt-6 flex flex-wrap gap-2">
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
