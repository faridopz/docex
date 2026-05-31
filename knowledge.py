"""
DOCex Knowledge Hub — Claude-powered Q&A over slide decks.

Given a deck and a user question, returns a KnowledgeAnswer with a
natural-language reply that includes inline [Slide N] citation markers
plus a parsed list of SlideCitation objects with short excerpts so the
frontend can render the citations as clickable chips.

Why slide-N citations: the user MUST be able to verify Claude's claim
against the original. NGO check-in decks are full of indicator numbers
and state-by-state percentages that have to be defensible. A hallucinated
answer with no citation is worse than no answer.

Prompt strategy:
  - System message tells Claude it's reading a slide deck and MUST cite
  - User message includes the full deck-as-context + the question
  - Claude returns plain text with [Slide N] markers
  - Post-processing extracts the markers + finds excerpts from the
    referenced slides

Cost note: each chat call is one Claude Sonnet 4.6 invocation. With a
67-slide deck (~30KB of context) + a question + response, that's
roughly $0.03 per question. For a power user asking 50 questions/day
across the team, that's $1.50/day, $45/month — well within the Pro
tier's economics.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import anthropic

from models import KnowledgeAnswer, SlideCitation, SlideDeck
from slides import chunk_label_for, deck_to_context

logger = logging.getLogger(__name__)

# Explicit timeout — see assistant.py for the rationale. Library-wide chat
# can run up to ~30s on a full 100-document library; 180s gives generous
# margin while preventing hangs on Anthropic side effects.
_client = anthropic.Anthropic(timeout=180.0)
_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1500


_SYSTEM_PROMPT_TEMPLATE = """You are the DOCex Knowledge Assistant. You \
answer questions about a single document the user has uploaded — a slide \
deck, a Word document, or a PDF. The document content is provided in full \
in the user message, chunked into navigable pieces with clear \
"=== {LABEL} N ===" headers.

Your job:
  1. Read every {LABEL_LOWER} in the document before answering.
  2. Answer the user's question concisely, in plain English. 2-4 \
     sentences is the sweet spot for most questions; longer is fine when \
     the answer truly is longer.
  3. Cite EVERY claim you make. Use the format [{LABEL} N] inline, attached \
     to the claim it supports. Multiple references are fine: [{LABEL} 4, {LABEL} 7].
  4. If the document doesn't contain the answer, say so explicitly. Do NOT \
     speculate or pull from external knowledge — the user trusts you to be \
     faithful to the source. A clear "this document doesn't cover that" is \
     more valuable than a guess.
  5. When the question is about numbers (percentages, counts, indicator \
     values), quote the exact figures from the document. Don't paraphrase.
  6. Tables and speaker notes (where present) count as part of the content — \
     use them.

Tone: confident, friendly, no fluff. No "I'd be happy to" preamble. Just \
answer.

Format: plain text. No markdown headers. No bullet lists unless the \
question explicitly calls for one. The frontend renders citations as \
chips automatically — you just need to include the [{LABEL} N] markers.

Examples of well-formed answers:
  "Coverage in Lagos is 78% as of March 2026 [{LABEL} 11], up from 62% in \
  the previous quarter [{LABEL} 12]. Bauchi is lagging at 41% [{LABEL} 11]."

  "The document doesn't include action items for next quarter. You may be \
  thinking of a different file."
"""


# The same [Slide N] / [Section N] / [Page N] vocabulary needs to be parsed
# back out of the answer text. One pattern handles all three.
_CITATION_PATTERN = re.compile(
    r"\[(?:Slide|Section|Page)\s+(\d+(?:\s*,\s*\d+)*)\]",
    re.IGNORECASE,
)

# Library-wide citation pattern. Format:
#   [Document Name → Slide 4]
#   [Document Name → Page 7, Page 9]
#   [Document Name → Section 2]
# The arrow can be → or -> (Claude sometimes substitutes). The label can
# be Slide / Page / Section. The number group accepts multiple comma-
# separated values for grouped citations.
_LIBRARY_CITATION_PATTERN = re.compile(
    r"\[([^\]\[→\->]+?)\s*(?:→|->)\s*(?:Slide|Section|Page)\s+(\d+(?:\s*,\s*(?:Slide|Section|Page)?\s*\d+)*)\]",
    re.IGNORECASE,
)


_LIBRARY_SYSTEM_PROMPT = """You are the DOCex Library Assistant. You answer \
questions across the user's ENTIRE document library — multiple slide decks, \
Word documents, and PDFs at once. The library is provided in full in the \
user message, split by clear "# DOCUMENT: <name>" headers. Each document \
internally uses "=== Slide N ===" / "=== Section N ===" / "=== Page N ===" \
headers as before.

