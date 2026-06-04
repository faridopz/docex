"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  BookOpen,
  ChevronRight,
  Folder,
  FolderOpen,
  Layers,
  Loader2,
  Plus,
  Sparkles,
  Tag,
  X,
} from "lucide-react";
import {
  chatWithLibrary,
  listDecks,
  suggestFolder,
  updateDeck,
} from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { GuidanceCard } from "@/components/GuidanceCard";
import type {
  KnowledgeAnswer,
  SlideCitation,
  SlideDeckSummary,
} from "@/types";
import {
  chunkLabelPlural,
  contentTypeBadge,
  contentTypeLabel,
} from "@/types";

/**
 * /knowledge — the Library.
 *
 * V2 of the Knowledge Hub landing. Three new surfaces compared to V1:
 *
 *   1. Library-wide chat at the top — ask one question across every doc.
 *      Citations carry deck name AND chunk number; chips deep-link to
 *      the source document.
 *   2. Folder filter row — every distinct folder path becomes a pill.
 *      Click to scope the library (chat + cards) to that folder.
 *   3. Per-card folder actions — set/move folder, or hit "Suggest folder"
 *      to have Claude propose one based on the document content.
 *
 * The "smart SharePoint" feel comes from the combination: folders are
 * just slash-paths so they're flexible, but the AI suggestion makes
 * organising feel collaborative rather than chore-like.
 */

