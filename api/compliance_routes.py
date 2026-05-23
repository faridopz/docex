"""
DOCex compliance routes.

Endpoints for the Compliance Check feature:
  POST   /compliance/policy             — interpret a policy doc into a rulebook
  GET    /compliance/rulebooks          — list saved rulebooks (summaries)
  GET    /compliance/rulebooks/{id}     — fetch one rulebook in full
  PUT    /compliance/rulebooks/{id}     — update (edit / activate / rename)
  DELETE /compliance/rulebooks/{id}     — delete a rulebook
  POST   /compliance/check/single       — check one payment against a rulebook
  POST   /compliance/check/batch        — check many payments against a rulebook

Rulebooks are persisted as JSON files in {project_root}/rulebooks/{id}.json.
File-based storage is sufficient for MVP — swaps cleanly to Supabase in
Phase 2 (same Pydantic models, just a different store).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import uuid
from pathlib import Path
from typing import Annotated

import pdfplumber
from docx import Document as DocxDocument
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

# Same sys.path hack the rest of api/ uses to import root-level modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from compliance import (  # noqa: E402
    check_payment_batch,
    check_payment_safe,
    interpret_policy,
)
from models import (  # noqa: E402
    ComplianceCheckBatchResult,
    ComplianceCheckResult,
    PolicyRulebook,
)
from notifications import send_check_notification  # noqa: E402
from .schemas import (  # noqa: E402
    CheckListResponse,
    CheckSummary,
    RulebookListResponse,
    RulebookSummary,
    RulebookUpdateIn,
)

router = APIRouter(prefix="/compliance", tags=["compliance"])


# ─── File extraction ────────────────────────────────────────────────────────
#
# Duplicated from api/main.py rather than cross-imported. The cross-import
# (from .main import _extract_text) is fragile because main.py imports this
# router at module load time, which would create an import cycle. The right
# fix later is to extract these into api/files.py; for now keeping them
# local avoids touching the working extraction flow.

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
        return _docx_to_text(doc).strip()

    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("latin-1").strip()


def _docx_to_text(doc: DocxDocument) -> str:
    """Flatten a docx into plain text including table cells.

    Iterates the body in document order so paragraphs and tables appear in
    the right sequence — important when answers depend on the table that
    immediately follows a heading.
    """
    from docx.oxml.ns import qn

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
            parts.append("")
    return "\n".join(parts)


def _read_files(uploads: list[UploadFile]) -> list[tuple[str, str]]:
    """Extract text from uploaded files into (filename, text) tuples.

    Skips files that fail to parse individually (logs a warning), but raises
    a 422 if NO files yielded text — there's nothing to work with downstream.
    """
    out: list[tuple[str, str]] = []
    for upload in uploads:
        filename = upload.filename or f"file_{uuid.uuid4().hex[:6]}"
        try:
            text = _extract_text(upload)
            if text:
                out.append((filename, text))
        except Exception as exc:
            print(f"Warning: could not extract text from '{filename}': {exc}")
    if not out:
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from the uploaded documents. "
                   "Make sure the files are readable PDFs, DOCX, or plain text.",
        )
    return out


# ─── Rulebook persistence (file-based) ──────────────────────────────────────
#
# One JSON file per rulebook under {project_root}/rulebooks/. Stores the full
# PolicyRulebook including created_at and updated_at timestamps. Swaps to
# Supabase in Phase 2 — same model shape, different store.

_RULEBOOK_DIR = Path(__file__).parent.parent / "rulebooks"
_CHECK_DIR = Path(__file__).parent.parent / "checks"


def _ensure_rulebook_dir() -> None:
    _RULEBOOK_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    """UTC timestamp in ISO 8601. String form keeps round-tripping painless
    on the frontend (no Date deserialisation gymnastics)."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _rulebook_path(rulebook_id: str) -> Path:
    # Defensive: rulebook IDs are server-generated kebab-case-uuids, but if
    # a forged ID ever reaches us we don't want it traversing outside the
    # rulebooks directory.
    if "/" in rulebook_id or ".." in rulebook_id or not rulebook_id.strip():
        raise HTTPException(status_code=400, detail="Invalid rulebook id.")
    return _RULEBOOK_DIR / f"{rulebook_id}.json"


def _save_rulebook(rulebook: PolicyRulebook) -> PolicyRulebook:
    """Persist a rulebook to disk. Sets timestamps and returns the saved object."""
    _ensure_rulebook_dir()
    now = _now_iso()
    if not rulebook.created_at:
        rulebook.created_at = now
    rulebook.updated_at = now
    _rulebook_path(rulebook.id).write_text(rulebook.model_dump_json(indent=2))
    return rulebook


