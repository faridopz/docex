"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, Loader2, RotateCcw, ShieldAlert, XCircle } from "lucide-react";
import { PolicyCheckList } from "@/components/erp/PolicyChecks";
import {
  actOnRequisitionSignoff,
  verifyRequisitionSignoff,
  type SignoffView,
} from "@/lib/requisitionApi";
import { humanise, money, shortDate } from "@/lib/requisitionFormat";

/**
 * Emailed sign-off — the page an approver lands on from their link.
 *
 * Deliberately outside AppShell: whoever opens this may have no DOCex
 * account, no session and no idea what DOCex is. There is no nav to give
 * them, and showing one would imply an application they cannot get into.
 *
 * The design rule here is that nobody authorises money on a summary line.
 * This shows the amount, the amount in words, the payee, the purpose, who
 * raised it, and every deterministic policy check — including any that are
 * blocking — before the buttons. If an approver has to open something else
 * to decide, the link has failed at its job.
 *
 * What this page cannot do, on purpose: release a blocking check. An
 * override needs a named authority and an amount within that step's limit,
 * checked against a real account. A link in an inbox is not that, so a
 * blocked request can only be returned from here, never approved through.
 */
export default function RequisitionSignoffPage() {
  const params = useParams<{ token: string }>();
  const token = typeof params?.token === "string" ? params.token : "";

  const [view, setView] = useState<SignoffView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"" | "approve" | "return" | "decline">("");
  const [done, setDone] = useState<{ action: string; ref: string } | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      setView(await verifyRequisitionSignoff(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "This link could not be opened.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(action: "approve" | "return" | "decline") {
    setBusy(action);
    setError(null);
    try {
      const res = await actOnRequisitionSignoff(token, { action, note });
      setDone({ action, ref: res.requisition_ref });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not record that decision.");
      // Re-read: the most common reason is that it moved on, and the page
      // should now show that rather than keep offering buttons.
      void load();
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="min-h-screen bg-[#fafaf7] px-4 py-10">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6">
          <p className="text-lg font-bold tracking-tight text-brand-700">DOCex</p>
          <p className="text-xs uppercase tracking-wide text-gray-400">
            Audit-grade compliance
          </p>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 rounded-2xl border border-gray-200 bg-white p-8 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Opening your approval link…
          </div>
        ) : done ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-8 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-600" />
            <h1 className="mt-3 text-lg font-bold text-emerald-900">
              {done.action === "approve"
                ? `${done.ref} approved`
                : done.action === "return"
                  ? `${done.ref} sent back`
                  : `${done.ref} declined`}
            </h1>
            <p className="mt-1 text-sm text-emerald-800">
              Recorded against {view?.approver_email} with the time and the address it came
              from. You can close this page.
            </p>
          </div>
        ) : error && !view ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8">
            <h1 className="text-base font-semibold text-red-900">
              This approval link cannot be used
            </h1>
            <p className="mt-1 text-sm text-red-800">{error}</p>
            <p className="mt-3 text-xs text-red-700">
              Links expire after seven days and only work for the person they were sent to.
              Ask whoever sent it for a new one.
            </p>
          </div>
        ) : view ? (
          <div className="space-y-4">
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                {view.step_label} — sign-off requested
              </p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-gray-900">
                {view.requisition_ref}
              </h1>
              <p className="mt-1 text-sm text-gray-600">
                Requested from {view.approver_email}
              </p>

              <dl className="mt-5 grid gap-x-8 gap-y-3 border-t border-gray-100 pt-5 sm:grid-cols-2">
                <Detail label="Payee" value={view.payee} />
                <Detail label="Amount" value={money(view.amount, view.currency)} />
                <Detail label="Payment type" value={humanise(view.payment_type)} />
                <Detail label="Category" value={humanise(view.category) || "—"} />
                <Detail label="Raised by" value={view.submitted_by} />
                <Detail label="Raised on" value={shortDate(view.submitted_at)} />
              </dl>
              <p className="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-500">
                Amount in words:{" "}
                <span className="text-gray-700">{view.amount_in_words}</span>
              </p>
              {view.description ? (
                <p className="mt-3 text-sm text-gray-700">{view.description}</p>
              ) : null}
              {view.attachment_count > 0 ? (
                <p className="mt-3 text-xs text-gray-500">
                  {view.attachment_count} supporting{" "}
                  {view.attachment_count === 1 ? "document" : "documents"} attached — ask the
                  requester if you need to see {view.attachment_count === 1 ? "it" : "them"}.
                </p>
              ) : null}
            </div>

            {view.blocking_count > 0 ? (
              <div className="flex gap-3 rounded-2xl border border-red-300 bg-red-50 p-5">
                <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
                <div>
                  <p className="text-sm font-semibold text-red-900">
                    {view.blocking_count}{" "}
                    {view.blocking_count === 1 ? "check blocks" : "checks block"} this payment
                  </p>
                  <p className="mt-0.5 text-sm text-red-800">
                    A blocking check can only be released by someone signed in who holds that
                    authority, and it is recorded against their name. From this link you can
                    send it back, but not approve it through.
                  </p>
                </div>
              </div>
            ) : null}

            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="mb-3 text-sm font-semibold text-gray-900">Policy checks</h2>
              <PolicyCheckList checks={view.checks} />
            </div>

            {view.compliance ? (
              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
                <h2 className="text-sm font-semibold text-gray-900">
                  Checked against &ldquo;{view.compliance.rulebook_name}&rdquo;
                </h2>
                <p className="mt-1 text-sm text-gray-700">
                  <span className="font-semibold">
                    {humanise(view.compliance.overall_verdict)}
                  </span>{" "}
                  — {view.compliance.overall_summary}
                </p>
              </div>
            ) : null}

            {!view.actionable ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
                {view.already_moved
                  ? `${view.requisition_ref} has already moved past the ${view.step_label} step, so there is nothing to sign off here.`
                  : `${view.requisition_ref} is ${humanise(view.status)} and is not awaiting a decision.`}
              </div>
            ) : (
              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-gray-700">
                    Note {view.blocking_count > 0 ? "(required when sending back)" : "(optional)"}
                  </span>
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={3}
                    placeholder="Anything the requester or the next approver should know."
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                </label>

                {error ? (
                  <p className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                    {error}
                  </p>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => act("approve")}
                    disabled={busy !== "" || view.blocking_count > 0}
                    title={
                      view.blocking_count > 0
                        ? "A blocking check must be released by someone signed in"
                        : undefined
                    }
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busy === "approve" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4" />
                    )}
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => act("return")}
                    disabled={busy !== ""}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-700 shadow-sm transition hover:bg-gray-50 disabled:opacity-50"
                  >
                    {busy === "return" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RotateCcw className="h-4 w-4" />
                    )}
                    Send back
                  </button>
                  <button
                    type="button"
                    onClick={() => act("decline")}
                    disabled={busy !== ""}
                    className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-50 disabled:opacity-50"
                  >
                    {busy === "decline" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <XCircle className="h-4 w-4" />
                    )}
                    Decline
                  </button>
                </div>

                <p className="mt-4 border-t border-gray-100 pt-3 text-xs text-gray-400">
                  Your decision is recorded against {view.approver_email}, with the time and
                  the address it came from, in a tamper-evident log. This link expires seven
                  days after it was sent and works only once for this step.
                </p>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </main>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900">{value}</dd>
    </div>
  );
}
