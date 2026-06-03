"""
DOCex FastAPI wrapper.

Endpoints:
  GET  /health              — liveness check
  POST /extract/single      — one applicant, multiple files
  POST /extract/batch       — many applicants, each with their own files

Run locally:
  uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import io
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Annotated

import anthropic
import pdfplumber
from docx import Document as DocxDocument
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Load .env from the project root (sibling of /api). Means the user can paste
# ANTHROPIC_API_KEY into one file once and never re-export it per shell.
# override=False so an explicit `export ANTHROPIC_API_KEY=...` in the shell
# still wins, which matters for CI/CD and one-off testing.
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# Loud startup checks — if a required env var is missing, every call to the
# affected primitive will fail with a 401/RuntimeError and the user will
# only see "errors" in the UI. Catch them here so the terminal makes the
# cause obvious before the first request lands. The diagnostic at
# /admin/diagnostics surfaces the same issues at runtime; the startup
# print is the loud first-line-of-defence for ops.
_missing_secrets: list[str] = []
if not os.environ.get("ANTHROPIC_API_KEY"):
    _missing_secrets.append("ANTHROPIC_API_KEY  (powers Extraction + Compliance Check + follow-up drafting)")
if not os.environ.get("PAYSTACK_SECRET_KEY"):
    _missing_secrets.append("PAYSTACK_SECRET_KEY  (powers Bank Verify + Attendance Payment Agent verification)")

if _missing_secrets:
    print(
        "\n" + "=" * 70 + "\n"
        "[DOCex] WARNING — missing environment variables:\n  "
        + "\n  ".join(f"• {s}" for s in _missing_secrets) + "\n\n"
        "Affected calls will fail. Add the values to .env at the project\n"
        "root, then restart uvicorn. /admin/diagnostics will show the\n"
        "same status with fix hints once the API is running.\n"
        + "=" * 70 + "\n",
        flush=True,
    )

# Bootstrap persistence directories at app boot — every primitive's storage
# layer is file-based JSON under {project_root}/{thing}/. Creating these
# at import time means a fresh checkout doesn't trip on the first request
# that tries to write. mkdir(exist_ok=True) is idempotent so re-runs are safe.
for _dirname in ("rulebooks", "checks", "verifications",
                  "attendance_runs", "rate_cards", "diagnostics", "decks"):
    try:
        (Path(__file__).parent.parent / _dirname).mkdir(parents=True, exist_ok=True)
    except Exception as _exc:
        # Non-fatal — the lazy _ensure_dir() in each routes file will retry.
        # We don't want a chmod issue on one directory to prevent the whole
        # API from booting.
        print(f"[DOCex] Notice: could not pre-create {_dirname}/: {_exc}", flush=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ApplicantExtraction, ExtractionAnswer, Question  # noqa: E402
from screener import extract_applicant, extract_batch  # noqa: E402
from .assistant_routes import router as assistant_router  # noqa: E402
from .attendance_agent_routes import router as attendance_router  # noqa: E402
from .attendance_collection_routes import router as attendance_collection_router  # noqa: E402
from .bank_verify_routes import router as bank_verify_router  # noqa: E402
from .compliance_routes import router as compliance_router  # noqa: E402
from .knowledge_routes import router as knowledge_router  # noqa: E402
from .rate_card_routes import router as rate_card_router  # noqa: E402
from .self_check_routes import router as self_check_router  # noqa: E402
from .schemas import (  # noqa: E402
    BatchExtractionResponse,
    FollowupDraft,
    FollowupRequest,
    FollowupResponse,
    HealthOut,
    QuestionIn,
    SingleExtractionResponse,
)

# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DOCex API",
    description="AI-powered document extraction — define questions, upload docs, get answers.",
    version="2.0.0",
)

# CORS configuration.
#   - Localhost origins are always allowed (so `npm run dev` works without
#     any env var setup).
#   - Production origins come from the ALLOWED_ORIGINS env var as a
#     comma-separated list. On Railway/Fly set this to your Vercel URL,
#     e.g. ALLOWED_ORIGINS=https://docex.vercel.app,https://docex.com
_default_dev_origins = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:3001", "http://127.0.0.1:3001",
]
_extra_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
_extra_origins = (
    [o.strip() for o in _extra_origins_env.split(",") if o.strip()]
    if _extra_origins_env
    else []
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_dev_origins + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression — shrinks JSON responses ~60-80% on payloads over 1KB.
# Cost is a tiny CPU bump on the API; benefit is faster page loads everywhere
# the frontend hits a list endpoint (Bank Verify batches, attendance runs,
# rate cards, diagnostic reports). FastAPI's stock GZipMiddleware handles
# the Accept-Encoding negotiation correctly.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Compliance Check routes — policy interpretation, rulebook CRUD, payment
# checks (single + batch). See api/compliance_routes.py.
app.include_router(compliance_router)

# Bank Verify routes — bulk verification of recipient bank accounts against
# Paystack /bank/resolve, with fuzzy name matching. See api/bank_verify_routes.py.
app.include_router(bank_verify_router)

# Attendance Payment Agent — DOCex's first composite agent. Chains the
# attendance-log + payment-info parsing primitives with cross-matching,
# then hands the resulting schedule off to Bank Verify for verification.
# See api/attendance_agent_routes.py.
app.include_router(attendance_router)

# Attendance Collections — native intake grid + public self-check-in links.
# Converts collected attendees into a normal run. See
# api/attendance_collection_routes.py.
app.include_router(attendance_collection_router)

# Rate cards — reusable per-diem schedules consumed by the Attendance
# Payment Agent and (later) any other agent that needs to compute payment
# amounts. See api/rate_card_routes.py.
app.include_router(rate_card_router)

# Self-Check Agent — runtime diagnostic that exercises every primitive and
# reports health. V1 of the longer-term Self-Improvement Agent (observe →
# recommend). See api/self_check_routes.py.
app.include_router(self_check_router)

# DOCex Assistant — agentic narrator. Every result page calls this to get
# a plain-English briefing on what just happened plus recommended next
# actions. See api/assistant_routes.py.
app.include_router(assistant_router)

# Knowledge Hub — slide-deck ingestion + chat-with-slides. The fifth
# DOCex primitive. Upload .pptx → parsed slide-by-slide → ask questions
# with slide-N citations. See api/knowledge_routes.py.
app.include_router(knowledge_router)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _extract_text(upload: UploadFile) -> str:
    """Extract plain text from a PDF, DOCX, or TXT upload."""
    raw = upload.file.read()
    name = (upload.filename or "").lower()

    if name.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            parts = []
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                parts.append(f"=== PAGE {i} ===\n{text}")
        return "\n\n".join(parts).strip()

    if name.endswith(".docx"):
        # Walk the document body in order, capturing both paragraphs AND
        # table cell text. NGO reports put a lot of the substance (indicator
        # tables, target-vs-actual tables, financial summaries) in tables —
        # paragraph-only extraction silently drops most of it.
        doc = DocxDocument(io.BytesIO(raw))
        return _docx_to_text(doc).strip()

    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("latin-1").strip()


def _docx_to_text(doc: DocxDocument) -> str:
    """
    Flatten a docx into plain text including table cells.

    Iterates the body element in document order so paragraphs and tables
    appear in the right sequence — important when answers depend on the
    table that immediately follows a heading.
    """
    from docx.oxml.ns import qn  # local import keeps top of file clean

    parts: list[str] = []
    body = doc.element.body

    for child in body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            # Paragraph — read its text
            text = "".join(t.text or "" for t in child.iter(qn("w:t")))
            if text.strip():
                parts.append(text)
        elif tag == qn("w:tbl"):
            # Table — read each row as a pipe-separated line so structure
            # is preserved enough for Claude to recognise tabular data.
            for row in child.iter(qn("w:tr")):
                cells: list[str] = []
                for cell in row.iter(qn("w:tc")):
                    cell_text = "".join(t.text or "" for t in cell.iter(qn("w:t")))
                    cells.append(cell_text.strip())
                if any(cells):
                    parts.append(" | ".join(cells))
            parts.append("")  # blank line after each table

    return "\n".join(parts)


def _parse_questions(questions_json: str) -> list[Question]:
    """Parse and validate the questions JSON string sent from the frontend."""
    try:
        raw = json.loads(questions_json)
        validated = [QuestionIn.model_validate(q) for q in raw]
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid questions: {exc}") from exc

    if not validated:
        raise HTTPException(status_code=422, detail="At least one question is required.")

    return [Question(id=q.id, text=q.text) for q in validated]


def _read_uploads(uploads: list[UploadFile]) -> dict[str, tuple[str, str]]:
    """
    Extract text from every uploaded file.
    Returns a dict of {filename: (filename, text)}.
    Files that fail to parse are silently skipped — the caller decides
    whether to raise or continue.
    """
    result: dict[str, tuple[str, str]] = {}
    for upload in uploads:
        filename = upload.filename or f"file_{uuid.uuid4().hex[:6]}"
        try:
            text = _extract_text(upload)
            if text:
                result[filename] = (filename, text)
        except Exception as exc:
            print(f"Warning: could not extract text from '{filename}': {exc}")
    return result


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthOut, tags=["meta"])
def health() -> HealthOut:
    return HealthOut()


@app.post("/extract/single", response_model=SingleExtractionResponse, tags=["extraction"])
async def extract_single(
    documents: Annotated[list[UploadFile], File(description="All documents for this one applicant")],
    questions: Annotated[str, Form(description='JSON array: [{id, text}, ...]')],
    applicant_name: Annotated[str, Form(description="Name or label for this applicant")] = "Applicant",
) -> SingleExtractionResponse:
    """
    Extract answers for a single applicant from multiple uploaded documents.
    All files are read together — answers can come from any of them.
    """
    questions_list = _parse_questions(questions)
    file_texts = _read_uploads(documents)

    if not file_texts:
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from the uploaded documents. "
                   "Make sure the files are readable PDFs, DOCX, or plain text.",
        )

    result = extract_applicant(
        applicant_id=str(uuid.uuid4()),
        applicant_name=applicant_name,
        documents=list(file_texts.values()),
        questions=questions_list,
    )

    return SingleExtractionResponse(
        applicant_name=result.applicant_name,
        documents=result.documents,
        answers=result.answers,
        error=result.error,
    )


@app.post("/extract/batch", response_model=BatchExtractionResponse, tags=["extraction"])
async def extract_batch_endpoint(
    documents: Annotated[list[UploadFile], File(description="All files for all applicants")],
    questions: Annotated[str, Form(description='JSON array: [{id, text}, ...]')],
    applicants: Annotated[str, Form(description='JSON array: [{id, name, filenames: [...]}]')],
) -> BatchExtractionResponse:
    """
    Extract answers for multiple applicants in one request.

    Upload ALL files for ALL applicants together, then pass an `applicants`
    JSON array mapping each applicant to their specific filenames.

    Example applicants JSON:
    [
      {"id": "org-1", "name": "Health Initiative Abuja", "filenames": ["hi_cac.pdf", "hi_proposal.docx"]},
      {"id": "org-2", "name": "Women in Agric",          "filenames": ["wia_reg.pdf", "wia_budget.pdf"]}
    ]
    """
    questions_list = _parse_questions(questions)

    try:
        applicants_raw = json.loads(applicants)
        if not isinstance(applicants_raw, list) or len(applicants_raw) == 0:
            raise ValueError("Must be a non-empty array.")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid applicants JSON: {exc}") from exc

    # Extract text from every uploaded file, keyed by filename
    file_texts = _read_uploads(documents)

    # Build the applicant list, catching missing files loudly
    applicant_list = []
    for ap in applicants_raw:
        ap_name = ap.get("name", "Unknown")
        ap_id = ap.get("id", str(uuid.uuid4()))
        requested_files = ap.get("filenames", [])

        missing = [fn for fn in requested_files if fn not in file_texts]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Applicant '{ap_name}': these filenames were listed but not uploaded: {missing}. "
                       f"Uploaded files are: {list(file_texts.keys())}",
            )

        ap_docs = [file_texts[fn] for fn in requested_files if fn in file_texts]

        if not ap_docs:
            raise HTTPException(
                status_code=422,
                detail=f"Applicant '{ap_name}' has no readable documents. "
                       "Check that the files uploaded are valid PDFs, DOCX, or text files.",
            )

        applicant_list.append({"id": ap_id, "name": ap_name, "documents": ap_docs})

    results: list[ApplicantExtraction] = extract_batch(applicant_list, questions_list)

    succeeded = sum(1 for r in results if not r.error)
    failed = len(results) - succeeded

    return BatchExtractionResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        applicants=results,
    )


# ─── Follow-up note drafting ───────────────────────────────────────────────

_followup_client = anthropic.Anthropic()


def _build_followup_system(template_id: Optional[str]) -> str:
    """
    Return a follow-up drafting system prompt tuned to the workflow.

    The shape is the same across templates (acknowledge → list 2-3 specific
    gaps → close politely), but the vocabulary and the ask differ:
      - For application screening, partners are "applicants" and the ask is
        to submit missing items before assessment can complete.
      - For quarterly report review, the partners are existing collaborators
        and the ask is for an addendum or for next reporting cycle.

    Mirrors the workflow-labels file used on the frontend.
    """
    if template_id == "quarterly-report-review":
        return """You draft short follow-up notes about partner quarterly progress reports.

