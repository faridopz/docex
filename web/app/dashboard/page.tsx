"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Banknote,
  Inbox,
  Loader2,
  Plus,
  ShieldAlert,
  Wallet,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Page } from "@/components/layout/Page";
import { StatusBadge } from "@/components/erp/StatusBadge";
import { useAuth } from "@/lib/auth";
import { getDashboard, listTransactions } from "@/lib/erpApi";
import { getDocumentPermissions, listPendingForMe, listRequisitions } from "@/lib/requisitionApi";
import { useDepartmentNames } from "@/lib/orgNames";
import { WHERE_TONE, whereItIs } from "@/lib/whereItIs";
import {
  agingLabel,
  money,
  relativeTime,
  STATE_LABEL,
} from "@/lib/erpFormat";
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
  const deptName = useDepartmentNames();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [queue, setQueue] = useState<TransactionSummary[]>([]);
  const [reqQueue, setReqQueue] = useState<RequisitionSummary[]>([]);
  const [ownsAStep, setOwnsAStep] = useState(false);
  const [seesEverything, setSeesEverything] = useState(false);
  const [allReqs, setAllReqs] = useState<RequisitionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || !user) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [pending, all, perms] = await Promise.all([
          listPendingForMe(),
          listRequisitions(),
          getDocumentPermissions().catch(() => null),
        ]);
        if (!cancelled) {
          setReqQueue(pending.requisitions);
          setOwnsAStep(pending.steps.length > 0);
          setAllReqs(all);
          setSeesEverything(Boolean(perms?.sees_everything));
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

  const me = (user?.email || "").toLowerCase();
  // My own requests: the ones that need something from me first, then the
  // ones still moving, then finished ones. A programme officer's home.
  const rank = (r: RequisitionSummary) =>
    r.status === "returned" || r.status === "draft" || (r.status === "in_review" && r.blocking_count > 0)
      ? 0
      : r.status === "in_review" || r.status === "on_hold" || r.status === "approved"
        ? 1
        : 2;
  const mine = allReqs
    .filter((r) => r.submitted_by.toLowerCase() === me)
    .sort((a, b) => rank(a) - rank(b) || (b.submitted_at || "").localeCompare(a.submitted_at || ""));
  const mineNeedingMe = mine.filter((r) => rank(r) === 0).length;

  // Organisation figures — only for the people who see the whole
  // organisation. For staff they would be their department's slice, with a
  // label claiming otherwise.
  const openReqs = allReqs.filter((r) => r.status !== "paid" && r.status !== "declined");
  const valuePending = openReqs.reduce((sum, r) => sum + r.amount, 0);
  const reqCurrency = allReqs[0]?.currency ?? "NGN";
  const blockedCount = openReqs.filter((r) => r.status === "in_review" && r.blocking_count > 0).length;
  const awaitingPayment = allReqs.filter((r) => r.status === "approved");

  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const firstName = (user?.name || "").split(" ")[0];

  return (
    <AppShell
      actions={
        <Link
          href="/requisitions/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" /> New payment request
        </Link>
      }
    >
      <Page
        title={`${hello}${firstName ? `, ${firstName}` : ""}`}
        subtitle={
          loading
            ? "Loading…"
            : ownsAStep
              ? reqQueue.length
                ? `${reqQueue.length} payment request${reqQueue.length === 1 ? " is" : "s are"} waiting on ${deptName(user?.department)}.`
                : `Nothing is waiting on ${deptName(user?.department)} right now.`
              : mineNeedingMe
                ? `${mineNeedingMe} of your requests need${mineNeedingMe === 1 ? "s" : ""} something from you.`
                : "Here is where your payment requests are."
        }
      >
        {error && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</p>
        )}

        {seesEverything ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard
              icon={<Inbox className="h-4 w-4" />}
              label="Waiting on you"
              value={loading ? "—" : String(reqQueue.length)}
              hint="to approve or return"
            />
            <KpiCard
              icon={<Wallet className="h-4 w-4" />}
              label="Not yet paid"
              value={loading ? "—" : money(valuePending, reqCurrency)}
              hint={`${openReqs.length} open request${openReqs.length === 1 ? "" : "s"}`}
              accent
            />
            <KpiCard
              icon={<ShieldAlert className="h-4 w-4" />}
              label="Blocked by a check"
              value={loading ? "—" : String(blockedCount)}
              hint="need a fix or a written release"
            />
            <KpiCard
              icon={<Banknote className="h-4 w-4" />}
              label="Approved, not paid"
              value={loading ? "—" : String(awaitingPayment.length)}
              hint="ready for Finance to pay"
            />
          </div>
        ) : null}

        {ownsAStep ? (
          <RequestList
            title="Waiting on you"
            seeAll={{ href: "/requisitions?tab=waiting", label: "Open the full queue" }}
            rows={reqQueue.slice(0, 8)}
            more={Math.max(0, reqQueue.length - 8)}
            loading={loading}
            empty={`Nothing waiting. When a request reaches ${deptName(user?.department)}, it appears here and you get an alert.`}
            deptName={deptName}
            me={user?.email}
            onOpen={(id) => router.push(`/requisitions/${encodeURIComponent(id)}`)}
          />
        ) : null}

        <RequestList
          title="Your requests"
          seeAll={{ href: "/requisitions?tab=raised", label: "See all of yours" }}
          rows={mine.slice(0, 6)}
          more={Math.max(0, mine.length - 6)}
          loading={loading}
          empty="You haven't raised a payment request yet. Use “New payment request” at the top when you need to pay someone."
          deptName={deptName}
          me={user?.email}
          onOpen={(id) => router.push(`/requisitions/${encodeURIComponent(id)}`)}
        />

        {/* Legacy voucher/transaction queue — rendered ONLY when that system
            actually holds something for this department, so an org that has
            moved to requisitions never sees an empty second queue. */}
        {queue.length > 0 && (
          <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
              <h2 className="text-sm font-semibold text-gray-900">Vouchers pending on you</h2>
              <span className="text-xs text-gray-400">{queue.length} item{queue.length === 1 ? "" : "s"}</span>
            </div>
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
                      <span className="w-14 shrink-0 font-mono text-sm font-semibold text-brand-700">{t.ref}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-gray-900">{t.title}</span>
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
      </Page>
    </AppShell>
  );
}

