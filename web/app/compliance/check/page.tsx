"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Layers,
  Loader2,
  Plus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { DropZone } from "@/components/DropZone";
import { GuidanceCard } from "@/components/GuidanceCard";
import { checkPaymentSingle, listRulebooks, routePayment } from "@/lib/api";
import {
  overallVerdictColor,
  overallVerdictDot,
  overallVerdictLabel,
  type ComplianceCheckResult,
  type RulebookSummary,
} from "@/types";

/**
 * Payment-first compliance check.
 *
 * The original flow was rulebook-first: open a policy, then upload a
 * payment. But the real mental model — confirmed by AP/audit practice —
 * is the reverse: "here's an invoice, which of our policies does it have
 * to satisfy?" This page inverts it. Upload the payment bundle, pick one
 * OR MORE policy sets to check it against, and DOCex runs each, linking
 * the payment to every policy it was tested on with a full audit trail.
 *
 * Running against multiple rulebooks issues independent checks (each gets
 * its own audit-stable URL) and shows a combined verdict roll-up.
 */

type Phase = "form" | "checking" | "done" | "error";

type RunResult = {
  rulebook: RulebookSummary;
  result?: ComplianceCheckResult;
  error?: string;
};

export default function PaymentCheckPage() {
  const router = useRouter();

  const [rulebooks, setRulebooks] = useState<RulebookSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [paymentLabel, setPaymentLabel] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [phase, setPhase] = useState<Phase>("form");
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [runResults, setRunResults] = useState<RunResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [routing, setRouting] = useState(false);
  const [routeMsg, setRouteMsg] = useState<string | null>(null);

  async function autoDetect() {
    if (files.length === 0) return;
    setRouting(true);
    setRouteMsg(null);
    try {
      const suggestions = await routePayment(files);
      const strong = suggestions.filter(
        (s) => s.confidence === "high" || s.confidence === "medium",
      );
      if (strong.length === 0) {
        setRouteMsg(
          "Couldn't confidently match a policy set from the documents — pick one below.",
        );
        return;
      }
      setSelected(new Set(strong.map((s) => s.rulebook_id)));
      const top = strong[0];
      setRouteMsg(
        `Matched ${strong.map((s) => s.rulebook_name).join(", ")}` +
          (top.matched_terms.length
            ? ` (on: ${top.matched_terms.slice(0, 4).join(", ")})`
            : ""),
      );
    } catch (err) {
      setRouteMsg(
        err instanceof Error ? err.message : "Auto-detect failed — pick a policy set below.",
      );
    } finally {
      setRouting(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rbs = await listRulebooks();
        if (!cancelled) setRulebooks(rbs);
      } catch (err) {
        if (!cancelled)
          setLoadError(
            err instanceof Error
              ? err.message
              : "Could not load your policy sets. Is the API running?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const canRun =
    files.length > 0 && selected.size > 0 && phase !== "checking";

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function run() {
    if (!canRun || !rulebooks) return;
    const chosen = rulebooks.filter((r) => selected.has(r.id));
    const label = paymentLabel.trim() || "Payment request";

    setPhase("checking");
    setError(null);
    setRunResults([]);
    setProgress({ done: 0, total: chosen.length });

    const results: RunResult[] = [];
    for (const rb of chosen) {
      try {
        const result = await checkPaymentSingle(rb.id, label, files);
        results.push({ rulebook: rb, result });
      } catch (err) {
        results.push({
          rulebook: rb,
          error: err instanceof Error ? err.message : "Check failed.",
        });
      }
      setProgress((p) => ({ ...p, done: p.done + 1 }));
    }

    setRunResults(results);

    // Single policy set → jump straight to the full verdict screen.
    const ok = results.filter((r) => r.result);
    if (ok.length === 1 && results.length === 1 && ok[0].result) {
      router.push(`/compliance/checks/${ok[0].result.payment_id}`);
      return;
    }
    if (ok.length === 0) {
      setError("Every check failed. Check the API and try again.");
      setPhase("error");
      return;
    }
    setPhase("done");
  }

  return (
    <AppShell
      active="compliance"
      actions={
        <>
          <Link
            href="/compliance/check/bulk"
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
          >
            <Layers className="h-3.5 w-3.5" />
            Bulk check
          </Link>
          <Link
            href="/compliance/new"
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
          >
            <Plus className="h-3.5 w-3.5" />
            New policy set
          </Link>
        </>
      }
    >
      <main className="mx-auto max-w-3xl px-6 py-10">
        {phase === "checking" ? (
          <Checking progress={progress} />
        ) : phase === "done" ? (
          <Results
            label={paymentLabel.trim() || "Payment request"}
            results={runResults}
            onReset={() => {
              setPhase("form");
              setRunResults([]);
            }}
          />
        ) : (
          <div className="space-y-8">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Check a payment voucher
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Upload the payment voucher with all its supporting documents,
                choose which policy set(s) it has to satisfy, and DOCex checks
                it rule by rule — with citations and an audit trail for each.
              </p>
            </div>

            {/* 1. Payment voucher + supporting documents */}
            <section className="space-y-3">
              <SectionHeading n={1} title="The payment voucher" />
              <p className="text-sm text-gray-600">
                Add the voucher and everything attached to it — Goods Received
                Note, invoice(s), purchase order, quotations / bid analysis,
                and approvals. DOCex reads the whole package together.
              </p>
              <input
                type="text"
                value={paymentLabel}
                onChange={(e) => setPaymentLabel(e.target.value)}
                placeholder="Label, e.g. 'PV #2026-0142 — Vendor X'"
                className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
              <DropZone files={files} onFilesChange={setFiles} />
            </section>

            {/* 2. Policy sets */}
            <section className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <SectionHeading n={2} title="Apply policy set(s)" />
                <button
                  type="button"
                  onClick={autoDetect}
                  disabled={files.length === 0 || routing}
                  title={
                    files.length === 0
                      ? "Add the payment documents first"
                      : "Let DOCex pick the best-fitting policy set from the documents"
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 transition hover:border-brand-300 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {routing ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" />
                  )}
                  Auto-detect policy
                </button>
              </div>
              <p className="text-sm text-gray-600">
                Pick every policy this payment must comply with — or let DOCex
                auto-detect it from the documents. Each is checked
                independently and gets its own audit-stable record.
              </p>

              {routeMsg && (
                <div className="flex items-start gap-2 rounded-lg border border-brand-100 bg-brand-50/60 px-3 py-2 text-xs text-brand-800">
                  <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{routeMsg}</span>
                </div>
              )}

              {loadError && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {loadError}
                </div>
              )}

              {rulebooks === null && !loadError ? (
                <div className="flex items-center gap-2 py-6 text-sm text-gray-500">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading your policy sets…
                </div>
              ) : rulebooks && rulebooks.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-10 text-center">
                  <p className="text-sm font-medium text-gray-900">
                    No policy sets yet
                  </p>
                  <p className="mx-auto mt-1 max-w-sm text-xs text-gray-500">
                    Upload a policy (procurement, travel, donor terms — one or
                    several documents) and DOCex turns it into a reusable
                    rulebook you can check payments against.
                  </p>
                  <Link
                    href="/compliance/new"
                    className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
                  >
                    <Plus className="h-4 w-4" />
                    Create your first policy set
                  </Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {rulebooks?.map((rb) => {
                    const on = selected.has(rb.id);
                    return (
                      <button
                        key={rb.id}
                        type="button"
                        onClick={() => toggle(rb.id)}
                        aria-pressed={on}
                        className={
                          "flex w-full items-center gap-3 rounded-xl border p-4 text-left transition " +
                          (on
                            ? "border-brand-300 bg-brand-50/60 ring-1 ring-brand-100"
                            : "border-gray-200 bg-white hover:border-brand-200")
                        }
                      >
                        <span
                          className={
                            "flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition " +
                            (on
                              ? "border-brand-600 bg-brand-600 text-white"
                              : "border-gray-300 bg-white")
                          }
                        >
                          {on && <CheckCircle2 className="h-4 w-4" />}
                        </span>
                        <ShieldCheck
                          className={
                            "h-5 w-5 shrink-0 " +
                            (on ? "text-brand-600" : "text-gray-400")
                          }
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-gray-900">
                            {rb.name}
                          </span>
                          <span className="block text-xs text-gray-500">
                            {rb.active_rule_count} active rule
                            {rb.active_rule_count === 1 ? "" : "s"}
                            {rb.source_documents.length > 1
                              ? ` · ${rb.source_documents.length} policy docs`
                              : ""}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </section>

            <GuidanceCard title="Why pick more than one?">
              A single payment voucher often has to satisfy several policies at once —
              procurement rules, travel limits, and a donor's specific terms.
              Selecting them all checks the payment against each and keeps a
              separate, defensible record per policy.
            </GuidanceCard>

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
                {selected.size > 1
                  ? `Check against ${selected.size} policy sets`
                  : "Run check"}
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

function Checking({ progress }: { progress: { done: number; total: number } }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <Loader2 className="mb-6 h-10 w-10 animate-spin text-brand-600" />
      <p className="text-lg font-semibold text-gray-900">
        Checking the payment…
      </p>
      <p className="mt-2 text-sm text-gray-600">
        {progress.total > 1
          ? `Policy set ${Math.min(progress.done + 1, progress.total)} of ${progress.total}`
          : "Reading the documents and testing every rule."}
      </p>
    </div>
  );
}

function Results({
  label,
  results,
  onReset,
}: {
  label: string;
  results: RunResult[];
  onReset: () => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">
          Checked against {results.length} policy set
          {results.length === 1 ? "" : "s"}
        </h1>
        <p className="mt-1 text-sm text-gray-600">{label}</p>
      </div>

      <div className="space-y-3">
        {results.map((r, i) => (
          <div
            key={i}
            className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-gray-900">
                {r.rulebook.name}
              </p>
              {r.result ? (
                <p className="mt-0.5 line-clamp-2 text-xs text-gray-500">
                  {r.result.overall_summary}
                </p>
              ) : (
                <p className="mt-0.5 text-xs text-rose-600">{r.error}</p>
              )}
            </div>
            {r.result && (
              <span
                className={
                  "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium " +
                  overallVerdictColor[r.result.overall_verdict]
                }
              >
                <span
                  className={
                    "h-1.5 w-1.5 rounded-full " +
                    overallVerdictDot[r.result.overall_verdict]
                  }
                />
                {overallVerdictLabel[r.result.overall_verdict]}
              </span>
            )}
            {r.result && (
              <Link
                href={`/compliance/checks/${r.result.payment_id}`}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-brand-700 transition hover:border-brand-300"
              >
                Open
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 border-t border-gray-200 pt-6">
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
        >
          <FileText className="h-4 w-4" />
          Check another payment
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
