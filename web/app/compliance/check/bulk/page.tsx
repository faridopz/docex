"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  FileText,
  Loader2,
  Plus,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { DropZone } from "@/components/DropZone";
import { GuidanceCard } from "@/components/GuidanceCard";
import { checkPaymentBatch, listRulebooks, type PaymentInput } from "@/lib/api";
import {
  overallVerdictColor,
  overallVerdictDot,
  overallVerdictLabel,
  type ComplianceCheckBatchResult,
  type ComplianceCheckResult,
  type OverallVerdict,
  type RulebookSummary,
} from "@/types";

/**
 * Bulk compliance — check MANY payments against one policy set in a single
 * run, then read the results grouped by verdict (blocked first). The
 * backend (/compliance/check/batch) warms the policy cache on the first
 * check and fans the rest out concurrently, so a stack of vouchers is far
 * faster than running them one at a time. Every check is saved individually
 * with its own audit-stable record.
 */

type Phase = "form" | "checking" | "done" | "error";

type Row = { id: string; label: string; files: File[] };

function blankRow(): Row {
  return {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `p_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    label: "",
    files: [],
  };
}

const GROUP_ORDER: OverallVerdict[] = ["blocked", "flagged", "approved"];

export default function BulkCheckPage() {
  const [rulebooks, setRulebooks] = useState<RulebookSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rulebookId, setRulebookId] = useState<string>("");
  const [rows, setRows] = useState<Row[]>([blankRow()]);

  const [phase, setPhase] = useState<Phase>("form");
  const [result, setResult] = useState<ComplianceCheckBatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rbs = await listRulebooks();
        if (cancelled) return;
        setRulebooks(rbs);
        if (rbs.length === 1) setRulebookId(rbs[0].id);
      } catch (err) {
        if (!cancelled)
          setLoadError(
            err instanceof Error ? err.message : "Could not load your policy sets.",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const readyPayments = rows.filter((r) => r.files.length > 0);
  const canRun = Boolean(rulebookId) && readyPayments.length > 0 && phase !== "checking";

  function patchRow(id: string, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  async function run() {
    if (!canRun) return;
    setPhase("checking");
    setError(null);
    setResult(null);
    const payments: PaymentInput[] = readyPayments.map((r, i) => ({
      label: r.label.trim() || `Payment ${i + 1}`,
      files: r.files,
    }));
    try {
      const res = await checkPaymentBatch(rulebookId, payments);
      setResult(res);
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk check failed.");
      setPhase("error");
    }
  }

  const grouped: Record<OverallVerdict, ComplianceCheckResult[]> = {
    blocked: [],
    flagged: [],
    approved: [],
  };
  if (result) {
    for (const c of result.checks) grouped[c.overall_verdict]?.push(c);
  }

  return (
    <AppShell
      active="compliance"
      actions={
        <Link
          href="/compliance/check"
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
        >
          Single check
        </Link>
      }
    >
      <main className="mx-auto max-w-3xl px-6 py-10">
        {phase === "checking" ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <Loader2 className="mb-6 h-10 w-10 animate-spin text-brand-600" />
            <p className="text-lg font-semibold text-gray-900">
              Checking {readyPayments.length} payment
              {readyPayments.length === 1 ? "" : "s"}…
            </p>
            <p className="mt-2 text-sm text-gray-600">
              Running each against the policy set. This is faster than one at a
              time, but a big stack can still take a minute or two.
            </p>
          </div>
        ) : phase === "done" && result ? (
          <Results
            result={result}
            grouped={grouped}
            onReset={() => {
              setPhase("form");
              setResult(null);
              setRows([blankRow()]);
            }}
          />
        ) : (
          <div className="space-y-8">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Bulk payment-voucher check
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Check a whole stack of payment vouchers against one policy set
                in a single run. Each voucher is checked independently and saved
                with its own audit trail; results come back grouped by verdict.
              </p>
            </div>

            {/* Policy set */}
            <section className="space-y-3">
              <SectionHeading n={1} title="Policy set to check against" />
              {loadError && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {loadError}
                </div>
              )}
              {rulebooks === null && !loadError ? (
                <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading…
                </div>
              ) : rulebooks && rulebooks.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-8 text-center">
                  <p className="text-sm font-medium text-gray-900">No policy sets yet</p>
                  <Link
                    href="/compliance/new"
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
                  >
                    <Plus className="h-4 w-4" /> Create a policy set
                  </Link>
                </div>
              ) : (
                <select
                  value={rulebookId}
                  onChange={(e) => setRulebookId(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                >
                  <option value="">Select a policy set…</option>
                  {rulebooks?.map((rb) => (
                    <option key={rb.id} value={rb.id}>
                      {rb.name} ({rb.active_rule_count} rules)
                    </option>
                  ))}
                </select>
              )}
            </section>

            {/* Payments */}
            <section className="space-y-3">
              <SectionHeading n={2} title="Payment vouchers" />
              <p className="text-sm text-gray-600">
                Add one block per voucher — a label and all its supporting
                documents (GRN, invoice, PO, quotations, approvals).
              </p>
              <div className="space-y-3">
                {rows.map((r, i) => (
                  <div key={r.id} className="rounded-xl border border-gray-200 bg-white p-4">
                    <div className="mb-3 flex items-center gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-600">
                        {i + 1}
                      </span>
                      <input
                        value={r.label}
                        onChange={(e) => patchRow(r.id, { label: e.target.value })}
                        placeholder={`Payment ${i + 1} label, e.g. 'Voucher #${1000 + i} — Vendor'`}
                        className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                      />
                      {rows.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}
                          className="shrink-0 rounded-md p-1.5 text-gray-400 transition hover:bg-rose-50 hover:text-rose-600"
                          aria-label="Remove payment"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                    <DropZone
                      files={r.files}
                      onFilesChange={(files) => patchRow(r.id, { files })}
                    />
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setRows((rs) => [...rs, blankRow()])}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
              >
                <Plus className="h-4 w-4" /> Add another payment
              </button>
            </section>

            <GuidanceCard title="One policy set per run">
              Bulk runs check every voucher against a single policy set. To
              apply several policy sets, run the bulk check once per set, or use
              the single voucher check to pick multiple sets for one voucher.
            </GuidanceCard>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <div className="flex items-center justify-between border-t border-gray-200 pt-6">
              <Link
                href="/compliance"
                className="text-sm font-medium text-gray-500 transition hover:text-gray-800"
              >
                ← Back
              </Link>
              <button
                type="button"
                onClick={run}
                disabled={!canRun}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
              >
                <ShieldCheck className="h-4 w-4" />
                Check {readyPayments.length || ""} payment
                {readyPayments.length === 1 ? "" : "s"}
              </button>
            </div>
          </div>
        )}
      </main>
    </AppShell>
  );
}

function SectionHeading({ n, title }: { n: number; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
        {n}
      </span>
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
    </div>
  );
}

function Results({
  result,
  grouped,
  onReset,
}: {
  result: ComplianceCheckBatchResult;
  grouped: Record<OverallVerdict, ComplianceCheckResult[]>;
  onReset: () => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          {result.total} payment{result.total === 1 ? "" : "s"} checked
        </h1>
        <div className="mt-3 flex flex-wrap gap-2">
          {GROUP_ORDER.map((v) => (
            <span
              key={v}
              className={
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium " +
                overallVerdictColor[v]
              }
            >
              <span className={"h-1.5 w-1.5 rounded-full " + overallVerdictDot[v]} />
              {grouped[v].length} {overallVerdictLabel[v].toLowerCase()}
            </span>
          ))}
        </div>
      </div>

      {GROUP_ORDER.filter((v) => grouped[v].length > 0).map((v) => (
        <section key={v}>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            {overallVerdictLabel[v]} · {grouped[v].length}
          </h2>
          <div className="space-y-2">
            {grouped[v].map((c) => (
              <Link
                key={c.payment_id}
                href={`/compliance/checks/${c.payment_id}`}
                className="group flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-card-hover"
              >
                <span
                  className={"h-2 w-2 shrink-0 rounded-full " + overallVerdictDot[c.overall_verdict]}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-gray-900">
                    {c.payment_label}
                  </p>
                  <p className="mt-0.5 line-clamp-1 text-xs text-gray-500">
                    {c.overall_summary}
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-gray-300 transition group-hover:translate-x-0.5 group-hover:text-brand-600" />
              </Link>
            ))}
          </div>
        </section>
      ))}

      <div className="flex items-center gap-3 border-t border-gray-200 pt-6">
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
        >
          <FileText className="h-4 w-4" />
          New bulk check
        </button>
        <Link
          href="/compliance/checks"
          className="text-sm font-medium text-gray-500 transition hover:text-gray-800"
        >
          View all checks →
        </Link>
      </div>
    </div>
  );
}
