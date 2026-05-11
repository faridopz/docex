"use client";

import { useState } from "react";
import type {
  SingleExtractionResponse,
  BatchExtractionResponse,
  ExtractionAnswer,
  Question,
} from "@/types";
import {
  confidenceLabel,
  confidenceColor,
  confidenceDot,
} from "@/types";
import { GuidanceCard } from "./GuidanceCard";
import { Download, FileSpreadsheet, FileJson, ExternalLink } from "lucide-react";
import { exportToExcel, exportJson } from "@/lib/api";

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

  return (
    <section className="space-y-6">
      {/* Summary */}
      <GuidanceCard title="Your results are ready">
        {batch
          ? `Screened ${result.total} applicants — ${result.succeeded} succeeded, ${result.failed} failed.`
          : `Screened ${result.applicant_name} — ${result.documents.length} document${result.documents.length !== 1 ? "s" : ""} read.`}
      </GuidanceCard>

      {/* Export buttons */}
      <div className="flex justify-end gap-3">
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
      </div>

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

  const toggleCell = (key: string) => {
    setExpandedCell((prev) => (prev === key ? null : key));
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th className="sticky left-0 z-10 bg-gray-50 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 min-w-[180px]">
              Applicant
            </th>
            {questions.map((q) => (
              <th
                key={q.id}
                title={q.text}
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 min-w-[200px]"
              >
                {truncate(q.text, 30)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {applicants.map((ap) => {
            const answerMap = new Map(ap.answers.map((a) => [a.question_id, a]));

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
                      <td key={q.id} className="px-4 py-3 text-gray-400 italic text-xs">
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
                            {a.answer
                              ? truncate(a.answer, 80)
                              : <span className="italic text-gray-400">Not found</span>}
                          </span>
                        </div>
                      </button>

                      {isExpanded && a.answer && (
                        <div className="mt-2 space-y-2 rounded-md border border-gray-100 bg-gray-50 p-3">
                          <ConfidenceBadge confidence={a.confidence} />
                          <p className="text-sm text-gray-700">{a.answer}</p>
                          {a.source_document && (
                            <p className="flex items-center gap-1.5 text-xs text-gray-500">
                              <ExternalLink className="h-3 w-3 shrink-0" />
                              {a.source_document}
                              {a.source_page != null && ` · p.${a.source_page}`}
                            </p>
                          )}
                          {a.quote && (
                            <div className="rounded-md bg-white border border-gray-100 px-3 py-2">
                              <p className="text-xs font-mono text-gray-600 leading-relaxed whitespace-pre-wrap">
                                {a.quote}
                              </p>
                            </div>
                          )}
                        </div>
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
