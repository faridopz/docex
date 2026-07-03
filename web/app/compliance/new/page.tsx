"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  FileText,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { DropZone } from "@/components/DropZone";
import { GuidanceCard } from "@/components/GuidanceCard";
import { startPolicyJob, getPolicyJob } from "@/lib/api";
import type { PolicyJob } from "@/types";

/**
 * Create rulebook page — non-blocking.
 *
 * Uploading a policy no longer holds the customer on a 30-60s spinner. The
 * upload returns in ~1s with an INSTANT deterministic preview ("we read it —
 * 3 files, ~4,200 words, 6 sections"), and the slow Claude interpretation runs
 * server-side in the background. We poll the job until the rulebook is ready,
 * then navigate to it. The customer can also just leave — the job keeps going
 * and the rulebook shows up under Compliance when it's done.
 */

type Phase = "idle" | "working" | "error";

export default function CreateRulebookPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [job, setJob] = useState<PolicyJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canSubmit =
    name.trim().length > 0 && files.length > 0 && phase !== "working";

  async function handleSubmit() {
    if (!canSubmit) return;
    setPhase("working");
    setError(null);
    setJob(null);
    try {
      // Fast: server extracts text + returns a preview immediately, then runs
      // the LLM pass in the background.
      const started = await startPolicyJob(name.trim(), files);
      setJob(started);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not upload your policy. Is the API running?",
      );
      setPhase("error");
    }
  }

  // Poll the background job. Each state update reschedules the next poll, so
  // this drives itself until the rulebook is ready or the job errors.
  useEffect(() => {
    if (phase !== "working" || !job) return;

    if (job.status === "ready" && job.rulebook_id) {
      router.push(`/compliance/rulebooks/${job.rulebook_id}`);
      return;
    }
    if (job.status === "error") {
      setError(
        job.error ||
          "We couldn't extract rules from this document. It may be empty, a scan, or contain no testable requirements.",
      );
      setPhase("error");
      return;
    }

    const t = setTimeout(async () => {
      try {
        const next = await getPolicyJob(job.job_id);
        setJob(next);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Lost contact with the server while generating rules.",
        );
        setPhase("error");
      }
    }, 2000);
    return () => clearTimeout(t);
  }, [phase, job, router]);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between gap-6 px-6">
          <Link
            href="/compliance"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <ShieldCheck className="h-4 w-4 text-brand-600" />
            New rulebook
          </span>
          <div className="w-28" />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        {phase === "working" ? (
          <WorkingState job={job} name={name} />
        ) : (
          <div className="space-y-8">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Create a new rulebook
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Upload your policy — DOCex confirms it straight away and builds
                your rulebook in the background. No long wait.
              </p>
            </div>

            <GuidanceCard title="What happens next">
              As soon as you upload, we confirm what we read. DOCex then
              extracts testable rules (thresholds, evidence requirements,
              approval levels) in the background — you can wait a few seconds or
              leave the page and find the finished rulebook under Compliance.
            </GuidanceCard>

            {/* Name */}
            <div className="space-y-2">
              <label
                htmlFor="rulebook-name"
                className="block text-sm font-semibold text-gray-900"
              >
                Name this rulebook
              </label>
              <p className="text-xs text-gray-500">
                Use something you&apos;ll recognise — e.g. &quot;TA Connect
                Procurement Policy 2025&quot; or &quot;Travel &amp; Expense
                Policy&quot;.
              </p>
              <input
                id="rulebook-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Procurement Policy 2025"
                className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder:text-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
              />
            </div>

            {/* Upload */}
            <div className="space-y-2">
              <label className="block text-sm font-semibold text-gray-900">
                Upload your policy document
              </label>
              <p className="text-xs text-gray-500">
                PDF, DOCX, or TXT. If your policy is split across several files,
                drop them all in.
              </p>
              <DropZone files={files} onFilesChange={setFiles} />
            </div>

            {/* Error state */}
            {phase === "error" && error && (
              <div className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                <p className="font-medium text-red-900">
                  Could not build your rulebook
                </p>
                <p>{error}</p>
                <button
                  type="button"
                  onClick={() => {
                    setPhase("idle");
                    setError(null);
                  }}
                  className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100"
                >
                  Try again
                </button>
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-between border-t border-gray-200 pt-6">
              <Link
                href="/compliance"
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-5 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-300 hover:text-gray-900"
              >
                <ArrowLeft className="h-4 w-4" />
                Back
              </Link>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSubmit}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Sparkles className="h-4 w-4" />
                Upload &amp; build
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/* ─── Working state — instant preview + background progress ───────────────── */

function WorkingState({
  job,
  name,
}: {
  job: PolicyJob | null;
  name: string;
}) {
  // Before the upload call returns, `job` is null — that window is sub-second
  // (just text extraction), so a light "reading" line covers it.
  if (!job) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <Loader2 className="mb-6 h-10 w-10 animate-spin text-brand-600" />
        <p className="text-lg font-semibold text-gray-900">
          Reading your policy…
        </p>
        <p className="mt-2 text-sm text-gray-600">This only takes a moment.</p>
      </div>
    );
  }

  const p = job.preview;

  return (
    <div className="space-y-6">
      {/* Instant confirmation — the "we read it" moment */}
      <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-emerald-600" />
        <div className="min-w-0">
          <p className="text-base font-semibold text-emerald-900">
            Policy added — {name || "your rulebook"}
          </p>
          <p className="mt-0.5 text-sm text-emerald-800">{p.summary}</p>
          {p.files.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {p.files.map((f) => (
                <span
                  key={f}
                  className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-white px-2.5 py-1 text-xs font-medium text-emerald-800"
                >
                  <FileText className="h-3.5 w-3.5" />
                  {f}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Background progress — non-blocking */}
      <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-5">
        <Loader2 className="h-5 w-5 shrink-0 animate-spin text-brand-600" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900">
            Building your rulebook…
          </p>
          <p className="mt-0.5 text-sm text-gray-600">
            Extracting testable rules — thresholds, evidence, and approval
            levels. This takes a few seconds. We&apos;ll open the rulebook the
            moment it&apos;s ready.
          </p>
        </div>
      </div>

      {/* Leave-and-continue — the whole point of the background job */}
      <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 text-center">
        <p className="text-sm text-gray-600">
          You don&apos;t have to wait here. This keeps running in the
          background — the finished rulebook will be waiting under Compliance.
        </p>
        <Link
          href="/compliance"
          className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-brand-600 transition hover:text-brand-700"
        >
          Back to Compliance
          <ArrowLeft className="h-3.5 w-3.5 rotate-180" />
        </Link>
      </div>
    </div>
  );
}
