"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleHelp,
  ChevronDown,
  ChevronRight,
  Clock,
  HelpCircle,
  Loader2,
  Play,
  RotateCw,
  Server,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  AdminAuthError,
  getAdminSecret,
  getLastDiagnostic,
  listDiagnosticReports,
  runDiagnostic,
  setAdminSecret,
} from "@/lib/api";
import { AssistantBrief } from "@/components/AssistantBrief";
import { GuidanceCard } from "@/components/GuidanceCard";
import type {
  CheckResult,
  CheckStatus,
  DiagnosticReport,
  DiagnosticReportSummary,
} from "@/types";
import {
  checkStatusColor,
  checkStatusDot,
  overallColor,
} from "@/types";

/**
 * /admin/diagnostics — DOCex Self-Check Agent UI.
 *
 * Runtime diagnostic dashboard. Lets the operator (today: Farid; later:
 * any NGO admin) run the full check suite on demand and see what's
 * healthy, warning, or broken across every primitive.
 *
 * Sections, top to bottom:
 *   1. Overall status hero (green/amber/rose pill)
 *   2. Counts strip (passed / warned / failed / skipped)
 *   3. Run button + history dropdown
 *   4. Per-category accordion of every check, with evidence + fix hints
 *
 * The 'fix hints' are the most important UX — every failing check tells
 * the operator exactly what to do next. That's the difference between a
 * diagnostic that's useful and one that's noise.
 */

const CATEGORY_LABELS: Record<string, { label: string; icon: React.ReactNode }> = {
  environment: { label: "Environment", icon: <Server className="h-4 w-4" /> },
  filesystem: { label: "Filesystem", icon: <Server className="h-4 w-4" /> },
  engines: { label: "Engines", icon: <Activity className="h-4 w-4" /> },
  api: { label: "API routes", icon: <Activity className="h-4 w-4" /> },
  smoke: { label: "End-to-end smoke", icon: <ShieldCheck className="h-4 w-4" /> },
  data: { label: "Data integrity", icon: <ShieldCheck className="h-4 w-4" /> },
  internal: { label: "Internal", icon: <AlertTriangle className="h-4 w-4" /> },
};

const CATEGORY_ORDER = [
  "environment",
  "filesystem",
  "engines",
  "api",
  "smoke",
  "data",
  "internal",
];

