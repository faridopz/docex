"""
DOCex extraction engine.

Core function: extract_from_documents()
  - Takes a list of documents (all belonging to ONE applicant)
  - Takes a list of questions the user wants answered
  - Reads all documents together and answers every question
  - Returns structured answers with source, quote, and confidence

The system prompt is cached with cache_control so that repeated calls
within a session (batch mode, same questions) only bill the document
tokens, not the instructions.
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
import traceback
from typing import Optional

import anthropic
from ai_config import EXTRACTION_MODEL
from models import ApplicantExtraction, ExtractionAnswer, Question

logger = logging.getLogger(__name__)

# Tune this if you start hitting Anthropic rate limits. The demo workload
# (3–5 partners) sits well under, but TA Connect's full 20-partner cycle
# may want this lowered or made adaptive.
_BATCH_MAX_PARALLEL = 5

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazily construct the Anthropic client on first use.

    Constructing at import time would crash the whole API on startup when
    ANTHROPIC_API_KEY isn't set — taking down non-AI endpoints too. Lazy
    init lets the backend boot regardless; only the actual AI call fails if
    the key is missing.
    """
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

_SYSTEM_PROMPT = """You are a document extraction specialist for NGO partner screening in Nigeria.

You support sub-award teams who must shortlist partner organisations from large
piles of application documents — registration certificates, audit reports,
organisational profiles, financial statements, proposals, policy documents.
The people relying on your output are grants officers working under deadline.
Accuracy matters more than speed. A wrong answer is worse than no answer.

## Your task
You will be given:
1. A set of documents belonging to ONE applicant organisation.
2. A list of questions to answer about that organisation.

Read ALL the documents carefully before answering ANY question. Information
relevant to one question is often spread across several documents — for example,
a CAC registration number may appear in the certificate, the organisational
profile, and the audit report. Do not answer from the first document you see;
read everything first, then answer.

## How to answer each question
For every question, return an object with:
- question_id      — the id provided in brackets in the question list
- question_text    — the question as given
- answer           — the extracted answer in plain language.
                     Formatting rules:
                       • For a single fact, write ONE short sentence.
                         e.g. "The organisation is registered with CAC."
                       • For multiple items (a list of states, achievements,
                         activities, indicators, risks, etc.), put EACH ITEM
                         ON ITS OWN LINE prefixed with "- ".
                         e.g. "- Kano\n- Lagos\n- Borno"
                              "- Enrolled 64,981 women in G-ANC\n"
                              "- ANC 4th visit attendance up 34% to 50%\n"
                              "- IPT4 uptake up 27% to 58%"
                       • Do NOT use inline "(1)... (2)... (3)..." numbering
                         pretending to be a list. Use real newlines.
                       • Never write a paragraph. Never explain in prose
                         what should be a list.
- confidence       — one of: "found", "inferred", "not_found"
- source_document  — the exact filename you took the answer from
- quote            — the verbatim excerpt from that document that supports
                     the answer (copy it word-for-word, preserving casing)
- source_page      — the page number from the === PAGE N === marker the quote
                     came from. If the document has no page markers (DOCX or
                     TXT), set source_page to null.
- search_notes     — reasoning trail showing what you searched for and what
                     you found or did not find. See the "Showing your work"
                     section below for when to populate this field.

## Confidence levels — use these strictly
- "found"     — the answer is explicitly stated in a document. The quote
                directly contains the answer.
- "inferred"  — the answer is not stated outright but can be reasonably
                concluded from context in the documents (e.g. the proposal
                says "we have operated in Kano, Lagos and Borno since 2018"
                — the states they work in can be inferred even if no
                document has a heading called "states of operation").
- "not_found" — the information is not mentioned anywhere in any document.
                In this case set answer, source_document, and quote to null.

If you are not sure whether something is "found" or "inferred", choose
"inferred". If you are not sure whether something is "inferred" or
"not_found", choose "not_found". When in doubt, do less.

## Showing your work — search_notes
For every answer, you must demonstrate that you actually reviewed the
documents. The search_notes field exposes your reasoning. Rules:

- When confidence is "found": the verbatim quote and page number ARE your
  evidence. Leave search_notes as null (or a single sentence if a brief
  context note adds value).

- When confidence is "inferred": populate search_notes with one sentence
  explaining the inference. Example:
  "The proposal lists offices in Abuja (FCT), Kaduna, Kwara, Borno, Osun,
  and Lagos on page 3 of the Technical Proposal, which implies operational
  presence in those states."

- When confidence is "not_found": leave answer, quote, source_document, and
  source_page as null, BUT populate search_notes with a clear note showing
  the search you performed. Examples:
  - "Searched all 5 documents (47 pages total). No mention of 'anti-fraud',
    'whistleblower', 'fraud prevention', or related procedures was found in
    any document."
  - "Reviewed the technical proposal (15 pages) and the M&E plan (12 pages).
    No explicit sustainability or scalability strategy was articulated, though
    the workplan does mention community engagement."
  - "Examined the budget and cost proposal. No specific allocation for
    community health worker training was identified, though the workplan
    lists training as an activity (page 4, Workplan)."

Be specific about what you looked for. Mention adjacent terms you searched.
Cite which documents you reviewed and how many pages. The search_notes field
is what makes a "not found" trustworthy — without it, the user cannot tell
whether DOCex actually looked or just gave up.

## Quote substance — not just titles
When a question asks whether something exists ("does the organisation have
an X policy?", "is the organisation registered?"), and the answer is yes,
the quote MUST come from the body of the document demonstrating the thing —
not the document's title or cover page. A title only proves a file with that
name exists; it does not prove the content is real or substantive. Prefer:
- A sentence from the policy's purpose, scope, or rules sections
- A sentence from the registration certificate body, not the header
- A specific commitment, definition, or procedure from inside the document

If the only place the information appears is the document title, lower the
confidence to "inferred" rather than "found".

## Rules — these are absolute
- Answer ONLY from what is written in the documents. Never use outside
  knowledge about Nigeria, the NGO sector, named organisations, or anything
  else. Your job is to extract, not to assess.
- Never make up information. Never guess. Never fill gaps with what seems
  likely. If it is not in the documents, the answer is "not_found".
- If multiple documents mention the same thing, cite the MOST SPECIFIC
  source. Prefer a registration certificate over a proposal's mention of
  registration; prefer an audit report over a self-description; prefer
  the document where the information is the primary subject.
- The quote must be a verbatim excerpt — do not paraphrase or summarise
  inside the quote field. The answer field may be paraphrased; the quote
  field never is.
- For list-type questions (states, focus areas, donors, staff counts),
  return all items found across the documents, not just the first one.
- The source_document must match an exact filename from the documents you
  were given. Never invent filenames.
- Concise answers. No commentary. No hedging language inside the answer
  field — confidence is expressed through the confidence level, not
  through phrases like "it appears that" or "possibly".
- Return exactly one answer object per question, in the same order as the
  questions were given.

## Context (when provided)
Some runs include a "WHAT THE FUNDER IS LOOKING FOR" block before the
documents. Use it ONLY to interpret the documents better — for example,
to recognise relevant items by the funder's vocabulary, or to disambiguate
which detail matters when several are mentioned. Do NOT use it to score,
rank, or judge the applicant. Do NOT mention the funder's preferences in
your answers. You are still extracting, not assessing."""


