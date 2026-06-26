"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { DropZone } from "@/components/DropZone";
import { GuidanceCard } from "@/components/GuidanceCard";
import { VerdictScreen } from "@/components/compliance/VerdictScreen";
import {
  approveCheck,
  checkPaymentSingle,
  getRulebook,
  unapproveCheck,
} from "@/lib/api";
import type {
  ComplianceCheckResult,
  PolicyRulebook,
} from "@/types";

/**
 * Run-check page.
 *
 * Two phases: payment upload form, then verdict. The verdict UI is the
 * shared VerdictScreen component (also used at /compliance/checks/[id]).
 *
 * Every check is auto-persisted by the backend the moment it runs, so the
 * user can navigate away and come back to it via /compliance/checks/[id].
 * The approval toggle here calls the live persistence API.
 */

type Phase = "loading_rulebook" | "upload" | "checking" | "result" | "error";

export default function RunCheckPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;

  const [phase, setPhase] = useState<Phase>("loading_rulebook");
  const [rulebook, setRulebook] = useState<PolicyRulebook | null>(null);
  const [paymentLabel, setPaymentLabel] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<ComplianceCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rb = await getRulebook(id);
        if (!cancelled) {
          setRulebook(rb);
          setPhase("upload");
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load this rulebook.",
          );
          setPhase("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const canSubmit =
    phase === "upload" &&
    paymentLabel.trim().length > 0 &&
    files.length > 0;

  async function handleSubmit() {
    if (!canSubmit || !rulebook) return;
    setPhase("checking");
    setError(null);
    try {
      const res = await checkPaymentSingle(
        rulebook.id,
        paymentLabel.trim(),
        files,
      );
      setResult(res);
      setPhase("result");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "The compliance check failed. Is the API running?",
      );
      setPhase("error");
    }
  }

  function handleReset() {
    setResult(null);
    setPaymentLabel("");
    setFiles([]);
    setError(null);
    setApprovalError(null);
    setPhase("upload");
  }

  async function handleApprovalToggle() {
    if (!result) return;
    setApprovalLoading(true);
    setApprovalError(null);
    try {
      const updated = result.approved
        ? await unapproveCheck(result.payment_id)
        : await approveCheck(result.payment_id);
      setResult(updated);
    } catch (err) {
      setApprovalError(
        err instanceof Error ? err.message : "Could not update approval.",
      );
    } finally {
      setApprovalLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-4 px-6">
          <Link
            href={`/compliance/rulebooks/${id}`}
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <div className="hidden flex-1 items-center justify-center gap-1.5 text-sm font-medium text-gray-500 sm:flex">
            <ShieldCheck className="h-4 w-4 text-brand-600" />
            <span>
              Compliance check
              {rulebook && (
                <>
                  <span className="mx-2 text-gray-300">·</span>
                  <span className="text-gray-700">{rulebook.name}</span>
                </>
              )}
            </span>
          </div>
          <Link
            href="/compliance/checks"
            className="hidden text-xs font-medium text-gray-500 transition hover:text-brand-700 sm:inline-flex"
            title="View all saved checks"
          >
            All checks
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-10">
        {phase === "loading_rulebook" && (
          <div className="flex items-center justify-center gap-2 py-24 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading rulebook…
          </div>
        )}

        {phase === "error" && !rulebook && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            <p className="font-medium text-red-900">
              Could not load this rulebook
            </p>
            <p className="mt-1">{error}</p>
            <Link
              href="/compliance"
              className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100"
            >
              <ArrowLeft className="h-3 w-3" />
              Back to rulebooks
            </Link>
          </div>
        )}

        {(phase === "upload" || phase === "checking" || phase === "error") &&
          rulebook && (
            <UploadForm
              rulebook={rulebook}
              paymentLabel={paymentLabel}
              onPaymentLabelChange={setPaymentLabel}
              files={files}
              onFilesChange={setFiles}
              canSubmit={canSubmit}
              phase={phase}
              error={error}
              onSubmit={handleSubmit}
              onClearError={() => {
                setError(null);
                setPhase("upload");
              }}
            />
          )}

        {phase === "result" && result && rulebook && (
          <VerdictScreen
            result={result}
            // Prefer the live rulebook rules in fresh-run mode, but the
            // snapshot (frozen at save) is also returned and would work.
            rulesForLookup={rulebook.rules}
            onApprovalToggle={handleApprovalToggle}
            approvalLoading={approvalLoading}
            approvalError={approvalError}
            onRunAnother={handleReset}
            runAnotherLabel="Run another check"
          />
        )}
      </main>
    </div>
  );
}

