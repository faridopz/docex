"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Clock,
  FileSearch,
  FileSpreadsheet,
  Loader2,
  Stamp,
} from "lucide-react";
import { AppNav } from "@/components/AppNav";
import { GuidanceCard } from "@/components/GuidanceCard";
import { exportChecksListToExcel, listChecks } from "@/lib/api";
import {
  overallVerdictColor,
  overallVerdictDot,
  overallVerdictLabel,
  type CheckSummary,
  type OverallVerdict,
} from "@/types";

/**
 * Saved checks archive.
 *
 * Every compliance check the team has ever run, persistent and filterable.
 * This is the page that becomes "Approved PVs" once you filter to approved
 * — but it's also "all checks" by default, including drafts/flagged/blocked
 * ones that the audit team might want to see.
 *
 * Design follows Anthropic principles: clean filter chips, generous
 * whitespace, scannable cards, no aggressive engagement nudges, empty
 * state teaches the next action.
 */

type Filter = "all" | "approved" | "flagged" | "blocked" | "needs-attention";

const FILTERS: { id: Filter; label: string; hint: string }[] = [
  {
    id: "all",
    label: "All",
    hint: "Every check ever run",
  },
  {
    id: "approved",
    label: "Approved",
    hint: "Approved checks — the final, audit-ready archive",
  },
  {
    id: "needs-attention",
    label: "Needs attention",
    hint: "Flagged or blocked checks awaiting officer review",
  },
  {
    id: "flagged",
    label: "Flagged only",
    hint: "Borderline checks — partial compliance or missing info",
  },
  {
    id: "blocked",
    label: "Blocked",
    hint: "Checks that clearly violated a rule",
  },
];