def _build_document_block(documents: list[tuple[str, str]]) -> str:
    """Format all documents into a single readable block for the prompt."""
    parts = []
    for filename, text in documents:
        parts.append(
            f"=== DOCUMENT: {filename} ===\n{text.strip()}\n=== END: {filename} ==="
        )
    return "\n\n".join(parts)


def _build_questions_block(questions: list[Question]) -> str:
    """Format questions as a numbered list for the prompt."""
    return "\n".join(f"{i+1}. [{q.id}] {q.text}" for i, q in enumerate(questions))


def extract_from_documents(
    documents: list[tuple[str, str]],  # (filename, text)
    questions: list[Question],
    applicant_name: str = "Applicant",
    context: Optional[str] = None,
) -> list[ExtractionAnswer]:
    """
    Extract answers to all questions from a set of documents.

    documents: list of (filename, extracted_text) tuples — all belonging
               to ONE applicant
    questions: list of Question objects
    context:   optional short paragraph from the funder describing what
               they are looking for. Used by Claude to interpret the
               documents better — never to score or rank the applicant.
    Returns:   list of ExtractionAnswer objects, one per question
    """

    # Pydantic schema Claude will fill in — a list of answers, one per question.
    class AnswerSet(anthropic.BaseModel):
        answers: list[ExtractionAnswer]

    doc_block = _build_document_block(documents)
    q_block = _build_questions_block(questions)

    # Optional context block — only added if the funder provided something
    context_block = ""
    if context and context.strip():
        context_block = (
            f"WHAT THE FUNDER IS LOOKING FOR:\n{context.strip()}\n\n"
        )

    user_message = f"""APPLICANT: {applicant_name}

{context_block}DOCUMENTS PROVIDED:
{doc_block}

QUESTIONS TO ANSWER:
{q_block}

Read every document carefully before answering. Answer every question based
strictly on the documents above. Return one answer object per question, using
the question_id from the brackets above. Use exact filenames as the
source_document. Quote verbatim."""

    # max_tokens sized for 20 structured answers with quotes + search_notes.
    # Each answer can be 300–600 tokens; with 20 questions we need headroom
    # well past the previous 8096 cap, which silently truncated big runs.
    response = _get_client().messages.parse(
        model=EXTRACTION_MODEL,
        max_tokens=16384,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                # Cache the instructions — they stay the same for every applicant
                # in a batch run. Only the documents and questions change.
                # Ephemeral cache means batch processing only pays full price
                # for the first applicant; the rest reuse the cached prompt.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
        output_format=AnswerSet,
    )

    if response.parsed_output is None:
        # Bubble up everything we can see — stop_reason tells us whether we
        # hit max_tokens, the model refused, or the schema couldn't be parsed.
        raise ValueError(
            f"Model could not parse output. Stop reason: {response.stop_reason}. "
            f"Usage: in={getattr(response.usage, 'input_tokens', '?')} "
            f"out={getattr(response.usage, 'output_tokens', '?')}."
        )

    # Fill in question_text from our questions list in case Claude omits it
    q_map = {q.id: q.text for q in questions}
    answers = response.parsed_output.answers
    for answer in answers:
        if not answer.question_text and answer.question_id in q_map:
            answer.question_text = q_map[answer.question_id]

    # Ensure we have one answer per question (fill missing ones as not_found)
    answered_ids = {a.question_id for a in answers}
    for q in questions:
        if q.id not in answered_ids:
            answers.append(ExtractionAnswer(
                question_id=q.id,
                question_text=q.text,
                answer=None,
                confidence="not_found",
                source_document=None,
                quote=None,
            ))

    return answers


