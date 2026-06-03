"use client";

import { useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Stamp,
} from "lucide-react";
import { exportCheckToExcel, exportJson } from "@/lib/api";
import {
  categoryLabel,
  overallVerdictColor,
  overallVerdictLabel,
  type ComplianceCheckResult,
  type PolicyRule,
  type RuleResult,
  type RuleVerdict,
  verdictColor,
  verdictDot,
  verdictLabel,
} from "@/types";

/**
 * VerdictScreen
 *
 * The marquee surface — what a compliance officer sees after a check runs
 * (or when re-opening a saved check via its stable URL).
 *
 * Reused in two contexts:
 *   1. /compliance/rulebooks/[id]/check — immediately after running a check
 *   2. /compliance/checks/[id]          — viewing a saved check by its URL
 *
 * Design principles followed (Anthropic-flavoured):
 *   - The overall verdict is the dominant visual. Officers want the bottom
 *     line before the details. Lead with the verdict, support with the
 *     rule-by-rule breakdown.
 *   - Policy citation + payment evidence are shown SIDE BY SIDE on every
 *     rule card. That's the audit-defensible UX — here's the rule, here's
 *     the evidence, here's the verdict. No black box.
 *   - Receipt-level findings are visually grouped per-receipt because the
 *     officer often needs to flag a specific receipt back to finance, not
 *     the whole payment bundle.
 *   - Receipt group headers are colour-coded by the worst verdict in the
 *     group — gives a 2-second scan of "which receipt is the problem?"
 *   - Effort stat ("X documents · Y minutes of manual review") makes the
 *     value concrete — honest numbers, not aspirational marketing.
 */

interface VerdictScreenProps {
  result: ComplianceCheckResult;
  // Rules for looking up clause_reference, source_quote, category by rule_id.
  // In fresh-run mode pass the live rulebook.rules. In saved-check mode
  // pass result.rulebook_snapshot_rules — the frozen version so the audit
  // trail never drifts when the rulebook is later edited.
  rulesForLookup: PolicyRule[];
  // Approval toggle — if undefined, the button is hidden (e.g. when the
  // check isn't yet saved).
  onApprovalToggle?: () => void | Promise<void>;
  approvalLoading?: boolean;
  approvalError?: string | null;
  // "Run another" action — different per context (reset form vs navigate).
  // If undefined, the button is hidden.
  onRunAnother?: () => void;
  runAnotherLabel?: string;
  // Optional banner shown at the top — used in saved-check mode to remind
  // the user this is an immutable record from a specific time.
  bannerText?: string;
}

