"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, Loader2, Lock, RotateCcw, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { PolicyCheckList } from "@/components/erp/PolicyChecks";
import { getPayment } from "@/lib/requisitionApi";
import { dateTime, humanise, money } from "@/lib/requisitionFormat";
import type { TransactionRecord } from "@/types/requisition";

/**
 * The immutable transaction record — the screen an auditor opens.
 *
 * Nothing here is editable and nothing is recomputed. These are the frozen
 * copies of every check, approval and audit line as they stood at the moment
 * the payment was made, which is the only version that means anything after
 * the fact. If a policy changed last week, this record still shows the policy
 * that was actually applied.
 */
export default function PaymentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === "string" ? params.id : "";

  const [txn, setTxn] = useState<TransactionRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const t = await getPayment(id);
        if (!cancelled) setTxn(t);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load this transaction.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

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

  if (error || !txn) {
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl space-y-4">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error ?? "Transaction not found."}
          </div>
          <Link href="/payments" className="text-sm font-medium text-brand-600">
            ← Back to payments
          </Link>
        </div>
      </AppShell>
    );
  }

  const exceptions = txn.checks.filter((c) => c.overridden);

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6">
        <Link
          href="/payments"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Payments
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">
                {txn.requisition_ref}
              </h1>
              {txn.locked ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-700 ring-1 ring-inset ring-gray-300">
                  <Lock className="h-3 w-3" />
                  Locked
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-sm text-gray-600">
              {money(txn.amount, txn.currency)} paid to {txn.vendor_name}
            </p>
          </div>
          <div className="text-right text-xs text-gray-500">
            <p>Paid by {txn.paid_by}</p>
            <p>{dateTime(txn.paid_at)}</p>
          </div>
        </div>

        {exceptions.length > 0 ? (
          <div className="rounded-lg border border-purple-200 bg-purple-50 p-4">
            <p className="text-sm font-semibold text-purple-900">
              {exceptions.length} policy {exceptions.length === 1 ? "exception" : "exceptions"} were
              released to make this payment
            </p>
            <p className="mt-1 text-sm text-purple-800">
              Each one carries the reason given and the authority relied on, below.
            </p>
          </div>
        ) : (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
            <span className="font-semibold">No exceptions.</span> This payment cleared every policy
            check on its own.
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
          <div className="space-y-6">
            <Card title="Payment">
              <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                <Detail label="Payee" value={txn.vendor_name || "—"} />
                <Detail label="Vendor account" value={txn.vendor_account || "—"} />
                <Detail label="Amount" value={money(txn.amount, txn.currency)} />
                <Detail label="Bank reference" value={txn.bank_reference || "—"} />
                <Detail label="Category" value={humanise(txn.category)} />
                <Detail label="Project / cost centre" value={txn.project_code || "—"} />
                <Detail label="Grant" value={txn.grant_code || "—"} />
                <Detail label="Paid at" value={dateTime(txn.paid_at)} />
              </dl>
            </Card>

            <Card
              title="Policy checks as applied"
              subtitle="Frozen at payment — not recomputed against today's policy"
            >
              <PolicyCheckList checks={txn.checks} />
            </Card>
          </div>

          <div className="space-y-6">
            <Card title="Approval trail">
              {txn.approvals.length === 0 ? (
                <p className="text-sm text-gray-500">No approvals recorded.</p>
              ) : (
                <ol className="space-y-3">
                  {txn.approvals.map((a, i) => (
                    <li key={`${a.step}-${a.at}-${i}`} className="border-l-2 border-gray-200 pl-3">
                      <div className="flex items-center gap-1.5">
                        {a.decision === "approved" ? (
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                        ) : a.decision === "declined" ? (
                          <X className="h-3.5 w-3.5 text-red-600" />
                        ) : (
                          <RotateCcw className="h-3.5 w-3.5 text-orange-600" />
                        )}
                        <span className="text-sm font-medium text-gray-900">
                          {humanise(a.step)}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-gray-600">
                        {a.actor} · {humanise(a.department)}
                      </p>
                      <p className="text-xs text-gray-400">{dateTime(a.at)}</p>
                      {a.notes ? (
                        <p className="mt-1 text-xs text-gray-700">&ldquo;{a.notes}&rdquo;</p>
                      ) : null}
                      {a.signature ? (
                        <p className="mt-1 font-mono text-[10px] text-gray-400">
                          sig {a.signature}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </Card>

            <Card title="Audit log" subtitle="Append-only, hash-chained">
              <ol className="space-y-2.5">
                {txn.audit_log.map((e) => (
                  <li key={e.seq} className="text-xs">
                    <p className="font-medium text-gray-900">{humanise(e.event)}</p>
                    {e.detail ? <p className="text-gray-600">{e.detail}</p> : null}
                    <p className="text-gray-400">
                      {e.actor ? `${e.actor} · ` : ""}
                      {dateTime(e.at)}
                    </p>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900">{value}</dd>
    </div>
  );
}
