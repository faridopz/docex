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

# OCR is orders of magnitude slower than a text layer (~1-3s per page vs
# milliseconds). Cap it so one 200-page scan can't hold a request open; a
# receipt or invoice — the realistic field case — is one or two pages.
_OCR_MAX_PAGES = 10


def extract_text(filename: str, data: bytes) -> str:
    """Extract text from a PDF, DOCX, spreadsheet, image, or plain-text file.

    Never raises — returns "" on failure so a single bad file can't break a
    batch. An empty return means "no text recovered"; use ``extract_detail``
    when you need to know *why*, because the difference between a scan, a
    corrupt file and an unsupported one changes what you tell the user.
    """
    return _extract(filename, data)[0]


# Magic bytes, checked before the extension. A fieldworker's phone happily
# produces "receipt.pdf" that is actually a JPEG, and Kobo attachments arrive
# with whatever name the device gave them. Sniffing the content means we route
# on what the file *is*, not what it claims to be.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"\xff\xd8\xff", "image"),           # JPEG
    (b"GIF87a", "image"),
    (b"GIF89a", "image"),
    (b"BM", "image"),                     # BMP
    (b"II*\x00", "image"),                # TIFF little-endian
    (b"MM\x00*", "image"),                # TIFF big-endian
)

_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic")
_TEXT_EXT = (".txt", ".text", ".md", ".csv", ".tsv", ".json", ".log")


def _sniff(filename: str, data: bytes) -> str:
    """Classify a file as pdf | image | docx | xlsx | text | unknown.

    Content beats the extension in BOTH directions, which matters because
    filenames in this domain are routinely wrong:

      * A phone photo saved as "receipt.pdf" must not go to the PDF parser.
      * A plain-text receipt exported as "receipt.pdf" — common from Kobo
        attachments and email gateways — must still be read, not rejected as
        a damaged PDF.

    Every format we parse as a document is binary (PDF, and the ZIP-based
    Office formats). So if the bytes are readable text and carry no binary
    signature, it is text, whatever the name claims.
    """
    head = data[:16] if data else b""
    for sig, kind in _SIGNATURES:
        if head.startswith(sig):
            return kind
    # RIFF....WEBP
    if head.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image"

    name = (filename or "").lower()

    # OOXML (.docx/.xlsx) is a ZIP. The signature tells us it's an Office file;
    # only the extension can say which parser to use.
    if head.startswith(b"PK\x03\x04"):
        if name.endswith(".docx"):
            return "docx"
        if name.endswith((".xlsx", ".xlsm")):
            return "xlsx"
        return "unknown"

    # No binary signature. If it reads as text, it IS text — a mislabelled
    # extension shouldn't cost us a perfectly readable receipt.
    if not _looks_binary(data):
        return "text"

    # Binary, but unrecognised. Fall back to what the name claims so a valid
    # file in a format we didn't sniff still reaches the right parser.
    if name.endswith(".docx"):
        return "docx"
    if name.endswith((".xlsx", ".xlsm")):
        return "xlsx"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(_IMAGE_EXT):
        return "image"
    return "unknown"


def _looks_binary(data: bytes) -> bool:
    """True if these bytes are clearly not human-readable text.

    Guards the last-resort decode. Without this, a PNG fell through to
    ``decode(errors="ignore")`` and returned several kilobytes of mangled
    bytes as "text" — which downstream is far worse than returning nothing,
    because the vendor heuristic then reported a receipt from a supplier
    called "PNG" and the amount regex was free to match random digits.
    """
    if not data:
        return False
    sample = data[:2048]
    if b"\x00" in sample:
        return True
    # Bytes that aren't tab/newline/carriage-return and aren't printable ASCII
    # or valid UTF-8 continuation. A real text file is overwhelmingly these.
    printable = sum(1 for b in sample if b in (9, 10, 13) or 32 <= b < 127 or b >= 128)
    return (printable / len(sample)) < 0.85