export function VerdictScreen({
  result,
  rulesForLookup,
  onApprovalToggle,
  approvalLoading = false,
  approvalError = null,
  onRunAnother,
  runAnotherLabel = "Run another check",
  bannerText,
}: VerdictScreenProps) {
  // Bucket the results by verdict for the stat strip
  const counts = useMemo(() => {
    const c: Record<RuleVerdict, number> = {
      pass: 0,
      flag: 0,
      block: 0,
      not_applicable: 0,
      insufficient_evidence: 0,
    };
    for (const r of result.results) c[r.verdict]++;
    return c;
  }, [result.results]);

  // Split into payment-level vs receipt-level findings
  const paymentLevel = result.results.filter((r) => !r.applied_to_document);
  const receiptLevel = result.results.filter((r) => r.applied_to_document);

  // Group receipt-level by filename
  const receiptGroups = useMemo(() => {
    const groups = new Map<string, RuleResult[]>();
    for (const r of receiptLevel) {
      const fn = r.applied_to_document!;
      if (!groups.has(fn)) groups.set(fn, []);
      groups.get(fn)!.push(r);
    }
    return Array.from(groups.entries()).map(([filename, results]) => ({
      filename,
      results,
    }));
  }, [receiptLevel]);

  // Effort stat — honest estimate at 10 mins per doc for thorough manual review
  const effortMinutes = result.documents.length * 10;
  const effortLabel =
    effortMinutes >= 60
      ? `~${(effortMinutes / 60).toFixed(1)} hours of manual review`
      : `~${effortMinutes} minutes of manual review`;

  const approved = !!result.approved;

  return (
    <div className="space-y-8">
      {/* Optional banner — saved-check mode */}
      {bannerText && (
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-xs text-gray-600">
          {bannerText}
        </div>
      )}

      {/* Overall verdict — the dominant visual */}
      <div
        className={`rounded-2xl px-6 py-6 ${overallVerdictColor[result.overall_verdict]}`}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold uppercase tracking-widest opacity-80">
                Verdict
              </span>
              <span className="text-3xl font-bold">
                {overallVerdictLabel[result.overall_verdict]}
              </span>
              {approved && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500 px-2.5 py-0.5 text-xs font-semibold text-white">
                  <Stamp className="h-3 w-3" />
                  Approved
                </span>
              )}
            </div>
            <p className="text-base leading-relaxed">{result.overall_summary}</p>
            <p className="text-xs opacity-70">
              {result.payment_label}{" "}
              <span className="opacity-60">
                · checked against {result.rulebook_name}
              </span>
            </p>
          </div>
        </div>

        {/* Stat strip */}
        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-current/10 pt-4">
          <StatPill label="Pass" verdict="pass" count={counts.pass} />
          <StatPill label="Flag" verdict="flag" count={counts.flag} />
          <StatPill label="Block" verdict="block" count={counts.block} />
          <StatPill
            label="Need info"
            verdict="insufficient_evidence"
            count={counts.insufficient_evidence}
          />
          <StatPill
            label="N/A"
            verdict="not_applicable"
            count={counts.not_applicable}
          />
        </div>

        {/* Effort stat — the orchestrator value prop made concrete */}
        <div className="mt-3 flex items-center gap-1.5 text-xs opacity-80">
          <Clock className="h-3 w-3" />
          <span>
            {result.documents.length}{" "}
            {result.documents.length === 1 ? "document" : "documents"} · {effortLabel} compressed to seconds
          </span>
        </div>
      </div>

      {/* Action bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-y border-gray-200 py-3">
        <div className="flex flex-wrap items-center gap-2">
          {onApprovalToggle && (
            <button
              type="button"
              onClick={onApprovalToggle}
              disabled={approvalLoading}
              className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
                approved
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:border-emerald-400 hover:bg-emerald-100"
                  : "border-gray-200 bg-white text-gray-700 hover:border-emerald-300 hover:text-emerald-700"
              }`}
              title={
                approved
                  ? "This check has been marked as Approved. Click to undo."
                  : "Mark this check as Approved — it'll appear in the Approved PVs archive."
              }
            >
              {approvalLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : approved ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <Stamp className="h-4 w-4" />
              )}
              {approved ? "Approved" : "Mark as approved"}
            </button>
          )}
          <button
            type="button"
            onClick={() => exportCheckToExcel(result, rulesForLookup)}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700"
            title="Two-sheet workbook — Summary + per-rule Findings"
          >
            <FileSpreadsheet className="h-4 w-4" />
            Export Excel
          </button>
          <button
            type="button"
            onClick={() =>
              exportJson(
                result,
                `compliance-check-${result.payment_label || result.payment_id}.json`,
              )
            }
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700"
            title="Raw JSON — useful for piping into other tools"
          >
            <Download className="h-4 w-4" />
            JSON
          </button>
          {approvalError && (
            <span className="text-xs text-rose-600">{approvalError}</span>
          )}
        </div>
        {onRunAnother && (
          <button
            type="button"
            onClick={onRunAnother}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
          >
            <RotateCcw className="h-4 w-4" />
            {runAnotherLabel}
          </button>
        )}
      </div>

      {/* Payment-level findings */}
      {paymentLevel.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="text-xl font-semibold text-gray-900">
              Payment-level findings
            </h2>
            <span className="text-sm text-gray-500">
              {paymentLevel.length}{" "}
              {paymentLevel.length === 1 ? "rule" : "rules"} evaluated against the payment
            </span>
          </div>
          <div className="space-y-3">
            {paymentLevel.map((r, i) => (
              <RuleResultCard
                key={`pl-${i}`}
                result={r}
                rulesForLookup={rulesForLookup}
              />
            ))}
          </div>
        </section>
      )}

      {/* Receipt-level findings */}
      {receiptGroups.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-xl font-semibold text-gray-900">
              Receipt-level findings
            </h2>
            <span className="text-sm text-gray-500">
              {receiptGroups.length}{" "}
              {receiptGroups.length === 1 ? "receipt" : "receipts"} checked
            </span>
          </div>
          <div className="space-y-5">
            {receiptGroups.map((g) => (
              <ReceiptGroup
                key={g.filename}
                filename={g.filename}
                results={g.results}
                rulesForLookup={rulesForLookup}
              />
            ))}
          </div>
        </section>
      )}

      {/* Empty state — no rules evaluated */}
      {paymentLevel.length === 0 && receiptGroups.length === 0 && (
        <div className="rounded-lg border border-gray-200 bg-white px-6 py-12 text-center text-sm text-gray-500">
          The check completed but no rule results were returned. Try re-running,
          or check the backend logs for warnings.
        </div>
      )}
    </div>
  );
}

/* ─── Stat pill ──────────────────────────────────────────────────────── */

function StatPill({
  label,
  verdict,
  count,
}: {
  label: string;
  verdict: RuleVerdict;
  count: number;
}) {
  if (count === 0) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/40 px-3 py-1 text-xs font-medium text-gray-500">
        <span className="h-1.5 w-1.5 rounded-full bg-gray-300" />
        {label} · 0
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-medium text-gray-700 ring-1 ring-gray-200">
      <span className={`h-1.5 w-1.5 rounded-full ${verdictDot[verdict]}`} />
      <span className="font-semibold tabular-nums">{count}</span>
      <span>{label}</span>
    </span>
  );
}