def _load_rulebook(rulebook_id: str) -> PolicyRulebook:
    path = _rulebook_path(rulebook_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Rulebook '{rulebook_id}' not found.",
        )
    try:
        return PolicyRulebook.model_validate_json(path.read_text())
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load rulebook '{rulebook_id}': {exc}",
        ) from exc


def _list_rulebooks() -> list[PolicyRulebook]:
    """List every persisted rulebook. Skips corrupted files rather than
    failing the whole list — the officer can still see all valid rulebooks."""
    _ensure_rulebook_dir()
    rulebooks: list[PolicyRulebook] = []
    for path in sorted(_RULEBOOK_DIR.glob("*.json")):
        try:
            rulebooks.append(PolicyRulebook.model_validate_json(path.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupted rulebook {path.name}: {exc}")
            continue
    return rulebooks


def _to_summary(rb: PolicyRulebook) -> RulebookSummary:
    return RulebookSummary(
        id=rb.id,
        name=rb.name,
        rule_count=len(rb.rules),
        active_rule_count=sum(1 for r in rb.rules if r.active),
        source_documents=rb.source_documents,
        created_at=rb.created_at,
        updated_at=rb.updated_at,
    )


# ─── Check persistence (file-based) ─────────────────────────────────────────
#
# Every check that runs is auto-saved to /checks/{payment_id}.json so it
# survives page refreshes, gets a stable URL, and can be marked approved.
# The rulebook snapshot is captured at save time so editing the rulebook
# later doesn't retroactively change the audit trail.

def _ensure_check_dir() -> None:
    _CHECK_DIR.mkdir(parents=True, exist_ok=True)


def _check_path(check_id: str) -> Path:
    if "/" in check_id or ".." in check_id or not check_id.strip():
        raise HTTPException(status_code=400, detail="Invalid check id.")
    return _CHECK_DIR / f"{check_id}.json"


def _save_check(
    check: ComplianceCheckResult,
    rulebook: PolicyRulebook,
) -> ComplianceCheckResult:
    """Persist a check result. Snapshots the active rules at check time so
    later rulebook edits don't change historical checks."""
    _ensure_check_dir()
    if not check.created_at:
        check.created_at = _now_iso()
    # Snapshot active rules — only on first save, never overwrite an existing
    # snapshot. This protects the audit trail against accidental re-saves.
    if check.rulebook_snapshot_rules is None:
        check.rulebook_snapshot_rules = [r for r in rulebook.rules if r.active]
    _check_path(check.payment_id).write_text(check.model_dump_json(indent=2))
    return check


def _load_check(check_id: str) -> ComplianceCheckResult:
    path = _check_path(check_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Check '{check_id}' not found.",
        )
    try:
        return ComplianceCheckResult.model_validate_json(path.read_text())
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load check '{check_id}': {exc}",
        ) from exc


def _list_checks() -> list[ComplianceCheckResult]:
    """List every persisted check, newest first. Skips corrupted files."""
    _ensure_check_dir()
    paths = sorted(
        _CHECK_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    checks: list[ComplianceCheckResult] = []
    for path in paths:
        try:
            checks.append(ComplianceCheckResult.model_validate_json(path.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupted check {path.name}: {exc}")
            continue
    return checks


def _to_check_summary(c: ComplianceCheckResult) -> CheckSummary:
    return CheckSummary(
        payment_id=c.payment_id,
        payment_label=c.payment_label,
        rulebook_id=c.rulebook_id,
        rulebook_name=c.rulebook_name,
        overall_verdict=c.overall_verdict,
        overall_summary=c.overall_summary,
        document_count=len(c.documents),
        created_at=c.created_at,
        approved=c.approved,
        approved_at=c.approved_at,
        error=c.error,
    )


# ─── Policy interpretation ─────────────────────────────────────────────────

@router.post("/policy", response_model=PolicyRulebook)
async def interpret_policy_endpoint(
    policy_documents: Annotated[
        list[UploadFile],
        File(description="Policy document(s) to interpret — PDF, DOCX, or TXT"),
    ],
    name: Annotated[
        str,
        Form(description="Human-readable name, e.g. 'TA Connect Procurement Policy 2025'"),
    ],
) -> PolicyRulebook:
    """Interpret a policy document into a structured PolicyRulebook and save it.

    Pass 1 of the two-pass compliance flow. Read the policy doc(s), extract
    every testable rule into the rulebook format, persist to disk, return
    the rulebook for the officer to review and optionally edit.
    """
    if not name.strip():
        raise HTTPException(status_code=422, detail="Rulebook name is required.")
    docs = _read_files(policy_documents)
    try:
        rulebook = interpret_policy(docs, name.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _save_rulebook(rulebook)


# ─── Rulebook CRUD ─────────────────────────────────────────────────────────

@router.get("/rulebooks", response_model=RulebookListResponse)
async def list_rulebooks_endpoint() -> RulebookListResponse:
    """List all saved rulebooks (summary view) — for the rulebook landing page."""
    return RulebookListResponse(
        rulebooks=[_to_summary(rb) for rb in _list_rulebooks()]
    )


@router.get("/rulebooks/{rulebook_id}", response_model=PolicyRulebook)
async def get_rulebook_endpoint(rulebook_id: str) -> PolicyRulebook:
    """Fetch one rulebook in full — for the editor or before running checks."""
    return _load_rulebook(rulebook_id)


@router.put("/rulebooks/{rulebook_id}", response_model=PolicyRulebook)
async def update_rulebook_endpoint(
    rulebook_id: str,
    body: RulebookUpdateIn,
) -> PolicyRulebook:
    """Update a rulebook — rename, edit rules, change interpretation_notes,
    or update notification settings.

    Full replacement of the rules list. The editor sends the entire current
    state back; we save it. Simpler than diffing, and matches how the form
    works on the frontend.
    """
    rulebook = _load_rulebook(rulebook_id)
    if body.name and body.name.strip():
        rulebook.name = body.name.strip()
    rulebook.rules = body.rules
    rulebook.interpretation_notes = body.interpretation_notes
    # Notification settings — explicit None means "clear", empty string also
    # means "clear" (officer cleared the field in the UI).
    rulebook.notification_email = (
        body.notification_email.strip()
        if body.notification_email and body.notification_email.strip()
        else None
    )
    # Validate the trigger value — pydantic doesn't constrain it on input
    # because we don't want strict failures, but we do want valid storage.
    if body.notification_trigger in (
        "always",
        "flagged_or_blocked",
        "blocked_only",
    ):
        rulebook.notification_trigger = body.notification_trigger  # type: ignore[assignment]
    else:
        rulebook.notification_trigger = None
    return _save_rulebook(rulebook)


@router.delete("/rulebooks/{rulebook_id}")
async def delete_rulebook_endpoint(rulebook_id: str) -> dict:
    """Delete a rulebook permanently."""
    path = _rulebook_path(rulebook_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Rulebook '{rulebook_id}' not found.",
        )
    path.unlink()
    return {"deleted": rulebook_id}


# ─── Compliance checks ─────────────────────────────────────────────────────

@router.post("/check/single", response_model=ComplianceCheckResult)
async def check_single_endpoint(
    payment_documents: Annotated[
        list[UploadFile],
        File(description="Payment bundle — voucher + invoice + receipts + any other supporting docs"),
    ],
    rulebook_id: Annotated[
        str,
        Form(description="ID of the saved rulebook to check against"),
    ],
    payment_label: Annotated[
        str,
        Form(description="Label for this payment, e.g. 'Voucher #2025-04-17 — Office Supplies'"),
    ] = "Payment Request",
) -> ComplianceCheckResult:
    """Check one payment request bundle against a saved rulebook.

    The result is auto-saved to /checks/{payment_id}.json with a snapshot
    of the active rules at check time, so the audit trail can't drift if
    the rulebook is edited later. Returns per-rule verdicts plus the
    overall verdict and a one-line summary.
    """
    rulebook = _load_rulebook(rulebook_id)
    docs = _read_files(payment_documents)
    result = check_payment_safe(docs, rulebook, payment_label)
    # Auto-persist. Best-effort: a save failure is logged but doesn't
    # fail the request — the UI still gets the result and the user can
    # always re-run the check.
    try:
        _save_check(result, rulebook)
    except Exception as exc:
        print(f"Warning: failed to persist check {result.payment_id}: {exc}")
    # Send notification email if configured — best-effort, never blocks
    # the check response. A failed send is a warning, not an error.
    try:
        sent = send_check_notification(result, rulebook)
        if sent:
            print(
                f"[DOCex] Notified {rulebook.notification_email} "
                f"about check {result.payment_id} ({result.overall_verdict})"
            )
    except Exception as exc:
        print(f"Warning: notification send failed for {result.payment_id}: {exc}")
    return result


@router.post("/check/batch", response_model=ComplianceCheckBatchResult)
async def check_batch_endpoint(
    documents: Annotated[
        list[UploadFile],
        File(description="All files for all payments in this batch"),
    ],
    rulebook_id: Annotated[str, Form()],
    payments: Annotated[
        str,
        Form(description='JSON array: [{"label": "...", "filenames": [...]}]'),
    ],
) -> ComplianceCheckBatchResult:
    """Check many payment request bundles against one rulebook.

    Upload ALL files for ALL payments together, then pass a `payments` JSON
    array mapping each payment label to its specific filenames. Same shape
    as /extract/batch.

    Batch mode benefits from the cached system prompt + rulebook: the first
    check warms the cache, the rest fan out concurrently and only pay for
    their own payment-bundle tokens.

    Example payments JSON:
    [
      {"label": "Voucher #001 — Office Supplies",  "filenames": ["v1.pdf", "inv1.pdf", "r1a.jpg"]},
      {"label": "Voucher #002 — Workshop venue",   "filenames": ["v2.pdf", "inv2.pdf"]}
    ]
    """
    rulebook = _load_rulebook(rulebook_id)

    try:
        payments_raw = json.loads(payments)
        if not isinstance(payments_raw, list) or len(payments_raw) == 0:
            raise ValueError("Must be a non-empty array.")
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid payments JSON: {exc}",
        ) from exc

    # Extract text from every uploaded file, keyed by filename so each
    # payment can pluck its specific files out by name.
    file_texts: dict[str, tuple[str, str]] = {}
    for upload in documents:
        filename = upload.filename or f"file_{uuid.uuid4().hex[:6]}"
        try:
            text = _extract_text(upload)
            if text:
                file_texts[filename] = (filename, text)
        except Exception as exc:
            print(f"Warning: could not extract text from '{filename}': {exc}")

    if not file_texts:
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from any uploaded file.",
        )

    # Build the payment list, catching missing files loudly so the user knows
    # whether they forgot to upload a receipt rather than getting a silent
    # "no readable docs" downstream.
    payment_jobs: list[dict] = []
    for p in payments_raw:
        label = p.get("label", "Payment Request")
        requested = p.get("filenames", [])

        missing = [fn for fn in requested if fn not in file_texts]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Payment '{label}': these filenames were listed but not uploaded: {missing}. "
                       f"Uploaded files are: {list(file_texts.keys())}",
            )

        docs = [file_texts[fn] for fn in requested if fn in file_texts]
        if not docs:
            raise HTTPException(
                status_code=422,
                detail=f"Payment '{label}' has no readable documents.",
            )

        payment_jobs.append({"label": label, "documents": docs})

    batch = check_payment_batch(payment_jobs, rulebook)
    # Auto-persist every check in the batch — same audit story as single.
    for c in batch.checks:
        try:
            _save_check(c, rulebook)
        except Exception as exc:
            print(f"Warning: failed to persist check {c.payment_id}: {exc}")
    # Send one notification per check that matches the rulebook trigger.
    # For large batches with notification enabled, this could be N emails.
    # Acceptable for v1 — if it becomes annoying, a digest email is easy.
    for c in batch.checks:
        try:
            send_check_notification(c, rulebook)
        except Exception as exc:
            print(f"Warning: notification send failed for {c.payment_id}: {exc}")
    return batch


# ─── Check CRUD + approval ─────────────────────────────────────────────────

@router.get("/checks", response_model=CheckListResponse)
async def list_checks_endpoint() -> CheckListResponse:
    """List every persisted compliance check, newest first (summary view)."""
    return CheckListResponse(
        checks=[_to_check_summary(c) for c in _list_checks()]
    )


@router.get("/checks/{check_id}", response_model=ComplianceCheckResult)
async def get_check_endpoint(check_id: str) -> ComplianceCheckResult:
    """Fetch a single check by ID — the stable URL for auditors."""
    return _load_check(check_id)


@router.post(
    "/checks/{check_id}/approve",
    response_model=ComplianceCheckResult,
)
async def approve_check_endpoint(check_id: str) -> ComplianceCheckResult:
    """Mark a check as ED-approved. Sets the approved flag and timestamp."""
    check = _load_check(check_id)
    check.approved = True
    check.approved_at = _now_iso()
    # Direct write — don't pass through _save_check or it would try to
    # re-snapshot the rulebook (which we don't have at this point and
    # which is already correctly captured).
    _check_path(check_id).write_text(check.model_dump_json(indent=2))
    return check


@router.post(
    "/checks/{check_id}/unapprove",
    response_model=ComplianceCheckResult,
)
async def unapprove_check_endpoint(check_id: str) -> ComplianceCheckResult:
    """Reverse approval — sets approved=False, clears approved_at."""
    check = _load_check(check_id)
    check.approved = False
    check.approved_at = None
    _check_path(check_id).write_text(check.model_dump_json(indent=2))
    return check


@router.delete("/checks/{check_id}")
async def delete_check_endpoint(check_id: str) -> dict:
    """Delete a check permanently. Use with care — this removes audit trail."""
    path = _check_path(check_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Check '{check_id}' not found.",
        )
    path.unlink()
    return {"deleted": check_id}
