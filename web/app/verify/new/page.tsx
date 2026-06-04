"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  FileSpreadsheet,
  Landmark,
  Loader2,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { verifyBankBatch } from "@/lib/api";
import type { StandardPurpose } from "@/types";
import { purposeDescription, purposeLabel } from "@/types";

/**
 * /verify/new — drop a payment schedule, tag the purpose, kick off the run.
 *
 * UX choices that matter:
 *
 *  - Purpose first, file second. The purpose is the metadata that makes the
 *    audit trail useful three months later. Putting it BEFORE the file in
 *    visual order trains the user to think about it; it also lets us tailor
 *    the upload helper copy ("Drop the disbursement schedule" vs "Drop the
 *    attendance-derived schedule") in a follow-up iteration.
 *
 *  - Drag-drop with visible state. The drop zone responds to hover so the
 *    user knows the file is being received. Once a file is selected, it's
 *    shown as a card with size + remove affordance, NOT as a label.
 *
 *  - Submit button is disabled until both purpose and file are present.
 *    Validation is shown inline; no toast notifications.
 *
 *  - During the run we show the estimated time. Real-time per-row results
 *    would need a streaming endpoint; that's a future iteration. For now
 *    we show a confident, time-bounded loading state that ends in a
 *    redirect to the batch detail page.
 */

const STANDARD_PURPOSES: StandardPurpose[] = [
  "event_payment",
  "grantee_disbursement",
  "vendor_payment",
  "partner_reimbursement",
  "other",
];

export default function VerifyNewPage() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);

  const [purpose, setPurpose] = useState<StandardPurpose | null>(null);
  const [purposeDetail, setPurposeDetail] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    const xlsx = arr.find((f) =>
      f.name.toLowerCase().endsWith(".xlsx") ||
      f.name.toLowerCase().endsWith(".xlsm"),
    );
    if (!xlsx) {
      setError("Please upload an .xlsx (or .xlsm) file.");
      return;
    }
    setError(null);
    setFile(xlsx);
  }


  async function submit() {
    if (!file || !purpose) return;
    setError(null);
    setSubmitting(true);
    try {
      const batch = await verifyBankBatch(
        file,
        purpose,
        purpose === "other" ? purposeDetail : purposeDetail || undefined,
      );
      if (batch.batch_id) {
        router.push(`/verify/${batch.batch_id}`);
      } else {
        setError("Verification finished but no batch id was returned.");
        setSubmitting(false);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not verify the schedule. Check the backend.",
      );
      setSubmitting(false);
    }
  }

  const canSubmit =
    !!file &&
    !!purpose &&
    !submitting &&
    (purpose !== "other" || purposeDetail.trim().length > 0);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between gap-6 px-6">
          <Link
            href="/verify"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <Landmark className="h-4 w-4 text-brand-600" />
            New verification
          </span>
          <Link
            href="/verify"
            className="text-xs font-medium text-gray-500 hover:text-gray-700"
          >
            Cancel
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        <div className="space-y-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">
              Verify a payment schedule
            </h1>
            <p className="mt-2 max-w-xl text-base text-gray-600">
              Two steps. Tag what the verification is for, then drop in your
              schedule. DOCex calls each bank and returns a verdict per row
              in under a minute for most files.
            </p>
          </div>

          {/* Step 1 — Purpose */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-gray-200 text-[11px] font-bold text-gray-700">
                1
              </span>
              What are you verifying?
            </h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {STANDARD_PURPOSES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => {
                    setPurpose(p);
                    if (p !== "other") setPurposeDetail("");
                  }}
                  className={`text-left rounded-xl border p-4 transition ${
                    purpose === p
                      ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100"
                      : "border-gray-200 bg-white hover:border-brand-300"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                        purpose === p
                          ? "border-brand-600 bg-brand-600"
                          : "border-gray-300 bg-white"
                      }`}
                    >
                      {purpose === p && (
                        <CheckCircle2 className="h-3 w-3 text-white" />
                      )}
                    </span>
                    <span
                      className={`text-sm font-medium ${
                        purpose === p ? "text-brand-700" : "text-gray-900"
                      }`}
                    >
                      {purposeLabel[p]}
                    </span>
                  </div>
                  <p className="ml-6 mt-1 text-xs leading-relaxed text-gray-500">
                    {purposeDescription[p]}
                  </p>
                </button>
              ))}
            </div>

            {/* Free-text elaboration. Always available but visually emphasised
                when 'other' is selected (where it's required). */}
            {purpose && (
              <div className="mt-3">
                <label
                  htmlFor="purpose-detail"
                  className="text-xs font-medium text-gray-600"
                >
                  {purpose === "other"
                    ? "Describe the purpose"
                    : "Optional — anything that distinguishes this batch from others (e.g. 'Q2 cohort', 'May training group')"}
                </label>
                <input
                  id="purpose-detail"
                  type="text"
                  value={purposeDetail}
                  onChange={(e) => setPurposeDetail(e.target.value)}
                  placeholder={
                    purpose === "other"
                      ? "e.g. 'Q1 board honoraria'"
                      : "Optional"
                  }
                  className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
            )}
          </section>

          {/* Step 2 — File */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-gray-200 text-[11px] font-bold text-gray-700">
                2
              </span>
              Drop the schedule
            </h2>

            {!file ? (
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
                }}
                onClick={() => fileInput.current?.click()}
                className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition ${
                  dragOver
                    ? "border-brand-500 bg-brand-50"
                    : "border-gray-200 bg-white hover:border-brand-300 hover:bg-brand-50/30"
                }`}
              >
                <input
                  ref={fileInput}
                  type="file"
                  accept=".xlsx,.xlsm"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.length) handleFiles(e.target.files);
                  }}
                />
                <div className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
                  <Upload className="h-6 w-6" />
                </div>
                <p className="text-sm font-medium text-gray-900">
                  Drop your .xlsx schedule here
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  or click to choose · header row needs name, account, bank
                  columns
                </p>
              </div>
            ) : (
              <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
                  <FileSpreadsheet className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-gray-900">
                    {file.name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {(file.size / 1024).toFixed(1)} KB · ready to verify
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setFile(null)}
                  disabled={submitting}
                  className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50"
                  title="Remove file"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
          </section>

          {/* Submit */}
          <div className="border-t border-gray-100 pt-6">
            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}
            <button
              type="button"
              disabled={!canSubmit}
              onClick={submit}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-5 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500 disabled:shadow-none"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Calling banks…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Verify accounts
                </>
              )}
            </button>
            {submitting && (
              <p className="mt-3 text-center text-xs text-gray-500">
                Each row takes ~200ms. A 50-row schedule completes in about 10
                seconds; 500 rows takes ~2 minutes. Stay on this page — we'll
                redirect you when it's done.
              </p>
            )}
            {!submitting && file && purpose && (
              <p className="mt-3 text-center text-xs text-gray-500">
                Don't close the tab — the page will redirect to the results
                when the run completes.
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
