"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Loader2,
  ShieldCheck,
  Undo2,
} from "lucide-react";
import {
  submitApproval,
  verifyApprovalToken,
  type ApprovalTokenInfo,
} from "@/lib/api";
import {
  overallVerdictColor,
  overallVerdictDot,
  overallVerdictLabel,
} from "@/types";

/**
 * Public, token-verified approval page. The approver opens their unique
 * email link, reviews the voucher summary, and either signs off (verified
 * by control of their mailbox) or returns it for changes — no login. The
 * action is recorded on the voucher's audit trail with email + timestamp + IP.
 */
export default function ApprovePage({
  params,
}: {
  params: { token: string };
}) {
  const { token } = params;

  const [info, setInfo] = useState<ApprovalTokenInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<"idle" | "return">("idle");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<"approved" | "returned" | null>(null);

  const load = useCallback(async () => {
    try {
      setInfo(await verifyApprovalToken(token));
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "This approval link isn't valid.",
      );
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(action: "approve" | "return") {
    setSubmitting(true);
    setError(null);
    try {
      await submitApproval(token, action, action === "return" ? note.trim() : undefined);
      setDone(action === "approve" ? "approved" : "returned");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record your decision.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf7]">
      <header className="border-b border-gray-100 bg-white">
        <div className="mx-auto flex h-16 max-w-xl items-center px-6">
          <span className="text-lg font-bold tracking-tight text-brand-600">DOCex</span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-xl flex-1 px-6 py-10">
        {loadError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            {loadError}
          </div>
        ) : !info ? (
          <div className="flex items-center gap-2 py-24 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Verifying your link…
          </div>
        ) : done ? (
          <div className="rounded-2xl border border-emerald-200 bg-white p-8 text-center shadow-sm">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <h1 className="mt-4 text-xl font-semibold text-gray-900">
              {done === "approved" ? "Sign-off recorded" : "Returned for changes"}
            </h1>
            <p className="mt-2 text-sm text-gray-600">
              {done === "approved"
                ? `Thank you. Your sign-off as ${info.stage} on ${info.payment_label} is on the audit trail.`
                : `Your request has been sent back to the team for ${info.payment_label}.`}
            </p>
          </div>
        ) : info.already_signed ? (
          <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
            <ShieldCheck className="mx-auto h-10 w-10 text-gray-300" />
            <h1 className="mt-3 text-lg font-semibold text-gray-900">
              Already signed off
            </h1>
            <p className="mt-1 text-sm text-gray-600">
              The {info.stage} stage on {info.payment_label} has already been
              signed. No further action is needed.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-600">
                <ShieldCheck className="h-3 w-3 text-brand-600" />
                Verified approval
              </div>
              <h1 className="mt-4 text-2xl font-bold tracking-tight text-gray-900">
                {info.payment_label}
              </h1>
              <p className="mt-1 text-sm text-gray-600">
                You&apos;re signing off as{" "}
                <span className="font-medium text-gray-800">{info.stage}</span>,
                as <span className="font-medium text-gray-800">{info.approver_email}</span>.
              </p>
            </div>

            <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-900">Compliance result</p>
                <span
                  className={
                    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium " +
                    overallVerdictColor[info.overall_verdict]
                  }
                >
                  <span className={"h-1.5 w-1.5 rounded-full " + overallVerdictDot[info.overall_verdict]} />
                  {overallVerdictLabel[info.overall_verdict]}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-gray-600">
                {info.overall_summary}
              </p>
              <p className="mt-3 text-xs text-gray-400">
                Checked against {info.rulebook_name}. Approval chain:{" "}
                {info.workflow.join(" → ")}.
              </p>
            </div>

            {info.overall_verdict === "blocked" && (
              <div className="rounded-lg border border-rose-200 bg-rose-50/60 px-3 py-2 text-xs text-rose-700">
                This voucher was <strong>blocked</strong> by the compliance check.
                Review carefully before approving, or return it for changes.
              </div>
            )}

            {mode === "return" ? (
              <div className="space-y-3 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-semibold text-gray-900">
                  What needs to change?
                </p>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                  placeholder="e.g. 'Missing the delivery note and the third quotation — please attach and resubmit.'"
                  className="w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setMode("idle")}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => act("return")}
                    disabled={submitting || !note.trim()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-amber-700 disabled:opacity-50"
                  >
                    {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Undo2 className="h-4 w-4" />}
                    Return for changes
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={() => act("approve")}
                  disabled={submitting}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-brand-600 px-5 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
                >
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  {info.is_final_stage ? "Approve voucher" : "Sign off this stage"}
                </button>
                <button
                  type="button"
                  onClick={() => setMode("return")}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-5 py-3 text-sm font-medium text-gray-700 transition hover:border-amber-300 hover:text-amber-700"
                >
                  <Undo2 className="h-4 w-4" />
                  Return for changes
                </button>
              </div>
            )}

            {error && <p className="text-sm text-rose-600">{error}</p>}
          </div>
        )}
      </main>
    </div>
  );
}
