"use client";

import { useState } from "react";
import { Check, CircleDashed, Loader2, Lock, PenLine } from "lucide-react";
import { addCheckNote, approveCheck } from "@/lib/api";
import type { ComplianceCheckResult } from "@/types";

/**
 * <ApprovalChain> — the configurable, multi-stage sign-off for a check.
 *
 * The stages come from the rulebook's `approval_workflow` (e.g. for TA
 * Connect: Compliance Officer → Head of Finance → Executive Director).
 * Another org's policy can define a completely different chain — nothing
 * here is hardcoded. Each stage is signed in order; the final sign-off
 * marks the check approved. Sign-offs are recorded on the append-only
 * decision log (reusing the existing note + approve endpoints), so the
 * audit trail captures who signed which stage and when.
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
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!workflow || workflow.length === 0) return null;

  const signed = signedStages(check);
  const nextIndex = workflow.findIndex((s) => !signed.has(s));
  const allDone = nextIndex === -1;

  async function signOff(stage: string, isLast: boolean) {
    setBusy(stage);
    setError(null);
    try {
      const who = name.trim();
      let updated = await addCheckNote(
        check.payment_id,
        `${MARKER} ${stage}${who ? `: ${who}` : ""}`,
      );
      if (isLast) {
        // Final stage approves the check (frozen audit snapshot).
        updated = await approveCheck(check.payment_id);
      }
      onUpdate(updated);
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the sign-off.");
    } finally {
      setBusy(null);
    }
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
          const isLast = i === workflow.length - 1;
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
                    ? "Signed off"
                    : isNext
                      ? "Awaiting sign-off"
                      : "Waiting for the previous stage"}
                </p>
              </div>

              {isNext && (
                <div className="flex items-center gap-2">
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your name (optional)"
                    className="w-40 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                  />
                  <button
                    type="button"
                    onClick={() => signOff(stage, isLast)}
                    disabled={busy === stage}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
                  >
                    {busy === stage ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <PenLine className="h-3.5 w-3.5" />
                    )}
                    {isLast ? "Sign off & approve" : "Sign off"}
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

      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}
      <p className="mt-3 text-[11px] text-gray-400">
        Stages come from this policy set&apos;s approval workflow. Each sign-off
        is recorded on the audit trail; the final stage approves the voucher.
      </p>
    </div>
  );
}