Your job:
  1. Read every document. Don't assume you know what's in any of them \
     before reading.
  2. Answer the user's question by synthesising across documents — pull \
     from whichever sources are relevant. The whole point is cross-corpus \
     understanding, not single-doc Q&A.
  3. Cite EVERY claim with the format [Document Name → Slide N], \
     [Document Name → Page N], or [Document Name → Section N] inline. \
     Multiple citations: [Doc A → Slide 4, Doc B → Page 7].
  4. If the answer is split across documents, name each source explicitly. \
     The user trusts you to attribute correctly.
  5. If no document covers the question, say so. Do NOT speculate or use \
     external knowledge. A clear "your library doesn't cover that" is more \
     valuable than a guess.

Tone: confident, friendly, no fluff. No "I'd be happy to" preamble.

Format: plain text. Synthesise into 2-5 sentences for most questions; \
longer is fine when the answer truly is longer. The frontend renders \
citations as chips automatically — just include the [Doc Name → Slide N] \
markers verbatim.

Examples of well-formed answers:
  "Bauchi PPH coverage is 41% as of March 2026 [Gates Check-in March → \
  Slide 11], well below the 67% regional median. The cause appears to be \
  uterotonic stockouts [Gates Check-in March → Slide 28]. Disbursements \
  above ₦500k require three quotes per the org's procurement policy \
  [Anti-Fraud Policy → Page 4]."

  "Your library doesn't include any documents about the Q4 2025 budget. \
  The most recent budget reference I found is Q2 2025 [CHAI Gombe Report \
  → Section 3]."
