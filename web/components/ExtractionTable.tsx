"use client";

import { useRef, useState, useMemo, useCallback, useEffect } from "react";
import type {
  SingleExtractionResponse,
  BatchExtractionResponse,
  ExtractionAnswer,
  Question,
  Confidence,
} from "@/types";
import {
  confidenceLabel,
  confidenceColor,
  confidenceDot,
} from "@/types";
import { GuidanceCard } from "./GuidanceCard";
import {
  Download,
  FileSpreadsheet,
  FileJson,
  FileText,
  ExternalLink,
  Mail,
  Copy,
  Check,
  RotateCcw,
  Loader2,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Filter,
  X,
  Rows3,
  ChevronRight,
} from "lucide-react";
import {
  exportToExcel,
  exportJson,
  draftFollowups,
  exportFollowupsAsText,
  type FollowupDraft,
} from "@/lib/api";
import { getWorkflowLabels } from "@/lib/workflow-labels";
import { assignBucket, BUCKETS, type BucketId, type Bucket } from "@/lib/buckets";

// ── Props ───────────────────────────────────────────────────────────────────

interface ExtractionTableProps {
  mode: "single" | "batch";
  result: SingleExtractionResponse | BatchExtractionResponse;
  questions: Question[];
  templateId?: string | null;
  onTemplateChange?: (templateId: string | null) => void;
}

// ── Type guards ─────────────────────────────────────────────────────────────

function isBatch(
  result: SingleExtractionResponse | BatchExtractionResponse,
): result is BatchExtractionResponse {
  return "applicants" in result;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Bucket badge — small pill that summarises an applicant's overall
 * answer profile (Complete / Near-complete / Has gaps / Major gaps).
 *
 * The bucket itself is derived deterministically from the answers (see
 * lib/buckets.ts), so the badge is always defensible — the user can verify
 * the justification on hover or in the Excel export.
 *
 * Two sizes:
 *   • "sm"   — dot + short label, used in tight spots (table first column)
 *   • "md"   — full pill with label, used in card headers and summary chips
 */
function BucketBadge({
  bucket,
  justification,
  size = "md",
}: {
  bucket: Bucket;
  justification: string;
  size?: "sm" | "md";
}) {
  if (size === "sm") {
    return (
      <span
        title={`${bucket.label} — ${justification}`}
        className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${bucket.colorClasses}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${bucket.dotClasses}`} />
        {bucket.label}
      </span>
    );
  }
  return (
    <span
      title={`${bucket.description} ${justification}`}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${bucket.colorClasses}`}
    >
      <span className={`h-2 w-2 rounded-full ${bucket.dotClasses}`} />
      {bucket.label}
    </span>
  );
}

/**
 * Compact cell content for the heatmap table view.
 * Shows a confidence dot + a tight one-line preview of the answer.
 * The full content lives in ExpandedAnswerCell, shown when the cell is clicked.
 */
function CompactAnswerCell({ answer }: { answer: ExtractionAnswer }) {
  // For list answers, the first line is the most useful preview.
  // For prose, take the start of the string. Either way: one line, tight.
  const firstLine = answer.answer
    ? answer.answer.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)[0] ?? ""
    : "";
  const preview = firstLine.length > 0
    ? firstLine.length > 48
      ? firstLine.slice(0, 48) + "…"
      : firstLine
    : "Not found";

  return (
    <div className="flex items-start gap-1.5 text-[11px] leading-snug">
      <span
        className={`mt-1 h-2 w-2 shrink-0 rounded-full ${confidenceDot[answer.confidence]}`}
      />
      <span
        className={`${
          answer.answer ? "text-gray-700" : "text-gray-400 italic"
        } line-clamp-2`}
        title={answer.answer ?? "Not found"}
      >
        {preview}
      </span>
    </div>
  );
}

/**
 * Expanded cell content shown when a table cell is clicked.
 * Full answer (list-aware), source, page, quote — everything from the card
 * view, packed into the cell.
 */
function ExpandedAnswerCell({
  answer,
  onClose,
}: {
  answer: ExtractionAnswer;
  onClose: () => void;
}) {
  return (
    <div
      className="space-y-1.5 text-xs"
      // Stop propagation so clicking internals (quote toggle, close button)
      // doesn't bubble up to the cell's onClick and re-collapse the view.
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-start justify-between gap-2">
        <ConfidenceBadge confidence={answer.confidence} />
        <button
          type="button"
          onClick={onClose}
          className="-mt-0.5 -mr-0.5 shrink-0 rounded p-0.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700"
          aria-label="Collapse cell"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
      {answer.answer ? (
        <AnswerText
          text={answer.answer}
          className="text-xs text-gray-800 leading-relaxed"
        />
      ) : (
        <p className="text-xs italic text-gray-400">Not found in any document</p>
      )}
      {answer.source_document && (
        <p className="flex items-start gap-1 text-[10px] text-gray-500">
          <ExternalLink className="mt-0.5 h-2.5 w-2.5 shrink-0" />
          <span className="break-all">
            {answer.source_document}
            {answer.source_page != null && ` · p.${answer.source_page}`}
          </span>
        </p>
      )}
      {answer.quote && (
        <details className="text-[10px]">
          <summary className="cursor-pointer font-medium text-blue-600 hover:text-blue-700">
            View quote
          </summary>
          <div className="mt-1 rounded border border-gray-100 bg-gray-50 px-2 py-1">
            <p className="font-mono leading-relaxed text-gray-600 whitespace-pre-wrap">
              {answer.quote}
            </p>
          </div>
        </details>
      )}
      {answer.search_notes && (
        <p className="text-[10px] italic text-gray-500 leading-relaxed">
          <span className="font-medium not-italic">
            {answer.confidence === "inferred"
              ? "Reasoning: "
              : answer.confidence === "not_found"
                ? "Search note: "
                : "Note: "}
          </span>
          {answer.search_notes}
        </p>
      )}
    </div>
  );
}

