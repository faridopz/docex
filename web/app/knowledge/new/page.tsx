"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { uploadDeck } from "@/lib/api";

/**
 * /knowledge/new — upload a .pptx into the Knowledge Hub.
 *
 * Three optional fields beyond the file itself: display name (defaults to
 * filename), description (1-2 sentences of context), tags (comma-separated
 * — for later filtering when a team has 50 decks). Drag-drop is the primary
 * interaction; the metadata fields stay collapsed unless the user expands
 * them so the first-run experience is "drop, done".
 */

export default function UploadDeckPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [showMeta, setShowMeta] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pickPptx(files: FileList | File[]): File | null {
    // Misleading name kept for diff brevity — accepts PPTX, DOCX, PDF now.
    const accepted = [".pptx", ".pptm", ".docx", ".docm", ".pdf"];
    return (
      Array.from(files).find((f) =>
        accepted.some((ext) => f.name.toLowerCase().endsWith(ext)),
      ) ?? null
    );
  }

  async function submit() {
    if (!file) return;
    setError(null);
    setSubmitting(true);
    try {
      const deck = await uploadDeck(file, {
        name: name.trim() || undefined,
        description: description.trim() || undefined,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      router.push(`/knowledge/${deck.id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not upload the deck. Check the backend is up.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-[#fafaf7]/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between gap-6 px-6">
          <Link
            href="/knowledge"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-gray-900">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <BookOpen className="h-4 w-4 text-brand-600" />
            Upload deck
          </span>
          <Link
            href="/knowledge"
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
              Add a deck to the Knowledge Hub
            </h1>
            <p className="mt-2 max-w-xl text-base text-gray-600">
              Drop in your .pptx — DOCex reads every slide, including titles,
              body text, tables, and speaker notes. You'll be chatting with it
              within seconds.
            </p>
          </div>

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
                const f = pickPptx(e.dataTransfer.files);
                if (f) setFile(f);
                else setError("Please upload a .pptx, .docx, or .pdf file.");
              }}
              onClick={() => inputRef.current?.click()}
              className={`cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center transition ${
                dragOver
                  ? "border-brand-500 bg-brand-50"
                  : "border-gray-200 bg-white hover:border-brand-300 hover:bg-brand-50/30"
              }`}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".pptx,.pptm,.docx,.docm,.pdf"
                className="hidden"
                onChange={(e) => {
                  if (!e.target.files?.length) return;
                  const f = pickPptx(e.target.files);
                  if (f) setFile(f);
                  else setError("Please upload a .pptx (or .pptm) file.");
                }}
              />
              <div className="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-100">
                <Upload className="h-7 w-7" />
              </div>
              <p className="text-base font-medium text-gray-900">
                Drop your document here
              </p>
              <p className="mt-1 text-sm text-gray-500">
                PowerPoint, Word, or PDF · up to ~200 chunks per document
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-700">
                <FileText className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-900">
                  {file.name}
                </p>
                <p className="text-xs text-gray-500">
                  {(file.size / 1024).toFixed(1)} KB · ready to parse
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

          {/* Optional metadata — collapsed by default. Drop-and-done first. */}
          {file && (
            <div>
              <button
                type="button"
                onClick={() => setShowMeta((s) => !s)}
                className="text-xs font-medium text-gray-500 transition hover:text-brand-700"
              >
                {showMeta ? "Hide" : "Add"} a name, description, or tags
                (optional)
              </button>

              {showMeta && (
                <div className="mt-3 space-y-3 rounded-xl border border-gray-100 bg-white p-5">
                  <div>
                    <label className="text-xs font-medium text-gray-600">
                      Display name
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder={file.name.replace(/\.(pptx|pptm)$/i, "")}
                      className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">
                      Description
                    </label>
                    <input
                      type="text"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="e.g. Gates Foundation March 2026 check-in"
                      className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">
                      Tags
                    </label>
                    <input
                      type="text"
                      value={tags}
                      onChange={(e) => setTags(e.target.value)}
                      placeholder="comma-separated, e.g. Gates Foundation, Check-in, Q1 2026"
                      className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="border-t border-gray-100 pt-6">
            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}
            <button
              type="button"
              disabled={!file || submitting}
              onClick={submit}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-5 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Parsing slides…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Add to Knowledge Hub
                </>
              )}
            </button>
            <p className="mt-3 text-center text-xs text-gray-500">
              {submitting
                ? "Reading every slide, extracting titles, body, tables, and speaker notes."
                : "We'll redirect to the chat interface as soon as parsing finishes."}
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