"""


def library_ask(question: str, decks: list[SlideDeck]) -> KnowledgeAnswer:
    """
    Ask one question across an entire library of documents.

    Stuffs every document's parsed content into Claude's context as one
    big multi-document blob, then asks. Returns a KnowledgeAnswer whose
    citations carry deck_id + deck_name so the frontend can deep-link
    citation chips to the right document.

    Scale note: Claude Sonnet 4.6 handles ~200K input tokens. Typical NGO
    documents land at ~5-15KB of extracted text each, so the library can
    hold ~80-100 documents before we have to start filtering/summarising.
    When we hit that ceiling, the natural next step is semantic retrieval
    (pgvector) — but that's a Phase 2 problem, not a Phase 1 blocker.
    """
    if not question.strip():
        return KnowledgeAnswer(
            question=question,
            answer="I need a question to search for. What would you like to know?",
            citations=[],
            deck_id="library",
            deck_name="Library",
            error="empty question",
            created_at=_now_iso(),
        )

    if not decks:
        return KnowledgeAnswer(
            question=question,
            answer="Your library is empty. Upload some documents first and I can search across all of them.",
            citations=[],
            deck_id="library",
            deck_name="Library",
            error="empty library",
            created_at=_now_iso(),
        )

    # Build one big context blob, document by document. Each document gets
    # its existing deck_to_context() treatment, prefixed by a clear name
    # header so Claude knows what to cite as.
    parts: list[str] = []
    total_chars = 0
    truncated_decks: list[str] = []
    char_budget = 180_000  # leave ~20K margin for prompt + question
    for d in decks:
        block = deck_to_context(d, max_chars=char_budget - total_chars - 1000)
        if not block:
            continue
        if total_chars + len(block) > char_budget:
            # We've hit the budget. Skip any remaining docs and tell the
            # user — better to be transparent than silently lose context.
            truncated_decks.append(d.name)
            continue
        parts.append(block)
        total_chars += len(block)

    library_context = "\n\n---\n\n".join(parts)
    if truncated_decks:
        library_context += (
            f"\n\n[Note: {len(truncated_decks)} document(s) skipped due to "
            f"context limit: {', '.join(truncated_decks[:3])}"
            + (f" +{len(truncated_decks) - 3} more" if len(truncated_decks) > 3 else "")
            + "]"
        )

    user_msg = (
        f"Here is the library — {len(parts)} documents. Answer the question "
        f"that follows.\n\n```\n{library_context}\n```\n\nQUESTION: {question.strip()}"
    )

    try:
        response = _client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_LIBRARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        answer_text = response.content[0].text.strip()
    except Exception as exc:
        logger.warning(f"Library ask failed: {exc}")
        return KnowledgeAnswer(
            question=question,
            answer="I couldn't reach Claude to search your library. Try again in a moment — your documents are still saved.",
            citations=[],
            deck_id="library",
            deck_name="Library",
            error=str(exc),
            created_at=_now_iso(),
        )

    citations = _extract_library_citations(answer_text, decks)

    return KnowledgeAnswer(
        question=question,
        answer=answer_text,
        citations=citations,
        deck_id="library",
        deck_name="Library",
        error=None,
        created_at=_now_iso(),
        truncated_decks=truncated_decks,
    )


def _extract_library_citations(
    answer_text: str, decks: list[SlideDeck]
) -> list[SlideCitation]:
    """Parse [Doc Name → Slide N] markers into SlideCitation records with
    deck_id back-resolved so the chip can deep-link to the right document.

    Matches are case-insensitive and tolerate small variations in the
    document name (Claude sometimes shortens or normalises whitespace).
    Falls back to substring matching when the exact name doesn't match.
    """
    decks_by_name = {d.name.lower(): d for d in decks}
    decks_list = list(decks)
    citations: list[SlideCitation] = []
    seen: set[tuple[str, int]] = set()

    for match in _LIBRARY_CITATION_PATTERN.finditer(answer_text):
        raw_name = match.group(1).strip()
        # Resolve the deck — exact lowercase match first, then substring fallback
        deck = decks_by_name.get(raw_name.lower())
        if deck is None:
            # Substring fallback — Claude may have shortened "Anti-Fraud Policy"
            # to "Anti-Fraud" or similar.
            lower_name = raw_name.lower()
            for d in decks_list:
                if (
                    lower_name in d.name.lower()
                    or d.name.lower() in lower_name
                ):
                    deck = d
                    break
        if deck is None:
            # Couldn't resolve; skip silently — better than rendering a
            # broken chip. The text citation in the answer still reads fine.
            continue

        # Pull all the numbers out of the second group
        for raw_n in re.findall(r"\d+", match.group(2)):
            try:
                n = int(raw_n)
            except ValueError:
                continue
            key = (deck.id, n)
            if key in seen:
                continue
            seen.add(key)

            # Best-effort excerpt
            slide = next((s for s in deck.slides if s.number == n), None)
            excerpt = None
            if slide:
                if slide.title:
                    excerpt = slide.title[:100]
                elif slide.body:
                    excerpt = slide.body[0][:100]
                elif slide.table_text:
                    excerpt = slide.table_text[0][:100]

            citations.append(
                SlideCitation(
                    slide_number=n,
                    excerpt=excerpt,
                    deck_id=deck.id,
                    deck_name=deck.name,
                )
            )

    return citations


def ask(deck: SlideDeck, question: str) -> KnowledgeAnswer:
    """
    Ask a question about a deck. Returns a KnowledgeAnswer.

    On any failure (network, API, parse), returns an answer with the
    error field populated and a graceful message in the answer field —
    never raises. The UI surfaces it as an inline error chip.
    """
    if not question.strip():
        return KnowledgeAnswer(
            question=question,
            answer="I need a question to answer — give me something specific to look for in the deck.",
            citations=[],
            deck_id=deck.id,
            deck_name=deck.name,
            error="empty question",
            created_at=_now_iso(),
        )

    context = deck_to_context(deck)

    # Pick the chunk vocabulary that matches the document's format. The
    # PPTX context blob uses "=== Slide N ===" headers (legacy default);
    # DOCX uses "=== Section N ==="; PDF uses "=== Page N ===". The system
    # prompt below tells Claude which label to use in citations so we get
    # round-trip-able citation markers.
    label = chunk_label_for(deck.content_type)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.replace("{LABEL}", label).replace(
        "{LABEL_LOWER}", label.lower()
    )

    user_msg = (
        f"Here is the document. Answer the question that follows.\n\n"
        f"```\n{context}\n```\n\n"
        f"QUESTION: {question.strip()}"
    )

    try:
        response = _client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        answer_text = response.content[0].text.strip()
    except Exception as exc:
        logger.warning(f"Knowledge ask failed: {exc}")
        return KnowledgeAnswer(
            question=question,
            answer="I couldn't reach Claude to answer this. Try again in a moment — your deck is still saved.",
            citations=[],
            deck_id=deck.id,
            deck_name=deck.name,
            error=str(exc),
            created_at=_now_iso(),
        )

    citations = _extract_citations(answer_text, deck)

    return KnowledgeAnswer(
        question=question,
        answer=answer_text,
        citations=citations,
        deck_id=deck.id,
        deck_name=deck.name,
        error=None,
        created_at=_now_iso(),
    )


def _extract_citations(answer_text: str, deck: SlideDeck) -> list[SlideCitation]:
    """
    Pull every [Slide N] marker out of the answer and build SlideCitation
    records with short excerpts from the referenced slide. De-duplicates
    by slide number — the same slide cited twice produces one citation.
    """
    seen: dict[int, SlideCitation] = {}
    slides_by_number = {s.number: s for s in deck.slides}

    for match in _CITATION_PATTERN.finditer(answer_text):
        # The group can be "4" or "4, 7" — split and process each.
        for raw in match.group(1).split(","):
            try:
                n = int(raw.strip())
            except ValueError:
                continue
            if n in seen:
                continue
            slide = slides_by_number.get(n)
            excerpt = None
            if slide:
                # Best-effort excerpt: prefer title, then first body line,
                # then first table row. Capped at 100 chars.
                if slide.title:
                    excerpt = slide.title[:100]
                elif slide.body:
                    excerpt = slide.body[0][:100]
                elif slide.table_text:
                    excerpt = slide.table_text[0][:100]
            seen[n] = SlideCitation(slide_number=n, excerpt=excerpt)

    return list(seen.values())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
