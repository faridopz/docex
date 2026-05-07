"use client";

import { Lightbulb, Plus, X } from "lucide-react";
import type { Question } from "@/types";

/**
 * QuestionBuilder
 *
 * Step 1 of the DOCex flow. Two stacked sections:
 *
 *   1. (Optional) Context — a short paragraph from the funder describing
 *      what they're looking for. Flows into screener.py as a prompt block
 *      so Claude interprets ambiguous answers correctly. NEVER used to
 *      rank or score applicants.
 *
 *   2. Questions — the list of plain-English questions the user wants
 *      answered for every applicant. Capped at 20.
 *
 * Each section has a short guidance card explaining what it's for and
 * how to get good results. Designed for a grants officer working under
 * deadline — clear, fast, no jargon.
 */

const SUGGESTED_QUESTIONS = [
  "Is this organisation registered with CAC?",
  "What states does this organisation work in?",
  "Has this organisation been audited in the last 2 years?",
  "What is the total budget requested?",
  "Does the organisation have an anti-fraud policy?",
  "Has this organisation managed donor funds before?",
  "How many full-time staff does the organisation have?",
  "What is the organisation's main focus area?",
] as const;

const MAX_QUESTIONS = 20;
const MAX_CONTEXT_CHARS = 800;

const CONTEXT_PLACEHOLDER =
  "Example: We fund partners working on TB and HIV in northern Nigeria. " +
  "Partners must be registered with CAC, audited within the last 2 years, " +
  "and have managed at least one donor-funded project.";

interface QuestionBuilderProps {
  questions: Question[];
  onChange: (questions: Question[]) => void;
  // Optional. When provided, a context textarea is rendered above the
  // questions and the value flows into screener.py at extraction time.
  context?: string;
  onContextChange?: (context: string) => void;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `q_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export function QuestionBuilder({
  questions,
  onChange,
  context,
  onContextChange,
}: QuestionBuilderProps) {
  const atLimit = questions.length >= MAX_QUESTIONS;

  // Hide chips that are already in the list — keeps the chip row tidy
  const usedTexts = new Set(questions.map((q) => q.text.trim().toLowerCase()));
  const remainingSuggestions = SUGGESTED_QUESTIONS.filter(
    (s) => !usedTexts.has(s.toLowerCase())
  );

  const updateQuestion = (id: string, text: string) => {
    onChange(questions.map((q) => (q.id === id ? { ...q, text } : q)));
  };

  const removeQuestion = (id: string) => {
    onChange(questions.filter((q) => q.id !== id));
  };

  const addQuestion = (text = "") => {
    if (atLimit) return;
    onChange([...questions, { id: newId(), text }]);
  };

  return (
    <section className="space-y-10">
      {onContextChange && (
        <ContextSection
          context={context ?? ""}
          onChange={onContextChange}
        />
      )}

      <div className="space-y-6">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">
              What do you want to know?
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Add the questions DOCex should answer for every applicant.
            </p>
          </div>
          <span
            className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${
              atLimit
                ? "bg-amber-50 text-amber-700"
                : "bg-gray-100 text-gray-600"
            }`}
          >
            {questions.length}/{MAX_QUESTIONS}
          </span>
        </header>

        <GuidanceCard title="How to write good questions">
          Specific questions get sharper answers.{" "}
          <span className="text-gray-900">
            “What is the total budget requested?”
          </span>{" "}
          beats{" "}
          <span className="text-gray-500">“tell me about their money.”</span>{" "}
          DOCex returns the answer, the source document, and the exact quote —
          so you can verify each answer in seconds.
        </GuidanceCard>

        {remainingSuggestions.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Common questions — click to add
            </p>
            <div className="flex flex-wrap gap-2">
              {remainingSuggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => addQuestion(s)}
                  disabled={atLimit}
                  className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 transition hover:border-blue-600 hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  + {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-2">
          {questions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center">
              <p className="text-sm text-gray-500">
                No questions yet. Click a suggestion above or add your own
                below.
              </p>
            </div>
          ) : (
            questions.map((q, index) => (
              <QuestionRow
                key={q.id}
                index={index}
                question={q}
                onChange={(text) => updateQuestion(q.id, text)}
                onRemove={() => removeQuestion(q.id)}
                onEnter={() => addQuestion("")}
              />
            ))
          )}
        </div>

        <button
          type="button"
          onClick={() => addQuestion("")}
          disabled={atLimit}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          {atLimit ? "Maximum 20 questions" : "Add question"}
        </button>
      </div>
    </section>
  );
}

// ── Context section ─────────────────────────────────────────────────────────

function ContextSection({
  context,
  onChange,
}: {
  context: string;
  onChange: (next: string) => void;
}) {
  const overLimit = context.length > MAX_CONTEXT_CHARS;

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">
            Tell DOCex what you’re looking for
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            Optional — a short paragraph that helps DOCex understand answers
            in your context.
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${
            overLimit
              ? "bg-amber-50 text-amber-700"
              : "bg-gray-100 text-gray-600"
          }`}
        >
          {context.length}/{MAX_CONTEXT_CHARS}
        </span>
      </header>

      <GuidanceCard title="What to write here">
        Two to four sentences about the funder’s priorities — focus areas,
        regions, baseline requirements. DOCex still extracts the same answers;
        it just understands them in your context.{" "}
        <span className="text-gray-900">
          It does not score, rank, or judge applicants.
        </span>
      </GuidanceCard>

      <textarea
        value={context}
        onChange={(e) => onChange(e.target.value)}
        placeholder={CONTEXT_PLACEHOLDER}
        rows={4}
        className="w-full resize-y rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
      />
    </div>
  );
}

// ── Guidance card (shared visual) ───────────────────────────────────────────

function GuidanceCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-blue-100 bg-blue-50/60 px-4 py-3">
      <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
      <div className="space-y-1 text-sm text-gray-700">
        <p className="font-medium text-gray-900">{title}</p>
        <p className="leading-relaxed">{children}</p>
      </div>
    </div>
  );
}

// ── Question row ────────────────────────────────────────────────────────────

interface QuestionRowProps {
  index: number;
  question: Question;
  onChange: (text: string) => void;
  onRemove: () => void;
  onEnter: () => void;
}

function QuestionRow({
  index,
  question,
  onChange,
  onRemove,
  onEnter,
}: QuestionRowProps) {
  const isEmpty = question.text.trim().length === 0;

  return (
    <div
      className={`group flex items-start gap-3 rounded-lg border bg-white p-3 transition ${
        isEmpty
          ? "border-amber-200 bg-amber-50/40"
          : "border-gray-200 hover:border-gray-300"
      }`}
    >
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-600">
        {index + 1}
      </span>
      <input
        type="text"
        value={question.text}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            // Enter on a non-empty question adds a new empty one — fast entry
            if (!isEmpty) onEnter();
          }
        }}
        placeholder="Type your question..."
        // autoFocus only fires on mount, so newly-added empty rows get focus
        // without stealing focus from rows already on screen.
        autoFocus={isEmpty}
        className="flex-1 border-0 bg-transparent text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0"
      />
      <button
        type="button"
        onClick={onRemove}
        className="shrink-0 rounded-md p-1 text-gray-400 transition hover:bg-red-50 hover:text-red-600"
        aria-label={`Remove question ${index + 1}`}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