def _extract(filename: str, data: bytes) -> tuple[str, str]:
    """Core routing. Returns ``(text, status)``.

    status is one of:
      ok          — text recovered from a real text layer
      ocr         — text recovered by OCR from a scan or photo. Same content,
                    lower trust: it is a machine reading pixels, so a caller
                    handling money should confirm figures with a human rather
                    than post them straight through.
      scanned     — a PDF or image with no readable text (OCR unavailable/failed)
      unreadable  — the bytes are damaged or not a document we can parse
      empty       — the file parsed fine but genuinely contains no text
    """
    if not data:
        return "", "unreadable"

    kind = _sniff(filename, data)
    try:
        if kind == "pdf":
            text = _extract_pdf(data)
            if text.strip():
                return text, "ok"
            # No text layer. Either a scan, or a damaged file that no parser
            # could open. Telling these apart matters: one is worth OCRing,
            # the other needs re-uploading.
            if not _pdf_is_parseable(data):
                return "", "unreadable"
            ocr = _ocr(data, is_pdf=True)
            return (ocr, "ocr") if ocr.strip() else ("", "scanned")

        if kind == "image":
            ocr = _ocr(data, is_pdf=False)
            return (ocr, "ocr") if ocr.strip() else ("", "scanned")

        if kind == "docx":
            return _extract_docx(data), "ok"

        if kind == "xlsx":
            return _extract_xlsx(data), "ok"

        if kind == "text":
            if _looks_binary(data):
                return "", "unreadable"
            return data.decode("utf-8", errors="ignore"), "ok"

        # Unknown extension and no recognised signature. Decode only if the
        # bytes actually look like text.
        if _looks_binary(data):
            return "", "unreadable"
        decoded = data.decode("utf-8", errors="ignore")
        return (decoded, "ok") if decoded.strip() else ("", "empty")
    except Exception:
        return "", "unreadable"


def extract_detail(filename: str, data: bytes) -> tuple[str, bool]:
    """Like ``extract_text`` but also reports whether the file looks scanned.

    Returns ``(text, scanned)``. Kept for the existing callers; prefer
    ``extract_status`` in new code, which distinguishes a scan from a damaged
    file. Single parse pass; no double work.
    """
    text, status = _extract(filename, data)
    return text, status == "scanned"


def extract_status(filename: str, data: bytes) -> tuple[str, str]:
    """Extract, and say what happened.

    Returns ``(text, status)`` with status in ``ok | scanned | unreadable |
    empty``. The distinction is the point: "we couldn't read this scan, please
    type the amount" and "this file is damaged, please upload it again" are
    different instructions, and a reviewer who is told the wrong one wastes
    their time. Both used to surface identically as an empty result.
    """
    return _extract(filename, data)


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
    """True if a file has no extractable text layer and would need OCR.

    Now covers photographs as well as scanned PDFs — for field operations a
    phone photo is the normal input, and it is just as much a "scan" as a
    flatbed output. A damaged file returns False: it is not a scan, and
    routing it to OCR would only fail slowly.
    """
    return _extract(filename, data)[1] == "scanned"


def _pdf_is_parseable(data: bytes) -> bool:
    """Can any parser open this PDF at all?

    Separates "a scan with no text layer" (worth OCRing, worth telling the user
    to expect manual entry) from "these bytes are damaged" (needs re-uploading).
    Both previously reported as ``scanned``, which sent broken files down an OCR
    path that could only fail.
    """
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            return doc.page_count > 0
    except ImportError:
        pass
    except Exception:
        return False
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages) > 0
    except Exception:
        return False


def ocr_available() -> bool:
    """True if OCR can actually run. Both the Python wrapper and the tesseract
    binary must be present — pytesseract alone does nothing."""
    try:
        import pytesseract
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr(data: bytes, is_pdf: bool) -> str:
    """Read text off a scan or photo.

    This is the field case: a receipt photographed on a phone in a market has
    no text layer at all, and for NEEM-style operations it is the *normal*
    input, not an edge case. Degrades silently to "" when OCR isn't installed,
    so the caller reports "couldn't read this" rather than crashing.

    OCR output is deliberately treated as lower-trust than a text layer —
    field_receipts flags it for human confirmation rather than trusting the
    amount, because a misread digit in a financial system is worse than a gap.
    """
    if not ocr_available():
        return ""
    try:
        import pytesseract
        from PIL import Image

        images: list = []
        if is_pdf:
            try:
                import fitz

                with fitz.open(stream=data, filetype="pdf") as doc:
                    for page in doc:
                        # 200 dpi: enough for receipt print, cheap enough for
                        # a phone photo of a page.
                        pix = page.get_pixmap(dpi=200)
                        images.append(Image.open(io.BytesIO(pix.tobytes("png"))))
            except ImportError:
                # Without fitz we cannot rasterise a PDF; pdfplumber has no
                # equivalent. Report nothing rather than guess.
                return ""
        else:
            images.append(Image.open(io.BytesIO(data)))

        parts = []
        for i, img in enumerate(images[:_OCR_MAX_PAGES]):
            if img.mode not in ("L", "RGB"):
                img = img.convert("RGB")
            txt = pytesseract.image_to_string(img) or ""
            if txt.strip():
                parts.append(f"=== PAGE {i + 1} ===\n{txt}" if is_pdf else txt)
        return "\n".join(parts)
    except Exception:
        return ""


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