export default function DiagnosticsPage() {
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [history, setHistory] = useState<DiagnosticReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track which categories are collapsed so the user can focus on what
  // matters. Failing categories default to OPEN.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  // Admin gate. The backend 404s diagnostic endpoints when ADMIN_SECRET
  // is set and the request header doesn't match. We surface a tiny
  // secret-input form when that happens, store the secret in localStorage,
  // and retry. If ADMIN_SECRET is unset on the backend (dev mode), the
  // endpoints are open and this form never appears.
  const [needsAuth, setNeedsAuth] = useState(false);
  const [secretInput, setSecretInput] = useState("");

  async function loadLast() {
    setError(null);
    setNeedsAuth(false);
    try {
      const last = await getLastDiagnostic();
      setReport(last);
      // List call surfaces auth status — if it throws AdminAuthError we
      // know the gate is on and we need the secret form.
      const hist = await listDiagnosticReports();
      setHistory(hist);
      // Auto-collapse categories with no fails/warns so failures stand out.
      if (last) {
        const collapse = new Set<string>();
        for (const cat of CATEGORY_ORDER) {
          const checks = last.checks.filter((c) => c.category === cat);
          if (checks.length > 0 && checks.every((c) => c.status === "pass")) {
            collapse.add(cat);
          }
        }
        setCollapsed(collapse);
      }
    } catch (err) {
      if (err instanceof AdminAuthError) {
        setNeedsAuth(true);
        setReport(null);
        setHistory([]);
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "Could not load diagnostic report. Is the API running on port 8000?",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadLast();
  }, []);

  function submitSecret(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = secretInput.trim();
    if (!trimmed) return;
    setAdminSecret(trimmed);
    setSecretInput("");
    setNeedsAuth(false);
    setLoading(true);
    void loadLast();
  }

  function clearSecret() {
    setAdminSecret("");
    setNeedsAuth(true);
    setReport(null);
    setHistory([]);
  }

  async function runNow() {
    setError(null);
    setRunning(true);
    try {
      const r = await runDiagnostic();
      setReport(r);
      const hist = await listDiagnosticReports();
      setHistory(hist);
      // Reset collapsed state — new report, new defaults
      const collapse = new Set<string>();
      for (const cat of CATEGORY_ORDER) {
        const checks = r.checks.filter((c) => c.category === cat);
        if (checks.length > 0 && checks.every((c) => c.status === "pass")) {
          collapse.add(cat);
        }
      }
      setCollapsed(collapse);
    } catch (err) {
      if (err instanceof AdminAuthError) {
        setNeedsAuth(true);
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "Could not run diagnostic. Check the backend is up.",
        );
      }
    } finally {
      setRunning(false);
    }
  }

  function toggleCategory(cat: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  // Group checks by category
  const grouped: Record<string, CheckResult[]> = {};
  if (report) {
    for (const c of report.checks) {
      (grouped[c.category] ??= []).push(c);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-6 px-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <Activity className="h-4 w-4 text-brand-600" />
            Self-Check
          </span>
          <button
            type="button"
            onClick={() => void loadLast()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
            title="Reload latest report"
          >
            <RotateCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12">
        {/* Admin gate — appears when the backend has ADMIN_SECRET set and
            localStorage doesn't have a matching token. Renders ABOVE
            everything else and short-circuits the rest of the page. */}
        {needsAuth ? (
          <div className="mx-auto max-w-md">
            <div className="rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
              <div className="mx-auto mb-5 inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
                <Activity className="h-6 w-6" />
              </div>
              <h1 className="text-xl font-bold tracking-tight text-gray-900">
                Admin access required
              </h1>
              <p className="mt-2 text-sm text-gray-600">
                The Self-Check Agent is locked. Paste your admin secret to
                unlock — it gets stored in this browser only, never sent
                anywhere except DOCex's API.
              </p>
              <form onSubmit={submitSecret} className="mt-5 space-y-3">
                <input
                  type="password"
                  value={secretInput}
                  onChange={(e) => setSecretInput(e.target.value)}
                  placeholder="ADMIN_SECRET"
                  autoFocus
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
                <button
                  type="submit"
                  disabled={!secretInput.trim()}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
                >
                  Unlock
                </button>
              </form>
              <p className="mt-4 text-[11px] text-gray-400">
                The secret is the value of ADMIN_SECRET in the backend's
                .env file. If you don't know it, ask the person who runs
                this DOCex instance.
              </p>
            </div>
          </div>
        ) : (
        <div className="space-y-8">
          {/* Title */}
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Self-Check Agent
              </h1>
              <p className="mt-2 max-w-2xl text-base text-gray-600">
                Runs DOCex through its own paces — every primitive, every
                engine, every persistence layer.{" "}
                <span className="text-gray-900">
                  If something's not production-ready, this page tells you
                  exactly what and how to fix it.
                </span>
              </p>
            </div>
            <button
              type="button"
              onClick={runNow}
              disabled={running}
              className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
            >
              {running ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running checks…
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Run diagnostic
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          )}

          {loading && !report && !error && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading last report…
            </div>
          )}

          {!loading && !report && !error && (
            <EmptyState onRun={runNow} running={running} />
          )}

          {report && (
            <>
              {/* DOCex Assistant briefing — Claude narrates the diagnostic
                  and proposes top 1-2 fixes. Visible above the hero so the
                  operator gets the headline before the data. */}
              <AssistantBrief
                contextKind="diagnostic"
                contextId={report.report_id ?? undefined}
                payload={report}
              />

              {/* Hero */}
              <div
                className={`flex flex-wrap items-center justify-between gap-4 rounded-2xl px-6 py-5 ${overallColor[report.overall]}`}
              >
                <div>
                  <div className="flex items-center gap-2">
                    {report.overall === "healthy" && (
                      <CheckCircle2 className="h-5 w-5" />
                    )}
                    {report.overall === "degraded" && (
                      <AlertTriangle className="h-5 w-5" />
                    )}
                    {report.overall === "broken" && (
                      <XCircle className="h-5 w-5" />
                    )}
                    <h2 className="text-xl font-bold capitalize">
                      System is {report.overall}
                    </h2>
                  </div>
                  <p className="mt-1 text-xs">
                    {new Date(report.started_at).toLocaleString()} · ran in{" "}
                    {(report.duration_ms / 1000).toFixed(1)}s
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <CountPill tone="emerald" label="passed" count={report.passed} />
                  {report.warned > 0 && (
                    <CountPill tone="amber" label="warned" count={report.warned} />
                  )}
                  {report.failed > 0 && (
                    <CountPill tone="rose" label="failed" count={report.failed} />
                  )}
                  {report.skipped > 0 && (
                    <CountPill tone="gray" label="skipped" count={report.skipped} />
                  )}
                </div>
              </div>

              {/* Guidance — visible always, the operator's manual */}
              {report.failed > 0 && (
                <GuidanceCard title="Action required">
                  {report.failed}{" "}
                  {report.failed === 1 ? "check has" : "checks have"} failed.
                  Each failing check has a <em>fix hint</em> below telling you
                  exactly what to do next. Work through them top to bottom —
                  environment issues first (they often cascade), then
                  filesystem, then engines.
                </GuidanceCard>
              )}
              {report.failed === 0 && report.warned > 0 && (
                <GuidanceCard title="Healthy with warnings">
                  No failures. {report.warned}{" "}
                  {report.warned === 1 ? "check is" : "checks are"} flagged
                  as worth attention — test-mode API keys, no sample data
                  yet, or other production-readiness gaps that aren't
                  blockers.
                </GuidanceCard>
              )}
              {report.failed === 0 && report.warned === 0 && (
                <GuidanceCard title="All clear">
                  Every check passed. DOCex is production-ready by the
                  Self-Check Agent's standards. Re-run periodically — esp.
                  before recording a demo or sending a proposal.
                </GuidanceCard>
              )}

              {/* Categories */}
              <div className="space-y-3">
                {CATEGORY_ORDER.filter((cat) => grouped[cat]?.length).map((cat) => {
                  const checks = grouped[cat];
                  const meta = CATEGORY_LABELS[cat] ?? {
                    label: cat,
                    icon: <HelpCircle className="h-4 w-4" />,
                  };
                  const isCollapsed = collapsed.has(cat);
                  const counts: Record<CheckStatus, number> = {
                    pass: 0,
                    warn: 0,
                    fail: 0,
                    skip: 0,
                  };
                  for (const c of checks) counts[c.status]++;
                  return (
                    <div
                      key={cat}
                      className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
                    >
                      <button
                        type="button"
                        onClick={() => toggleCategory(cat)}
                        className="flex w-full items-center justify-between gap-3 px-5 py-4 hover:bg-gray-50/60"
                      >
                        <div className="flex items-center gap-3">
                          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-100 text-gray-600">
                            {meta.icon}
                          </span>
                          <div className="text-left">
                            <p className="text-sm font-semibold text-gray-900">
                              {meta.label}
                            </p>
                            <p className="text-xs text-gray-500">
                              {checks.length}{" "}
                              {checks.length === 1 ? "check" : "checks"}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {counts.fail > 0 && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 ring-1 ring-rose-200">
                              {counts.fail} fail
                            </span>
                          )}
                          {counts.warn > 0 && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
                              {counts.warn} warn
                            </span>
                          )}
                          {counts.pass > 0 && counts.fail === 0 && counts.warn === 0 && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
                              {counts.pass} pass
                            </span>
                          )}
                          {isCollapsed ? (
                            <ChevronRight className="h-4 w-4 text-gray-400" />
                          ) : (
                            <ChevronDown className="h-4 w-4 text-gray-400" />
                          )}
                        </div>
                      </button>
                      {!isCollapsed && (
                        <div className="divide-y divide-gray-100 border-t border-gray-100">
                          {checks.map((c) => (
                            <CheckRow key={c.id} check={c} />
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* History */}
              {history.length > 1 && (
                <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                    <Clock className="h-4 w-4 text-gray-400" />
                    Recent runs
                  </h3>
                  <ul className="mt-3 space-y-1.5">
                    {history.slice(0, 8).map((h) => (
                      <li
                        key={h.report_id}
                        className="flex items-center justify-between gap-3 text-xs text-gray-600"
                      >
                        <span className="flex items-center gap-2">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              h.overall === "healthy"
                                ? "bg-emerald-500"
                                : h.overall === "degraded"
                                  ? "bg-amber-400"
                                  : "bg-rose-500"
                            }`}
                          />
                          {new Date(h.started_at).toLocaleString()}
                        </span>
                        <span className="tabular-nums">
                          {h.passed} pass · {h.warned} warn · {h.failed}{" "}
                          fail · {(h.duration_ms / 1000).toFixed(1)}s
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Sign out — clears the locally-stored secret so the next
                  reload prompts for it again. Useful if Farid wants to
                  hand the laptop to a teammate without exposing diagnostics. */}
              {getAdminSecret() && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={clearSecret}
                    className="text-[11px] text-gray-400 hover:text-rose-600"
                  >
                    Sign out of admin
                  </button>
                </div>
              )}
            </>
          )}
        </div>
        )}
      </main>
    </div>
  );
}

/* ─── Components ───────────────────────────────────────────────────────── */

function CountPill({
  tone,
  label,
  count,
}: {
  tone: "emerald" | "amber" | "rose" | "gray";
  label: string;
  count: number;
}) {
  const styles: Record<typeof tone, string> = {
    emerald: "bg-white/60 text-emerald-900 ring-1 ring-emerald-200",
    amber: "bg-white/60 text-amber-900 ring-1 ring-amber-200",
    rose: "bg-white/60 text-rose-900 ring-1 ring-rose-200",
    gray: "bg-white/60 text-gray-700 ring-1 ring-gray-200",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${styles[tone]}`}
    >
      <span className="font-bold tabular-nums">{count}</span>
      {label}
    </span>
  );
}

function CheckRow({ check }: { check: CheckResult }) {
  const hasMore = !!(check.evidence || check.fix_hint);
  return (
    <div className="px-5 py-4">
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${checkStatusColor[check.status]} border`}
          title={check.status}
        >
          <span className={`h-2 w-2 rounded-full ${checkStatusDot[check.status]}`} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-gray-900">{check.title}</p>
          <p className="mt-0.5 text-xs text-gray-600">{check.summary}</p>
          {hasMore && (
            <details className="group mt-2">
              <summary className="cursor-pointer list-none text-[11px] font-medium text-gray-500 transition hover:text-brand-700">
                <span className="inline-flex items-center gap-1">
                  <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
                  Details
                </span>
              </summary>
              <div className="mt-2 space-y-2 rounded-lg bg-gray-50 p-3 text-xs">
                {check.evidence && (
                  <div>
                    <p className="font-semibold uppercase tracking-wide text-gray-500">
                      Evidence
                    </p>
                    <p className="mt-1 whitespace-pre-wrap font-mono text-[11px] text-gray-700">
                      {check.evidence}
                    </p>
                  </div>
                )}
                {check.fix_hint && (
                  <div>
                    <p className="font-semibold uppercase tracking-wide text-gray-500">
                      How to fix
                    </p>
                    <p className="mt-1 text-gray-700">{check.fix_hint}</p>
                  </div>
                )}
              </div>
            </details>
          )}
        </div>
        <span className="shrink-0 text-[11px] tabular-nums text-gray-400">
          {check.duration_ms}ms
        </span>
      </div>
    </div>
  );
}

function EmptyState({
  onRun,
  running,
}: {
  onRun: () => void;
  running: boolean;
}) {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <Activity className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">
        Run your first diagnostic
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        DOCex checks every primitive, every engine, every persistence
        layer, every API route — then tells you exactly what's healthy,
        warning, or broken.
      </p>
      <button
        type="button"
        onClick={onRun}
        disabled={running}
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-brand-100 transition hover:bg-brand-700 disabled:opacity-50"
      >
        {running ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Running…
          </>
        ) : (
          <>
            <Play className="h-4 w-4" />
            Run Self-Check
          </>
        )}
      </button>
      <p className="mt-4 text-xs text-gray-400">
        Takes ~5 seconds · safe to re-run anytime
      </p>
    </div>
  );
}