The user will give you the partner's name and a summary of gaps a reviewer
flagged — questions where the answer was "not_found" or confidence was
"inferred". The partner is an EXISTING collaborator, not a new applicant.

Write a SHORT follow-up note (2-3 sentences, never more):
- Opens by acknowledging the partner's quarterly submission (not "application")
- Names 2-3 specific gaps with the missing data point or section
- Closes with a clear, low-friction ask: a brief addendum, or that the gap
  be addressed in the next reporting cycle
- Maintains a respectful, collegial tone — this is a continuing partnership

DO NOT:
- Use the word "applicant" or "application"
- Imply an approval or selection decision is pending
- Assert facts about section letters (Section A/B/C/D) unless the search
  notes explicitly mention them
- Use bureaucratic phrasing like "before the review can be completed"

Return ONLY the note body — no greeting, no signature, no subject line.
Be specific about each gap. Cite the actual data point that was missing, not
generic phrases like "some areas need improvement"."""

    # Default: application screening (sub-award or generic)
    return """You draft short follow-up notes for partner application screening.

The user will give you an applicant's name and a summary of screening gaps —
questions where the answer was "not_found" or confidence was "inferred".

Write a SHORT follow-up note (2-3 sentences, never more):
- Acknowledges the applicant submitted their application
- Names 2-3 specific gaps with the missing document or data point
- Closes with a clear, low-friction ask for what to provide
- Maintains a respectful, encouraging tone
- Does NOT make a final selection decision — that is up to the human reviewer

