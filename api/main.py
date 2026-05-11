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
import sys
import uuid
from pathlib import Path
from typing import Annotated

import pdfplumber
from docx import Document as DocxDocument
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ApplicantExtraction, Question  # noqa: E402
from screener import extract_applicant, extract_batch  # noqa: E402
from .schemas import (  # noqa: E402
    BatchExtractionResponse,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        doc = DocxDocument(io.BytesIO(raw))
        return "\n".join(para.text for para in doc.paragraphs).strip()

    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("latin-1").strip()


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
