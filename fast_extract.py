"""
Fast text extraction — code, not LLM.

Pulling raw text out of a document is a solved, deterministic problem: a good
parser does it in milliseconds. DOCex reserves LLM tokens for *understanding*
text, never for extracting it. This module is the SINGLE shared extraction
layer — every engine (screening, compliance, knowledge) routes uploads through
here so they all get the same speed, the same fallbacks, and the same handling
of scans.

PDF strategy:
  1. PyMuPDF (``fitz``) when available — the fastest text extractor by a wide
     margin (typically 5–10× pdfplumber).
  2. ``pdfplumber`` fallback so nothing breaks if fitz isn't installed.
  3. Empty string when a PDF has no text layer (a scan) — the caller can then
     decide to OCR, rather than silently returning nothing useful.

DOCX strategy:
  Walk the document body IN ORDER, capturing both paragraphs and table cells,
  so a table that answers a heading stays next to that heading. NGO reports put
  much of the substance (indicator tables, target-vs-actual, financials) in
  tables — paragraph-only extraction silently drops most of it.

Page markers ("=== PAGE N ===") are preserved so downstream citations can still
report a source page.

Batch helpers:
  ``extract_many`` parses a list of files IN PARALLEL (a thread pool). fitz and
  pdfplumber release the GIL during page work, so ingesting many docs — the
  screening "5-8 files per applicant" case — is meaningfully faster than the
  old file-by-file loop, while preserving input order.
"""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

# Parsing is I/O + C-extension heavy (fitz/pdfplumber release the GIL), so a
# modest thread pool overlaps the work. Capped so a huge batch can't spawn an
# unbounded number of threads.
_MAX_WORKERS = 8


def extract_text(filename: str, data: bytes) -> str:
    """Extract text from a PDF, DOCX, or plain-text file. Never raises — returns
    "" on failure so a single bad file can't break a batch."""
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            return _extract_pdf(data)
        if name.endswith(".docx"):
            return _extract_docx(data)
        if name.endswith((".xlsx", ".xlsm")):
            return _extract_xlsx(data)
        if name.endswith((".txt", ".text", ".md", ".csv", ".tsv")):
            return data.decode("utf-8", errors="ignore")
        # Unknown extension — best-effort decode (covers stray text files).
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract_detail(filename: str, data: bytes) -> tuple[str, bool]:
    """Like ``extract_text`` but also reports whether the file looks scanned.

    Returns ``(text, scanned)`` where ``scanned`` is True for a PDF that yielded
    no text layer (an image/scan that would need OCR). Surfacing this lets a
    caller warn "this file is a scan we couldn't read" instead of silently
    dropping it — the difference between a confusing empty result and a clear
    one. Single parse pass; no double work.
    """
    text = extract_text(filename, data)
    scanned = (not text.strip()) and (filename or "").lower().endswith(".pdf")
    return text, scanned


def extract_many(
    files: list[tuple[str, bytes]],
    max_workers: int = _MAX_WORKERS,
) -> list[tuple[str, str]]:
    """Extract text from many files IN PARALLEL, preserving input order.

    files: list of (filename, raw_bytes)
    Returns: list of (filename, text) in the same order as the input. Files that
    fail to parse come back with "" (never dropped here — the caller decides
    whether an empty result should be skipped or surfaced).
    """
    if not files:
        return []
    # One file: skip the pool overhead entirely.
    if len(files) == 1:
        fn, data = files[0]
        return [(fn, extract_text(fn, data))]
    workers = max(1, min(max_workers, len(files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # executor.map preserves order, so results line up with `files`.
        texts = list(pool.map(lambda f: extract_text(f[0], f[1]), files))
    return [(files[i][0], texts[i]) for i in range(len(files))]


def extract_many_detailed(
    files: list[tuple[str, bytes]],
    max_workers: int = _MAX_WORKERS,
) -> list[tuple[str, str, bool]]:
    """Parallel variant that also returns the scanned flag per file.

    Returns: list of (filename, text, scanned) in input order. Use this when the
    engine wants to tell the user which uploads were unreadable scans.
    """
    if not files:
        return []
    if len(files) == 1:
        fn, data = files[0]
        text, scanned = extract_detail(fn, data)
        return [(fn, text, scanned)]
    workers = max(1, min(max_workers, len(files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        details = list(pool.map(lambda f: extract_detail(f[0], f[1]), files))
    return [(files[i][0], details[i][0], details[i][1]) for i in range(len(files))]


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


def _cell_to_str(value) -> str:
    """Render an Excel cell value as clean text. Numbers avoid scientific
    notation (so ₦1,250,000 stays readable), integers drop the '.0', and
    dates/datetimes stringify to an ISO-ish form the date regex can read."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value).strip()


def _extract_xlsx(data: bytes) -> str:
    """Extract a spreadsheet (.xlsx/.xlsm) into text — for payment vouchers,
    schedules, and any table-shaped document.

    Rendering is tuned so the downstream field extractors still work: a
    two-column row (the classic 'Label | Value' voucher layout) is rendered as
    'Label: Value' so labelled-regex extraction ('Invoice No: ...', 'Total: ...')
    fires exactly as it does on a PDF; wider rows (line items, headers) are
    pipe-joined. Uses data_only so computed cells return their VALUE, not the
    formula, and read_only for speed on large sheets.
    """
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        return ""

    parts: list[str] = []
    try:
        for ws in wb.worksheets:
            rows_out: list[str] = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 5000:  # guard against runaway sheets
                    break
                cells = [_cell_to_str(c) for c in row]
                cells = [c for c in cells if c]
                if not cells:
                    continue
                if len(cells) == 2:
                    rows_out.append(f"{cells[0]}: {cells[1]}")
                else:
                    rows_out.append(" | ".join(cells))
            if rows_out:
                # Sheet marker mirrors the "=== PAGE N ===" markers so downstream
                # citation/structure handling stays consistent.
                parts.append(f"=== SHEET: {ws.title} ===\n" + "\n".join(rows_out))
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return "\n\n".join(parts)


def _extract_docx(data: bytes) -> str:
    """Flatten a docx into plain text including table cells, in document order.

    Iterates the body element in order so paragraphs and tables appear in the
    right sequence — important when an answer depends on the table that
    immediately follows a heading.
    """
    try:
        from docx import Document
        from docx.oxml.ns import qn

        doc = Document(io.BytesIO(data))
        parts: list[str] = []
        body = doc.element.body
        for child in body.iterchildren():
            tag = child.tag
            if tag == qn("w:p"):
                text = "".join(t.text or "" for t in child.iter(qn("w:t")))
                if text.strip():
                    parts.append(text)
            elif tag == qn("w:tbl"):
                for row in child.iter(qn("w:tr")):
                    cells: list[str] = []
                    for cell in row.iter(qn("w:tc")):
                        cell_text = "".join(t.text or "" for t in cell.iter(qn("w:t")))
                        cells.append(cell_text.strip())
                    if any(cells):
                        parts.append(" | ".join(cells))
                parts.append("")  # blank line after each table
        return "\n".join(parts)
    except Exception:
        return ""
