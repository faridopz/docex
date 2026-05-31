"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  FormEvent,
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowLeft,
  ArrowUp,
  BookOpen,
  Layers,
  Loader2,
  Sparkles,
  Tag,
  Trash2,
} from "lucide-react";
import { chatWithDeck, deleteDeck, getDeck } from "@/lib/api";
import type { KnowledgeAnswer, Slide, SlideDeck } from "@/types";
import {
  chunkLabel,
  chunkLabelPlural,
  contentTypeBadge,
  contentTypeLabel,
} from "@/types";

/**
 * /knowledge/[id] — the chat-with-slides interface.
 *
 * Two-column layout (collapses on mobile):
 *   Left: chat thread + composer. The product surface.
 *   Right: slide list with title + body preview. Clicking a [Slide N] chip
 *          on any answer scrolls the right pane to that slide and pulses it.
 *
 * The chat is in-memory — the whole conversation lives in component state.
 * When a question is asked, the prior context isn't sent (each call is
 * stateless on the server). That's deliberate for MVP: scoping each
 * question to the deck content keeps Claude focused. Threaded follow-ups
 * with conversational memory are a Phase 2 add.
 *
 * Citations: the answer text contains [Slide N] markers. We parse them
 * client-side and render each as a small chip next to (or inside) the
 * answer. Clicking a chip scrolls the slide pane.
 */

type ChatTurn = {
  id: string;
  question: string;
  answer: KnowledgeAnswer | null;
  loading: boolean;
  error: string | null;
};