export default function KnowledgeLibraryPage() {
  const router = useRouter();

  const [decks, setDecks] = useState<SlideDeckSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Library chat state — kept in-memory; not persisted (each session is
  // independent for now). Phase 2 of the Knowledge Hub adds a chat history
  // surface that persists per user + per scope.
  type ChatTurn = {
    id: string;
    question: string;
    answer: KnowledgeAnswer | null;
    loading: boolean;
    error: string | null;
  };
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");

  // Folder filter — null = "everything", "" = root, otherwise the path.
  const [folderFilter, setFolderFilter] = useState<string | null>(null);

  // Per-card UI state — which card is in folder-edit mode, pending API calls
  const [editingFolderFor, setEditingFolderFor] = useState<string | null>(null);
  const [folderInput, setFolderInput] = useState("");
  const [suggesting, setSuggesting] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement | null>(null);

  async function reload() {
    setError(null);
    try {
      const list = await listDecks();
      setDecks(list);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load library. Is the API running on port 8000?",
      );
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  // Distinct folders, sorted. Used to render the filter pill row.
  // Decks without a folder contribute "root" implicitly so we always
  // offer an "Unfoldered" pill when applicable.
  const folders = useMemo(() => {
    if (!decks) return [];
    const set = new Set<string>();
    for (const d of decks) {
      if (d.folder) set.add(d.folder);
    }
    return Array.from(set).sort();
  }, [decks]);

  const hasRoot = useMemo(
    () => (decks ?? []).some((d) => !d.folder),
    [decks],
  );

  const filteredDecks = useMemo(() => {
    if (!decks) return [];
    if (folderFilter === null) return decks;
    if (folderFilter === "") return decks.filter((d) => !d.folder);
    return decks.filter(
      (d) =>
        d.folder === folderFilter || (d.folder?.startsWith(folderFilter + "/") ?? false),
    );
  }, [decks, folderFilter]);

  async function submitChat(question: string) {
    const q = question.trim();
    if (!q) return;
    const id = Math.random().toString(36).slice(2);
    setTurns((t) => [
      ...t,
      { id, question: q, answer: null, loading: true, error: null },
    ]);
    setInput("");
    try {
      const ans = await chatWithLibrary(q, { folder: folderFilter });
      setTurns((t) =>
        t.map((x) =>
          x.id === id ? { ...x, answer: ans, loading: false } : x,
        ),
      );
    } catch (err) {
      setTurns((t) =>
        t.map((x) =>
          x.id === id
            ? {
                ...x,
                loading: false,
                error:
                  err instanceof Error
                    ? err.message
                    : "Couldn't reach the Assistant.",
              }
            : x,
        ),
      );
    }
  }

  async function saveFolder(deckId: string, folder: string) {
    try {
      await updateDeck(deckId, { folder: folder.trim() || null });
      setEditingFolderFor(null);
      setFolderInput("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not move document.");
    }
  }

  async function handleSuggestFolder(deckId: string) {
    setSuggesting(deckId);
    try {
      const { suggested_folder } = await suggestFolder(deckId);
      setFolderInput(suggested_folder);
      setEditingFolderFor(deckId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not get a suggestion.",
      );
    } finally {
      setSuggesting(null);
    }
  }

  return (
    <AppShell
      active="knowledge"
      actions={
        <Link
          href="/knowledge/new"
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-3.5 w-3.5" />
          Add document
        </Link>
      }
    >
      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="space-y-8">
          {/* Hero */}
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              Your organisation&apos;s memory.
            </h1>
            <p className="mt-2 max-w-2xl text-base text-gray-600">
              Ask anything across every document. Answers come back with{" "}
              <span className="font-medium text-gray-900">citations you can verify</span>{" "}
              — slide, page, or section. Drop documents in, organise them
              into folders, and let DOCex do the rest.
            </p>
          </div>

          {/* Library chat surface — the headline new feature */}
          <section className="overflow-hidden rounded-2xl border border-brand-100 bg-white shadow-card">
            <div className="border-b border-gray-100 bg-gradient-to-br from-brand-50/40 via-white to-white px-5 py-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-brand-600" />
                <p className="text-xs font-semibold uppercase tracking-widest text-brand-700">
                  Ask the library
                </p>
                {folderFilter !== null && (
                  <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-brand-200">
                    <Folder className="h-3 w-3" />
                    Scoped to {folderFilter === "" ? "Unfoldered" : folderFilter}
                    <button
                      type="button"
                      onClick={() => setFolderFilter(null)}
                      className="ml-1 rounded hover:bg-brand-100"
                      title="Clear folder filter"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                )}
              </div>
            </div>

            {turns.length > 0 && (
              <div className="max-h-[28rem] overflow-y-auto px-5 py-4">
                <div className="space-y-5">
                  {turns.map((t) => (
                    <LibraryTurn
                      key={t.id}
                      turn={t}
                      onCitationClick={(c) => {
                        if (c.deck_id) router.push(`/knowledge/${c.deck_id}`);
                      }}
                    />
                  ))}
                  <div ref={chatEndRef} />
                </div>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void submitChat(input);
              }}
              className="flex items-end gap-2 border-t border-gray-100 bg-white p-2"
            >
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void submitChat(input);
                  }
                }}
                rows={1}
                placeholder={
                  decks && decks.length === 0
                    ? "Add a document first — then ask anything across your library."
                    : `Ask across ${
                        folderFilter === null
                          ? "every document"
                          : folderFilter === ""
                            ? "unfoldered documents"
                            : `the ${folderFilter} folder`
                      }… (e.g. "What's our PPH coverage in Bauchi?")`
                }
                disabled={!decks || decks.length === 0}
                className="flex-1 resize-none border-0 bg-transparent px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || !decks || decks.length === 0}
                className="inline-flex shrink-0 items-center justify-center rounded-lg bg-brand-600 p-2.5 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
                title="Ask the library"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </form>
          </section>

          {/* Folder filter pills */}
          {decks && decks.length > 0 && (folders.length > 0 || hasRoot) && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                Folders
              </span>
              <FolderPill
                label="All documents"
                active={folderFilter === null}
                onClick={() => setFolderFilter(null)}
                icon={<Layers className="h-3 w-3" />}
              />
              {hasRoot && (
                <FolderPill
                  label="Unfoldered"
                  active={folderFilter === ""}
                  onClick={() => setFolderFilter("")}
                  icon={<Folder className="h-3 w-3" />}
                />
              )}
              {folders.map((f) => (
                <FolderPill
                  key={f}
                  label={f}
                  active={folderFilter === f}
                  onClick={() => setFolderFilter(f)}
                  icon={
                    folderFilter === f ? (
                      <FolderOpen className="h-3 w-3" />
                    ) : (
                      <Folder className="h-3 w-3" />
                    )
                  }
                />
              ))}
            </div>
          )}

          {/* Guidance — only on populated state */}
          {decks && decks.length > 0 && turns.length === 0 && (
            <GuidanceCard title="Two ways to work">
              <span className="font-medium">Ask the library</span> for a
              cross-document answer with citations. Or click into a single
              document for a focused chat with just that file. Organise into
              folders to scope your questions, and hit{" "}
              <span className="font-medium">Suggest folder</span> to let
              DOCex propose where each document belongs.
            </GuidanceCard>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p className="font-medium text-red-900">Something went wrong</p>
              <p className="mt-1">{error}</p>
            </div>
          )}

          {/* States */}
          {decks === null && !error && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading library…
            </div>
          )}

          {decks !== null && decks.length === 0 && !error && <EmptyState />}

          {decks !== null && decks.length > 0 && (
            <div className="grid gap-3">
              {filteredDecks.length === 0 && (
                <p className="rounded-xl border border-dashed border-gray-200 bg-white px-6 py-10 text-center text-sm text-gray-500">
                  No documents in this folder.{" "}
                  <button
                    type="button"
                    onClick={() => setFolderFilter(null)}
                    className="text-brand-700 hover:underline"
                  >
                    Show all
                  </button>
                </p>
              )}
              {filteredDecks.map((d) => (
                <DeckCard
                  key={d.id}
                  deck={d}
                  editing={editingFolderFor === d.id}
                  folderInput={folderInput}
                  suggesting={suggesting === d.id}
                  onStartFolderEdit={() => {
                    setFolderInput(d.folder ?? "");
                    setEditingFolderFor(d.id);
                  }}
                  onCancelFolderEdit={() => {
                    setEditingFolderFor(null);
                    setFolderInput("");
                  }}
                  onFolderInputChange={setFolderInput}
                  onSaveFolder={() => void saveFolder(d.id, folderInput)}
                  onSuggestFolder={() => void handleSuggestFolder(d.id)}
                  onFolderClick={() => d.folder && setFolderFilter(d.folder)}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </AppShell>
  );
}

/* ─── Library chat turn ────────────────────────────────────────────────── */

function LibraryTurn({
  turn,
  onCitationClick,
}: {
  turn: {
    id: string;
    question: string;
    answer: KnowledgeAnswer | null;
    loading: boolean;
    error: string | null;
  };
  onCitationClick: (c: SlideCitation) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-2xl rounded-tr-md bg-brand-600 px-4 py-2 text-sm text-white shadow-sm">
          {turn.question}
        </div>
      </div>
      <div className="flex justify-start">
        <div className="flex w-full max-w-[94%] items-start gap-2.5">
          <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-100">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-gray-100 bg-gray-50/60 px-4 py-3 text-sm leading-relaxed text-gray-800">
            {turn.loading ? (
              <div className="flex items-center gap-2 text-gray-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Reading every document in your library…
              </div>
            ) : turn.error ? (
              <p className="text-rose-700">{turn.error}</p>
            ) : turn.answer ? (
              <LibraryAnswerBody
                answer={turn.answer}
                onCitationClick={onCitationClick}
              />
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function LibraryAnswerBody({
  answer,
  onCitationClick,
}: {
  answer: KnowledgeAnswer;
  onCitationClick: (c: SlideCitation) => void;
}) {
  // Match [Doc Name → Slide N] / [Doc Name → Page N] / [Doc Name → Section N]
  const re =
    /\[([^\]\[→\->]+?)\s*(?:→|->)\s*(Slide|Section|Page)\s+([\d,\s]+)\]/gi;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Build a lookup so chip clicks can resolve the citation back to its
  // deck (and slide number) from the parsed list.
  const citationByKey = new Map<string, SlideCitation>();
  for (const c of answer.citations) {
    if (c.deck_id) citationByKey.set(`${c.deck_id}-${c.slide_number}`, c);
  }

  while ((match = re.exec(answer.answer)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <Fragment key={`t-${lastIndex}`}>
          {answer.answer.slice(lastIndex, match.index)}
        </Fragment>,
      );
    }
    const docName = match[1].trim();
    const label = match[2];
    const numbers = match[3]
      .split(",")
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => Number.isFinite(n));

    parts.push(
      <span key={`c-${match.index}`} className="inline-flex flex-wrap gap-1">
        {numbers.map((n) => {
          // Resolve via citation list → get the deck_id for deep-link
          const matchedCit = answer.citations.find(
            (c) =>
              c.slide_number === n &&
              c.deck_name?.toLowerCase().includes(docName.toLowerCase()),
          );
          return (
            <button
              key={n}
              type="button"
              onClick={() =>
                matchedCit && onCitationClick(matchedCit)
              }
              className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-1.5 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-brand-200 transition hover:bg-brand-100"
              title={`Open ${docName}`}
            >
              {docName.length > 24 ? docName.slice(0, 24) + "…" : docName}{" "}
              · {label} {n}
            </button>
          );
        })}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < answer.answer.length) {
    parts.push(
      <Fragment key="t-end">{answer.answer.slice(lastIndex)}</Fragment>,
    );
  }

  return (
    <div>
      <p className="whitespace-pre-wrap">{parts}</p>
      {answer.truncated_decks && answer.truncated_decks.length > 0 && (
        // Soft warning when library size exceeded Claude's context budget.
        // We tell the user exactly what was skipped + how to scope to fit.
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/60 p-2.5 text-[11px] text-amber-900">
          <span className="mt-0.5 shrink-0 text-amber-600">⚠</span>
          <span>
            <span className="font-medium">
              {answer.truncated_decks.length} document
              {answer.truncated_decks.length === 1 ? "" : "s"} skipped
            </span>{" "}
            because the library exceeded the context limit:{" "}
            {answer.truncated_decks.slice(0, 3).join(", ")}
            {answer.truncated_decks.length > 3 &&
              ` +${answer.truncated_decks.length - 3} more`}
            . Narrow with a folder or tag filter to include them.
          </span>
        </div>
      )}
    </div>
  );
}

/* ─── Folder pill ──────────────────────────────────────────────────────── */

function FolderPill({
  label,
  active,
  onClick,
  icon,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition ${
        active
          ? "bg-brand-600 text-white shadow-sm"
          : "bg-white text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50 hover:ring-brand-300"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

/* ─── Deck card ────────────────────────────────────────────────────────── */

function DeckCard({
  deck,
  editing,
  folderInput,
  suggesting,
  onStartFolderEdit,
  onCancelFolderEdit,
  onFolderInputChange,
  onSaveFolder,
  onSuggestFolder,
  onFolderClick,
}: {
  deck: SlideDeckSummary;
  editing: boolean;
  folderInput: string;
  suggesting: boolean;
  onStartFolderEdit: () => void;
  onCancelFolderEdit: () => void;
  onFolderInputChange: (v: string) => void;
  onSaveFolder: () => void;
  onSuggestFolder: () => void;
  onFolderClick: () => void;
}) {
  return (
    <div className="group rounded-xl border border-gray-200 bg-white p-5 transition hover:border-brand-300 hover:shadow-card-hover">
      <div className="flex items-start justify-between gap-3">
        <Link
          href={`/knowledge/${deck.id}`}
          className="min-w-0 flex-1"
        >
          <h3 className="truncate text-base font-semibold text-gray-900 group-hover:text-brand-700">
            {deck.name}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${contentTypeBadge[deck.content_type]}`}
            >
              {contentTypeLabel[deck.content_type]}
            </span>
            <span className="inline-flex items-center gap-1">
              <Layers className="h-3 w-3 shrink-0" />
              {deck.slide_count} {chunkLabelPlural[deck.content_type]}
            </span>
          </div>
          {deck.description && (
            <p className="mt-2 line-clamp-2 text-sm text-gray-600">
              {deck.description}
            </p>
          )}
        </Link>
        <ChevronRight className="h-5 w-5 shrink-0 text-gray-300 transition-colors group-hover:text-brand-600" />
      </div>

      {/* Folder + tags row */}
      <div
        className="mt-3 flex flex-wrap items-center gap-1.5"
        onClick={(e) => e.stopPropagation()}
      >
        {editing ? (
          <div className="flex w-full items-center gap-1.5">
            <Folder className="h-3.5 w-3.5 text-gray-400" />
            <input
              type="text"
              value={folderInput}
              onChange={(e) => onFolderInputChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  onSaveFolder();
                } else if (e.key === "Escape") {
                  onCancelFolderEdit();
                }
              }}
              placeholder="e.g. Reports/2026/Q1"
              autoFocus
              className="flex-1 rounded-md border border-brand-300 bg-white px-2 py-0.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
            <button
              type="button"
              onClick={onSaveFolder}
              className="rounded-md bg-brand-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-brand-700"
            >
              Save
            </button>
            <button
              type="button"
              onClick={onCancelFolderEdit}
              className="rounded-md px-2 py-0.5 text-[11px] text-gray-500 hover:text-gray-800"
            >
              Cancel
            </button>
          </div>
        ) : (
          <>
            {deck.folder ? (
              <button
                type="button"
                onClick={onFolderClick}
                className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200 transition hover:bg-amber-100"
                title="Filter library by this folder"
              >
                <Folder className="h-3 w-3" />
                {deck.folder}
              </button>
            ) : (
              <button
                type="button"
                onClick={onStartFolderEdit}
                className="inline-flex items-center gap-1 rounded-full border border-dashed border-gray-200 px-2 py-0.5 text-[11px] font-medium text-gray-400 hover:border-brand-300 hover:text-brand-700"
              >
                <Folder className="h-3 w-3" />
                Add to folder
              </button>
            )}
            {deck.tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2 py-0.5 text-[11px] font-medium text-gray-700 ring-1 ring-gray-200"
              >
                <Tag className="h-2.5 w-2.5" />
                {t}
              </span>
            ))}
            <span className="ml-auto flex items-center gap-1.5 opacity-0 transition group-hover:opacity-100">
              <button
                type="button"
                onClick={onStartFolderEdit}
                className="text-[11px] text-gray-500 hover:text-brand-700"
              >
                {deck.folder ? "Move" : "Folder"}
              </button>
              <span className="text-gray-300">·</span>
              <button
                type="button"
                onClick={onSuggestFolder}
                disabled={suggesting}
                className="inline-flex items-center gap-1 text-[11px] text-gray-500 hover:text-brand-700 disabled:opacity-50"
                title="Have DOCex suggest a folder"
              >
                {suggesting ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Thinking…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3 w-3" />
                    Suggest
                  </>
                )}
              </button>
            </span>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Empty state ──────────────────────────────────────────────────────── */

function EmptyState() {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-100">
        <BookOpen className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">
        Start building your library
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        Drop in your first document — a slide deck, a Word proposal, a PDF
        policy. The library becomes searchable the moment the first file
        lands.
      </p>
      <Link
        href="/knowledge/new"
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-brand-100 transition hover:bg-brand-700"
      >
        <Sparkles className="h-4 w-4" />
        Add your first document
      </Link>
      <p className="mt-4 text-xs text-gray-400">
        PowerPoint, Word, or PDF · cross-document chat as soon as you have 2+
      </p>
    </div>
  );
}
