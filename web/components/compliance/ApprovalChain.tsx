"use client";

import { useState } from "react";
import { Check, CircleDashed, Copy, Loader2, Lock, Mail } from "lucide-react";
import { requestSignoff } from "@/lib/api";
import type { ComplianceCheckResult } from "@/types";

/**
 * <ApprovalChain> — the configurable, multi-stage, VERIFIED sign-off.
 *
 * Stages come from the rulebook's `approval_workflow` (e.g. TA Connect:
 * Compliance Officer → Head of Finance → Executive Director); another org
 * defines its own — nothing here is hardcoded.
 *
 * Sign-off is not a button anyone can click. For the current stage, the
 * officer sends a request to the approver's email; DOCex emails them a
 * unique, expiring, single-use magic link. Only the mailbox owner can open
 * it and approve (or return the voucher for changes), and the sign-off is
 * recorded with their email + timestamp + IP. This panel orchestrates the
 * chain and shows who we're waiting on; the actual approval happens on the
 * verified /approve/<token> page.
 */

const MARKER = "Stage sign-off —";

function signedStages(check: ComplianceCheckResult): Set<string> {
  const out = new Set<string>();
  for (const e of check.decision_log ?? []) {
    const note = e.note ?? "";
    const i = note.indexOf(MARKER);
    if (i !== -1) {
      // format: "Stage sign-off — <stage>: <name>"
      const after = note.slice(i + MARKER.length).trim();
      const stage = after.split(":")[0]?.trim();
      if (stage) out.add(stage);
    }
  }
  return out;
}

export function ApprovalChain({
  check,
  workflow,
  onUpdate,
}: {
  check: ComplianceCheckResult;
  workflow: string[];
  onUpdate: (updated: ComplianceCheckResult) => void;
}) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<{ stage: string; emailed: boolean; link: string } | null>(null);
  const [copied, setCopied] = useState(false);

  if (!workflow || workflow.length === 0) return null;

  const signed = signedStages(check);
  const nextIndex = workflow.findIndex((s) => !signed.has(s));
  const allDone = nextIndex === -1;

  async function sendRequest(stage: string) {
    if (!email.trim()) return;
    setBusy(stage);
    setError(null);
    try {
      const res = await requestSignoff(check.payment_id, stage, email.trim());
      setSent({ stage, emailed: res.emailed, link: res.link });
      setEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the request.");
    } finally {
      setBusy(null);
    }
  }

  function absoluteLink(link: string): string {
    if (typeof window === "undefined") return link;
    return link.startsWith("http") ? link : `${window.location.origin}${link}`;
  }

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-900">Approval chain</p>
        {allDone ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
            <Check className="h-3.5 w-3.5" />
            Fully approved
          </span>
        ) : (
          <span className="text-xs text-gray-500">
            {signed.size} of {workflow.length} signed
          </span>
        )}
      </div>

      <ol className="mt-4 space-y-2">
        {workflow.map((stage, i) => {
          const isSigned = signed.has(stage);
          const isNext = i === nextIndex;
          return (
            <li
              key={stage}
              className={
                "flex flex-wrap items-center gap-3 rounded-xl border p-3 " +
                (isSigned
                  ? "border-emerald-200 bg-emerald-50/50"
                  : isNext
                    ? "border-brand-200 bg-brand-50/40"
                    : "border-gray-200 bg-gray-50/40")
              }
            >
              <span
                className={
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold " +
                  (isSigned
                    ? "bg-emerald-500 text-white"
                    : isNext
                      ? "bg-brand-600 text-white"
                      : "bg-gray-200 text-gray-500")
                }
              >
                {isSigned ? (
                  <Check className="h-4 w-4" />
                ) : isNext ? (
                  i + 1
                ) : (
                  <Lock className="h-3.5 w-3.5" />
                )}
              </span>

              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900">{stage}</p>
                <p className="text-[11px] text-gray-500">
                  {isSigned
                    ? "Verified sign-off recorded"
                    : isNext
                      ? sent?.stage === stage
                        ? `Awaiting verified sign-off from the approver`
                        : "Send a verified sign-off request"
                      : "Waiting for the previous stage"}
                </p>
              </div>

              {isNext && sent?.stage !== stage && (
                <div className="flex items-center gap-2">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="approver@org.com"
                    className="w-48 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                  />
                  <button
                    type="button"
                    onClick={() => sendRequest(stage)}
                    disabled={busy === stage || !email.trim()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
                  >
                    {busy === stage ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Mail className="h-3.5 w-3.5" />
                    )}
                    Send request
                  </button>
                </div>
              )}

              {!isSigned && !isNext && (
                <CircleDashed className="h-4 w-4 shrink-0 text-gray-300" />
              )}
            </li>
          );
        })}
      </ol>

      {sent && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 text-xs text-emerald-800">
          <p className="flex items-center gap-1.5 font-medium">
            <Mail className="h-3.5 w-3.5" />
            {sent.emailed
              ? "Secure sign-off link emailed to the approver."
              : "Sign-off link created (email not configured — share it manually)."}
          </p>
          <p className="mt-1 text-emerald-700/80">
            Only the approver, from their inbox, can open it and sign off. Hit
            Refresh once they&apos;ve actioned it.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <input
              readOnly
              value={absoluteLink(sent.link)}
              className="min-w-0 flex-1 rounded border border-emerald-200 bg-white px-2 py-1 text-[11px] text-gray-600"
            />
            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(absoluteLink(sent.link));
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="inline-flex shrink-0 items-center gap-1 rounded border border-emerald-200 bg-white px-2 py-1 text-[11px] font-medium text-emerald-700"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy link"}
            </button>
          </div>
        </div>
      )}

      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}
      <p className="mt-3 text-[11px] text-gray-400">
        Sign-off is verified by email — DOCex sends each approver a unique,
        expiring link; only the mailbox owner can approve. Every sign-off is
        recorded with their email, timestamp and IP. The final stage approves
        the voucher.
      </p>
    </div>
  );
}