/* ─── Receipt group ──────────────────────────────────────────────────── */

function ReceiptGroup({
  filename,
  results,
  rulesForLookup,
}: {
  filename: string;
  results: RuleResult[];
  rulesForLookup: PolicyRule[];
}) {
  const worst = worstVerdict(results.map((r) => r.verdict));

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
      <header
        className={`flex items-center justify-between gap-3 border-b px-4 py-3 ${headerColor(worst)}`}
      >
        <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
          <FileText className="h-4 w-4 shrink-0 opacity-70" />
          <span className="truncate">{filename}</span>
        </div>
        <span className="shrink-0 text-xs opacity-80">
          {results.length} {results.length === 1 ? "check" : "checks"}
        </span>
      </header>
      <div className="space-y-3 p-4">
        {results.map((r, i) => (
          <RuleResultCard
            key={`r-${filename}-${i}`}
            result={r}
            rulesForLookup={rulesForLookup}
          />
        ))}
      </div>
    </div>
  );
}

const VERDICT_RANK: Record<RuleVerdict, number> = {
  block: 5,
  flag: 4,
  insufficient_evidence: 3,
  pass: 2,
  not_applicable: 1,
};

function worstVerdict(verdicts: RuleVerdict[]): RuleVerdict {
  return verdicts.reduce(
    (worst, v) => (VERDICT_RANK[v] > VERDICT_RANK[worst] ? v : worst),
    "pass" as RuleVerdict,
  );
}

function headerColor(verdict: RuleVerdict): string {
  if (verdict === "block")
    return "border-rose-200 bg-rose-50 text-rose-900";
  if (verdict === "flag" || verdict === "insufficient_evidence")
    return "border-amber-200 bg-amber-50 text-amber-900";
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
}

/* ─── Rule result card ──────────────────────────────────────────────── */

function RuleResultCard({
  result,
  rulesForLookup,
}: {
  result: RuleResult;
  rulesForLookup: PolicyRule[];
}) {
  const rule = rulesForLookup.find((r) => r.id === result.rule_id);
  const category = rule?.category ?? null;
  const [showQuote, setShowQuote] = useState(false);

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-medium text-gray-900">
            {result.rule_description}
          </p>
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
            {rule?.clause_reference && (
              <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-600">
                {rule.clause_reference}
              </span>
            )}
            {category && (
              <span className="text-gray-500">{categoryLabel[category]}</span>
            )}
          </div>
        </div>
        <VerdictBadge verdict={result.verdict} />
      </header>

      <p className="text-sm leading-relaxed text-gray-700">{result.reasoning}</p>

      {(result.policy_citation || result.payment_evidence) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {result.policy_citation && (
            <EvidenceBlock
              label="From the policy"
              tone="brand"
              text={result.policy_citation}
            />
          )}
          {result.payment_evidence && (
            <EvidenceBlock
              label="From the payment"
              tone="neutral"
              text={result.payment_evidence}
            />
          )}
        </div>
      )}

      {result.missing_evidence && result.missing_evidence.length > 0 && (
        <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 p-3">
          <p className="mb-1 text-xs font-semibold text-sky-900">
            What's missing
          </p>
          <ul className="space-y-1 text-xs text-sky-800">
            {result.missing_evidence.map((m, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <ChevronRight className="mt-0.5 h-3 w-3 shrink-0" />
                <span>{m}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {rule?.source_quote && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowQuote((s) => !s)}
            className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700"
          >
            <ExternalLink className="h-3 w-3" />
            {showQuote ? "Hide" : "View"} source quote from policy
            {rule.source_page != null && ` · p.${rule.source_page}`}
          </button>
          {showQuote && (
            <div className="mt-2 rounded-md border border-gray-100 bg-gray-50 px-3 py-2">
              <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-gray-600">
                {rule.source_quote}
              </p>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function VerdictBadge({ verdict }: { verdict: RuleVerdict }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${verdictColor[verdict]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${verdictDot[verdict]}`} />
      {verdictLabel[verdict]}
    </span>
  );
}

function EvidenceBlock({
  label,
  tone,
  text,
}: {
  label: string;
  tone: "brand" | "neutral";
  text: string;
}) {
  const wrap =
    tone === "brand"
      ? "border-blue-100 bg-blue-50/40"
      : "border-gray-200 bg-gray-50";
  const labelColor = tone === "brand" ? "text-blue-700" : "text-gray-600";

  return (
    <div className={`rounded-md border ${wrap} p-3`}>
      <div
        className={`mb-1 flex items-center gap-1.5 text-xs font-semibold ${labelColor}`}
      >
        {tone === "brand" ? (
          <ShieldCheck className="h-3 w-3" />
        ) : (
          <CheckCircle2 className="h-3 w-3" />
        )}
        {label}
      </div>
      <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-gray-700">
        “{text}”
      </p>
    </div>
  );
}
