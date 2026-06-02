"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  FileSpreadsheet,
  Landmark,
  Loader2,
  Plus,
  Sparkles,
  Tag,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { listVerifyBatches } from "@/lib/api";
import { GuidanceCard } from "@/components/GuidanceCard";
import type { BatchVerifySummary, StandardPurpose } from "@/types";
import { purposeLabel } from "@/types";

/**
 * Bank Verify landing — the saved-batches list.
 *
 * Bank Verify is one of DOCex's three primitives (alongside Extraction and
 * Compliance Check). It's both a standalone tool — anyone can drop a list
 * of accounts in and verify them — AND a step inside larger agents
 * (Attendance Payment Co-Pilot, Sub-award Co-Pilot, etc).
 *
 * This page is the front door: see every batch you've run, recognise them
 * by source schedule + purpose, jump back into any of them, or kick off a
 * new verification. Designed to mirror /compliance/page.tsx pixel-for-pixel
 * so the user's eye doesn't have to relearn the layout for each primitive.
 */

export default function VerifyListPage() {
  const [batches, setBatches] = useState<BatchVerifySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listVerifyBatches();
        if (!cancelled) setBatches(list);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load batches. Is the API running on port 8000?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Aggregate stats across every batch. "DOCex is working" widget — same
  // psychological role as the compliance landing's stats: orchestrator
  // framing, not a chatbot you visit.
  const stats = batches
    ? batches.reduce(
        (acc, b) => ({
          batches: acc.batches + 1,
          verified: acc.verified + b.verified,
          warning: acc.warning + b.warning,
          mismatch: acc.mismatch + b.mismatch,
          unverifiable: acc.unverifiable + b.unverifiable,
          total: acc.total + b.total,
        }),
        { batches: 0, verified: 0, warning: 0, mismatch: 0, unverifiable: 0, total: 0 },
      )
    : null;

  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between gap-6 px-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>

          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <Landmark className="h-4 w-4 text-brand-600" />
            Bank Verify
          </span>

          <div className="flex items-center gap-2">
            <Link
              href="/agents/attendance-payment"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
              title="Attendance Payment Co-Pilot"
            >
              Attendance
            </Link>
            <Link
              href="/knowledge"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
              title="Knowledge Hub"
            >
              Knowledge
            </Link>
            <Link
              href="/compliance"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
              title="Switch to compliance checks"
            >
              Compliance
            </Link>
            <Link
              href="/app"
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
              title="Switch to extraction mode"
            >
              Extraction
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="space-y-8">
          {/* Page header */}
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Never pay the wrong account again.
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Upload a payment schedule, DOCex calls each bank live and{" "}
                <span className="text-gray-900">
                  matches every recipient name against the bank record.
                </span>{" "}
                Catches typos, wrong-recipient redirects, and impossible
                accounts before money moves.
              </p>
            </div>
            {batches && batches.length > 0 && (
              <Link
                href="/verify/new"
                className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
              >
                <Plus className="h-4 w-4" />
                New verification
              </Link>
            )}
          </div>

          {/* Stats — visible only when there's history to show. Same psychology
              as the compliance landing's track-record widget. */}
          {batches && batches.length > 0 && stats && (
            <div className="grid gap-3 sm:grid-cols-4">
              <StatCard
                icon={<CheckCircle2 className="h-4 w-4" />}
                label="Verified"
                value={stats.verified}
                tone="emerald"
                hint="Bank record matched the name"
              />
              <StatCard
                icon={<TriangleAlert className="h-4 w-4" />}
                label="Warnings"
                value={stats.warning}
                tone="amber"
                hint="Borderline — needs human review"
              />
              <StatCard
                icon={<XCircle className="h-4 w-4" />}
                label="Mismatches"
                value={stats.mismatch}
                tone="rose"
                hint="Wrong name on the account"
              />
              <StatCard
                icon={<CircleHelp className="h-4 w-4" />}
                label="Unverifiable"
                value={stats.unverifiable}
                tone="gray"
                hint="Bank API could not resolve"
              />
            </div>
          )}

          {batches && batches.length > 0 && (
            <GuidanceCard title="How this works">
              Each row in your schedule is checked against the bank-of-record
              via Paystack. DOCex fuzzy-matches the returned name against the
              recipient name on the schedule and returns one of four verdicts.
              Save the result, download a colour-coded copy of the schedule,
              or kick the warnings back to whoever prepared the file.
            </GuidanceCard>
          )}

          {/* Error state */}
          {error && (
            <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p className="font-medium text-red-900">
                Could not load batches
              </p>
              <p>{error}</p>
              <p className="text-xs text-red-600">
                Check the backend is running:{" "}
                <code className="rounded bg-red-100 px-1 py-0.5">
                  uvicorn api.main:app --reload --port 8000
                </code>
              </p>
            </div>
          )}

          {/* Loading */}
          {batches === null && !error && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading verifications…
            </div>
          )}

          {/* Empty state */}
          {batches !== null && batches.length === 0 && !error && <EmptyState />}

          {/* Populated state */}
          {batches !== null && batches.length > 0 && (
            <div className="grid gap-3">
              {batches.map((b) => (
                <BatchCard key={b.batch_id} batch={b} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

/* ─── Stats card ───────────────────────────────────────────────────────── */

function StatCard({
  icon,
  label,
  value,
  tone,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: "emerald" | "amber" | "rose" | "gray";
  hint: string;
}) {
  // Static colour-token maps. Tailwind needs the full class names present at
  // build time — dynamic interpolation gets stripped by purging.
  const styles: Record<typeof tone, { border: string; bg: string; text: string; hintText: string }> = {
    emerald: {
      border: "border-emerald-200",
      bg: "bg-emerald-50/40",
      text: "text-emerald-700",
      hintText: "text-emerald-700/80",
    },
    amber: {
      border: "border-amber-200",
      bg: "bg-amber-50/40",
      text: "text-amber-700",
      hintText: "text-amber-700/80",
    },
    rose: {
      border: "border-rose-200",
      bg: "bg-rose-50/40",
      text: "text-rose-700",
      hintText: "text-rose-700/80",
    },
    gray: {
      border: "border-gray-200",
      bg: "bg-white",
      text: "text-gray-600",
      hintText: "text-gray-500",
    },
  };
  const s = styles[tone];

  return (
    <div className={`rounded-xl border ${s.border} ${s.bg} p-4`}>
      <div
        className={`flex items-center gap-2 text-xs font-medium uppercase tracking-wide ${s.text}`}
      >
        {icon}
        {label}
      </div>
      <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900">
        {value}
      </p>
      <p className={`mt-1 text-[11px] ${s.hintText}`}>{hint}</p>
    </div>
  );
}

/* ─── Empty state ───────────────────────────────────────────────────────── */

function EmptyState() {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <Landmark className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">
        No verifications yet
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        Drop in your first payment schedule — DOCex calls each bank live,
        matches every recipient name against the bank-of-record, and returns a
        colour-coded copy you can paste into the approval thread or audit
        folder.
      </p>
      <Link
        href="/verify/new"
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-brand-100 transition hover:bg-brand-700"
      >
        <Sparkles className="h-4 w-4" />
        Verify your first schedule
      </Link>
      <p className="mt-4 text-xs text-gray-400">
        .xlsx · ~5 seconds per row · Nigerian banks supported
      </p>
    </div>
  );
}

/* ─── Card ─────────────────────────────────────────────────────────────── */

function BatchCard({ batch }: { batch: BatchVerifySummary }) {
  const created = batch.created_at ? new Date(batch.created_at) : null;
  // Format the purpose as a human label when it's one of the standard
  // values; fall back to the raw string for custom purposes.
  const purposeText = batch.purpose
    ? (purposeLabel as Record<string, string>)[batch.purpose] ?? batch.purpose
    : null;

  return (
    <Link
      href={`/verify/${batch.batch_id}`}
      className="group block rounded-xl border border-gray-200 bg-white p-5 transition hover:border-brand-300 hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
            {batch.source_schedule ?? "Verification batch"}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
            <span className="inline-flex items-center gap-1">
              <FileSpreadsheet className="h-3 w-3 shrink-0" />
              {batch.total} {batch.total === 1 ? "row" : "rows"}
            </span>
            {purposeText && (
              <span className="inline-flex items-center gap-1">
                <Tag className="h-3 w-3 shrink-0" />
                {purposeText}
              </span>
            )}
            {batch.purpose_detail && (
              <span
                className="truncate text-gray-400"
                title={batch.purpose_detail}
              >
                · {batch.purpose_detail}
              </span>
            )}
          </div>
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 text-gray-300 transition-colors group-hover:text-brand-600" />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1.5">
        {batch.verified > 0 && (
          <VerdictPill tone="emerald" count={batch.verified} label="verified" />
        )}
        {batch.warning > 0 && (
          <VerdictPill tone="amber" count={batch.warning} label="warning" />
        )}
        {batch.mismatch > 0 && (
          <VerdictPill tone="rose" count={batch.mismatch} label="mismatch" />
        )}
        {batch.unverifiable > 0 && (
          <VerdictPill
            tone="gray"
            count={batch.unverifiable}
            label="unverifiable"
          />
        )}
        {created && (
          <span className="ml-auto text-xs text-gray-400">
            {formatRelative(created)}
          </span>
        )}
      </div>
    </Link>
  );
}

function VerdictPill({
  tone,
  count,
  label,
}: {
  tone: "emerald" | "amber" | "rose" | "gray";
  count: number;
  label: string;
}) {
  // Static maps so Tailwind can purge correctly.
  const styles: Record<typeof tone, string> = {
    emerald:
      "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    amber: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    rose: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
    gray: "bg-gray-50 text-gray-600 ring-1 ring-gray-200",
  };
  const dots: Record<typeof tone, string> = {
    emerald: "bg-emerald-500",
    amber: "bg-amber-400",
    rose: "bg-rose-500",
    gray: "bg-gray-400",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${styles[tone]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dots[tone]}`} />
      {count} {label}
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
