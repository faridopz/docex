"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  CircleHelp,
  Download,
  FileSpreadsheet,
  Landmark,
  Loader2,
  Tag,
  Trash2,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import {
  deleteVerifyBatch,
  exportVerifyBatchToXlsx,
  getVerifyBatch,
} from "@/lib/api";
import { AssistantBrief } from "@/components/AssistantBrief";
import { GuidanceCard } from "@/components/GuidanceCard";
import type {
  BankVerifyBatchResult,
  BankVerifyVerdict,
  StandardPurpose,
} from "@/types";
import {
  bankVerdictColor,
  bankVerdictDot,
  bankVerdictLabel,
  purposeLabel,
} from "@/types";

/**
 * /verify/[id] — one verification batch in full.
 *
 * Layout choices:
 *
 *  - The summary banner sits at the top: source schedule, purpose tag, total
 *    + verdict counts. This is the artifact the user shares; everything
 *    above the table is what gets read first.
 *
 *  - Verdict filter chips let the user drill into "just the mismatches" or
 *    "just the warnings" without scrolling — critical for schedules with
 *    100+ rows where the eye needs to skip past the green.
 *
 *  - The results table mirrors the CLI output vocabulary (verified ✓,
 *    warning !, mismatch ✗, unverifiable ?) so users moving between CLI
 *    and UI never have to relearn the colour grammar.
 *
 *  - Download produces the canonical xlsx the backend already builds —
 *    colour-coded by verdict, summary banner intact. Client-side re-emission
 *    would lose the polish.
 */