/**
 * Render an answer string with smart list detection.
 *
 * If the answer is a single line (or a single short paragraph), it renders
 * as a paragraph. If it contains newline-separated items — which is what
 * the system prompt now asks for on list answers — it renders as a bulleted
 * list. Any common bullet prefix the model added ("- ", "• ", "1. ", etc.)
 * is stripped so we apply consistent UI styling.
 */
function AnswerText({
  text,
  className = "text-sm text-gray-700 leading-relaxed",
}: {
  text: string;
  className?: string;
}) {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  if (lines.length <= 1) {
    return <p className={className}>{text}</p>;
  }

  const stripped = lines
    .map((l) => l.replace(/^(\s*[-•*–—]\s+|\s*\(?\d+[.)]\s+)/, "").trim())
    .filter(Boolean);

  return (
    <ul className={`${className} list-disc space-y-1 pl-5 marker:text-gray-400`}>
      {stripped.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  );
}

function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max) + "…" : str;
}

function singleToApplicantArray(result: SingleExtractionResponse) {
  return [
    {
      applicant_id: "single",
      applicant_name: result.applicant_name,
      documents: result.documents,
      answers: result.answers,
      error: result.error ?? undefined,
    },
  ];
}

// ── Component ───────────────────────────────────────────────────────────────

