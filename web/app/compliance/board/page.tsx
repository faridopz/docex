"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Banknote,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { listChecks, markPaid } from "@/lib/api";
import type { CheckLifecycle, CheckSummary } from "@/types";

/**
 * Payment pipeline board — where every voucher sits, end to end. Mirrors the
 * finance flow (request → finance → compliance → director → ED → paid) but
 * stays org-agnostic: the lifecycle bucket is derived server-side from each
 * check's verdict, its rulebook's approval chain, the signed stages, and paid
 * status. The per-card stage label shows the exact next step.
 */

const COLUMNS: {
  key: CheckLifecycle;
  title: string;
  hint: string;
  icon: typeof Clock;
  accent: string;
}[] = [
  {
    key: "needs_attention",
    title: "Needs attention",
    hint: "Blocked, flagged, or has an open risk",
    icon: ShieldAlert,
    accent: "text-rose-600",
  },
  {
    key: "requisition",
    title: "Requisition",
    hint: "Checked — before a PV is raised",
    icon: FileText,
    accent: "text-gray-600",
  },
  {
    key: "in_approval",
    title: "In approval (PV)",
    hint: "Voucher raised, moving through sign-off",
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
    hint: "Payment executed",
    icon: Banknote,
    accent: "text-brand-600",
  },
];

export default function PipelineBoardPage() {
  const [checks, setChecks] = useState<CheckSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listChecks();
        if (!cancelled) setChecks(list);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load the board. Is the API running?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => {
    const g: Record<CheckLifecycle, CheckSummary[]> = {
      needs_attention: [],
      requisition: [],
      in_approval: [],
      approved: [],
      paid: [],
    };
    for (const c of checks ?? []) {
      const key = (c.lifecycle ?? "in_approval") as CheckLifecycle;
      (g[key] ?? g.in_approval).push(c);
    }
    return g;
  }, [checks]);

  async function handleMarkPaid(id: string) {
    setBusyId(id);
    try {
      const updated = await markPaid(id);
      // Move the card to Paid (or back) by refreshing its summary fields.
      setChecks((prev) =>
        (prev ?? []).map((c) =>
          c.payment_id === id
            ? {
                ...c,
                paid: updated.paid,
                lifecycle: updated.paid ? "paid" : "approved",
                stage_label: updated.paid
                  ? "Paid"
                  : "Approved — ready for payment",
              }
            : c,
        ),
      );
    } catch {
      /* surfaced via the row staying put; keep it simple */
    } finally {
      setBusyId(null);
    }
  }

  return (
    <AppShell active="compliance">
      <main className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            Payment pipeline
          </h1>
          <p className="mt-2 max-w-2xl text-base text-gray-600">
            Every payment, and exactly where it sits — from check to sign-off to
            paid. No more chasing email threads to find a voucher's status.
          </p>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {checks === null && !error && (
          <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading board…
          </div>
        )}

        {checks !== null && (
          <div className="grid gap-4 lg:grid-cols-5">
            {COLUMNS.map((col) => {
              const items = grouped[col.key];
              const Icon = col.icon;
              return (
                <div key={col.key} className="flex flex-col">
                  <div className="mb-2 flex items-center gap-2 px-1">
                    <Icon className={`h-4 w-4 ${col.accent}`} />
                    <h2 className="text-sm font-semibold text-gray-900">
                      {col.title}
                    </h2>
                    <span className="ml-auto inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-gray-100 px-1.5 text-xs font-semibold tabular-nums text-gray-600">
                      {items.length}
                    </span>
                  </div>
                  <p className="mb-3 px-1 text-[11px] text-gray-400">{col.hint}</p>

                  <div className="flex-1 space-y-2 rounded-xl bg-gray-50/70 p-2">
                    {items.length === 0 ? (
                      <p className="px-2 py-6 text-center text-xs text-gray-400">
                        Nothing here
                      </p>
                    ) : (
                      items.map((c) => (
                        <div
                          key={c.payment_id}
                          className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm"
                        >
                          <Link
                            href={`/compliance/checks/${c.payment_id}`}
                            className="group block"
                          >
                            <p className="truncate text-sm font-semibold text-gray-900 group-hover:text-brand-700">
                              {c.payment_label}
                            </p>
                            <p className="mt-0.5 truncate text-[11px] text-gray-500">
                              {c.rulebook_name}
                            </p>
                          </Link>
                          <div className="mt-2 flex items-center justify-between gap-2">
                            <span className="truncate text-[11px] font-medium text-gray-600">
                              {c.stage_label}
                            </span>
                            {(c.open_risk_count ?? 0) > 0 && (
                              <span className="shrink-0 rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700">
                                {c.open_risk_count} risk
                                {c.open_risk_count === 1 ? "" : "s"}
                              </span>
                            )}
                          </div>
                          {col.key === "approved" && (
                            <button
                              type="button"
                              onClick={() => handleMarkPaid(c.payment_id)}
                              disabled={busyId === c.payment_id}
                              className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-brand-600 px-2 py-1.5 text-xs font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
                            >
                              {busyId === c.payment_id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Banknote className="h-3.5 w-3.5" />
                              )}
                              Mark paid
                            </button>
                          )}
                          {col.key === "paid" && (
                            <button
                              type="button"
                              onClick={() => handleMarkPaid(c.payment_id)}
                              disabled={busyId === c.payment_id}
                              className="mt-2 text-[11px] text-gray-400 transition hover:text-gray-700 disabled:opacity-50"
                            >
                              Undo paid
                            </button>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {checks !== null && checks.length > 0 && (
          <div className="mt-6">
            <Link
              href="/compliance/checks"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-brand-700"
            >
              View all checks as a list
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}
      </main>
    </AppShell>
  );
}
