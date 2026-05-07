"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { QuestionBuilder } from "@/components/QuestionBuilder";
import { ApplicantUpload } from "@/components/ApplicantUpload";
import type { Question, ApplicantInput } from "@/types";

/* ─── Step bar ───────────────────────────────────────────────────────────────*/

const STEPS = [
  { n: 1, label: "Define questions" },
  { n: 2, label: "Add applicants" },
  { n: 3, label: "Review results" },
];

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center">
      {STEPS.map((step, idx) => {
        const done = step.n < current;
        const active = step.n === current;
        return (
          <React.Fragment key={step.n}>
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all",
                  done || active ? "bg-brand-600 text-white" : "bg-gray-100 text-gray-400",
                  active && "ring-4 ring-brand-100",
                )}
              >
                {done ? <CheckCircle2 className="w-4 h-4" /> : step.n}
              </div>
              <span
                className={cn(
                  "text-sm font-medium hidden sm:block transition-colors",
                  active ? "text-gray-900" : done ? "text-brand-600" : "text-gray-400",
                )}
              >
                {step.label}
              </span>
            </div>
            {idx < STEPS.length - 1 && (
              <div
                className={cn(
                  "flex-1 h-px mx-4 transition-colors",
                  done ? "bg-brand-300" : "bg-gray-200",
                )}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────────*/

export default function AppPage() {
  const [step, setStep] = React.useState<1 | 2 | 3>(1);
  const [questions, setQuestions] = React.useState<Question[]>([]);
  const [context, setContext] = React.useState("");
  const [mode, setMode] = React.useState<"single" | "batch">("single");
  const [applicants, setApplicants] = React.useState<ApplicantInput[]>([]);

  const hasQuestions = questions.some((q) => q.text.trim().length > 0);
  const hasReadyApplicant = applicants.some(
    (a) => a.name.trim().length > 0 && a.files.length > 0,
  );

  const canNext =
    (step === 1 && hasQuestions) ||
    (step === 2 && hasReadyApplicant);

  const nextLabel =
    step === 1 ? "Next" : step === 2 ? "Screen applications" : "Done";

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 bg-white border-b border-gray-100 shadow-sm">
        <div className="mx-auto max-w-4xl px-6 h-16 flex items-center justify-between gap-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-gray-400 hover:text-gray-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="font-bold text-brand-600 text-lg">DOCex</span>
          </Link>

          <div className="flex-1 max-w-md">
            <StepBar current={step} />
          </div>

          <div className="w-28" />
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-12">
        {/* Step content */}
        {step === 1 && (
          <QuestionBuilder
            questions={questions}
            onChange={setQuestions}
            context={context}
            onContextChange={setContext}
          />
        )}

        {step === 2 && (
          <ApplicantUpload
            mode={mode}
            onModeChange={setMode}
            applicants={applicants}
            onChange={setApplicants}
          />
        )}

        {step === 3 && (
          <div className="rounded-2xl border-2 border-dashed border-gray-200 p-16 text-center text-gray-400">
            <p className="text-sm">Results table coming next</p>
          </div>
        )}

        {/* Bottom navigation */}
        <div className="flex justify-between mt-10 pt-6 border-t border-gray-200">
          {step > 1 ? (
            <button
              type="button"
              onClick={() => setStep((s) => Math.max(1, s - 1) as 1 | 2 | 3)}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-5 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </button>
          ) : (
            <div />
          )}

          <button
            type="button"
            disabled={!canNext}
            onClick={() => setStep((s) => Math.min(3, s + 1) as 1 | 2 | 3)}
            className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {nextLabel}
          </button>
        </div>
      </main>
    </div>
  );
}
