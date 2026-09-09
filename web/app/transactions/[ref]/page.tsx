"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CornerUpLeft, Eye, Loader2, Send } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/erp/StatusBadge";
import { StatusTimeline } from "@/components/erp/StatusTimeline";
import { useAuth } from "@/lib/auth";
import {
  addTransactionNote,
  getAllowedTransitions,
  getTransaction,
  transitionTransaction,
  viewTransaction,
} from "@/lib/erpApi";
import { DEPT_LABEL, money, STATE_LABEL } from "@/lib/erpFormat";
import type { Transaction, TxnState } from "@/types/erp";

/** Friendly labels for the action buttons, per target state. */
const ACTION_LABEL: Record<TxnState, string> = {
  submitted: "Reopen",
  intake: "Send to intake",
  compliance_review: "Send to compliance",
  finance_review: "Pass to finance",
  approval: "Send for approval",
  paid: "Mark paid",
  returned: "Return for fixes",
};

export default function TransactionDetailPage() {
  const params = useParams();
  const ref = decodeURIComponent(String(params?.ref ?? ""));
  const { user, ready } = useAuth();

  const [txn, setTxn] = useState<Transaction | null>(null);
  const [allowed, setAllowed] = useState<TxnState[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<TxnState | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [t, next] = await Promise.all([getTransaction(ref), getAllowedTransitions(ref)]);
    setTxn(t);
    setAllowed(next.allowed);
  }, [ref]);

  useEffect(() => {
    if (!ready || !user || !ref) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        // Record that this department looked at it (the "viewed by" signal),
        // then load the (updated) transaction + allowed actions.
        await viewTransaction(ref, user.department, user.name).catch(() => {});
        if (!cancelled) await load();
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load this transaction.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, user, ref, load]);

  async function act(to: TxnState) {
    if (!user) return;
    setBusy(to);
    setError(null);
    try {
      await transitionTransaction(ref, {
        to_state: to,
        department: user.department,
        actor: user.name,
        note: note.trim() || undefined,
      });
      setNote("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That action could not be completed.");
    } finally {
      setBusy(null);
    }
  }

  async function saveNote() {
    if (!user || !note.trim()) return;
    setBusy("submitted"); // reuse busy flag as a generic "working"
    try {
      await addTransactionNote(ref, note.trim(), user.department, user.name);
      setNote("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the note.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-8">
        <Link
          href="/dashboard"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
        </Link>

        {loading ? (
          <div className="flex items-center justify-center py-24 text-gray-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : !txn ? (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {error ?? "Transaction not found."}
          </p>
        ) : (
          <>
            {/* Header */}
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-lg font-bold text-brand-700">{txn.ref}</span>
                  <StatusBadge state={txn.state} />
                </div>
                <h1 className="mt-1.5 text-xl font-bold tracking-tight text-gray-900">{txn.title}</h1>
                <p className="mt-1 text-sm text-gray-500">
                  {txn.owner_department ? `With ${DEPT_LABEL[txn.owner_department]}` : "Unassigned"} ·{" "}
                  {money(txn.amount, txn.currency)}
                </p>
              </div>
            </div>

            {error && (
              <p className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</p>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
              {/* Actions + note */}
              <div className="lg:col-span-2">
                <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                  <h2 className="text-sm font-semibold text-gray-900">Actions</h2>
                  {allowed.length === 0 ? (
                    <p className="mt-2 text-xs text-gray-500">
                      This item is {STATE_LABEL[txn.state].toLowerCase()} — no further action.
                    </p>
                  ) : (
                    <div className="mt-3 space-y-2">
                      {allowed.map((to) => {
                        const isReturn = to === "returned";
                        return (
                          <button
                            key={to}
                            type="button"
                            disabled={busy !== null}
                            onClick={() => act(to)}
                            className={
                              "flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60 " +
                              (isReturn
                                ? "border border-red-200 bg-red-50 text-red-700 hover:bg-red-100"
                                : "bg-brand-600 text-white hover:bg-brand-700")
                            }
                          >
                            {busy === to ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : isReturn ? (
                              <CornerUpLeft className="h-4 w-4" />
                            ) : (
                              <Send className="h-4 w-4" />
                            )}
                            {ACTION_LABEL[to]}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  <div className="mt-4">
                    <label className="mb-1 block text-xs font-medium text-gray-700">
                      Note {allowed.includes("returned") && <span className="text-gray-400">(recommended when returning)</span>}
                    </label>
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      rows={3}
                      placeholder="Add context for the next department…"
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                    />
                    <button
                      type="button"
                      onClick={saveNote}
                      disabled={!note.trim() || busy !== null}
                      className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-600 transition hover:bg-gray-50 disabled:opacity-50"
                    >
                      Save note only
                    </button>
                  </div>
                </div>

                {/* Viewed by */}
                {txn.viewed_by.length > 0 && (
                  <div className="mt-4 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                    <h2 className="flex items-center gap-1.5 text-sm font-semibold text-gray-900">
                      <Eye className="h-4 w-4 text-gray-400" /> Viewed by
                    </h2>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {txn.viewed_by.map((v) => (
                        <span key={v} className="rounded-full bg-gray-50 px-2.5 py-0.5 text-xs text-gray-600 ring-1 ring-inset ring-gray-100">
                          {DEPT_LABEL[v as keyof typeof DEPT_LABEL] ?? v}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Audit timeline */}
              <div className="lg:col-span-3">
                <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                  <h2 className="mb-4 text-sm font-semibold text-gray-900">Status history</h2>
                  <StatusTimeline history={txn.history} />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