/* ─── Upload form ─────────────────────────────────────────────────────── */

function UploadForm({
  rulebook,
  paymentLabel,
  onPaymentLabelChange,
  files,
  onFilesChange,
  canSubmit,
  phase,
  error,
  onSubmit,
  onClearError,
}: {
  rulebook: PolicyRulebook;
  paymentLabel: string;
  onPaymentLabelChange: (s: string) => void;
  files: File[];
  onFilesChange: (f: File[]) => void;
  canSubmit: boolean;
  phase: Phase;
  error: string | null;
  onSubmit: () => void;
  onClearError: () => void;
}) {
  const activeCount = rulebook.rules.filter((r) => r.active).length;

  if (phase === "checking") {
    return <CheckingState rulebookName={rulebook.name} />;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          Run a compliance check
        </h1>
        <p className="mt-2 max-w-xl text-base text-gray-600">
          Drop in the payment voucher with everything attached — invoice,
          receipts, quotes, approvals. DOCex checks it against{" "}
          <span className="font-semibold text-gray-900">{rulebook.name}</span>{" "}
          ({activeCount} active{" "}
          {activeCount === 1 ? "rule" : "rules"}) and returns a verdict for
          every rule with citations.
        </p>

        {/* One-off ⇄ bulk toggle — same policy set, one voucher or a whole
            stack. Bulk hands off to the batch flow, pre-scoped to this policy. */}
        <div className="mt-4 inline-flex rounded-lg border border-gray-200 bg-white p-0.5 text-sm">
          <span className="rounded-md bg-brand-600 px-3 py-1.5 font-medium text-white">
            One-off
          </span>
          <Link
            href={`/compliance/check/bulk?rulebook=${rulebook.id}`}
            className="rounded-md px-3 py-1.5 font-medium text-gray-600 transition hover:text-brand-700"
            title={`Check a whole stack of vouchers against ${rulebook.name}`}
          >
            Bulk
          </Link>
        </div>
      </div>

      <GuidanceCard title="What to upload">
        Include every supporting document in one bundle — voucher, invoice,
        receipts, vendor quotes, signed approval forms, contracts. DOCex
        reads them all together. Receipts get checked individually against
        any receipts-category rules in your rulebook.
      </GuidanceCard>

      {/* Payment label */}
      <div className="space-y-2">
        <label
          htmlFor="payment-label"
          className="block text-sm font-semibold text-gray-900"
        >
          Payment label
        </label>
        <p className="text-xs text-gray-500">
          Something the audit team will recognise — e.g. "PV-2025-04-17 ·
          Office Supplies — Vendor X" or "Workshop Catering · April 2025".
        </p>
        <input
          id="payment-label"
          type="text"
          value={paymentLabel}
          onChange={(e) => onPaymentLabelChange(e.target.value)}
          placeholder="e.g. PV-2025-04-17 · Office Supplies"
          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder:text-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
        />
      </div>

      {/* Upload */}
      <div className="space-y-2">
        <label className="block text-sm font-semibold text-gray-900">
          Upload the payment bundle
        </label>
        <p className="text-xs text-gray-500">
          PDF, DOCX, or TXT. Drop in the voucher + invoice + every receipt
          + any supporting docs together.
        </p>
        <DropZone files={files} onFilesChange={onFilesChange} />
      </div>

      {/* Error */}
      {phase === "error" && error && (
        <div className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium text-red-900">
            The compliance check did not complete
          </p>
          <p>{error}</p>
          <button
            type="button"
            onClick={onClearError}
            className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100"
          >
            Try again
          </button>
        </div>
      )}

      {/* Submit */}
      <div className="flex justify-between border-t border-gray-200 pt-6">
        <Link
          href={`/compliance/rulebooks/${rulebook.id}`}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-5 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-300 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to rulebook
        </Link>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!canSubmit}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4" />
          Run check
        </button>
      </div>
    </div>
  );
}

/* ─── Checking state ──────────────────────────────────────────────────── */

function CheckingState({ rulebookName }: { rulebookName: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <Loader2 className="mb-6 h-10 w-10 animate-spin text-brand-600" />
      <p className="text-lg font-semibold text-gray-900">
        Checking against {rulebookName}…
      </p>
      <p className="mt-2 text-sm text-gray-600">
        Reading the payment bundle, evaluating every active rule.
      </p>
      <p className="mt-6 text-xs text-gray-400">
        This usually takes 30 to 60 seconds.
      </p>
    </div>
  );
}
