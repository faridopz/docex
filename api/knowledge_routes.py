"""
DOCex Knowledge Hub routes.

  POST   /knowledge/decks                — upload + parse a .pptx
  GET    /knowledge/decks                — list saved decks
  GET    /knowledge/decks/{id}           — fetch one deck in full
  DELETE /knowledge/decks/{id}           — delete a deck
  POST   /knowledge/decks/{id}/chat      — ask a question, get a cited answer

Persistence under {project_root}/decks/{deck_id}.json — same pattern as
every other primitive. Deck text content is stored inline in the JSON (a
67-slide deck lands at ~30-50 KB, well under any reasonable file-system
limit; no need for blob storage at MVP scale).
"""
from __future__ import annotations

import datetime as dt
import io
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge import ask, library_ask  # noqa: E402
from models import KnowledgeAnswer, SlideDeck  # noqa: E402
from slides import parse_document  # noqa: E402
import connectors  # noqa: E402

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


_DECK_DIR = Path(__file__).parent.parent / "decks"


def _ensure_dir() -> None:
    _DECK_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _deck_path(deck_id: str) -> Path:
    if "/" in deck_id or ".." in deck_id or not deck_id.strip():
        raise HTTPException(status_code=400, detail="Invalid deck id.")
    return _DECK_DIR / f"{deck_id}.json"


def _save_deck(deck: SlideDeck) -> SlideDeck:
    _ensure_dir()
    now = _now_iso()
    if not deck.created_at:
        deck.created_at = now
    deck.updated_at = now
    _deck_path(deck.id).write_text(deck.model_dump_json(indent=2))
    return deck


def _load_deck(deck_id: str) -> SlideDeck:
    path = _deck_path(deck_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Deck '{deck_id}' not found.")
    try:
        return SlideDeck.model_validate_json(path.read_text())
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load deck '{deck_id}': {exc}",
        ) from exc


def _list_decks() -> list[SlideDeck]:
    _ensure_dir()
    paths = sorted(
        _DECK_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    decks: list[SlideDeck] = []
    for p in paths:
        try:
            decks.append(SlideDeck.model_validate_json(p.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupted deck {p.name}: {exc}")
            continue
    return decks


# ─── Routes ─────────────────────────────────────────────────────────────────


_ALLOWED_EXTENSIONS = (".pptx", ".pptm", ".pdf", ".docx", ".docm")

# Hard cap on uploaded document size. Most NGO documents are well under
# 10 MB; an 80 MB PowerPoint exists (image-heavy decks) but is the outlier.
# 50 MB is a friendly ceiling — large enough that legitimate docs pass,
# small enough that a single malformed upload can't OOM the backend.
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/decks", response_model=SlideDeck)
async def upload_deck(
    file: Annotated[
        UploadFile,
        File(
            description=(
                "A document — .pptx (slide deck), .pdf, or .docx (Word). "
                "Up to ~200 chunks per document."
            )
        ),
    ],
    name: Annotated[
        str,
        Form(description="Optional display name. Defaults to the filename."),
    ] = "",
    description: Annotated[
        str,
        Form(description="Optional 1-2 sentence summary of what the document covers"),
    ] = "",
    tags: Annotated[
        str,
        Form(description="Optional comma-separated tags, e.g. 'Gates Foundation, Q1 2026'"),
    ] = "",
) -> SlideDeck:
    """Upload a document, parse it chunk-by-chunk, save it, return the deck.

    The "deck" terminology is historical — this endpoint now accepts any
    supported document format. Slides for PPTX, pages for PDF, sections
    for DOCX. The frontend labels chunks based on the deck's content_type.
    """
    fn = (file.filename or "").lower()
    if not fn.endswith(_ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Only PPTX, PDF, and DOCX files are supported. Got: "
                f"{file.filename!r}"
            ),
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(raw) > _MAX_UPLOAD_BYTES:
        mb = len(raw) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File is {mb:.1f} MB — DOCex's Knowledge Hub accepts up "
                f"to {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB per document. "
                f"If this is an image-heavy deck, try exporting it as a PDF first."
            ),
        )

    try:
        deck = parse_document(
            io.BytesIO(raw),
            name=name.strip() or None,
            source_filename=file.filename or "document",
            description=description.strip() or None,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse {file.filename!r}: {exc}",
        ) from exc

    if deck.slide_count == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "Parsed document has zero content chunks. Is the file empty "
                "or image-only?"
            ),
        )

    return _save_deck(deck)


@router.get("/decks", response_model=dict)
def list_decks_endpoint() -> dict:
    """List every saved deck, newest first. Slim summaries — the per-slide
    content is heavy, so list views drop the slides array. Frontend fetches
    full content via /knowledge/decks/{id}."""
    decks = _list_decks()
    return {
        "decks": [
            {
                "id": d.id,
                "name": d.name,
                "source_filename": d.source_filename,
                "content_type": d.content_type,
                "slide_count": d.slide_count,
                "tags": d.tags,
                "description": d.description,
                "folder": d.folder,
                "created_at": d.created_at,
                "updated_at": d.updated_at,
            }
            for d in decks
        ]
    }