def extract_applicant(
    applicant_id: str,
    applicant_name: str,
    documents: list[tuple[str, str]],  # (filename, text)
    questions: list[Question],
    context: Optional[str] = None,
) -> ApplicantExtraction:
    """
    Run full extraction for one applicant.
    Wraps extract_from_documents with error handling so a single bad
    applicant does not break a whole batch.
    """
    filenames = [fn for fn, _ in documents]
    try:
        answers = extract_from_documents(
            documents, questions, applicant_name, context=context
        )
        return ApplicantExtraction(
            applicant_id=applicant_id,
            applicant_name=applicant_name,
            documents=filenames,
            answers=answers,
        )
    except Exception as exc:
        # Log to the uvicorn terminal so the user actually sees what failed.
        # The exception is also bubbled into the response so the UI can show it.
        logger.error(
            "Extraction failed for applicant '%s' (id=%s): %s\n%s",
            applicant_name,
            applicant_id,
            exc,
            traceback.format_exc(),
        )
        print(
            f"\n[DOCex] Extraction failed for '{applicant_name}': {type(exc).__name__}: {exc}\n",
            flush=True,
        )
        return ApplicantExtraction(
            applicant_id=applicant_id,
            applicant_name=applicant_name,
            documents=filenames,
            answers=[],
            error=f"{type(exc).__name__}: {exc}",
        )


def extract_batch(
    applicants: list[dict],  # each: {id, name, documents: [(filename, text)]}
    questions: list[Question],
    context: Optional[str] = None,
) -> list[ApplicantExtraction]:
    """
    Run extraction for multiple applicants against the same question set.

    Strategy: HYBRID warmup + parallel fan-out.
      - The first applicant runs alone and writes the prompt cache on the
        Anthropic side (the system prompt is heavy and has cache_control:
        ephemeral set in extract_from_documents).
      - The remaining applicants run concurrently in a small thread pool.
        They all benefit from the cached system prompt, so each call only
        pays for its own document tokens AND completes much faster.
      - With N=3 applicants and ~60s per call, wall-clock drops from
        ~180s (sequential) to ~75-90s (1 warmup + 2 parallel).
      - The threads are I/O-bound (waiting on the HTTPS round-trip to
        Anthropic), so the GIL is not a bottleneck.

    The same context string is applied to every applicant in the batch,
    so a single funder description shapes interpretation across the run.
    Output order matches input order.
    """
    if not applicants:
        return []

    def _run(applicant: dict) -> ApplicantExtraction:
        return extract_applicant(
            applicant_id=applicant["id"],
            applicant_name=applicant["name"],
            documents=applicant["documents"],
            questions=questions,
            context=context,
        )

    n = len(applicants)
    if n == 1:
        return [_run(applicants[0])]

    parallel_workers = min(_BATCH_MAX_PARALLEL, n - 1)
    print(
        f"[DOCex] Batch extract: {n} applicants "
        f"(1 cache warmup, then {n - 1} parallel across {parallel_workers} workers)",
        flush=True,
    )

    started = time.monotonic()

    # 1) Warm the prompt cache with the first applicant
    first = _run(applicants[0])
    print(
        f"[DOCex] Warmup done in {time.monotonic() - started:.1f}s. "
        f"Fanning out the remaining {n - 1}...",
        flush=True,
    )

    # 2) Fan out the rest — concurrent.futures.map preserves input order
    fanout_started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as ex:
        rest = list(ex.map(_run, applicants[1:]))

    print(
        f"[DOCex] Batch complete: {n} applicants in "
        f"{time.monotonic() - started:.1f}s "
        f"(fan-out alone: {time.monotonic() - fanout_started:.1f}s).",
        flush=True,
    )

    return [first] + rest
