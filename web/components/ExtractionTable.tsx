"use client";

import { useRef, useState, useMemo, useCallback } from "react";
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
}

// ── Type guards ─────────────────────────────────────────────────────────────

function isBatch(
  result: SingleExtractionResponse | BatchExtractionResponse,
): result is BatchExtractionResponse {
  return "applicants" in result;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

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
}: ExtractionTableProps) {
  const batch = isBatch(result);
  const applicants = batch ? result.applicants : singleToApplicantArray(result);

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
          ? `Screened ${result.total} applicants — ${result.succeeded} succeeded, ${result.failed} failed.`
          : `Screened ${result.applicant_name} — ${result.documents.length} document${result.documents.length !== 1 ? "s" : ""} read.`}
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
        <FollowupPanel
          drafts={editedDrafts}
          originalDrafts={originalDrafts}
          onUpdate={updateDraftNote}
          onReset={resetDraft}
          onClose={() => setFollowupState("idle")}
        />
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
      <div className="space-y-1.5">
        {stats.map((s) => (
          <button
            key={s.question.id}
            type="button"
            onClick={() => onQuestionClick(s.question.id)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs text-gray-600 transition hover:bg-gray-50"
          >
            <span className="flex-1 truncate text-gray-700">
              {truncate(s.question.text, 50)}
            </span>
            <span className="inline-flex items-center gap-1 shrink-0">
              <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.found}`} />
              <span className="tabular-nums">{s.found}</span>
            </span>
            <span className="inline-flex items-center gap-1 shrink-0">
              <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.inferred}`} />
              <span className="tabular-nums">{s.inferred}</span>
            </span>
            <span className="inline-flex items-center gap-1 shrink-0">
              <span className={`h-1.5 w-1.5 rounded-full ${confidenceDot.not_found}`} />
              <span className="tabular-nums">{s.notFound}</span>
            </span>
          </button>
        ))}
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
}: {
  applicants: BatchExtractionResponse["applicants"];
  questions: Question[];
}) {
  const [expandedCell, setExpandedCell] = useState<string | null>(null);
  const [compact, setCompact] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<Filters>({});
  const [sortCol, setSortCol] = useState<SortColumn>(null);
  const [sortDir, setSortDir] = useState<SortDirection>("none");
  const tableRef = useRef<HTMLDivElement>(null);
  const colRefs = useRef<Record<string, HTMLTableCellElement | null>>({});

  const toggleCell = (key: string) => {
    if (compact) {
      setExpandedCell((prev) => (prev === key ? null : key));
    } else {
      setExpandedCell((prev) => (prev === key ? null : key));
    }
  };

  // ── Sort handler ──────────────────────────────────────────────────────
  const handleSort = useCallback(
    (columnId: string) => {
      if (sortCol === columnId) {
        // Cycle: asc -> desc -> none
        if (sortDir === "asc") setSortDir("desc");
        else if (sortDir === "desc") {
          setSortDir("none");
          setSortCol(null);
        }
      } else {
        setSortCol(columnId);
        setSortDir("asc");
      }
    },
    [sortCol, sortDir],
  );

  // ── Filter handler ────────────────────────────────────────────────────
  const toggleFilter = useCallback(
    (questionId: string, confidence: Confidence) => {
      setFilters((prev) => {
        const next = { ...prev };
        const set = new Set(next[questionId] ?? []);
        if (set.has(confidence)) set.delete(confidence);
        else set.add(confidence);
        next[questionId] = set;
        return next;
      });
    },
    [],
  );

  const clearAllFilters = useCallback(() => setFilters({}), []);

  const hasActiveFilters = Object.values(filters).some((s) => s.size > 0);

  // ── Compute filtered + sorted applicants ──────────────────────────────
  const processedApplicants = useMemo(() => {
    let list = [...applicants];

    // Apply filters (AND across questions)
    if (hasActiveFilters) {
      list = list.filter((ap) => {
        const answerMap = new Map(
          ap.answers.map((a) => [a.question_id, a]),
        );
        for (const [qId, required] of Object.entries(filters)) {
          if (required.size === 0) continue;
          const a = answerMap.get(qId);
          const confidence: Confidence = a ? a.confidence : "not_found";
          if (!required.has(confidence)) return false;
        }
        return true;
      });
    }

    // Apply sort
    if (sortCol && sortDir !== "none") {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortCol === "_name") {
        list.sort(
          (a, b) =>
            dir * a.applicant_name.localeCompare(b.applicant_name),
        );
      } else {
        list.sort((a, b) => {
          const aAnswer = a.answers.find(
            (ans) => ans.question_id === sortCol,
          );
          const bAnswer = b.answers.find(
            (ans) => ans.question_id === sortCol,
          );
          const aOrder =
            CONFIDENCE_ORDER[aAnswer?.confidence ?? "not_found"];
          const bOrder =
            CONFIDENCE_ORDER[bAnswer?.confidence ?? "not_found"];
          return dir * (aOrder - bOrder);
        });
      }
    }

    return list;
  }, [applicants, filters, hasActiveFilters, sortCol, sortDir]);

  // ── Scroll to column when stats row is clicked ────────────────────────
  const scrollToColumn = useCallback((questionId: string) => {
    const th = colRefs.current[questionId];
    if (th && tableRef.current) {
      th.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
    }
  }, []);

  // ── Sort icon helper ──────────────────────────────────────────────────
  const SortIcon = ({ columnId }: { columnId: string }) => {
    if (sortCol !== columnId || sortDir === "none")
      return <ArrowUpDown className="h-3 w-3 text-gray-400" />;
    if (sortDir === "asc")
      return <ArrowUp className="h-3 w-3 text-blue-600" />;
    return <ArrowDown className="h-3 w-3 text-blue-600" />;
  };

  return (
    <div className="space-y-4">
      {/* Aggregate stats */}
      <AggregateStats
        applicants={applicants}
        questions={questions}
        onQuestionClick={scrollToColumn}
      />

      {/* Toolbar: filter toggle + compact toggle + count */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowFilters((p) => !p)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              showFilters || hasActiveFilters
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
            }`}
          >
            <Filter className="h-3.5 w-3.5" />
            Filter
            {hasActiveFilters && (
              <span className="ml-0.5 rounded-full bg-blue-600 px-1.5 py-px text-[10px] font-bold text-white">
                {Object.values(filters).filter((s) => s.size > 0).length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setCompact((p) => !p)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              compact
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
            }`}
          >
            <Rows3 className="h-3.5 w-3.5" />
            Compact
          </button>
        </div>
        {hasActiveFilters && (
          <p className="text-xs text-gray-500">
            Showing {processedApplicants.length} of {applicants.length} applicant{applicants.length !== 1 ? "s" : ""}
          </p>
        )}
      </div>

      {/* Filter bar */}
      {showFilters && (
        <FilterBar
          questions={questions}
          filters={filters}
          onToggle={toggleFilter}
          onClearAll={clearAllFilters}
        />
      )}

      {/* Table */}
      <div ref={tableRef} className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
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
                  ref={(el) => { colRefs.current[q.id] = el; }}
                  title={q.text}
                  className="px-4 py-3 text-left min-w-[200px]"
                >
                  <button
                    type="button"
                    onClick={() => handleSort(q.id)}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-700"
                  >
                    {truncate(q.text, 30)}
                    <SortIcon columnId={q.id} />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {processedApplicants.length === 0 ? (
              <tr>
                <td
                  colSpan={questions.length + 1}
                  className="px-4 py-8 text-center text-sm text-gray-400 italic"
                >
                  No applicants match the current filters.
                </td>
              </tr>
            ) : (
              processedApplicants.map((ap) => {
                const answerMap = new Map(
                  ap.answers.map((a) => [a.question_id, a]),
                );

                return (
                  <tr key={ap.applicant_id} className="hover:bg-gray-50/50">
                    {/* Sticky applicant name */}
                    <td className="sticky left-0 z-10 bg-white px-4 py-3 font-medium text-gray-900 border-r border-gray-100">
                      <span>{ap.applicant_name || "Unnamed"}</span>
                      {ap.error && (
                        <span className="ml-2 inline-flex items-center rounded-full bg-red-50 border border-red-200 px-2 py-0.5 text-xs text-red-700">
                          Has error
                        </span>
                      )}
                    </td>

                    {/* One cell per question */}
                    {questions.map((q) => {
                      const a = answerMap.get(q.id);
                      const cellKey = `${ap.applicant_id}:${q.id}`;
                      const isExpanded = expandedCell === cellKey;

                      if (!a) {
                        return (
                          <td
                            key={q.id}
                            className="px-4 py-3 text-gray-400 italic text-xs"
                          >
                            —
                          </td>
                        );
                      }

                      return (
                        <td key={q.id} className="px-4 py-3 align-top">
                          <button
                            type="button"
                            onClick={() => toggleCell(cellKey)}
                            className="w-full text-left"
                          >
                            <div className="flex items-start gap-2">
                              <span
                                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${confidenceDot[a.confidence]}`}
                                title={confidenceLabel[a.confidence]}
                              />
                              <span className="text-sm text-gray-700">
                                {a.answer ? (
                                  truncate(a.answer, compact ? 60 : 80)
                                ) : (
                                  <span className="italic text-gray-400">
                                    Not found
                                  </span>
                                )}
                              </span>
                            </div>
                          </button>

                          {/* Expanded detail — hidden in compact mode unless explicitly opened */}
                          {isExpanded && !compact && a.answer && (
                            <div className="mt-2 space-y-2 rounded-md border border-gray-100 bg-gray-50 p-3">
                              <ConfidenceBadge confidence={a.confidence} />
                              <p className="text-sm text-gray-700">
                                {a.answer}
                              </p>
                              {a.source_document && (
                                <p className="flex items-center gap-1.5 text-xs text-gray-500">
                                  <ExternalLink className="h-3 w-3 shrink-0" />
                                  {a.source_document}
                                  {a.source_page != null &&
                                    ` · p.${a.source_page}`}
                                </p>
                              )}
                              {a.quote && (
                                <div className="rounded-md bg-white border border-gray-100 px-3 py-2">
                                  <p className="text-xs font-mono text-gray-600 leading-relaxed whitespace-pre-wrap">
                                    {a.quote}
                                  </p>
                                </div>
                              )}
                              {a.search_notes && (
                                <p className="text-xs text-gray-500 leading-relaxed">
                                  <span className="font-medium text-gray-600">
                                    {a.confidence === "inferred"
                                      ? "Reasoning: "
                                      : a.confidence === "not_found"
                                        ? "Search note: "
                                        : "Note: "}
                                  </span>
                                  {a.search_notes}
                                </p>
                              )}
                            </div>
                          )}

                          {/* Compact expanded — just badge + source, no quote */}
                          {isExpanded && compact && (
                            <div className="mt-2 space-y-1.5 rounded-md border border-gray-100 bg-gray-50 p-2">
                              <ConfidenceBadge confidence={a.confidence} />
                              {a.source_document && (
                                <p className="flex items-center gap-1.5 text-xs text-gray-500">
                                  <ExternalLink className="h-3 w-3 shrink-0" />
                                  {a.source_document}
                                  {a.source_page != null &&
                                    ` · p.${a.source_page}`}
                                </p>
                              )}
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
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