export default function VerifyBatchDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [batch, setBatch] = useState<BankVerifyBatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<BankVerifyVerdict | "all">("all");
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getVerifyBatch(id);
        if (!cancelled) setBatch(data);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load this verification batch.",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const filteredRows = useMemo(() => {
    if (!batch) return [];
    if (filter === "all") return batch.results;
    return batch.results.filter((r) => r.verdict === filter);
  }, [batch, filter]);

  async function handleDownload() {
    if (!batch) return;
    setDownloading(true);
    try {
      await exportVerifyBatchToXlsx(id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not download the verified schedule.",
      );
    } finally {
      setDownloading(false);
    }
  }

  async function handleDelete() {
    if (!batch) return;
    const ok = window.confirm(
      "Delete this verification batch? The audit record will be permanently removed.",
    );
    if (!ok) return;
    setDeleting(true);
    try {
      await deleteVerifyBatch(id);
      router.push("/verify");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not delete the verification batch.",
      );
      setDeleting(false);
    }
  }

  const purposeText = batch?.purpose
    ? (purposeLabel as Record<string, string>)[batch.purpose] ?? batch.purpose
    : null;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-6 px-6">
          <Link
            href="/verify"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <Landmark className="h-4 w-4 text-brand-600" />
            Verification batch
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDownload}
              disabled={!batch || downloading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
              title="Download verified .xlsx"
            >
              {downloading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              Download
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={!batch || deleting}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs font-medium text-gray-500 transition hover:border-rose-300 hover:text-rose-700 disabled:opacity-50"
              title="Delete batch"
            >
              {deleting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12">
        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {!batch && !error && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading batch…
          </div>
        )}

        {batch && (
          <div className="space-y-8">
            {/* DOCex Assistant — the AI's plain-English briefing sits ABOVE
                the verdict table. Reads what happened, recommends actions. */}
            <AssistantBrief
              contextKind="bank_verify_batch"
              contextId={id}
              payload={batch}
              onAction={(label) => {
                // Map a few well-known action labels to real handlers.
                // Unmapped labels remain informational chips (good UX —
                // a chip the user can read but not click is honest).
                const l = label.toLowerCase();
                if (l.includes("download")) void handleDownload();
                else if (l.includes("delete") || l.includes("remove batch"))
                  void handleDelete();
              }}
            />

            {/* Summary banner */}
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <h1 className="truncate text-2xl font-bold tracking-tight text-gray-900">
                    {batch.source_schedule ?? "Verification batch"}
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
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
                      <span className="text-gray-400">
                        · {batch.purpose_detail}
                      </span>
                    )}
                    {batch.created_at && (
                      <span className="text-gray-400">
                        · {new Date(batch.created_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Filter chips — clicking one drills the table */}
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <FilterChip
                  active={filter === "all"}
                  onClick={() => setFilter("all")}
                  tone="gray"
                  count={batch.total}
                  label="All rows"
                />
                {batch.verified > 0 && (
                  <FilterChip
                    active={filter === "verified"}
                    onClick={() => setFilter("verified")}
                    tone="emerald"
                    count={batch.verified}
                    label="Verified"
                  />
                )}
                {batch.warning > 0 && (
                  <FilterChip
                    active={filter === "warning"}
                    onClick={() => setFilter("warning")}
                    tone="amber"
                    count={batch.warning}
                    label="Warnings"
                  />
                )}
                {batch.mismatch > 0 && (
                  <FilterChip
                    active={filter === "mismatch"}
                    onClick={() => setFilter("mismatch")}
                    tone="rose"
                    count={batch.mismatch}
                    label="Mismatches"
                  />
                )}
                {batch.unverifiable > 0 && (
                  <FilterChip
                    active={filter === "unverifiable"}
                    onClick={() => setFilter("unverifiable")}
                    tone="gray"
                    count={batch.unverifiable}
                    label="Unverifiable"
                  />
                )}
              </div>
            </div>

            {/* Guidance card — first-time helpfulness */}
            {(batch.warning > 0 || batch.mismatch > 0) && (
              <GuidanceCard title="What to do with these rows">
                <span className="text-amber-700 font-medium">Warnings</span>{" "}
                are name variants — typo, missing middle name, etc. Worth a
                quick eyeball; usually safe to release.{" "}
                <span className="text-rose-700 font-medium">Mismatches</span>{" "}
                are different people on the account — block these and kick
                back to whoever prepared the schedule before any money moves.
              </GuidanceCard>
            )}

            {/* Results table */}
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-100">
                  <thead className="bg-gray-50/60">
                    <tr>
                      <Th>Verdict</Th>
                      <Th>Recipient name</Th>
                      <Th>Bank-of-record name</Th>
                      <Th className="text-right">Match</Th>
                      <Th>Account</Th>
                      <Th>Bank</Th>
                      <Th className="text-right">Amount</Th>
                      <Th>Notes</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredRows.length === 0 ? (
                      <tr>
                        <td
                          colSpan={8}
                          className="px-4 py-12 text-center text-sm text-gray-500"
                        >
                          No rows match this filter.
                        </td>
                      </tr>
                    ) : (
                      filteredRows.map((r, i) => (
                        <ResultRow key={i} row={r} />
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Bottom action band — second chance at the download for users
                who scrolled all the way through the table */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white p-5">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  Done reviewing?
                </p>
                <p className="text-xs text-gray-500">
                  Download the verified copy — colour-coded by verdict, ready to
                  share or file.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloading}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
              >
                {downloading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating…
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" />
                    Download verified .xlsx
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/* ─── Table primitives ──────────────────────────────────────────────────── */

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500 ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function ResultRow({
  row,
}: {
  row: BankVerifyBatchResult["results"][number];
}) {
  return (
    <tr className="hover:bg-gray-50/60">
      <td className="px-4 py-3">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium border ${bankVerdictColor[row.verdict]}`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${bankVerdictDot[row.verdict]}`}
          />
          {bankVerdictLabel[row.verdict]}
        </span>
      </td>
      <td className="px-4 py-3 text-sm font-medium text-gray-900">
        {row.recipient_name}
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">
        {row.resolved_name ?? <span className="text-gray-300">—</span>}
      </td>
      <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-700">
        {row.match_score != null ? (
          <span className="font-medium">{row.match_score}</span>
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-gray-700">
        {row.account_number}
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">
        {row.bank_name ?? row.bank_code}
      </td>
      <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-700">
        {row.amount != null ? (
          `₦${row.amount.toLocaleString()}`
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-gray-500">
        {row.error_message ?? row.notes ?? ""}
      </td>
    </tr>
  );
}

/* ─── Filter chip ──────────────────────────────────────────────────────── */

function FilterChip({
  active,
  onClick,
  tone,
  count,
  label,
}: {
  active: boolean;
  onClick: () => void;
  tone: "emerald" | "amber" | "rose" | "gray";
  count: number;
  label: string;
}) {
  // Static class maps for Tailwind purging
  const activeStyles: Record<typeof tone, string> = {
    emerald:
      "bg-emerald-600 text-white ring-1 ring-emerald-600",
    amber: "bg-amber-500 text-white ring-1 ring-amber-500",
    rose: "bg-rose-600 text-white ring-1 ring-rose-600",
    gray: "bg-gray-900 text-white ring-1 ring-gray-900",
  };
  const idleStyles: Record<typeof tone, string> = {
    emerald:
      "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 hover:bg-emerald-100",
    amber:
      "bg-amber-50 text-amber-700 ring-1 ring-amber-200 hover:bg-amber-100",
    rose: "bg-rose-50 text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100",
    gray: "bg-white text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${active ? activeStyles[tone] : idleStyles[tone]}`}
    >
      {label}
      <span
        className={`rounded-full px-1.5 py-0 text-[10px] ${active ? "bg-white/20" : "bg-black/5"}`}
      >
        {count}
      </span>
    </button>
  );
}