@router.get("/decks/{deck_id}", response_model=SlideDeck)
def get_deck(deck_id: str) -> SlideDeck:
    return _load_deck(deck_id)


@router.delete("/decks/{deck_id}")
def delete_deck(deck_id: str) -> dict[str, str]:
    path = _deck_path(deck_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Deck '{deck_id}' not found.")
    path.unlink()
    return {"status": "deleted", "deck_id": deck_id}


# ─── Chat ───────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    question: str


@router.post("/decks/{deck_id}/chat", response_model=KnowledgeAnswer)
def chat_with_deck(deck_id: str, body: ChatRequest) -> KnowledgeAnswer:
    """Ask one question about one deck. Returns a cited answer."""
    deck = _load_deck(deck_id)
    return ask(deck=deck, question=body.question)


# ─── Library-wide chat ──────────────────────────────────────────────────────


class LibraryChatRequest(BaseModel):
    question: str
    # Optional folder filter — when set, only documents in this exact folder
    # (or descendant folders) are searched. Lets the user scope chat to a
    # specific area of their library ("only ask my Reports folder").
    folder: Optional[str] = None
    # Optional tag filter — when set, only documents carrying ALL these
    # tags are searched.
    tags: Optional[list[str]] = None


@router.post("/library/chat", response_model=KnowledgeAnswer)
def chat_with_library(body: LibraryChatRequest) -> KnowledgeAnswer:
    """
    Ask one question across the entire document library.

    Optional `folder` and `tags` filters narrow the search to a subset —
    useful when the library is large and the user wants to scope (e.g.
    "ask just my quarterly reports"). Without filters, every document
    is included.

    Returns a KnowledgeAnswer whose citations carry deck_id + deck_name,
    so the frontend can render each citation chip as a deep-link to the
    right document at the right chunk.
    """
    decks = _list_decks()

    # Apply folder filter — exact match OR descendant. Empty folder means
    # "root" — matches decks with no folder set.
    if body.folder is not None:
        target = body.folder.strip().strip("/")
        if target == "":
            # Root means: documents with no folder
            decks = [d for d in decks if not d.folder]
        else:
            decks = [
                d
                for d in decks
                if d.folder
                and (d.folder == target or d.folder.startswith(target + "/"))
            ]

    # Apply tag filter — ALL tags must be present (AND semantics)
    if body.tags:
        required = {t.strip().lower() for t in body.tags if t.strip()}
        decks = [
            d for d in decks if required.issubset({t.lower() for t in d.tags})
        ]

    return library_ask(question=body.question, decks=decks)


# ─── Folder management ──────────────────────────────────────────────────────


class DeckUpdateRequest(BaseModel):
    """Patch a saved deck — rename, move folder, edit description, retag.

    All fields are optional. Sending only the ones you want to change
    leaves the others alone. To clear a field (e.g. unset folder), send
    an empty string.
    """
    name: Optional[str] = None
    folder: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


@router.patch("/decks/{deck_id}", response_model=SlideDeck)
def update_deck(deck_id: str, body: DeckUpdateRequest) -> SlideDeck:
    """Update deck metadata — used for moving to a folder, renaming, etc."""
    deck = _load_deck(deck_id)

    if body.name is not None:
        cleaned = body.name.strip()
        if cleaned:
            deck.name = cleaned
    if body.folder is not None:
        # Normalise: trim whitespace + leading/trailing slashes.
        # Empty string → "root" (clear the folder).
        cleaned = body.folder.strip().strip("/")
        deck.folder = cleaned or None
    if body.description is not None:
        deck.description = body.description.strip() or None
    if body.tags is not None:
        deck.tags = [t.strip() for t in body.tags if t.strip()]

    return _save_deck(deck)


class SuggestFolderRequest(BaseModel):
    deck_id: str


@router.post("/folders/suggest", response_model=dict)
def suggest_folder(body: SuggestFolderRequest) -> dict:
    """Ask Claude to suggest a folder path for a document, based on its
    content + the existing folder structure in the library.

    Returns:
      {
        "suggested_folder": "Reports/2026/Q1",
        "reasoning": "This is a Q1 2026 progress report, fits the existing Reports/2026 hierarchy."
      }

    Falls back gracefully if Claude is unreachable — returns a safe
    suggestion based on tags + name.
    """
    deck = _load_deck(body.deck_id)
    all_decks = _list_decks()

    # Existing folder paths (deduped, sorted) — gives Claude the structure
    # to reuse rather than inventing a new hierarchy every time.
    existing_folders = sorted({d.folder for d in all_decks if d.folder})

    # Snippet of the deck's content — first 3 chunk titles + description
    title_hints = [s.title for s in deck.slides[:3] if s and s.title]
    snippet = " · ".join(title_hints) if title_hints else (deck.description or "")

    prompt = (
        f"Suggest a folder path for this document in a knowledge library. "
        f"Folder paths use slash-delimited hierarchies like 'Reports/2026/Q1' "
        f"or 'Policies/Anti-Fraud'.\n\n"
        f"Document name: {deck.name}\n"
        f"Document type: {deck.content_type}\n"
        f"Document tags: {', '.join(deck.tags) if deck.tags else '(none)'}\n"
        f"Content snippet: {snippet[:300]}\n\n"
        f"Existing folders in the library:\n"
        + ("\n".join(f"  - {f}" for f in existing_folders) if existing_folders else "  (none yet)")
        + "\n\n"
        f"Suggest ONE folder path. Reuse an existing folder when it fits; "
        f"only create a new one when nothing fits. Respond ONLY in JSON: "
        f'{{"suggested_folder": "...", "reasoning": "one sentence"}}.'
    )

    try:
        import json

        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # Strip code fences if Claude wrapped its JSON
        if raw.startswith("```"):
            nl = raw.find("\n")
            if nl != -1:
                raw = raw[nl + 1 :]
            if raw.endswith("```"):
                raw = raw[:-3]
        data = json.loads(raw.strip())
        return {
            "suggested_folder": str(data.get("suggested_folder", "")).strip().strip("/"),
            "reasoning": str(data.get("reasoning", "")).strip()
            or "Based on document name + existing structure.",
        }
    except Exception as exc:
        # Safe fallback: use the first tag if available, else "Uncategorised"
        fallback = deck.tags[0] if deck.tags else "Uncategorised"
        return {
            "suggested_folder": fallback,
            "reasoning": f"Auto-suggestion unavailable ({type(exc).__name__}); fell back to tag-based folder.",
        }


# ─── External integrations (pluggable connectors) ───────────────────────────
#
# Pull documents from external systems (ERPNext today; other ERPs / drives
# next) into the Hub so they become retrieval-searchable. We index a copy and
# re-sync — the source is never queried live on a search. Provider-agnostic:
# every connector in connectors.REGISTRY is exposed here automatically.


class IntegrationInfo(BaseModel):
    id: str
    label: str
    configured: bool
    detail: str          # host / status hint (non-sensitive)
    synced: int          # documents in the Hub sourced from this provider


class IntegrationSyncResult(BaseModel):
    provider: str
    found: int           # supported documents seen in the source
    ingested: int        # newly pulled into the Hub
    skipped: int         # already synced (deduped by source_ref)
    failed: int
    errors: list[str]


@router.get("/integrations", response_model=list[IntegrationInfo])
async def list_integrations() -> list[IntegrationInfo]:
    decks = _list_decks()
    out: list[IntegrationInfo] = []
    for c in connectors.list_connectors():
        synced = sum(
            1 for d in decks if (d.source_ref or "").startswith(f"{c.id}:")
        )
        out.append(
            IntegrationInfo(
                id=c.id,
                label=c.label,
                configured=c.is_configured(),
                detail=c.status_detail(),
                synced=synced,
            )
        )
    return out


@router.post(
    "/integrations/{provider}/sync", response_model=IntegrationSyncResult
)
async def sync_integration(provider: str) -> IntegrationSyncResult:
    """Pull new documents from an external provider into the Knowledge Hub.

    Lists the source's documents, skips any already ingested (deduped on
    source_ref), downloads + parses the rest, and saves them as searchable
    documents tagged with their source context. Idempotent — safe to re-run
    and to schedule.
    """
    conn = connectors.get_connector(provider)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'.")
    if not conn.is_configured():
        raise HTTPException(
            status_code=400,
            detail=f"{conn.label} isn't configured. Add its credentials to the backend .env.",
        )
    try:
        docs = conn.list_documents()
    except connectors.ConnectorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    existing = {d.source_ref for d in _list_decks() if d.source_ref}
    ingested = skipped = failed = 0
    errors: list[str] = []

    for ref in docs:
        source_ref = f"{conn.id}:{ref.id}"
        if source_ref in existing:
            skipped += 1
            continue
        try:
            data = conn.download(ref)
            deck = parse_document(
                io.BytesIO(data),
                name=ref.name,
                source_filename=ref.name,
                tags=ref.tags,
                deck_id=uuid.uuid4().hex,
            )
            deck.source_ref = source_ref
            deck.folder = conn.label
            _save_deck(deck)
            ingested += 1
        except Exception as exc:  # noqa: BLE001 — one bad file shouldn't stop the sync
            failed += 1
            errors.append(f"{ref.name}: {exc}")

    return IntegrationSyncResult(
        provider=conn.id,
        found=len(docs),
        ingested=ingested,
        skipped=skipped,
        failed=failed,
        errors=errors[:20],
    )
