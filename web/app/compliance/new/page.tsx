"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { DropZone } from "@/components/DropZone";
import { GuidanceCard } from "@/components/GuidanceCard";
import { interpretPolicy } from "@/lib/api";

/**
 * Create rulebook page.
 *
 * The interpretation step takes 30-60 seconds — long enough that a generic
 * spinner reads as "stuck". Instead we cycle through three labels in
 * sequence ("Reading your policy" → "Extracting rules" → "Almost ready"),
 * which gives the user a sense of forward motion. Pure goal-gradient
 * psychology; the labels are not synchronised to actual backend progress
 * because the backend is a single Claude call, not a streamed pipeline.
 */

type Phase = "idle" | "loading" | "error";
type LoadingStage = "reading" | "extracting" | "saving";

export default function CreateRulebookPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [stage, setStage] = useState<LoadingStage>("reading");
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim().length > 0 && files.length > 0 && phase === "idle";

  // Drive the progressive labels while loading. Numbers are tuned for a
  // typical 30-60s interpretation — they're soft and may finish before
  // the API call returns; that's fine, "Almost ready" just sits there.
  useEffect(() => {
    if (phase !== "loading") return;
    setStage("reading");
    const t1 = setTimeout(() => setStage("extracting"), 8000);
    const t2 = setTimeout(() => setStage("saving"), 25000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [phase]);

  async function handleSubmit() {
    if (!canSubmit) return;
    setPhase("loading");
    setError(null);
    try {
      const rulebook = await interpretPolicy(name.trim(), files);
      router.push(`/compliance/rulebooks/${rulebook.id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not interpret your policy. Is the API running?",
      );
      setPhase("error");
    }
  }

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
        {phase === "loading" ? (
          <LoadingState stage={stage} name={name} />
        ) : (
          <div className="space-y-8">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Create a new rulebook
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Upload your policy — DOCex reads it and extracts every rule
                into a structured rulebook you can review and edit.
              </p>
            </div>

            <GuidanceCard title="What happens next">
              We'll read the document, extract testable rules (thresholds,
              evidence requirements, approval levels) and group them by
              category. You'll be able to verify, edit, or remove anything
              before running any checks against it.
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
                Use something you'll recognise — e.g. "TA Connect Procurement
                Policy 2025" or "Travel & Expense Policy".
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
                PDF, DOCX, or TXT. If your policy is split across several
                files, drop them all in.
              </p>
              <DropZone files={files} onFilesChange={setFiles} />
            </div>

            {/* Error state */}
            {phase === "error" && error && (
              <div className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                <p className="font-medium text-red-900">
                  Could not interpret your policy
                </p>
                <p>{error}</p>
                <button
                  type="button"
                  onClick={() => setPhase("idle")}
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
                Interpret policy
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/* ─── Loading state ───────────────────────────────────────────────────── */

function LoadingState({
  stage,
  name,
}: {
  stage: LoadingStage;
  name: string;
}) {
  const labels: Record<LoadingStage, { title: string; sub: string }> = {
    reading: {
      title: "Reading your policy…",
      sub: "Scanning every page for testable rules.",
    },
    extracting: {
      title: "Extracting rules…",
      sub: "Structuring thresholds, conditions, and evidence requirements.",
    },
    saving: {
      title: "Almost ready…",
      sub: "Organising the rulebook and saving it.",
    },
  };
  const s = labels[stage];

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <Loader2 className="mb-6 h-10 w-10 animate-spin text-brand-600" />
      <p className="text-lg font-semibold text-gray-900">{s.title}</p>
      <p className="mt-2 text-sm text-gray-600">{s.sub}</p>
      <p className="mt-6 text-xs text-gray-400">
        Building{" "}
        <span className="font-medium text-gray-600">{name || "your rulebook"}</span>{" "}
        — this usually takes 30 to 60 seconds.
      </p>
    </div>
  );
}