export function ExtractionTable({
  mode,
  result,
  questions,
  templateId,
}: ExtractionTableProps) {
  const batch = isBatch(result);
  const applicants = batch ? result.applicants : singleToApplicantArray(result);
  const labels = getWorkflowLabels(templateId);

  // Count actual errors (applicants with error field set)
  const errorCount = applicants.filter((ap) => ap.error).length;

  // Follow-up notes state
  const [followupState, setFollowupState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [followupError, setFollowupError] = useState<string | null>(null);
  // Original drafts from Claude (for reset)
  const [originalDrafts, setOriginalDrafts] = useState<FollowupDraft[]>([]);
  // Editable drafts the user can modify
  const [editedDrafts, setEditedDrafts] = useState<
    { applicant_id: string; applicant_name: string; note: string }[]
  >([]);

  const handleDraftFollowups = async () => {
    setFollowupState("loading");
    setFollowupError(null);
    try {
      const drafts = await draftFollowups(applicants, questions, templateId);
      setOriginalDrafts(drafts);
      setEditedDrafts(drafts.map((d) => ({ ...d })));
      setFollowupState("ready");
    } catch (err) {
      setFollowupError(
        err instanceof Error ? err.message : "Failed to generate follow-up notes.",
      );
      setFollowupState("error");
    }
  };

  const updateDraftNote = (applicantId: string, note: string) => {
    setEditedDrafts((prev) =>
      prev.map((d) => (d.applicant_id === applicantId ? { ...d, note } : d)),
    );
  };

  const resetDraft = (applicantId: string) => {
    const original = originalDrafts.find((d) => d.applicant_id === applicantId);
    if (original) updateDraftNote(applicantId, original.note);
  };

  // Per-applicant error messages from the backend. Surface these prominently
  // — without them the user sees "3 errors" with no idea what went wrong.
  const erroredApplicants = applicants.filter((ap) => ap.error);

  // Bucket distribution across the run. We compute once and re-use for the
  // summary chip row and (later) the by-bucket view mode. Note this only
  // makes sense in batch mode — in single mode there's only one applicant
  // to bucket and we surface it differently.
  const bucketDistribution = useMemo(() => {
    const counts = new Map<BucketId, number>();
    for (const ap of applicants) {
      const id = assignBucket(ap.answers).bucket.id;
      counts.set(id, (counts.get(id) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([id, count]) => ({ bucket: BUCKETS[id], count }))
      .sort((a, b) => a.bucket.order - b.bucket.order);
  }, [applicants]);

  return (
    <section className="space-y-6">
      {/* Summary */}
      <GuidanceCard title="Your results are ready">
        {batch
          ? `${labels.actionVerbPast} ${applicants.length} ${applicants.length === 1 ? labels.unitSingular : labels.unitPlural}${errorCount > 0 ? ` · ${errorCount} error${errorCount !== 1 ? "s" : ""}` : ""}.`
          : `${labels.actionVerbPast} ${result.applicant_name} — ${result.documents.length} document${result.documents.length !== 1 ? "s" : ""} read.`}
      </GuidanceCard>

      {/* Bucket distribution — one chip per bucket present in the run,
          batch-only because single-mode bucketing is surfaced inside the cards. */}
      {batch && applicants.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Distribution
          </span>
          {bucketDistribution.map(({ bucket, count }) => (
            <span
              key={bucket.id}
              title={bucket.description}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${bucket.colorClasses}`}
            >
              <span className={`h-2 w-2 rounded-full ${bucket.dotClasses}`} />
              <span className="font-semibold">{count}</span>
              <span>{bucket.label.toLowerCase()}</span>
            </span>
          ))}
        </div>
      )}

      {/* Per-applicant error banner — diagnostic surface for failed extractions */}
      {erroredApplicants.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 space-y-2">
          <p className="text-sm font-semibold text-red-900">
            {erroredApplicants.length === 1
              ? "1 extraction failed"
              : `${erroredApplicants.length} extractions failed`}
          </p>
          <ul className="space-y-1 text-xs text-red-800">
            {erroredApplicants.map((ap) => (
              <li key={ap.applicant_id} className="font-mono">
                <span className="font-sans font-medium not-italic">
                  {ap.applicant_name || "Unnamed"}:
                </span>{" "}
                {ap.error}
              </li>
            ))}
          </ul>
          <p className="text-xs text-red-700">
            Check the backend terminal (uvicorn) for the full traceback. Common
            causes: <code>ANTHROPIC_API_KEY</code> not set in the shell running
            the API, an unsupported model name, or the response exceeding
            <code> max_tokens</code>.
          </p>
        </div>
      )}

      {/* Export buttons */}
      <div className="flex flex-wrap justify-end gap-3">
        <button
          type="button"
          onClick={() => exportToExcel(applicants, questions)}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
        >
          <FileSpreadsheet className="h-4 w-4" />
          Download Excel
        </button>
        <button
          type="button"
          onClick={() => exportJson(result)}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700"
        >
          <FileJson className="h-4 w-4" />
          Download JSON
        </button>
        {applicants.length > 0 && followupState !== "ready" && (
          <button
            type="button"
            onClick={handleDraftFollowups}
            disabled={followupState === "loading"}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {followupState === "loading" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Mail className="h-4 w-4" />
            )}
            {followupState === "loading"
              ? "Drafting notes..."
              : "Draft follow-up notes"}
          </button>
        )}
      </div>

      {/* Follow-up error */}
      {followupState === "error" && followupError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {followupError}
          <button
            type="button"
            onClick={handleDraftFollowups}
            className="ml-2 font-medium underline hover:text-red-800"
          >
            Try again
          </button>
        </div>
      )}

      {/* Follow-up drafts panel */}
      {followupState === "ready" && editedDrafts.length > 0 && (
        <div>
          <hr className="border-t border-gray-200 mt-12 mb-8" />
          <h2 className="text-xl font-semibold text-gray-900">Follow-up Notes</h2>
          <p className="text-sm text-gray-600 mb-6">
            Draft notes for unsuccessful applicants &mdash; review and edit before sending
          </p>
          <FollowupPanel
            drafts={editedDrafts}
            originalDrafts={originalDrafts}
            onUpdate={updateDraftNote}
            onReset={resetDraft}
            onClose={() => setFollowupState("idle")}
          />
        </div>
      )}

      {/* Body */}
      {mode === "single" ? (
        <SingleView answers={(result as SingleExtractionResponse).answers} />
      ) : (
        <BatchView
          applicants={applicants}
          questions={questions}
          templateId={templateId}
        />
      )}
    </section>
  );
}

// ── Single mode: two-column answer list ─────────────────────────────────────

function SingleView({ answers }: { answers: ExtractionAnswer[] }) {
  const assignment = assignBucket(answers);
  return (
    <div className="space-y-4">
      {answers.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-4 py-2.5">
          <BucketBadge
            bucket={assignment.bucket}
            justification={assignment.justification}
            size="md"
          />
          <p className="text-xs text-gray-600">{assignment.justification}</p>
        </div>
      )}
      {answers.map((a) => (
        <AnswerCard key={a.question_id} answer={a} />
      ))}
    </div>
  );
}

function AnswerCard({ answer }: { answer: ExtractionAnswer }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
      {/* Question + confidence badge */}
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-gray-900">{answer.question_text}</p>
        <ConfidenceBadge confidence={answer.confidence} />
      </div>

      {/* Answer — list-aware rendering (newlines become bullets) */}
      {answer.answer ? (
        <AnswerText text={answer.answer} />
      ) : (
        <p className="text-sm italic text-gray-400">Not found in any document</p>
      )}

      {/* Source */}
      {answer.source_document && (
        <p className="flex items-center gap-1.5 text-xs text-gray-500">
          <ExternalLink className="h-3 w-3 shrink-0" />
          {answer.source_document}
          {answer.source_page != null && ` · p.${answer.source_page}`}
        </p>
      )}

      {/* Expandable quote */}
      {answer.quote && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-medium text-blue-600 hover:text-blue-700">
            View exact quote
          </summary>
          <div className="mt-2 rounded-md bg-gray-50 border border-gray-100 px-3 py-2">
            <p className="text-xs font-mono text-gray-600 leading-relaxed whitespace-pre-wrap">
              {answer.quote}
            </p>
          </div>
        </details>
      )}

      {/* Search notes — reasoning trail */}
      {answer.search_notes && (
        <p className="text-xs text-gray-500 leading-relaxed">
          <span className="font-medium text-gray-600">
            {answer.confidence === "inferred" ? "Reasoning: " : answer.confidence === "not_found" ? "Search note: " : "Note: "}
          </span>
          {answer.search_notes}
        </p>
      )}
    </div>
  );
}

// ── Batch mode: sort & filter types ────────────────────────────────────────

type SortDirection = "asc" | "desc" | "none";
// "name" for applicant column, or a question id
type SortColumn = string | null;

const CONFIDENCE_ORDER: Record<Confidence, number> = {
  found: 0,
  inferred: 1,
  not_found: 2,
};

// ── Batch mode: aggregate stats card ───────────────────────────────────────

function AggregateStats({
  applicants,
  questions,
  onQuestionClick,
}: {
  applicants: BatchExtractionResponse["applicants"];
  questions: Question[];
  onQuestionClick: (questionId: string) => void;
}) {
  const stats = useMemo(() => {
    return questions.map((q) => {
      let found = 0;
      let inferred = 0;
      let notFound = 0;
      for (const ap of applicants) {
        const a = ap.answers.find((ans) => ans.question_id === q.id);
        if (!a || a.confidence === "not_found") notFound++;
        else if (a.confidence === "found") found++;
        else inferred++;
      }
      return { question: q, found, inferred, notFound };
    });
  }, [applicants, questions]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 mb-6">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">
        Across {applicants.length} applicant{applicants.length !== 1 ? "s" : ""}
      </h3>
      <div className="space-y-0.5">
        {stats.map((s) => (
          <button
            key={s.question.id}
            type="button"
            onClick={() => onQuestionClick(s.question.id)}
            className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition hover:bg-gray-50"
          >
            <span className="flex-1 truncate text-gray-700">
              {truncate(s.question.text, 50)}
            </span>
            <span className="inline-flex items-center gap-1 shrink-0 w-10 justify-end">
              <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.found}`} />
              <span className="tabular-nums font-medium text-emerald-700">{s.found}</span>
            </span>
            <span className="inline-flex items-center gap-1 shrink-0 w-10 justify-end">
              <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.inferred}`} />
              <span className="tabular-nums font-medium text-amber-700">{s.inferred}</span>
            </span>
            <span className="inline-flex items-center gap-1 shrink-0 w-10 justify-end">
              <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.not_found}`} />
              <span className="tabular-nums font-medium text-gray-500">{s.notFound}</span>
            </span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-gray-300 opacity-0 transition group-hover:opacity-100" />
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Batch mode: per-question comparison drawer ─────────────────────────────

function ComparisonDrawer({
  question,
  applicants,
  onClose,
}: {
  question: Question;
  applicants: BatchExtractionResponse["applicants"];
  onClose: () => void;
}) {
  // Lock body scroll while open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 transition-opacity"
        onClick={onClose}
      />
      {/* Drawer panel */}
      <div className="relative w-full max-w-[480px] bg-white shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-gray-200 px-6 py-4">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-gray-900 leading-snug">
              {question.text}
            </h3>
            <p className="mt-1 text-xs text-gray-500">
              Comparing {applicants.length} applicant{applicants.length !== 1 ? "s" : ""} on this question
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {applicants.map((ap) => {
            const answer = ap.answers.find(
              (a) => a.question_id === question.id,
            );
            return (
              <div
                key={ap.applicant_id}
                className="rounded-lg border border-gray-200 bg-white p-4 space-y-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-gray-900">
                    {ap.applicant_name || "Unnamed"}
                  </p>
                  {answer && <ConfidenceBadge confidence={answer.confidence} />}
                </div>

                {answer?.answer ? (
                  <p className="text-sm text-gray-800 leading-relaxed">
                    {answer.answer}
                  </p>
                ) : (
                  <p className="text-sm italic text-gray-400">
                    Not found in any document
                  </p>
                )}

                {answer?.source_document && (
                  <p className="flex items-center gap-1.5 text-xs text-gray-500">
                    <ExternalLink className="h-3 w-3 shrink-0" />
                    {answer.source_document}
                    {answer.source_page != null && ` · p.${answer.source_page}`}
                  </p>
                )}

                {answer?.quote && (
                  <details className="group">
                    <summary className="cursor-pointer text-xs font-medium text-blue-600 hover:text-blue-700">
                      View exact quote
                    </summary>
                    <div className="mt-2 rounded-md bg-gray-50 border border-gray-100 px-3 py-2">
                      <p className="text-xs font-mono text-gray-600 leading-relaxed whitespace-pre-wrap">
                        {answer.quote}
                      </p>
                    </div>
                  </details>
                )}

                {answer?.search_notes && (
                  <p className="text-xs text-gray-500 leading-relaxed">
                    <span className="font-medium text-gray-600">
                      {answer.confidence === "inferred"
                        ? "Reasoning: "
                        : answer.confidence === "not_found"
                          ? "Search note: "
                          : "Note: "}
                    </span>
                    {answer.search_notes}
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 px-6 py-3 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-300 hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Batch mode: filter bar ─────────────────────────────────────────────────

type Filters = Record<string, Set<Confidence>>;

function FilterBar({
  questions,
  filters,
  onToggle,
  onClearAll,
}: {
  questions: Question[];
  filters: Filters;
  onToggle: (questionId: string, confidence: Confidence) => void;
  onClearAll: () => void;
}) {
  const hasAny = Object.values(filters).some((s) => s.size > 0);
  const levels: Confidence[] = ["found", "inferred", "not_found"];

  return (
    <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Filter by confidence
        </p>
        {hasAny && (
          <button
            type="button"
            onClick={onClearAll}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            Clear all
          </button>
        )}
      </div>
      <div className="space-y-2">
        {questions.map((q) => {
          const active = filters[q.id] ?? new Set();
          return (
            <div key={q.id} className="flex items-center gap-2">
              <span className="flex-1 truncate text-xs text-gray-600">
                {truncate(q.text, 40)}
              </span>
              <div className="flex gap-1.5 shrink-0">
                {levels.map((level) => {
                  const on = active.has(level);
                  return (
                    <button
                      key={level}
                      type="button"
                      onClick={() => onToggle(q.id, level)}
                      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium transition ${
                        on
                          ? confidenceColor[level]
                          : "border-gray-200 bg-white text-gray-400 hover:border-gray-300 hover:text-gray-600"
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          on ? confidenceDot[level] : "bg-gray-300"
                        }`}
                      />
                      {confidenceLabel[level]}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Batch mode: table view ──────────────────────────────────────────────────

function BatchView({
  applicants,
  questions,
  templateId,
}: {
  applicants: BatchExtractionResponse["applicants"];
  questions: Question[];
  templateId?: string | null;
}) {
  const [selectedQuestionId, setSelectedQuestionId] = useState<string | null>(
    questions.length > 0 ? questions[0].id : null,
  );
  const [viewMode, setViewMode] = useState<"by-question" | "table" | "by-bucket">(
    "by-question",
  );
  const [selectedConfidences, setSelectedConfidences] = useState<Set<Confidence>>(
    new Set<Confidence>(["found", "inferred", "not_found"]),
  );
  // Table view state
  const [expandedCell, setExpandedCell] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<SortColumn>(null);
  const [sortDir, setSortDir] = useState<SortDirection>("none");

  const selectedQuestion = selectedQuestionId
    ? questions.find((q) => q.id === selectedQuestionId)
    : null;

  const labels = getWorkflowLabels(templateId);

  // Compute counts per question
  const counts = useMemo(() => {
    return questions.map((q) => {
      let found = 0;
      let inferred = 0;
      let notFound = 0;
      for (const ap of applicants) {
        const a = ap.answers.find((ans) => ans.question_id === q.id);
        if (!a || a.confidence === "not_found") notFound++;
        else if (a.confidence === "found") found++;
        else inferred++;
      }
      return { questionId: q.id, found, inferred, notFound };
    });
  }, [applicants, questions]);

  // Filter applicants by selected confidences on current question
  const filteredApplicants = useMemo(() => {
    if (!selectedQuestion) return applicants;
    return applicants.filter((ap) => {
      const a = ap.answers.find((ans) => ans.question_id === selectedQuestion.id);
      const conf = a ? a.confidence : "not_found";
      return selectedConfidences.has(conf);
    });
  }, [applicants, selectedQuestion, selectedConfidences]);

  // Sort logic for table view
  const processedApplicants = useMemo(() => {
    let list = [...applicants];
    if (sortCol && sortDir !== "none") {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortCol === "_name") {
        list.sort((a, b) =>
          dir * a.applicant_name.localeCompare(b.applicant_name),
        );
      } else {
        list.sort((a, b) => {
          const aAns = a.answers.find((ans) => ans.question_id === sortCol);
          const bAns = b.answers.find((ans) => ans.question_id === sortCol);
          const aOrd = CONFIDENCE_ORDER[aAns?.confidence ?? "not_found"];
          const bOrd = CONFIDENCE_ORDER[bAns?.confidence ?? "not_found"];
          return dir * (aOrd - bOrd);
        });
      }
    }
    return list;
  }, [applicants, sortCol, sortDir]);

  const handleSort = useCallback((columnId: string) => {
    setSortCol((prev) => {
      if (prev === columnId) {
        if (sortDir === "asc") setSortDir("desc");
        else if (sortDir === "desc") {
          setSortDir("none");
          return null;
        }
      } else {
        setSortCol(columnId);
        setSortDir("asc");
      }
      return prev === columnId ? prev : columnId;
    });
  }, [sortDir]);

  const toggleConfidence = (conf: Confidence) => {
    setSelectedConfidences((prev) => {
      const next = new Set(prev);
      if (next.has(conf)) next.delete(conf);
      else next.add(conf);
      return next;
    });
  };

  const SortIcon = ({ columnId }: { columnId: string }) => {
    if (sortCol !== columnId || sortDir === "none")
      return <ArrowUpDown className="h-3 w-3 text-gray-400" />;
    if (sortDir === "asc") return <ArrowUp className="h-3 w-3 text-blue-600" />;
    return <ArrowDown className="h-3 w-3 text-blue-600" />;
  };

  if (viewMode === "by-bucket") {
    // Group applicants by their assigned bucket, ordered Complete → Major gaps.
    const groups = new Map<
      BucketId,
      { bucket: Bucket; members: typeof applicants; assignments: ReturnType<typeof assignBucket>[] }
    >();
    for (const ap of applicants) {
      const a = assignBucket(ap.answers);
      const existing = groups.get(a.bucket.id);
      if (existing) {
        existing.members.push(ap);
        existing.assignments.push(a);
      } else {
        groups.set(a.bucket.id, {
          bucket: a.bucket,
          members: [ap],
          assignments: [a],
        });
      }
    }
    const ordered = Array.from(groups.values()).sort(
      (a, b) => a.bucket.order - b.bucket.order,
    );

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => setViewMode("by-question")}
            className="text-xs font-medium text-blue-600 hover:text-blue-700"
          >
            ← Back to question view
          </button>
          <p className="text-[11px] text-gray-500">
            {applicants.length} {labels.unitPlural} across {ordered.length}{" "}
            bucket{ordered.length !== 1 ? "s" : ""}
          </p>
        </div>

        <div className="space-y-4">
          {ordered.map(({ bucket, members, assignments }) => (
            <section
              key={bucket.id}
              className="rounded-lg border border-gray-200 bg-white overflow-hidden"
            >
              <header
                className={`flex items-center justify-between px-4 py-2.5 ${bucket.colorClasses}`}
              >
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${bucket.dotClasses}`} />
                  <span className="text-sm font-semibold">{bucket.label}</span>
                  <span className="text-xs opacity-80">·</span>
                  <span className="text-xs">
                    {members.length} {labels.unitPlural}
                  </span>
                </div>
                <p className="hidden sm:block text-[11px] opacity-80">
                  {bucket.description}
                </p>
              </header>
              <ul className="divide-y divide-gray-100">
                {members.map((ap, i) => {
                  const assignment = assignments[i];
                  return (
                    <li
                      key={ap.applicant_id}
                      className="flex items-start justify-between gap-3 px-4 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-900">
                          {ap.applicant_name || "Unnamed"}
                        </p>
                        <p className="mt-0.5 text-xs text-gray-600">
                          {assignment.justification}
                        </p>
                        {ap.error && (
                          <p className="mt-1 text-[11px] font-mono text-red-700">
                            {ap.error}
                          </p>
                        )}
                      </div>
                      {/* Mini confidence breakdown bar */}
                      <div className="shrink-0 flex items-center gap-1.5 text-[10px] text-gray-600">
                        <span className="inline-flex items-center gap-1">
                          <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.found}`} />
                          <span className="font-medium text-emerald-700">
                            {assignment.counts.found}
                          </span>
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.inferred}`} />
                          <span className="font-medium text-amber-700">
                            {assignment.counts.inferred}
                          </span>
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.not_found}`} />
                          <span className="font-medium text-gray-500">
                            {assignment.counts.notFound}
                          </span>
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      </div>
    );
  }

  if (viewMode === "table") {
    return (
      <div className="space-y-3">
        {/* Toolbar: back link + density hint */}
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              setExpandedCell(null);
              setViewMode("by-question");
            }}
            className="text-xs font-medium text-blue-600 hover:text-blue-700"
          >
            ← Back to question view
          </button>
          <p className="text-[11px] text-gray-500">
            Click any cell to expand · {applicants.length} {labels.unitPlural} × {questions.length} questions
          </p>
        </div>
        {/* Old table view  */}
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="sticky left-0 z-10 bg-gray-50 px-4 py-3 text-left min-w-[180px]">
                  <button
                    type="button"
                    onClick={() => handleSort("_name")}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-700"
                  >
                    {labels.unitSingularCapital}
                    <SortIcon columnId="_name" />
                  </button>
                </th>
                {questions.map((q) => (
                  <th
                    key={q.id}
                    title={q.text}
                    className="px-3 py-3 text-left min-w-[140px] max-w-[170px]"
                  >
                    <button
                      type="button"
                      onClick={() => handleSort(q.id)}
                      className="inline-flex w-full items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-700"
                    >
                      <span className="truncate" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", whiteSpace: "normal" }}>
                        {q.text}
                      </span>
                      <SortIcon columnId={q.id} />
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {processedApplicants.map((ap) => {
                const answerMap = new Map(
                  ap.answers.map((a) => [a.question_id, a]),
                );
                return (
                  <tr key={ap.applicant_id} className="hover:bg-gray-50/30">
                    <td className="sticky left-0 z-10 bg-white px-4 py-2.5 font-medium text-gray-900 border-r border-gray-100 align-top">
                      <div className="space-y-1">
                        <p>{ap.applicant_name || "Unnamed"}</p>
                        <BucketBadge
                          bucket={assignBucket(ap.answers).bucket}
                          justification={assignBucket(ap.answers).justification}
                          size="sm"
                        />
                      </div>
                    </td>
                    {questions.map((q) => {
                      const a = answerMap.get(q.id);
                      const cellId = `${ap.applicant_id}:${q.id}`;
                      const isExpanded = expandedCell === cellId;
                      if (!a) {
                        return (
                          <td
                            key={q.id}
                            className="px-3 py-2.5 text-gray-300 italic text-xs align-top"
                          >
                            —
                          </td>
                        );
                      }
                      return (
                        <td
                          key={q.id}
                          onClick={() =>
                            setExpandedCell(isExpanded ? null : cellId)
                          }
                          className={`px-3 py-2 align-top cursor-pointer transition ${
                            isExpanded
                              ? "bg-blue-50/60"
                              : "hover:bg-blue-50/30"
                          }`}
                          aria-expanded={isExpanded}
                        >
                          {isExpanded ? (
                            <ExpandedAnswerCell
                              answer={a}
                              onClose={() => setExpandedCell(null)}
                            />
                          ) : (
                            <CompactAnswerCell answer={a} />
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // By-question view (default)
  return (
    <div className="flex gap-6">
      {/* Left sidebar: questions */}
      <div className="w-80 shrink-0 bg-gray-50 rounded-lg border border-gray-200 p-4 max-h-[70vh] overflow-y-auto">
        <h3 className="text-sm font-semibold text-gray-900 mb-1">
          {labels.sidebarHeader}
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          Across {applicants.length} {labels.unitPlural}
        </p>
        <div className="space-y-1">
          {questions.map((q) => {
            const isSelected = q.id === selectedQuestionId;
            const c = counts.find((c) => c.questionId === q.id);
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => setSelectedQuestionId(q.id)}
                className={`w-full text-left rounded-md px-3 py-2.5 text-xs transition ${
                  isSelected
                    ? "bg-blue-50 border-l-4 border-blue-600 text-gray-900"
                    : "hover:bg-gray-100 text-gray-700"
                }`}
              >
                <p className="font-medium leading-snug mb-1">{q.text}</p>
                {c && (
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="inline-flex items-center gap-1">
                      <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.found}`} />
                      <span className="font-medium text-emerald-700">{c.found}</span>
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.inferred}`} />
                      <span className="font-medium text-amber-700">{c.inferred}</span>
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.not_found}`} />
                      <span className="font-medium text-gray-500">{c.notFound}</span>
                    </span>
                  </div>
                )}
              </button>
            );
          })}
        </div>
        <div className="mt-6 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setViewMode("by-bucket")}
            className="py-2 text-xs text-blue-600 hover:text-blue-700 font-medium text-center hover:bg-blue-50 rounded-md transition border border-gray-200 bg-white"
          >
            Group by bucket
          </button>
          <button
            type="button"
            onClick={() => setViewMode("table")}
            className="py-2 text-xs text-blue-600 hover:text-blue-700 font-medium text-center hover:bg-blue-50 rounded-md transition border border-gray-200 bg-white"
          >
            Table view
          </button>
        </div>
      </div>

      {/* Right panel: applicant cards for selected question */}
      <div className="flex-1 max-h-[70vh] overflow-y-auto">
        {selectedQuestion && (
          <div className="space-y-3">
            <div className="sticky top-0 bg-white pt-px pb-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900 leading-snug">
                {selectedQuestion.text}
              </h2>
              {(() => {
                const c = counts.find((c) => c.questionId === selectedQuestion.id);
                return c ? (
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <span className="inline-flex items-center gap-1">
                      <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.found}`} />
                      <span className="text-emerald-700">{c.found} found</span>
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.inferred}`} />
                      <span className="text-amber-700">{c.inferred} inferred</span>
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.not_found}`} />
                      <span className="text-gray-500">{c.notFound} not found</span>
                    </span>
                  </div>
                ) : null;
              })()}
            </div>

            {/* Filter chips */}
            <div className="flex gap-1.5">
              {(["found", "inferred", "not_found"] as Confidence[]).map((conf) => {
                const on = selectedConfidences.has(conf);
                return (
                  <button
                    key={conf}
                    type="button"
                    onClick={() => toggleConfidence(conf)}
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                      on
                        ? confidenceColor[conf]
                        : "border-gray-200 bg-white text-gray-400 hover:border-gray-300 hover:text-gray-600"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        on ? confidenceDot[conf] : "bg-gray-300"
                      }`}
                    />
                    {confidenceLabel[conf]}
                  </button>
                );
              })}
            </div>
            {selectedConfidences.size < 3 && (
              <p className="text-xs text-gray-500">
                Showing {filteredApplicants.length} of {applicants.length}
              </p>
            )}

            {/* Applicant cards */}
            <div className="space-y-3 pr-4">
              {filteredApplicants.length === 0 ? (
                <p className="text-sm text-gray-400 italic py-8 text-center">
                  No {labels.unitPlural} match the selected filters.
                </p>
              ) : (
                filteredApplicants.map((ap) => {
                  const answer = ap.answers.find(
                    (a) => a.question_id === selectedQuestion.id,
                  );
                  const assignment = assignBucket(ap.answers);
                  return (
                    <div
                      key={ap.applicant_id}
                      className="border-b border-gray-100 pb-6 last:border-0 last:pb-0"
                    >
                      <div className="flex items-start justify-between gap-3 mb-1">
                        <div className="min-w-0 flex-1">
                          <p className="text-base font-semibold text-gray-900">
                            {ap.applicant_name || "Unnamed"}
                          </p>
                          <div className="mt-1 flex items-center gap-2">
                            <BucketBadge
                              bucket={assignment.bucket}
                              justification={assignment.justification}
                              size="sm"
                            />
                            <span className="text-[10px] text-gray-500">
                              {assignment.justification}
                            </span>
                          </div>
                        </div>
                        {answer && <ConfidenceBadge confidence={answer.confidence} />}
                      </div>
                      {answer?.answer ? (
                        <div className="mb-2">
                          <AnswerText
                            text={answer.answer}
                            className="text-sm text-gray-800 leading-relaxed"
                          />
                        </div>
                      ) : (
                        <p className="text-sm italic text-gray-400 mb-2">
                          Not found in any document
                        </p>
                      )}
                      {answer?.source_document && (
                        <p className="flex items-center gap-1.5 text-xs text-gray-500 mb-2">
                          <ExternalLink className="h-3 w-3 shrink-0" />
                          {answer.source_document}
                          {answer.source_page != null && ` · p.${answer.source_page}`}
                        </p>
                      )}
                      {answer?.quote && (
                        <details className="group">
                          <summary className="cursor-pointer text-xs font-medium text-blue-600 hover:text-blue-700">
                            View exact quote
                          </summary>
                          <div className="mt-2 rounded-md bg-gray-50 border border-gray-100 px-3 py-2">
                            <p className="text-xs font-mono text-gray-600 leading-relaxed whitespace-pre-wrap">
                              {answer.quote}
                            </p>
                          </div>
                        </details>
                      )}
                      {answer?.search_notes && (
                        <p className="text-xs italic text-gray-600 mt-2">
                          <span className="font-medium">
                            {answer.confidence === "inferred"
                              ? "Reasoning: "
                              : "Search note: "}
                          </span>
                          {answer.search_notes}
                        </p>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Table view toggle */}
            <button
              type="button"
              onClick={() => setViewMode("table")}
              className="sticky bottom-0 mt-6 py-2 px-3 text-xs text-blue-600 hover:text-blue-700 font-medium bg-white rounded-md transition hover:bg-blue-50 border border-gray-200"
            >
              Show table view
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Follow-up notes panel ──────────────────────────────────────────────────

function FollowupPanel({
  drafts,
  originalDrafts,
  onUpdate,
  onReset,
  onClose,
}: {
  drafts: { applicant_id: string; applicant_name: string; note: string }[];
  originalDrafts: FollowupDraft[];
  onUpdate: (applicantId: string, note: string) => void;
  onReset: (applicantId: string) => void;
  onClose: () => void;
}) {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyToClipboard = async (text: string, applicantId: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedId(applicantId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-4 rounded-lg border border-blue-200 bg-blue-50/30 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">
            Follow-up notes
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            Review and edit each note before sending. These are drafts &mdash;
            add a greeting, signature, and any personal context before use.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 text-sm text-gray-500 hover:text-gray-700"
        >
          Close
        </button>
      </div>

      {drafts.map((d) => {
        const original = originalDrafts.find(
          (o) => o.applicant_id === d.applicant_id,
        );
        const isModified = original ? d.note !== original.note : false;

        return (
          <div
            key={d.applicant_id}
            className="rounded-lg border border-gray-200 bg-white p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-900">
                {d.applicant_name}
              </p>
              <div className="flex items-center gap-2">
                {isModified && (
                  <button
                    type="button"
                    onClick={() => onReset(d.applicant_id)}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-500 transition hover:bg-gray-100 hover:text-gray-700"
                    title="Reset to original draft"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Reset
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => copyToClipboard(d.note, d.applicant_id)}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-500 transition hover:bg-gray-100 hover:text-gray-700"
                >
                  {copiedId === d.applicant_id ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-500" />
                      <span className="text-emerald-600">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      Copy
                    </>
                  )}
                </button>
              </div>
            </div>
            <textarea
              value={d.note}
              onChange={(e) => onUpdate(d.applicant_id, e.target.value)}
              rows={4}
              className="w-full resize-y rounded-md border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 leading-relaxed focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        );
      })}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => exportFollowupsAsText(drafts)}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700"
        >
          <FileText className="h-4 w-4" />
          Download all as text file
        </button>
      </div>
    </div>
  );
}

// ── Shared: confidence badge ────────────────────────────────────────────────

function ConfidenceBadge({ confidence }: { confidence: ExtractionAnswer["confidence"] }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-medium ${confidenceColor[confidence]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot[confidence]}`} />
      {confidenceLabel[confidence]}
    </span>
  );
}