export default function SavedChecksPage() {
  const [checks, setChecks] = useState<CheckSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listChecks();
        if (!cancelled) setChecks(list);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load saved checks. Is the API running?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const counts = useMemo(() => {
    if (!checks)
      return { all: 0, approved: 0, flagged: 0, blocked: 0, needs: 0 };
    return {
      all: checks.length,
      approved: checks.filter((c) => c.approved).length,
      flagged: checks.filter((c) => c.overall_verdict === "flagged").length,
      blocked: checks.filter((c) => c.overall_verdict === "blocked").length,
      needs: checks.filter(
        (c) => c.overall_verdict !== "approved" && !c.approved,
      ).length,
    };
  }, [checks]);

  const filtered = useMemo(() => {
    if (!checks) return [];
    switch (filter) {
      case "approved":
        return checks.filter((c) => c.approved);
      case "flagged":
        return checks.filter((c) => c.overall_verdict === "flagged");
      case "blocked":
        return checks.filter((c) => c.overall_verdict === "blocked");
      case "needs-attention":
        return checks.filter(
          (c) => c.overall_verdict !== "approved" && !c.approved,
        );
      default:
        return checks;
    }
  }, [checks, filter]);

  return (
    <div className="min-h-screen bg-gray-50">
      <AppNav active="compliance">
        <Link
          href="/compliance/pending"
          className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
        >
          Inbox
        </Link>
      </AppNav>

      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="space-y-8">
          {/* Header */}
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Saved checks
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Every compliance check is saved automatically with a stable
                URL.{" "}
                <span className="font-semibold text-gray-900">
                  Mark approved ones to build your audit-ready archive.
                </span>
              </p>
            </div>
          </div>

          {/* Summary stats */}
          {checks !== null && checks.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-3">
              <StatCard
                label="Total checks"
                value={counts.all}
                icon={<FileSearch className="h-4 w-4 text-brand-600" />}
              />
              <StatCard
                label="Approved"
                value={counts.approved}
                icon={<Stamp className="h-4 w-4 text-emerald-600" />}
                accent="emerald"
              />
              <StatCard
                label="Needs attention"
                value={counts.needs}
                icon={<Clock className="h-4 w-4 text-amber-600" />}
                accent="amber"
              />
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p className="font-medium text-red-900">Could not load checks</p>
              <p className="mt-1">{error}</p>
            </div>
          )}

          {/* Loading */}
          {checks === null && !error && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading…
            </div>
          )}

          {/* Empty state */}
          {checks !== null && checks.length === 0 && !error && (
            <EmptyState />
          )}

          {/* Filter + list */}
          {checks !== null && checks.length > 0 && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  {FILTERS.map((f) => (
                    <FilterChip
                      key={f.id}
                      active={filter === f.id}
                      onClick={() => setFilter(f.id)}
                      label={f.label}
                      hint={f.hint}
                      count={
                        f.id === "all"
                          ? counts.all
                          : f.id === "approved"
                            ? counts.approved
                            : f.id === "flagged"
                              ? counts.flagged
                              : f.id === "blocked"
                                ? counts.blocked
                                : counts.needs
                      }
                    />
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() =>
                    exportChecksListToExcel(
                      filtered,
                      `compliance-checks-${filter}.xlsx`,
                    )
                  }
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700"
                  title="Export the current filtered list as Excel — one row per check"
                >
                  <FileSpreadsheet className="h-4 w-4" />
                  Export {filter === "all" ? "all" : "filtered"} ({filtered.length})
                </button>
              </div>

              {filter === "approved" && counts.approved > 0 && (
                <GuidanceCard title="Audit-ready archive">
                  These checks have been marked Approved. Each has a stable
                  URL you can paste into an audit response — auditors see
                  exactly what the officer saw, with the rulebook frozen as
                  it was at check time.
                </GuidanceCard>
              )}

              {filtered.length === 0 ? (
                <div className="rounded-lg border border-gray-200 bg-white px-6 py-12 text-center text-sm text-gray-500">
                  No checks match this filter.
                </div>
              ) : (
                <div className="space-y-2">
                  {filtered.map((c) => (
                    <CheckCard key={c.payment_id} check={c} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

/* ─── Empty state ─────────────────────────────────────────────────────── */

function EmptyState() {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <FileSearch className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">No checks yet</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        Once you run your first compliance check, it'll be saved here
        automatically — with its own URL you can share with auditors.
      </p>
      <Link
        href="/compliance"
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Go to rulebooks
      </Link>
    </div>
  );
}

/* ─── Stat card ───────────────────────────────────────────────────────── */

function StatCard({
  label,
  value,
  icon,
  accent,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  accent?: "emerald" | "amber" | "brand";
}) {
  const accentClass =
    accent === "emerald"
      ? "border-emerald-200 bg-emerald-50/40"
      : accent === "amber"
        ? "border-amber-200 bg-amber-50/40"
        : "border-gray-200 bg-white";
  return (
    <div className={`rounded-xl border p-4 ${accentClass}`}>
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-600">
        {icon}
        {label}
      </div>
      <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900">
        {value}
      </p>
    </div>
  );
}

/* ─── Filter chip ─────────────────────────────────────────────────────── */

function FilterChip({
  active,
  onClick,
  label,
  hint,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint: string;
  count: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition ${
        active
          ? "bg-brand-600 text-white shadow-sm"
          : "border border-gray-200 bg-white text-gray-700 hover:border-brand-300 hover:text-brand-700"
      }`}
    >
      {label}
      <span
        className={`inline-flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-xs font-semibold tabular-nums ${
          active ? "bg-white/20" : "bg-gray-100 text-gray-600"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

/* ─── Check card (list row) ───────────────────────────────────────────── */

function CheckCard({ check }: { check: CheckSummary }) {
  const created = check.created_at ? new Date(check.created_at) : null;

  return (
    <Link
      href={`/compliance/checks/${check.payment_id}`}
      className="group block rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-base font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
              {check.payment_label}
            </h3>
            {check.approved && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
                <Check className="h-3 w-3" />
                Approved
              </span>
            )}
          </div>
          <p className="text-sm leading-relaxed text-gray-600">
            {check.overall_summary}
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
            <VerdictPill verdict={check.overall_verdict} />
            <span>{check.rulebook_name}</span>
            <span>
              {check.document_count}{" "}
              {check.document_count === 1 ? "document" : "documents"}
            </span>
            {created && <span>{formatRelative(created)}</span>}
          </div>
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 text-gray-300 transition-colors group-hover:text-brand-600" />
      </div>
    </Link>
  );
}

function VerdictPill({ verdict }: { verdict: OverallVerdict }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${overallVerdictColor[verdict]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${overallVerdictDot[verdict]}`} />
      {overallVerdictLabel[verdict]}
    </span>
  );
}

function formatRelative(d: Date): string {
  const diff = Date.now() - d.getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}
