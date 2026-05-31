"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { QuestionBuilder } from "@/components/QuestionBuilder";
import { ApplicantUpload } from "@/components/ApplicantUpload";
import { ExtractionTable } from "@/components/ExtractionTable";
import { extractSingle, extractBatch } from "@/lib/api";
import { getWorkflowLabels } from "@/lib/workflow-labels";
import type {
  Question,
  ApplicantInput,
  SingleExtractionResponse,
  BatchExtractionResponse,
} from "@/types";

/* ─── Step bar ───────────────────────────────────────────────────────────────*/

// Step labels are workflow-aware — they're built inside the component
// from the active template's labels. Step 1 and step 3 stay neutral;
// only step 2 adapts ("Add applicants" / "Add reports" / "Add applications").

function StepBar({
  current,
  step2Label,
}: {
  current: number;
  step2Label: string;
}) {
  const steps = [
    { n: 1, label: "Define questions" },
    { n: 2, label: step2Label },
    { n: 3, label: "Review results" },
  ];
  return (
    <div className="flex items-center">
      {steps.map((step, idx) => {
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
            {idx < steps.length - 1 && (
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
  const [templateId, setTemplateId] = React.useState<string | null>(null);

  const [isScreening, setIsScreening] = React.useState(false);
  const [result, setResult] = React.useState<
    SingleExtractionResponse | BatchExtractionResponse | null
  >(null);
  const [error, setError] = React.useState<string | null>(null);

  const hasQuestions = questions.some((q) => q.text.trim().length > 0);
  const hasReadyApplicant = applicants.some(
    (a) => a.name.trim().length > 0 && a.files.length > 0,
  );

  const canNext =
    (step === 1 && hasQuestions) ||
    (step === 2 && hasReadyApplicant);

  const workflowLabels = getWorkflowLabels(templateId);
  const nextLabel =
    step === 1 ? "Next" : step === 2 ? workflowLabels.stepTwoButton : "Done";

  // Number of applicants that will be screened (for loading estimate)
  const readyCount = applicants.filter(
    (a) => a.name.trim().length > 0 && a.files.length > 0,
  ).length;

  async function handleNext() {
    if (step === 1) {
      setStep(2);
      return;
    }

    if (step === 2) {
      // Start screening
      setIsScreening(true);
      setError(null);
      setResult(null);
      setStep(3);

      // Filter to only ready applicants
      const validQuestions = questions.filter((q) => q.text.trim().length > 0);
      const readyApplicants = applicants.filter(
        (a) => a.name.trim().length > 0 && a.files.length > 0,
      );

      try {
        if (mode === "single") {
          const ap = readyApplicants[0];
          const res = await extractSingle(ap.name, ap.files, validQuestions);
          setResult(res);
        } else {
          const res = await extractBatch(readyApplicants, validQuestions);
          setResult(res);
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Extraction failed. Is the API running on port 8000?",
        );
      } finally {
        setIsScreening(false);
      }
      return;
    }
  }

  // Back button visibility: hidden on step 1, hidden during screening
  const showBack = step > 1 && !isScreening;

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
            <StepBar current={step} step2Label={workflowLabels.step2Label} />
          </div>

          <div className="flex items-center justify-end gap-2">
            {/* Cross-mode links — keeps all three primitives discoverable from
                each other without forcing a chooser between landing and app.
                Order: Compliance, Bank Verify (newest, called out last so the
                eye lands on it). */}
            <Link
              href="/compliance"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
              title="Switch to Compliance Check"
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              Compliance
            </Link>
            <Link
              href="/verify"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
              title="Switch to Bank Verify"
            >
              Bank Verify
            </Link>
            <Link
              href="/agents/attendance-payment"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
              title="Attendance Payment Agent"
            >
              Attendance
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-12">
        {/* Step 1 */}
        {step === 1 && (
          <QuestionBuilder
            questions={questions}
            onChange={setQuestions}
            context={context}
            onContextChange={setContext}
            onTemplateChange={setTemplateId}
          />
        )}

        {/* Step 2 */}
        {step === 2 && (
          <ApplicantUpload
            mode={mode}
            onModeChange={setMode}
            applicants={applicants}
            onChange={setApplicants}
            templateId={templateId}
          />
        )}

        {/* Step 3 */}
        {step === 3 && (
          <>
            {isScreening && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <Loader2 className="h-8 w-8 animate-spin text-brand-600 mb-4" />
                <p className="text-base font-medium text-gray-900">
                  {workflowLabels.stepThreeLoadingTitle}
                </p>
                <p className="mt-2 text-sm text-gray-500">
                  This usually takes 1–2 minutes
                  {readyCount > 1
                    ? ` for ${readyCount} ${workflowLabels.unitPlural}`
                    : ""}.
                </p>
              </div>
            )}

            {error && !isScreening && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center space-y-4">
                <p className="text-sm font-medium text-red-800">{error}</p>
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setStep(2);
                  }}
                  className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50"
                >
                  Try again
                </button>
              </div>
            )}

            {result && !isScreening && (
              <ExtractionTable
                mode={mode}
                result={result}
                questions={questions.filter((q) => q.text.trim().length > 0)}
                templateId={templateId}
              />
            )}
          </>
        )}

        {/* Bottom navigation */}
        <div className="flex justify-between mt-10 pt-6 border-t border-gray-200">
          {showBack ? (
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

          {step < 3 && (
            <button
              type="button"
              disabled={!canNext}
              onClick={handleNext}
              className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {nextLabel}
            </button>
          )}

          {step === 3 && !isScreening && result && (
            <button
              type="button"
              disabled
              className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white opacity-50 cursor-not-allowed"
            >
              Done
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
