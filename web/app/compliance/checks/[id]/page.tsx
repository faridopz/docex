"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Download,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { AssistantBrief } from "@/components/AssistantBrief";
import { DecisionTimeline } from "@/components/compliance/DecisionTimeline";
import { VerdictScreen } from "@/components/compliance/VerdictScreen";
import {
  approveCheck,
  exportCheckAuditHistory,
  getCheck,
  getRulebook,
  unapproveCheck,
} from "@/lib/api";
import { ApprovalChain } from "@/components/compliance/ApprovalChain";
import { RiskPanel } from "@/components/compliance/RiskPanel";
import type { ComplianceCheckResult, PolicyRulebook } from "@/types";

/**
 * Saved-check page — the stable URL for a compliance check.
 *
 * Loads a persisted check by id and renders the VerdictScreen. The URL is
 * audit-shareable: paste it into a BMGF audit response and the auditor
 * sees exactly what the officer saw at check time, including the rulebook
 * snapshot frozen in place.
 *
 * "Run another check" from this page navigates to the rulebook's check
 * page rather than resetting a form (we're viewing history, not running
 * something new).
 */

export default function SavedCheckPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;

  const [check, setCheck] = useState<ComplianceCheckResult | null>(null);
  const [rulebook, setRulebook] = useState<PolicyRulebook | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const c = await getCheck(id);
        if (cancelled) return;
        setCheck(c);
        // Load the rulebook too (for its configurable approval workflow).
        // Best-effort: a missing rulebook just hides the approval chain.
        try {
          const rb = await getRulebook(c.rulebook_id);
          if (!cancelled) setRulebook(rb);
        } catch {
          /* ignore — no approval chain shown */
        }
      } catch (err) {
        if (!cancelled)
          setLoadError(
            err instanceof Error ? err.message : "Could not load this check.",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleApprovalToggle() {
    if (!check) return;
    setApprovalLoading(true);
    setApprovalError(null);
    try {
      const updated = check.approved
        ? await unapproveCheck(check.payment_id)
        : await approveCheck(check.payment_id);
      setCheck(updated);
    } catch (err) {
      setApprovalError(
        err instanceof Error ? err.message : "Could not update approval.",
      );
    } finally {
      setApprovalLoading(false);
    }
  }

  async function handleExportAudit() {
    if (!check) return;
    setExporting(true);
    try {
      await exportCheckAuditHistory(
        check,
        check.rulebook_snapshot_rules ?? [],
      );
    } finally {
      setExporting(false);
    }
  }

  // Banner explaining this is a saved/historical check
  const bannerText = check?.created_at
    ? `Saved check · ran ${formatDate(check.created_at)}${
        check.approved && check.approved_at
          ? ` · Approved ${formatDate(check.approved_at)}`
          : ""
      }`
    : undefined;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-4 px-6">
          <Link
            href="/compliance/checks"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <div className="hidden flex-1 items-center justify-center gap-1.5 text-sm font-medium text-gray-500 sm:flex">
            <ShieldCheck className="h-4 w-4 text-brand-600" />
            <span>Saved check</span>
          </div>
          <button
            type="button"
            onClick={handleExportAudit}
            disabled={!check || exporting}
            className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50 sm:inline-flex"
            title="Download the full audit trail — summary, findings, and decision history — as an Excel workbook"
          >
            {exporting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            Export audit trail
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-10">
        {!check && !loadError && (
          <div className="flex items-center justify-center gap-2 py-24 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading check…
          </div>
        )}

        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            <p className="font-medium text-red-900">Could not load this check</p>
            <p className="mt-1">{loadError}</p>
            <Link
              href="/compliance/checks"
              className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100"
            >
              <ArrowLeft className="h-3 w-3" />
              Back to all checks
            </Link>
          </div>
        )}

        {check && (
          <>
            <div className="mb-6">
              <AssistantBrief
                contextKind="compliance_check"
                contextId={check.payment_id}
                payload={check}
              />
            </div>
            {rulebook?.approval_workflow && rulebook.approval_workflow.length > 0 && (
              <div className="mb-6">
                <ApprovalChain
                  check={check}
                  workflow={rulebook.approval_workflow}
                  onUpdate={(updated) => setCheck(updated)}
                />
              </div>
            )}
            <div className="mb-6">
              <RiskPanel check={check} onUpdate={(updated) => setCheck(updated)} />
            </div>
            <div className="mb-6">
              <DecisionTimeline
                check={check}
                onUpdate={(updated) => setCheck(updated)}
              />
            </div>
            <VerdictScreen
              result={check}
            // In saved-check mode, use the frozen snapshot so the audit
            // trail stays consistent with the moment of check, even if
            // the rulebook has been edited since.
            rulesForLookup={check.rulebook_snapshot_rules ?? []}
            onApprovalToggle={handleApprovalToggle}
            approvalLoading={approvalLoading}
            approvalError={approvalError}
            bannerText={bannerText}
            />
          </>
        )}
      </main>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