Return ONLY the note body — no greeting, no signature, no subject line.

Be specific about the gaps — name the missing document, policy, or data point.
Do not use generic phrases like "some areas need improvement". Cite what was
actually missing based on the screening data provided."""


def _build_gap_summary(
    answers: list[ExtractionAnswer],
) -> str:
    """Summarise the gaps (not_found and inferred) for the follow-up prompt."""
    gaps: list[str] = []
    for a in answers:
        if a.confidence == "not_found":
            gaps.append(f"- NOT FOUND: {a.question_text}")
            if a.search_notes:
                gaps.append(f"  Search note: {a.search_notes}")
        elif a.confidence == "inferred":
            gaps.append(f"- INFERRED (not explicitly stated): {a.question_text}")
            if a.answer:
                gaps.append(f"  Best guess: {a.answer}")
            if a.search_notes:
                gaps.append(f"  Reasoning: {a.search_notes}")
    return "\n".join(gaps) if gaps else "No gaps identified — all answers were found."


@app.post("/draft-followups", response_model=FollowupResponse, tags=["followups"])
async def draft_followups(body: FollowupRequest) -> FollowupResponse:
    """
    Draft short follow-up notes based on extraction gaps.
    Vocabulary and ask shape adapt to the active template (sub-award
    application review vs quarterly report review).
    """
    system_prompt = _build_followup_system(body.template_id)
    workflow_label = (
        "partner" if body.template_id == "quarterly-report-review" else "applicant"
    )

    drafts: list[FollowupDraft] = []

    for ap in body.applicants:
        gap_summary = _build_gap_summary(ap.answers)

        user_msg = (
            f"{workflow_label.capitalize()}: {ap.applicant_name}\n\n"
            f"Gaps identified:\n{gap_summary}"
        )

        try:
            response = _followup_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            note = response.content[0].text.strip()
        except Exception as exc:
            note = f"[Could not generate draft: {exc}]"

        drafts.append(FollowupDraft(
            applicant_id=ap.applicant_id,
            applicant_name=ap.applicant_name,
            note=note,
        ))

    return FollowupResponse(drafts=drafts)
