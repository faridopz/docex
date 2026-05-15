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

function getWorkflowLabels(templateId: string | null | undefined) {
  if (templateId === "quarterly-report-review") {
    return {
      unitSingular: "report",
      unitPlural: "reports",
      actionVerb: "Analyse",
      actionVerbPast: "Analysed",
      pageHeader: "Report analysis",
      stepTwoButton: "Analyse reports",
      stepThreeLoadingTitle: "Reading reports...",
    };
  }
  if (templateId === "subaward-application-review") {
    return {
      unitSingular: "application",
      unitPlural: "applications",
      actionVerb: "Review",
      actionVerbPast: "Reviewed",
      pageHeader: "Application review",
      stepTwoButton: "Review applications",
      stepThreeLoadingTitle: "Reading applications...",
    };
  }
  return {
    unitSingular: "applicant",
    unitPlural: "applicants",
    actionVerb: "Run",
    actionVerbPast: "Reviewed",
    pageHeader: "Review results",
    stepTwoButton: "Run review",
    stepThreeLoadingTitle: "Reading documents...",
  };
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
      const drafts = await draftFollowups(applicants, questions);
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

  return (
    <section className="space-y-6">
      {/* Summary */}
      <GuidanceCard title="Your results are ready">
        {batch
          ? `${labels.actionVerbPast} ${applicants.length} ${applicants.length === 1 ? labels.unitSingular : labels.unitPlural}${errorCount > 0 ? ` · ${errorCount} error${errorCount !== 1 ? "s" : ""}` : ""}.`
          : `${labels.actionVerbPast} ${result.applicant_name} — ${result.documents.length} document${result.documents.length !== 1 ? "s" : ""} read.`}
      </GuidanceCard>

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
        <BatchView applicants={applicants} questions={questions} />
      )}
    </section>
  );
}

// ── Single mode: two-column answer list ─────────────────────────────────────

function SingleView({ answers }: { answers: ExtractionAnswer[] }) {
  return (
    <div className="space-y-4">
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

      {/* Answer */}
      {answer.answer ? (
        <p className="text-sm text-gray-700 leading-relaxed">{answer.answer}</p>
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
  const [viewMode, setViewMode] = useState<"by-question" | "table">("by-question");
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

  if (viewMode === "table") {
    return (
      <div className="space-y-4">
        {/* Table toggle back */}
        <button
          type="button"
          onClick={() => setViewMode("by-question")}
          className="text-xs text-blue-600 hover:text-blue-700 font-medium"
        >
          ← Back to question view
        </button>
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
                    Applicant
                    <SortIcon columnId="_name" />
                  </button>
                </th>
                {questions.map((q) => (
                  <th
                    key={q.id}
                    title={q.text}
                    className="px-4 py-3 text-left min-w-[180px] max-w-[220px]"
                  >
                    <button
                      type="button"
                      onClick={() => handleSort(q.id)}
                      className="inline-flex w-full items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-700"
                    >
                      <span className="truncate">{q.text}</span>
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
                  <tr key={ap.applicant_id} className="hover:bg-gray-50/50">
                    <td className="sticky left-0 z-10 bg-white px-4 py-3 font-medium text-gray-900 border-r border-gray-100">
                      {ap.applicant_name || "Unnamed"}
                    </td>
                    {questions.map((q) => {
                      const a = answerMap.get(q.id);
                      if (!a)
                        return (
                          <td key={q.id} className="px-4 py-3 text-gray-400 italic text-xs">
                            —
                          </td>
                        );
                      return (
                        <td key={q.id} className="px-4 py-3 text-sm text-gray-700">
                          <div className="flex items-center gap-1.5">
                            <span className={`h-2 w-2 rounded-full ${confidenceDot[a.confidence]}`} />
                            <span>{a.answer ?? "Not found"}</span>
                          </div>
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
          {labels.unitPlural === "applications"
            ? "Applications"
            : labels.unitPlural === "reports"
              ? "Reports"
              : "Applicants"}
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
        <button
          type="button"
          onClick={() => setViewMode("table")}
          className="mt-6 w-full py-2 text-xs text-blue-600 hover:text-blue-700 font-medium text-center hover:bg-blue-50 rounded-md transition"
        >
          Show table view
        </button>
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
                  return (
                    <div
                      key={ap.applicant_id}
                      className="border-b border-gray-100 pb-6 last:border-0 last:pb-0"
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <p className="text-base font-semibold text-gray-900">
                          {ap.applicant_name || "Unnamed"}
                        </p>
                        {answer && <ConfidenceBadge confidence={answer.confidence} />}
                      </div>
                      {answer?.answer ? (
                        <p className="text-sm text-gray-800 leading-relaxed mb-2">
                          {answer.answer}
                        </p>
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
