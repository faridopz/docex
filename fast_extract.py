"""
Fast text extraction — code, not LLM.

Pulling raw text out of a document is a solved, deterministic problem: a good
parser does it in milliseconds. DOCex reserves LLM tokens for *understanding*
text, never for extracting it.

PDF strategy:
  1. PyMuPDF (``fitz``) when available — the fastest text extractor by a wide
     margin (typically 5–10× pdfplumber).
  2. ``pdfplumber`` fallback so nothing breaks if fitz isn't installed.
  3. Empty string when a PDF has no text layer (a scan) — the caller can then
     decide to OCR, rather than silently returning nothing useful.

Page markers ("=== PAGE N ===") are preserved so downstream citations can still
report a source page.
"""
from __future__ import annotations

import io


def extract_text(filename: str, data: bytes) -> str:
    """Extract text from a PDF, DOCX, or plain-text file. Never raises — returns
    "" on failure so a single bad file can't break a batch."""
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            return _extract_pdf(data)
        if name.endswith(".docx"):
            return _extract_docx(data)
        if name.endswith((".txt", ".text", ".md", ".csv", ".tsv")):
            return data.decode("utf-8", errors="ignore")
        # Unknown extension — best-effort decode (covers stray text files).
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def is_probably_scanned(filename: str, data: bytes) -> bool:
    """True if a PDF has no extractable text layer (i.e. it's an image/scan and
    would need OCR). Cheap heuristic used to route scans separately."""
    if not (filename or "").lower().endswith(".pdf"):
        return False
    return not _extract_pdf(data).strip()


def _extract_pdf(data: bytes) -> str:
    # 1) PyMuPDF — fastest.
    try:
        import fitz  # PyMuPDF

        parts: list[str] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                txt = page.get_text("text") or ""
                if txt.strip():
                    parts.append(f"=== PAGE {i + 1} ===\n{txt}")
        joined = "\n".join(parts)
        if joined.strip():
            return joined
        return ""  # no text layer → scanned
    except ImportError:
        pass
    except Exception:
        pass

    # 2) pdfplumber fallback.
    try:
        import pdfplumber

        parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text() or ""
                if txt.strip():
                    parts.append(f"=== PAGE {i + 1} ===\n{txt}")
        return "\n".join(parts)
    except Exception:
        return ""


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        lines = [p.text for p in doc.paragraphs if p.text.strip()]
        # Tables often hold the real data (line items, amounts) — include them.
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))
        return "\n".join(lines)
    except Exception:
        return ""