export default function DeckChatPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [deck, setDeck] = useState<SlideDeck | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [activeSlide, setActiveSlide] = useState<number | null>(null);

  const slidesByNumber = useMemo(() => {
    const m: Record<number, Slide> = {};
    if (deck) for (const s of deck.slides) m[s.number] = s;
    return m;
  }, [deck]);

  // Refs for scrolling the slide pane when a citation is clicked.
  const slideRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await getDeck(id);
        if (!cancelled) setDeck(d);
      } catch (err) {
        if (!cancelled)
          setLoadError(
            err instanceof Error ? err.message : "Could not load this deck.",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Auto-scroll the chat to the latest turn whenever turns change.
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  async function submitQuestion(e: FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || !deck) return;
    const turnId = Math.random().toString(36).slice(2);
    setTurns((t) => [
      ...t,
      { id: turnId, question: q, answer: null, loading: true, error: null },
    ]);
    setInput("");
    try {
      const a = await chatWithDeck(id, q);
      setTurns((t) =>
        t.map((x) => (x.id === turnId ? { ...x, answer: a, loading: false } : x)),
      );
    } catch (err) {
      setTurns((t) =>
        t.map((x) =>
          x.id === turnId
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

  function scrollToSlide(n: number) {
    setActiveSlide(n);
    const el = slideRefs.current[n];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      // Briefly highlight then fade — handled by `data-active` styling.
      setTimeout(() => setActiveSlide((cur) => (cur === n ? null : cur)), 2400);
    }
  }

  async function handleDelete() {
    if (!deck) return;
    const ok = window.confirm(
      `Delete "${deck.name}"? The deck and any saved chat history will be removed.`,
    );
    if (!ok) return;
    try {
      await deleteDeck(id);
      router.push("/knowledge");
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not delete the deck.",
      );
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf7]">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-[#fafaf7]/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-6">
          <Link
            href="/knowledge"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-gray-900">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <BookOpen className="h-4 w-4 text-brand-600" />
            {deck ? deck.name : "Knowledge Hub"}
          </span>
          <button
            type="button"
            onClick={handleDelete}
            disabled={!deck}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs font-medium text-gray-500 transition hover:border-rose-300 hover:text-rose-700 disabled:opacity-50"
            title="Delete this deck"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {loadError}
          </div>
        )}

        {!deck && !loadError && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading deck…
          </div>
        )}

        {deck && (
          <div className="grid h-[calc(100vh-10rem)] gap-6 lg:grid-cols-[1fr_22rem]">
            {/* ─── Left: chat ─────────────────────────────────────────── */}
            <section className="flex min-h-0 flex-col">
              {/* Deck header */}
              <div className="mb-4">
                <h1 className="text-2xl font-semibold tracking-tight text-gray-900">
                  {deck.name}
                </h1>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${contentTypeBadge[deck.content_type]}`}
                  >
                    {contentTypeLabel[deck.content_type]}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Layers className="h-3 w-3" />
                    {deck.slide_count} {chunkLabelPlural[deck.content_type]}
                  </span>
                  {deck.tags.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-100"
                    >
                      <Tag className="h-2.5 w-2.5" />
                      {t}
                    </span>
                  ))}
                </div>
                {deck.description && (
                  <p className="mt-2 text-sm text-gray-600">{deck.description}</p>
                )}
              </div>

              {/* Chat thread */}
              <div className="flex-1 overflow-y-auto rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                {turns.length === 0 ? (
                  <EmptyChat deck={deck} />
                ) : (
                  <div className="space-y-6">
                    {turns.map((t) => (
                      <Turn
                        key={t.id}
                        turn={t}
                        deck={deck}
                        onCitationClick={scrollToSlide}
                      />
                    ))}
                    <div ref={chatEndRef} />
                  </div>
                )}
              </div>

              {/* Composer */}
              <form
                onSubmit={submitQuestion}
                className="mt-4 flex items-end gap-2 rounded-2xl border border-gray-200 bg-white p-2 shadow-sm focus-within:border-brand-300 focus-within:ring-2 focus-within:ring-brand-100"
              >
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void submitQuestion(e as unknown as FormEvent);
                    }
                  }}
                  rows={1}
                  placeholder="Ask anything about this deck… (e.g. 'Which states have the lowest PPH coverage?')"
                  className="flex-1 resize-none border-0 bg-transparent px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="inline-flex shrink-0 items-center justify-center rounded-lg bg-brand-600 p-2.5 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
                  title="Ask"
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              </form>
            </section>

            {/* ─── Right: chunk list ──────────────────────────────────── */}
            <aside className="hidden min-h-0 flex-col overflow-y-auto rounded-2xl border border-gray-200 bg-white shadow-sm lg:flex">
              <div className="sticky top-0 border-b border-gray-100 bg-white px-5 py-3">
                <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
                  {chunkLabelPlural[deck.content_type]}
                </p>
              </div>
              <div className="flex-1 divide-y divide-gray-100">
                {deck.slides.map((s) => (
                  <SlideRow
                    key={s.number}
                    slide={s}
                    active={activeSlide === s.number}
                    onClick={() => scrollToSlide(s.number)}
                    refCallback={(el) => (slideRefs.current[s.number] = el)}
                  />
                ))}
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}

/* ─── Chat turn ────────────────────────────────────────────────────────── */

function Turn({
  turn,
  deck,
  onCitationClick,
}: {
  turn: ChatTurn;
  deck: SlideDeck;
  onCitationClick: (slideNumber: number) => void;
}) {
  return (
    <div className="space-y-3">
      {/* User question */}
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm">
          {turn.question}
        </div>
      </div>

      {/* Assistant answer */}
      <div className="flex justify-start">
        <div className="flex w-full max-w-[92%] items-start gap-2.5">
          <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-100">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-gray-100 bg-gray-50/60 px-4 py-3 text-sm leading-relaxed text-gray-800">
            {turn.loading ? (
              <div className="flex items-center gap-2 text-gray-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Reading {turn.question.length > 50 ? "the deck" : "every slide"}…
              </div>
            ) : turn.error ? (
              <p className="text-rose-700">{turn.error}</p>
            ) : turn.answer ? (
              <AnswerBody
                answer={turn.answer}
                deck={deck}
                onCitationClick={onCitationClick}
              />
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Renders the answer text with [Slide N] / [Page N] / [Section N] markers
 * replaced by inline clickable chips. The regex matches any of the three
 * vocab variants; the chip label uses the deck's content_type so an
 * answer about a PDF says "Page 7" and a Word doc answer says "Section 2".
 */
function AnswerBody({
  answer,
  deck,
  onCitationClick,
}: {
  answer: KnowledgeAnswer;
  deck: SlideDeck;
  onCitationClick: (n: number) => void;
}) {
  const label = chunkLabel[deck.content_type];

  // Match [Slide|Page|Section N] or [Slide|Page|Section N, M, ...]
  const re = /\[(?:Slide|Page|Section)\s+([\d,\s]+)\]/gi;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(answer.answer)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <Fragment key={`t-${lastIndex}`}>
          {answer.answer.slice(lastIndex, match.index)}
        </Fragment>,
      );
    }
    const slideNumbers = match[1]
      .split(",")
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => Number.isFinite(n));
    parts.push(
      <span key={`c-${match.index}`} className="inline-flex flex-wrap gap-1">
        {slideNumbers.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onCitationClick(n)}
            className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-1.5 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-brand-200 transition hover:bg-brand-100"
            title={`Jump to ${label.toLowerCase()} ${n}`}
          >
            {label} {n}
          </button>
        ))}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < answer.answer.length) {
    parts.push(
      <Fragment key={`t-end`}>{answer.answer.slice(lastIndex)}</Fragment>,
    );
  }

  return (
    <div>
      <p className="whitespace-pre-wrap">{parts}</p>
      {answer.error && (
        <p className="mt-2 text-xs text-rose-600">
          The Assistant flagged an error: {answer.error}
        </p>
      )}
    </div>
  );
}

/* ─── Slide pane ───────────────────────────────────────────────────────── */

function SlideRow({
  slide,
  active,
  onClick,
  refCallback,
}: {
  slide: Slide;
  active: boolean;
  onClick: () => void;
  refCallback: (el: HTMLDivElement | null) => void;
}) {
  return (
    <div
      ref={refCallback}
      onClick={onClick}
      className={`cursor-pointer px-5 py-3 transition ${
        active
          ? "bg-brand-50 ring-1 ring-inset ring-brand-200"
          : "hover:bg-gray-50/80"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex h-5 min-w-[1.75rem] items-center justify-center rounded-md bg-gray-100 px-1.5 text-[11px] font-semibold tabular-nums text-gray-600">
          {slide.number}
        </span>
        <p className="truncate text-sm font-medium text-gray-900">
          {slide.title ?? "(no title)"}
        </p>
      </div>
      {slide.body.length > 0 && (
        <p className="mt-1 line-clamp-2 pl-9 text-[11px] text-gray-500">
          {slide.body.slice(0, 2).join(" · ")}
        </p>
      )}
    </div>
  );
}

/* ─── Empty chat ──────────────────────────────────────────────────────── */

function EmptyChat({ deck }: { deck: SlideDeck }) {
  // Format-tuned vocabulary + example questions so the chat empty state
  // doesn't suggest "compare states" for a Word proposal or "summarise
  // action items" for a 200-page policy PDF.
  const label = chunkLabel[deck.content_type];
  const noun = {
    pptx: "deck",
    docx: "document",
    pdf: "PDF",
  }[deck.content_type];

  const examples: Record<typeof deck.content_type, string[]> = {
    pptx: [
      "What states / regions are covered here?",
      "Summarise the key action items.",
      "Which indicators are flagged or behind target?",
      "What are the three biggest themes?",
    ],
    docx: [
      "Summarise the key findings in this report.",
      "List every deliverable and its deadline.",
      "What recommendations does the author make?",
      "Are there any risks or gaps flagged?",
    ],
    pdf: [
      "Summarise this document in plain English.",
      "What are the most important sections to read?",
      "List every defined term and its meaning.",
      "What does this say about approvals or sign-off?",
    ],
  };

  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <div className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-100">
        <Sparkles className="h-7 w-7" />
      </div>
      <h2 className="mt-5 text-lg font-semibold text-gray-900">
        Ask anything about this {noun}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        DOCex has read every {label.toLowerCase()} — titles, body text, tables
        {deck.content_type === "pptx" ? ", and speaker notes" : ""}. Answers
        come back with{" "}
        <span className="font-medium text-gray-900">
          [{label} N] citations
        </span>{" "}
        you can click to verify.
      </p>
      <div className="mt-6 grid w-full max-w-md gap-2 text-left">
        {examples[deck.content_type].map((q) => (
          <div
            key={q}
            className="rounded-lg border border-dashed border-gray-200 bg-gray-50/40 px-3 py-2 text-xs text-gray-500"
          >
            <span className="text-gray-400">Try:</span> {q}
          </div>
        ))}
      </div>
    </div>
  );
}
