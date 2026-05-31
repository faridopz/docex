"""
DOCex document library parser.

Reads any of PPTX / DOCX / PDF into a SlideDeck — the Knowledge Hub's
unit of persistence. The model name "SlideDeck" is historical; in the
multi-format era it really represents any structured document chunked
into navigable pieces.

Per format:
  PPTX → slides numbered 1..N, with title / body / speaker_notes / tables
  PDF  → pages numbered 1..N, with body (full page text) + heuristic title
  DOCX → sections numbered 1..N, split by heading; each section carries
         its heading as title plus paragraphs + tables as body

Why one unified shape rather than three sibling models: per-document chat
already works against SlideDeck. Generalising the shape rather than
forking it means every existing endpoint, every existing UI page, and
every existing prompt stays compatible. The cost is mild vocabulary
drift ("slides" referring to PDF pages) — handled by labelling at the
frontend.

Image OCR is out of scope for the MVP. PPTX slides with chart-only
content, and PDFs that are scanned images, will produce thin records.
We'll add OCR in a later pass when there's real demand.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import io

from pptx import Presentation
from pptx.util import Emu  # noqa: F401  (re-exported for future shape-position logic)

from models import DocumentContentType, Slide, SlideDeck

logger = logging.getLogger(__name__)


# ─── Top-level dispatch ─────────────────────────────────────────────────────
#
# One entry point. Sniffs the filename to pick the right parser. Every
# parser returns the same SlideDeck shape so downstream chat + UI doesn't
# care which format it was.

def parse_document(
    file_path_or_buffer,
    *,
    name: Optional[str] = None,
    source_filename: str = "document",
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    deck_id: Optional[str] = None,
) -> SlideDeck:
    """
    Parse any supported document into a SlideDeck.

    Routes based on the source_filename extension:
      .pptx / .pptm  → parse_pptx
      .pdf           → parse_pdf
      .docx / .docm  → parse_docx

    Raises ValueError if the extension isn't recognised. Doesn't sniff
    file content (we trust the filename; the API layer validates by
    extension already).
    """
    lower = source_filename.lower()
    if lower.endswith((".pptx", ".pptm")):
        return parse_pptx(
            file_path_or_buffer,
            name=name,
            source_filename=source_filename,
            description=description,
            tags=tags,
            deck_id=deck_id,
        )
    if lower.endswith(".pdf"):
        return parse_pdf(
            file_path_or_buffer,
            name=name,
            source_filename=source_filename,
            description=description,
            tags=tags,
            deck_id=deck_id,
        )
    if lower.endswith((".docx", ".docm")):
        return parse_docx(
            file_path_or_buffer,
            name=name,
            source_filename=source_filename,
            description=description,
            tags=tags,
            deck_id=deck_id,
        )
    raise ValueError(
        f"Unsupported file type for {source_filename!r}. "
        f"Knowledge Hub accepts .pptx, .pdf, and .docx."
    )


# ─── Format-specific labels for the chunk vocabulary ────────────────────────

def chunk_label_for(content_type: DocumentContentType) -> str:
    """The noun the UI uses for one chunk of a doc of this type."""
    return {"pptx": "Slide", "docx": "Section", "pdf": "Page"}.get(
        content_type, "Chunk"
    )


def parse_pptx(
    file_path_or_buffer,
    *,
    name: Optional[str] = None,
    source_filename: str = "deck.pptx",
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    deck_id: Optional[str] = None,
) -> SlideDeck:
    """
    Parse a .pptx into a SlideDeck.

    Accepts either a filesystem path or a file-like object (BytesIO, FastAPI
    UploadFile.file). python-pptx handles both natively.

    name: optional user-facing label. Defaults to source_filename without
          the .pptx extension.
    deck_id: optional pre-set id (for re-imports). Defaults to a uuid hex.
    """
    prs = Presentation(file_path_or_buffer)

    slides: list[Slide] = []
    for i, slide in enumerate(prs.slides, start=1):
        slides.append(_extract_slide(slide, slide_number=i))

    display_name = name or source_filename.rsplit(".", 1)[0]

    return SlideDeck(
        id=deck_id or uuid.uuid4().hex,
        name=display_name,
        source_filename=source_filename,
        content_type="pptx",
        slide_count=len(slides),
        slides=slides,
        description=description,
        tags=tags or [],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ─── DOCX ────────────────────────────────────────────────────────────────────
#
# Word documents split into "sections" by heading. Heading 1 starts a new
# section; everything under it (paragraphs + tables) belongs to that section.
# Why heading-based rather than page-based: page breaks in DOCX are unreliable
# (depend on rendering), but the logical structure (Heading 1 / 2 / 3) maps
# cleanly to chunks. Each section becomes a chat-citable unit.

def parse_docx(
    file_path_or_buffer,
    *,
    name: Optional[str] = None,
    source_filename: str = "document.docx",
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    deck_id: Optional[str] = None,
) -> SlideDeck:
    """Parse a .docx into a SlideDeck of sections."""
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn

    doc = DocxDocument(file_path_or_buffer)
    body = doc.element.body

    sections: list[Slide] = []
    current_title: Optional[str] = None
    current_body: list[str] = []
    current_tables: list[str] = []

    def flush() -> None:
        # Flush the in-progress section to the list. Skips empty sections
        # (heading with nothing under it) — defensive.
        nonlocal current_title, current_body, current_tables
        if current_title or current_body or current_tables:
            sections.append(
                Slide(
                    number=len(sections) + 1,
                    title=current_title,
                    body=current_body,
                    speaker_notes=None,  # DOCX has no speaker notes
                    table_text=current_tables,
                )
            )
        current_title = None
        current_body = []
        current_tables = []

    for child in body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            # A paragraph. Read its text + check whether it's a heading style.
            text = "".join(t.text or "" for t in child.iter(qn("w:t"))).strip()
            if not text:
                continue
            # Heading detection — paragraph style ending in a heading marker.
            style_el = child.find(".//" + qn("w:pStyle"))
            style = style_el.get(qn("w:val"), "") if style_el is not None else ""
            is_heading = style.lower().startswith("heading") or style.lower() in {
                "title",
                "subtitle",
            }
            if is_heading:
                # Heading starts a new section. Flush the in-progress one.
                flush()
                current_title = text
            else:
                current_body.append(text)
        elif tag == qn("w:tbl"):
            # Table — flatten each row to pipe-delimited so cell relationships survive.
            for row in child.iter(qn("w:tr")):
                cells: list[str] = []
                for cell in row.iter(qn("w:tc")):
                    cell_text = "".join(
                        t.text or "" for t in cell.iter(qn("w:t"))
                    ).strip()
                    cells.append(cell_text)
                cells = [c for c in cells if c]
                if cells:
                    current_tables.append(" | ".join(cells))

    flush()

    # If the doc had no headings, the entire content ends up under one
    # unnamed section. Give it a title derived from the filename so it
    # still cites cleanly.
    if len(sections) == 1 and sections[0].title is None:
        sections[0].title = (name or source_filename.rsplit(".", 1)[0])[:80]

    display_name = name or source_filename.rsplit(".", 1)[0]

    return SlideDeck(
        id=deck_id or uuid.uuid4().hex,
        name=display_name,
        source_filename=source_filename,
        content_type="docx",
        slide_count=len(sections),
        slides=sections,
        description=description,
        tags=tags or [],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ─── PDF ────────────────────────────────────────────────────────────────────
#
# PDFs split by page. Each page becomes a chunk with the page text as body
# and a heuristic title (the first non-empty line of the page, capped).
# Cleaner page numbering preserves the natural citation format ("Page 14").

def parse_pdf(
    file_path_or_buffer,
    *,
    name: Optional[str] = None,
    source_filename: str = "document.pdf",
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    deck_id: Optional[str] = None,
) -> SlideDeck:
    """Parse a .pdf into a SlideDeck of pages."""
    import pdfplumber

    # pdfplumber accepts file paths and file-like objects (BytesIO etc).
    # If we got bytes, wrap them; if it's already a buffer or path we're fine.
    if isinstance(file_path_or_buffer, (bytes, bytearray)):
        file_path_or_buffer = io.BytesIO(file_path_or_buffer)

    pages: list[Slide] = []
    with pdfplumber.open(file_path_or_buffer) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw_text = (page.extract_text() or "").strip()
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

            # First non-empty line = best-guess title for the page. PDFs
            # don't have explicit titles per page; this is heuristic but
            # works well for reports formatted with section headings.
            title = lines[0][:120] if lines else None
            body = lines[1:] if lines else []

            # Extract tables explicitly — pdfplumber surfaces them
            # separately from text. Same pipe-delimited row pattern as
            # DOCX/PPTX so the relationship survives.
            table_text: list[str] = []
            try:
                for table in page.extract_tables() or []:
                    for row in table:
                        cells = [
                            (cell or "").strip().replace("\n", " ")
                            for cell in row
                        ]
                        cells = [c for c in cells if c]
                        if cells:
                            table_text.append(" | ".join(cells))
            except Exception as exc:
                # pdfplumber occasionally chokes on malformed tables;
                # don't let one bad table kill the whole page.
                logger.debug(f"Table extraction skipped on page {i}: {exc}")

            pages.append(
                Slide(
                    number=i,
                    title=title,
                    body=body,
                    speaker_notes=None,
                    table_text=table_text,
                )
            )

    display_name = name or source_filename.rsplit(".", 1)[0]

    return SlideDeck(
        id=deck_id or uuid.uuid4().hex,
        name=display_name,
        source_filename=source_filename,
        content_type="pdf",
        slide_count=len(pages),
        slides=pages,
        description=description,
        tags=tags or [],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _extract_slide(slide, *, slide_number: int) -> Slide:
    """Pull title, body, notes, and tables off one slide."""
    title: Optional[str] = None
    body: list[str] = []
    table_text: list[str] = []

    # 1. Use the placeholder title if present (cleaner than guessing the
    #    first text frame). Fall back to "first shape's first paragraph".
    placeholder_title = _extract_placeholder_title(slide)
    if placeholder_title:
        title = placeholder_title

    # 2. Walk every shape on the slide
    for shape in slide.shapes:
        # Tables — flatten each row to a pipe-delimited string so the
        # relationship between cells survives the trip into Claude's context.
        if shape.has_table:
            for row in shape.table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                cells = [c for c in cells if c]
                if cells:
                    table_text.append(" | ".join(cells))
            continue

        # Text frames — capture paragraph-by-paragraph
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                t = "".join(run.text for run in para.runs).strip()
                if not t:
                    continue
                # If we don't have a title yet, the first non-empty text
                # we find is our best guess for one.
                if title is None:
                    title = t
                    continue
                body.append(t)

    # 3. Speaker notes — often where the substance lives in check-in decks
    speaker_notes: Optional[str] = None
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame.text.strip()
        if notes:
            speaker_notes = notes

    return Slide(
        number=slide_number,
        title=title,
        body=body,
        speaker_notes=speaker_notes,
        table_text=table_text,
    )


def _extract_placeholder_title(slide) -> Optional[str]:
    """python-pptx exposes the placeholder title via slide.shapes.title when
    the deck uses placeholder layouts. Many real-world decks don't — they
    use loose text boxes — so this returns None as the common case."""
    try:
        if slide.shapes.title is None:
            return None
        text = slide.shapes.title.text.strip()
        return text or None
    except Exception:
        return None


def slide_to_context(slide: Slide, label: str = "Slide") -> str:
    """
    Render a single chunk as a chat-context block. The label argument swaps
    the header wording to match document type ("Slide", "Page", "Section").
    Claude cites back using the same vocabulary.
    """
    parts: list[str] = [f"=== {label} {slide.number} ==="]
    if slide.title:
        parts.append(f"Title: {slide.title}")
    if slide.body:
        parts.append("Body:")
        parts.extend(f"  - {line}" for line in slide.body)
    if slide.table_text:
        parts.append("Tables:")
        parts.extend(f"  {row}" for row in slide.table_text)
    if slide.speaker_notes:
        parts.append(f"Speaker notes: {slide.speaker_notes}")
    return "\n".join(parts)


def deck_to_context(deck: SlideDeck, max_chars: int = 200_000) -> str:
    """
    Serialise a whole document to a single text blob for a chat-context
    window. Format-aware: PPTX uses "Slide N" headers, DOCX uses "Section N",
    PDF uses "Page N". Hard-caps at max_chars (~50K-token safety margin
    under Claude Sonnet 4.6's 200K input limit).
    """
    label = chunk_label_for(deck.content_type)
    type_label = {
        "pptx": "SLIDE DECK",
        "docx": "WORD DOCUMENT",
        "pdf": "PDF DOCUMENT",
    }.get(deck.content_type, "DOCUMENT")

    blocks: list[str] = [f"# {type_label}: {deck.name}\n"]
    if deck.description:
        blocks.append(f"Description: {deck.description}\n")
    if deck.tags:
        blocks.append(f"Tags: {', '.join(deck.tags)}\n")
    for s in deck.slides:
        blocks.append(slide_to_context(s, label=label))
    joined = "\n\n".join(blocks)
    if len(joined) > max_chars:
        joined = joined[: max_chars - 200] + "\n\n[truncated at context cap]"
    return joined