function RequestList({
  title,
  seeAll,
  rows,
  more,
  loading,
  empty,
  deptName,
  me,
  onOpen,
}: {
  title: string;
  seeAll: { href: string; label: string };
  rows: RequisitionSummary[];
  more: number;
  loading: boolean;
  empty: string;
  deptName: (key?: string | null) => string;
  me?: string | null;
  onOpen: (id: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {rows.length ? (
          <Link href={seeAll.href} className="text-xs font-medium text-gray-500 transition hover:text-brand-700">
            {seeAll.label}
            {more ? ` (${more} more)` : ""} →
          </Link>
        ) : null}
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : rows.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-gray-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-gray-50">
          {rows.map((r) => {
            const where = whereItIs(r, deptName, me);
            const aging = r.status === "in_review" ? agingLabel(r.updated_at ?? r.submitted_at) : null;
            return (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => onOpen(r.id)}
                  className="flex w-full items-center gap-4 px-5 py-3.5 text-left transition hover:bg-gray-50"
                >
                  <span className="w-20 shrink-0 font-mono text-sm font-semibold text-brand-700">{r.ref}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-gray-900">{r.vendor_name}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                      <span className={`rounded-md px-2 py-0.5 font-medium ${WHERE_TONE[where.tone]}`}>{where.text}</span>
                      {r.submitted_by.toLowerCase() !== (me || "").toLowerCase() ? (
                        <span>from {r.submitted_by_name || r.submitted_by}</span>
                      ) : null}
                      <span>· {relativeTime(r.submitted_at)}</span>
                      {aging && <span className={`font-medium ${aging.tone}`}>· {aging.label}</span>}
                      {r.blocking_count > 0 && r.submitted_by.toLowerCase() !== (me || "").toLowerCase() ? (
                        <span className="font-semibold text-rose-600">
                          · {r.blocking_count} check{r.blocking_count === 1 ? "" : "s"} blocking
                        </span>
                      ) : null}
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
