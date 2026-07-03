"""
DOCex compliance routes.

Endpoints for the Compliance Check feature:
  POST   /compliance/policy             — interpret a policy doc into a rulebook
  POST   /compliance/rulebooks/starter  — seed a deterministic-only rulebook from a named template
  GET    /compliance/rulebooks          — list saved rulebooks (summaries)
  GET    /compliance/rulebooks/{id}     — fetch one rulebook in full
  PUT    /compliance/rulebooks/{id}     — update (edit / activate / rename)
  DELETE /compliance/rulebooks/{id}     — delete a rulebook
  POST   /compliance/check/single       — check one document-based payment against a rulebook
  POST   /compliance/check/form         — check a form/hybrid submission (see PaymentType.intake_mode)
  POST   /compliance/check/batch        — check many payments against a rulebook

Rulebooks are persisted as JSON files in {project_root}/rulebooks/{id}.json.
File-based storage is sufficient for MVP — swaps cleanly to Supabase in
Phase 2 (same Pydantic models, just a different store).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Annotated, Literal, Optional

import pdfplumber
from docx import Document as DocxDocument
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

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
    DecisionEvent,
    DecisionEventType,
    FormField,
    OrgProfile,
    PaymentType,
    PolicyRulebook,
    RiskEntry,
    default_travel_advance_rules,
    default_travel_retirement_rules,
    default_vendor_payment_rules,
)
from pydantic import BaseModel  # noqa: E402
from notifications import (  # noqa: E402
    _send_raw_email,
    looks_like_email,
    send_check_notification,
    send_clarification_email,
    send_escalation_email,
)
from approval_tokens import make_token, verify_token  # noqa: E402
from approval_webhook import emit_approval_request, verify_callback_secret  # noqa: E402
import fast_extract  # noqa: E402 — fast PDF text extraction (fitz-first)
from doc_completeness import check_completeness  # noqa: E402 — deterministic doc-presence
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
        # Fast path: PyMuPDF (fitz) — ~5-10x pdfplumber — with automatic
        # pdfplumber fallback if fitz isn't installed. Same "=== PAGE N ==="
        # markers, so source-page citations are unaffected.
        return fast_extract.extract_text(upload.filename or "", raw).strip()

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
_ORG_PROFILE_PATH = Path(__file__).parent.parent / "org_profile.json"


def _load_org_profile() -> OrgProfile:
    """The org's config (singleton). Returns sensible defaults if unset."""
    try:
        if _ORG_PROFILE_PATH.exists():
            return OrgProfile.model_validate_json(_ORG_PROFILE_PATH.read_text())
    except Exception:  # noqa: BLE001 — never let a bad profile break the app
        pass
    return OrgProfile()


def _save_org_profile(profile: OrgProfile) -> OrgProfile:
    _ORG_PROFILE_PATH.write_text(profile.model_dump_json(indent=2))
    return profile


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
    later rulebook edits don't change historical checks. Also seeds the
    decision_log with a check_run event on first save."""
    _ensure_check_dir()
    is_first_save = not check.created_at
    if is_first_save:
        check.created_at = _now_iso()
    # Snapshot active rules — only on first save, never overwrite an existing
    # snapshot. This protects the audit trail against accidental re-saves.
    if check.rulebook_snapshot_rules is None:
        check.rulebook_snapshot_rules = [r for r in rulebook.rules if r.active]
    # Seed the decision log with the first event on initial save. Subsequent
    # events get appended by dedicated endpoints (approve, note, dismiss,
    # etc.) — never here, so re-saves don't double-log.
    if is_first_save and not check.decision_log:
        flag_count = sum(1 for r in check.results if r.verdict in ("flag", "block"))
        check.decision_log.append(
            DecisionEvent(
                type="check_run",
                timestamp=check.created_at,
                note=(
                    f"Check ran against rulebook '{rulebook.name}' — verdict "
                    f"{check.overall_verdict}"
                    + (
                        f" with {flag_count} flag(s) or block(s) to review."
                        if flag_count
                        else " — all rules satisfied."
                    )
                ),
            )
        )
    _check_path(check.payment_id).write_text(check.model_dump_json(indent=2))
    return check


def _append_decision_event(
    check: ComplianceCheckResult, event: DecisionEvent
) -> None:
    """Append an event to a check's decision log and persist. Used by every
    endpoint that mutates check state (approve, unapprove, note, dismiss).
    The event-log is append-only; existing entries are never edited or
    removed — that's the whole point of an audit trail."""
    check.decision_log.append(event)
    _check_path(check.payment_id).write_text(check.model_dump_json(indent=2))


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


def _try_load_check(check_id: str) -> Optional[ComplianceCheckResult]:
    """Non-raising variant of _load_check — a bad or unknown reference in a
    submitted form should resolve to a 'block' verdict on that rule, not a
    hard 404 for the whole request."""
    if not (check_id or "").strip():
        return None
    try:
        return _load_check(check_id.strip())
    except HTTPException:
        return None


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


def _derive_lifecycle(c: ComplianceCheckResult) -> tuple[str, str]:
    """Where is this payment in the pipeline? Returns (lifecycle, stage_label).
    Org-agnostic: built from the verdict, the rulebook's approval workflow, the
    signed stages, and paid status — works for any org's chain."""
    if c.paid:
        return "paid", "Paid"
    if c.approved:
        return "approved", "Approved — ready for payment"
    workflow = _workflow_for(c)
    signed = _signed_stages(c)
    open_risks = [r for r in (c.risks or []) if r.status != "resolved"]
    # Unresolved blocks/flags/risks with no sign-off progress → needs attention.
    if not signed and (c.overall_verdict == "blocked" or open_risks):
        return "needs_attention", (
            "Blocked — needs resolution" if c.overall_verdict == "blocked"
            else "Open risk — needs action"
        )
    if not signed and c.overall_verdict == "flagged":
        return "needs_attention", "Flagged — needs review"
    # Checked and clean, but no sign-off yet = still a REQUISITION (the request),
    # before Finance turns it into a payment voucher and the chain begins.
    if not signed:
        return "requisition", "Checked — awaiting PV / first sign-off"
    # At least one stage signed = a PV has been raised and is moving through the
    # approval chain.
    if workflow:
        nxt = next((s for s in workflow if s not in signed), None)
        if nxt:
            return "in_approval", f"Awaiting {nxt}"
        return "approved", "All sign-offs in — ready for payment"
    return "in_approval", "In approval"


def _to_check_summary(c: ComplianceCheckResult) -> CheckSummary:
    lifecycle, stage_label = _derive_lifecycle(c)
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
        pending_with=c.pending_with,
        pending_question=c.pending_question,
        paid=c.paid,
        paid_at=c.paid_at,
        lifecycle=lifecycle,
        stage_label=stage_label,
        open_risk_count=len([r for r in (c.risks or []) if r.status != "resolved"]),
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
    # Inherit the organisation's default approval chain so a new rulebook
    # matches THIS org's process out of the box (not a generic default). The
    # officer can still tailor it in the rulebook's workflow editor.
    org = _load_org_profile()
    if org.default_approval_workflow:
        rulebook.approval_workflow = list(org.default_approval_workflow)
    rulebook.org = org.name or rulebook.org
    return _save_rulebook(rulebook)


# ─── Organisation profile (the per-org config layer) ───────────────────────

class PrecheckOut(BaseModel):
    """Instant, deterministic document-completeness result (no LLM)."""
    checklist: list[str]              # required docs for the chosen type
    present: list[str]
    missing: list[str]
    unclassified_files: list[str]
    complete: bool


@router.post("/precheck", response_model=PrecheckOut)
async def precheck_endpoint(
    payment_documents: Annotated[
        list[UploadFile],
        File(description="The requisition's documents, to check for completeness"),
    ],
    payment_type: Annotated[str, Form(description="Payment type name")] = "",
) -> PrecheckOut:
    """Deterministic pre-flight: are the required documents attached? Runs in
    milliseconds with no LLM — the first, cheapest layer of the check, so the
    slow AI pass only runs on complete bundles. Required docs come from the
    org's payment-type checklist."""
    org = _load_org_profile()
    want = payment_type.strip().lower()
    pt = next(
        (t for t in org.payment_types if t.name.strip().lower() == want), None
    )
    required = pt.required_documents if pt else []
    files: list[tuple[str, str]] = []
    for u in payment_documents:
        raw = u.file.read()
        files.append((u.filename or "file", fast_extract.extract_text(u.filename or "", raw)))
    result = check_completeness(required, files)
    return PrecheckOut(checklist=required, **result)


@router.get("/org-profile", response_model=OrgProfile)
async def get_org_profile_endpoint() -> OrgProfile:
    """The organisation's configuration — name, roles, default approval chain,
    and the stage→person directory. Drives how DOCex adapts to each client."""
    return _load_org_profile()


@router.put("/org-profile", response_model=OrgProfile)
async def update_org_profile_endpoint(body: OrgProfile) -> OrgProfile:
    """Save the org config. Stage names and roles are trimmed; the default
    workflow is de-duped (case-insensitive) and order-preserving."""
    seen: set[str] = set()
    workflow: list[str] = []
    for stage in body.default_approval_workflow:
        s = (stage or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            workflow.append(s)
    body.default_approval_workflow = workflow
    body.roles = [r.strip() for r in body.roles if (r or "").strip()]
    body.directory = {
        k.strip(): v.strip()
        for k, v in (body.directory or {}).items()
        if k.strip() and v.strip()
    }
    body.name = (body.name or "").strip() or "Your organisation"
    # Payment types — keep those with a name; trim names + required docs.
    # Preserves intake_mode/form_fields/default_rulebook_id (added for the
    # forms build) so a save from the settings screen doesn't silently
    # revert a form/hybrid payment type back to a bare document checklist —
    # this endpoint used to rebuild PaymentType from only 3 fields, which
    # dropped the other three on every save. Every org's own payment types
    # round-trip through here, so this fix applies to any org, not just one.
    cleaned_types: list[PaymentType] = []
    for pt in body.payment_types or []:
        nm = (pt.name or "").strip()
        if not nm:
            continue
        cleaned_fields = [
            FormField(
                name=f.name.strip(), label=(f.label or "").strip() or f.name.strip(),
                type=f.type, required=f.required,
                choices=[c.strip() for c in f.choices if (c or "").strip()],
                # Preserve choices_source — dropped here once already (same
                # bug class as the Phase 3 fix above, on a different field).
                choices_source=f.choices_source,
            )
            for f in (pt.form_fields or [])
            if (f.name or "").strip()
        ]
        cleaned_types.append(
            PaymentType(
                name=nm,
                required_documents=[d.strip() for d in pt.required_documents if (d or "").strip()],
                notes=(pt.notes or "").strip() or None,
                intake_mode=pt.intake_mode if pt.intake_mode in ("document", "form", "hybrid") else "document",
                form_fields=cleaned_fields,
                default_rulebook_id=(pt.default_rulebook_id or "").strip() or None,
            )
        )
    body.payment_types = cleaned_types
    body.payment_subject = (body.payment_subject or "").strip() or "Payment requisition"
    # Enabled modules — keep only known values; never allow an empty set (an org
    # with zero modules would see a blank app), so fall back to all three.
    valid = {"compliance", "screening", "knowledge"}
    mods = [m.strip() for m in (body.enabled_modules or []) if m.strip() in valid]
    body.enabled_modules = mods or ["compliance", "screening", "knowledge"]
    # Approved vendor list — trim blanks, drop exact duplicates
    # (case-insensitive), order-preserving.
    seen_vendors: set[str] = set()
    vendors: list[str] = []
    for v in body.approved_vendors or []:
        vv = (v or "").strip()
        if vv and vv.lower() not in seen_vendors:
            seen_vendors.add(vv.lower())
            vendors.append(vv)
    body.approved_vendors = vendors
    body.updated_at = _now_iso()
    return _save_org_profile(body)


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
    # Approval workflow — None means "leave unchanged"; a provided list (even
    # empty) replaces it. Strip blanks and dedupe while preserving order so the
    # editor can't save empty/duplicate stages.
    if body.approval_workflow is not None:
        seen: set[str] = set()
        cleaned: list[str] = []
        for stage in body.approval_workflow:
            s = (stage or "").strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                cleaned.append(s)
        rulebook.approval_workflow = cleaned
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


# ─── Starter rulebooks (deterministic-only, for form/hybrid payment types) ──
#
# A form-mode payment type (e.g. Travel Advance) usually has no policy PDF
# to interpret — its rules ARE the deterministic field checks. This registry
# maps a template "kind" to a rules factory in models.py. It's a convenience,
# not a hardcoded engine assumption: the rulebook it produces is a completely
# normal, editable PolicyRulebook — any org can rename it, edit its rules, or
# delete it, exactly like an AI-interpreted one. Add a new kind here as more
# form/hybrid payment types ship; nothing about this is TA-Connect-specific.
_STARTER_RULEBOOK_TEMPLATES: dict[str, tuple[str, object]] = {
    "travel_advance": ("Travel Advance Rules", default_travel_advance_rules),
    "travel_retirement": ("Travel Retirement Rules", default_travel_retirement_rules),
    "vendor_payment": ("Vendor Payment Rules", default_vendor_payment_rules),
}


class StarterRulebookIn(BaseModel):
    kind: str                          # one of _STARTER_RULEBOOK_TEMPLATES
    name: Optional[str] = None         # override the template's default name


@router.post("/rulebooks/starter", response_model=PolicyRulebook)
async def create_starter_rulebook(body: StarterRulebookIn) -> PolicyRulebook:
    """Seed a deterministic-only rulebook from a named starter template —
    no policy PDF, no AI call, no cost. Every rule it creates is a normal
    PolicyRule the officer can edit or deactivate afterward exactly like
    one interpreted from a document."""
    entry = _STARTER_RULEBOOK_TEMPLATES.get(body.kind)
    if entry is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown starter kind '{body.kind}'. Available: {sorted(_STARTER_RULEBOOK_TEMPLATES)}",
        )
    default_name, rules_factory = entry
    org = _load_org_profile()
    rulebook = PolicyRulebook(
        id=f"rb-{uuid.uuid4().hex[:8]}",
        name=(body.name or "").strip() or default_name,
        source_documents=[],
        rules=rules_factory(),
        org=org.name or None,
        approval_workflow=list(org.default_approval_workflow) if org.default_approval_workflow else ["Approval"],
    )
    return _save_rulebook(rulebook)


# ─── Compliance checks ─────────────────────────────────────────────────────

class RouteSuggestionOut(BaseModel):
    rulebook_id: str
    rulebook_name: str
    score: float
    confidence: str
    matched_terms: list[str]


@router.post("/route", response_model=list[RouteSuggestionOut])
async def route_payment_endpoint(
    payment_documents: Annotated[
        list[UploadFile],
        File(description="Payment bundle to auto-match against saved policy sets"),
    ],
) -> list[RouteSuggestionOut]:
    """Auto-select the best-fitting policy set(s) for a payment.

    Reads the uploaded documents and ranks every saved rulebook by how well
    it fits — so the officer can apply the right policy without choosing it
    manually. Returns suggestions newest-first by score with a confidence
    flag and the terms that matched.
    """
    import compliance_router  # local import keeps module load light

    rulebooks = _list_rulebooks()
    if not rulebooks:
        return []
    text = "\n\n".join(filter(None, (_extract_text(f) for f in payment_documents)))
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="No readable text found in the uploaded documents.",
        )
    suggestions = compliance_router.rank_rulebooks(text, rulebooks)
    return [
        RouteSuggestionOut(
            rulebook_id=s.rulebook_id,
            rulebook_name=s.rulebook_name,
            score=s.score,
            confidence=s.confidence,
            matched_terms=s.matched_terms,
        )
        for s in suggestions
    ]


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
    # ─── Requisition context (Phase 2 — forms build) ────────────────────
    # Captured directly from the submit form now, instead of requiring the
    # AI to parse a scanned "Payment Requisition Form" PDF. All optional —
    # legacy callers and payment types that don't collect these keep working
    # unchanged. Only non-blank values are applied (see below), so a
    # partially-filled form never overwrites a field with an empty string.
    requisition_date: Annotated[Optional[str], Form()] = None,
    billing_donor: Annotated[Optional[str], Form()] = None,
    payment_purpose: Annotated[Optional[str], Form()] = None,
    items_requested: Annotated[Optional[str], Form()] = None,
    requested_by: Annotated[Optional[str], Form()] = None,
    approved_by: Annotated[Optional[str], Form()] = None,
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
    # Apply requisition context straight from form fields — replaces the
    # old "hope the LLM extracts this from an uploaded PDF" path with direct
    # structured capture. Blank/whitespace-only values are skipped.
    for _field, _value in (
        ("requisition_date", requisition_date),
        ("billing_donor", billing_donor),
        ("payment_purpose", payment_purpose),
        ("items_requested", items_requested),
        ("requested_by", requested_by),
        ("approved_by", approved_by),
    ):
        _v = (_value or "").strip()
        if _v:
            setattr(result, _field, _v)
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


def _resolve_live_deterministic_values(rulebook: PolicyRulebook, org: OrgProfile) -> PolicyRulebook:
    """Some deterministic rules compare against live org config rather than
    a fixed list baked into the rule — the approved vendor list changes
    constantly, and freezing it into the rulebook at seed time would go
    stale the moment a vendor is added or removed. This resolves any such
    rule's `values` from current org config, returning a rulebook COPY
    (the persisted rulebook file is never touched). That resolved copy is
    what's evaluated AND what gets frozen into the check's audit snapshot —
    so the record shows exactly which vendor list was live at check time.

    Currently the only live source is "org_approved_vendors"; more sources
    can be added the same way without touching any specific payment type.
    """
    resolved_rules: list[PolicyRule] = []
    changed = False
    for r in rulebook.rules:
        spec = r.deterministic_check
        if (
            r.evaluation_type == "deterministic"
            and spec is not None
            and spec.kind == "membership"
            and spec.values_source == "org_approved_vendors"
        ):
            new_spec = spec.model_copy(update={"values": list(org.approved_vendors)})
            r = r.model_copy(update={"deterministic_check": new_spec})
            changed = True
        resolved_rules.append(r)
    if not changed:
        return rulebook
    return rulebook.model_copy(update={"rules": resolved_rules})


def _gather_prior_open_submissions(
    rulebook: PolicyRulebook, form_data: dict[str, str]
) -> list[dict]:
    """For any 'no_outstanding_advance' deterministic rule on this rulebook,
    find prior unretired checks against the SAME rulebook whose form_data
    matches on that rule's field (e.g. the same requester's name). Generic:
    works for any org's rulebook and any field name that rule was configured
    with — nothing here is specific to Travel Advance or to TA Connect.

    Returns [] when the rulebook has no such rule (the common case for most
    rulebooks) or the submission didn't provide a value for that field —
    deterministic_checks.py treats an empty list as "nothing outstanding."
    """
    no_outstanding_rules = [
        r for r in rulebook.rules
        if r.active
        and r.evaluation_type == "deterministic"
        and r.deterministic_check is not None
        and r.deterministic_check.kind == "no_outstanding_advance"
    ]
    if not no_outstanding_rules:
        return []
    field = no_outstanding_rules[0].deterministic_check.field
    identity = (form_data.get(field) or "").strip().lower()
    if not identity:
        return []
    matches: list[dict] = []
    for c in _list_checks():
        if c.rulebook_id != rulebook.id or c.retired:
            continue
        # A blocked request never disbursed anything — nothing to retire, so
        # it must not count as "outstanding" and lock the requester out of
        # ever submitting again. Flagged still counts (it may get approved
        # on review); only "blocked" is excluded.
        if c.overall_verdict == "blocked":
            continue
        if (c.form_data.get(field) or "").strip().lower() == identity:
            matches.append({"label": c.payment_label, "payment_id": c.payment_id})
    return matches


def _resolve_reference_lookup(
    rulebook: PolicyRulebook, form_data: dict[str, str]
) -> Optional[dict]:
    """For any 'reference_lookup' deterministic rule on this rulebook,
    resolve the referenced check by ID and report whether it's real,
    unretired, and belongs to the same requester. Generic: the reference
    field, and which form field identifies the requester for the match
    (deterministic_check.compare_field, default 'requester_name'), both
    come from the rule's own configuration — nothing here is specific to
    Travel Retirement or any one org.

    Returns None when the rulebook has no such rule (deterministic_checks.py
    then skips the check entirely, same as _gather_prior_open_submissions).
    """
    ref_rules = [
        r for r in rulebook.rules
        if r.active
        and r.evaluation_type == "deterministic"
        and r.deterministic_check is not None
        and r.deterministic_check.kind == "reference_lookup"
    ]
    if not ref_rules:
        return None
    spec = ref_rules[0].deterministic_check
    ref_id = (form_data.get(spec.field) or "").strip()
    if not ref_id:
        return {"found": False}
    referenced = _try_load_check(ref_id)
    if referenced is None:
        return {"found": False}
    identity_field = spec.compare_field or "requester_name"
    mine = (form_data.get(identity_field) or "").strip().lower()
    theirs = (referenced.form_data.get(identity_field) or "").strip().lower()
    # Fail-open when either side lacks the identity field at all (it's an
    # extra integrity check, not the only gate — found/retired above already
    # block a bogus or already-closed reference). Both sides have this field
    # in the default Travel Advance/Retirement forms, so in practice it's
    # always populated.
    requester_match = (not mine) or (not theirs) or (mine == theirs)
    return {
        "found": True,
        "retired": referenced.retired,
        "requester_match": requester_match,
        "label": referenced.payment_label,
        "payment_id": referenced.payment_id,
    }


@router.post("/check/form", response_model=ComplianceCheckResult)
async def check_form_endpoint(
    payment_type_name: Annotated[
        str,
        Form(description="Name of the payment type being submitted, as configured in this org's payment_types"),
    ],
    payment_label: Annotated[str, Form()] = "Payment Request",
    form_data_json: Annotated[
        str,
        Form(description="JSON object of the submitted form field values, keyed by FormField.name"),
    ] = "{}",
    rulebook_id: Annotated[
        Optional[str],
        Form(description="Explicit rulebook override — skips default_rulebook_id / auto-routing"),
    ] = None,
    payment_documents: Annotated[
        list[UploadFile],
        File(description="Supporting documents, for hybrid payment types (optional)"),
    ] = [],
) -> ComplianceCheckResult:
    """Check a form or hybrid intake submission.

    Companion to /check/single, which is document-only. This is the entry
    point for any PaymentType with intake_mode "form" or "hybrid" (see
    models.PaymentType) — Travel Advance today, whatever an org configures
    tomorrow. Nothing here is hardcoded to one org or one payment type:
    payment_type_name is looked up in the CALLING org's own payment_types,
    and form_data_json is whatever fields that org's form asked for.

    Rulebook resolution, in order: an explicit rulebook_id override, then
    the payment type's own default_rulebook_id, then (only if documents were
    attached) the same auto-routing /compliance/route uses. A pure-form
    submission with no default_rulebook_id configured and no documents to
    route from is a 422 — there's nothing to check it against.
    """
    org = _load_org_profile()
    payment_type = next(
        (t for t in org.payment_types if t.name == payment_type_name), None
    )
    if payment_type is None:
        raise HTTPException(
            status_code=404,
            detail=f"Payment type '{payment_type_name}' not found in this org's payment_types.",
        )

    try:
        parsed = json.loads(form_data_json) if form_data_json else {}
        if not isinstance(parsed, dict):
            raise ValueError("form_data_json must be a JSON object")
        form_data: dict[str, str] = {str(k): str(v) for k, v in parsed.items()}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid form_data_json: {exc}") from exc

    docs = _read_files(payment_documents) if payment_documents else []

    rulebook: Optional[PolicyRulebook] = None
    if rulebook_id:
        rulebook = _load_rulebook(rulebook_id)
    elif payment_type.default_rulebook_id:
        rulebook = _load_rulebook(payment_type.default_rulebook_id)
    elif docs:
        import compliance_router  # local import — keeps module load light

        text = "\n\n".join(fn_text for _, fn_text in docs)
        suggestions = compliance_router.rank_rulebooks(text, _list_rulebooks())
        strong = [s for s in suggestions if s.confidence in ("high", "medium")]
        if strong:
            rulebook = _load_rulebook(strong[0].rulebook_id)

    if rulebook is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No rulebook configured for '{payment_type_name}'. Set "
                "default_rulebook_id on this payment type in the org profile, "
                "pass rulebook_id explicitly, or attach documents so DOCex "
                "can auto-route."
            ),
        )

    # Resolve any "live list" deterministic values (e.g. the approved
    # vendor list) from current org config before evaluating or gathering
    # anything else — everything downstream should see the resolved copy.
    rulebook = _resolve_live_deterministic_values(rulebook, org)

    prior_open = _gather_prior_open_submissions(rulebook, form_data)
    referenced = _resolve_reference_lookup(rulebook, form_data)
    result = check_payment_safe(
        docs, rulebook, payment_label,
        form_data=form_data, prior_open_submissions=prior_open,
        referenced_submission=referenced,
    )
    result.form_data = form_data
    try:
        _save_check(result, rulebook)
    except Exception as exc:
        print(f"Warning: failed to persist check {result.payment_id}: {exc}")
    # Auto-close the loop: an APPROVED submission that cleanly references
    # another (e.g. a Travel Retirement closing out its Travel Advance)
    # retires that original check automatically — no separate officer
    # action needed for the common, clean case. A flagged/blocked
    # retirement leaves the original advance open on purpose: something
    # needs review before this is considered closed.
    if result.overall_verdict == "approved" and referenced and referenced.get("found") and not referenced.get("retired"):
        try:
            original = _load_check(referenced["payment_id"])
            original.retired = True
            original.retired_at = _now_iso()
            _append_decision_event(
                original,
                DecisionEvent(
                    type="note_added",
                    timestamp=original.retired_at,
                    note=f"Auto-retired — closed out by '{result.payment_label}' ({result.payment_id}).",
                ),
            )
        except Exception as exc:
            print(f"Warning: could not auto-retire referenced check {referenced.get('payment_id')}: {exc}")
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


class AuditLogRow(BaseModel):
    """One line of the org-wide audit log — a single action on a voucher."""
    timestamp: Optional[str] = None
    check_id: str
    payment_label: str
    rulebook_name: str
    event: str                       # raw event type
    actor: Optional[str] = None      # who
    detail: Optional[str] = None     # why / what (note)
    rule: Optional[str] = None       # related rule, if any
    signed_name: Optional[str] = None
    notified_email: Optional[str] = None
    source: Optional[str] = None     # in-app / email-verified / system
    ip: Optional[str] = None         # where


@router.get("/audit-log", response_model=list[AuditLogRow])
async def audit_log_endpoint() -> list[AuditLogRow]:
    """The org-wide audit log: every action across every voucher, newest
    first. One clean, chronological register an internal auditor can read or
    export — who did what, when, from where, on which voucher.
    """
    rows: list[AuditLogRow] = []
    for c in _list_checks():
        for e in c.decision_log or []:
            rows.append(
                AuditLogRow(
                    timestamp=e.timestamp,
                    check_id=c.payment_id,
                    payment_label=c.payment_label,
                    rulebook_name=c.rulebook_name,
                    event=e.type,
                    actor=e.actor,
                    detail=e.note,
                    rule=e.rule_description,
                    signed_name=e.signed_name,
                    notified_email=e.notified_email,
                    source=e.source,
                    ip=e.ip,
                )
            )
    rows.sort(key=lambda r: r.timestamp or "", reverse=True)
    return rows


@router.get("/checks/{check_id}", response_model=ComplianceCheckResult)
async def get_check_endpoint(check_id: str) -> ComplianceCheckResult:
    """Fetch a single check by ID — the stable URL for auditors."""
    return _load_check(check_id)


class ApproveRequest(BaseModel):
    """Approve a check. Optionally with a signature for audit defensibility.

    Both fields are optional — pre-pilot demos can approve without
    signing, but for any real payment going out, the signature + typed
    name make the audit trail defensible under the Nigerian Electronic
    Transactions Bill.
    """
    signature_data_url: Optional[str] = None  # data:image/png;base64,... from canvas
    signed_name: Optional[str] = None         # typed name to accompany the signature


@router.post(
    "/checks/{check_id}/approve",
    response_model=ComplianceCheckResult,
)
async def approve_check_endpoint(
    check_id: str,
    body: Optional[ApproveRequest] = None,
) -> ComplianceCheckResult:
    """Mark a check as ED-approved. Sets the approved flag + timestamp,
    appends an 'approved' event to the decision log, optionally captures
    a signature + signed name on the event for audit-defensibility."""
    check = _load_check(check_id)
    now = _now_iso()
    check.approved = True
    check.approved_at = now
    sig_url = body.signature_data_url if body else None
    sig_name = body.signed_name.strip() if (body and body.signed_name) else None
    _append_decision_event(
        check,
        DecisionEvent(
            type="approved",
            timestamp=now,
            note=(
                f"Check approved — overall verdict was '{check.overall_verdict}'."
                + (f" Signed by {sig_name}." if sig_name else "")
            ),
            signature_data_url=sig_url,
            signed_name=sig_name,
        ),
    )
    return check


@router.post(
    "/checks/{check_id}/unapprove",
    response_model=ComplianceCheckResult,
)
async def unapprove_check_endpoint(check_id: str) -> ComplianceCheckResult:
    """Reverse approval — sets approved=False, clears approved_at, and
    appends an 'unapproved' event to the decision log. Rare but
    audit-relevant when an approval is later retracted."""
    check = _load_check(check_id)
    check.approved = False
    check.approved_at = None
    _append_decision_event(
        check,
        DecisionEvent(
            type="unapproved",
            timestamp=_now_iso(),
            note="Approval revoked.",
        ),
    )
    return check


# ─── Risk register endpoints ────────────────────────────────────────────────

class RiskIn(BaseModel):
    """Officer logs / updates a risk on a check."""
    description: str
    severity: Optional[str] = None       # high | medium | low
    action_taken: Optional[str] = None
    escalated: Optional[bool] = None
    escalated_to: Optional[str] = None
    action_plan: Optional[str] = None
    status: Optional[str] = None         # open | in_progress | resolved
    related_rule_id: Optional[str] = None


def _norm_severity(v: Optional[str]) -> str:
    return v if v in ("high", "medium", "low") else "medium"


def _norm_status(v: Optional[str]) -> str:
    return v if v in ("open", "in_progress", "resolved") else "open"


@router.post("/checks/{check_id}/risks", response_model=ComplianceCheckResult)
async def add_risk_endpoint(check_id: str, body: RiskIn) -> ComplianceCheckResult:
    """Log a risk on a check: what it is, severity, action taken, whether it
    was escalated, and the plan. Mirrored to the decision log so it lands in
    the audit trail and the officer's report."""
    desc = (body.description or "").strip()
    if not desc:
        raise HTTPException(status_code=422, detail="A risk description is required.")
    check = _load_check(check_id)
    now = _now_iso()
    severity = _norm_severity(body.severity)
    status = _norm_status(body.status)
    escalated = bool(body.escalated)
    risk = RiskEntry(
        id=f"risk-{uuid.uuid4().hex[:8]}",
        created_at=now,
        description=desc,
        severity=severity,  # type: ignore[arg-type]
        action_taken=(body.action_taken or None),
        escalated=escalated,
        escalated_to=(body.escalated_to or None),
        action_plan=(body.action_plan or None),
        status=status,  # type: ignore[arg-type]
        resolved_at=now if status == "resolved" else None,
        related_rule_id=(body.related_rule_id or None),
        updated_at=now,
    )
    check.risks.append(risk)
    esc = f" Escalated to {risk.escalated_to}." if escalated and risk.escalated_to else (" Escalated." if escalated else "")
    _append_decision_event(
        check,
        DecisionEvent(
            type="risk_identified",
            timestamp=now,
            note=f"Risk ({severity}): {desc}." + esc,
            rule_id=risk.related_rule_id,
        ),
    )
    return check


@router.put(
    "/checks/{check_id}/risks/{risk_id}", response_model=ComplianceCheckResult
)
async def update_risk_endpoint(
    check_id: str, risk_id: str, body: RiskIn
) -> ComplianceCheckResult:
    """Update a risk — revise the action/plan, escalate it, or move it toward
    resolved. Logged to the audit trail (resolution is its own event)."""
    check = _load_check(check_id)
    risk = next((r for r in check.risks if r.id == risk_id), None)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk not found on this check.")
    now = _now_iso()
    if body.description and body.description.strip():
        risk.description = body.description.strip()
    if body.severity is not None:
        risk.severity = _norm_severity(body.severity)  # type: ignore[assignment]
    if body.action_taken is not None:
        risk.action_taken = body.action_taken or None
    if body.escalated is not None:
        risk.escalated = bool(body.escalated)
    if body.escalated_to is not None:
        risk.escalated_to = body.escalated_to or None
    if body.action_plan is not None:
        risk.action_plan = body.action_plan or None
    became_resolved = False
    if body.status is not None:
        new_status = _norm_status(body.status)
        if new_status == "resolved" and risk.status != "resolved":
            became_resolved = True
            risk.resolved_at = now
        if new_status != "resolved":
            risk.resolved_at = None
        risk.status = new_status  # type: ignore[assignment]
    risk.updated_at = now
    _append_decision_event(
        check,
        DecisionEvent(
            type="risk_resolved" if became_resolved else "risk_updated",
            timestamp=now,
            note=(
                f"Risk resolved: {risk.description}."
                if became_resolved
                else f"Risk updated ({risk.severity}, {risk.status}): {risk.description}."
            ),
            rule_id=risk.related_rule_id,
        ),
    )
    return check


@router.post("/checks/{check_id}/mark-paid", response_model=ComplianceCheckResult)
async def mark_paid_endpoint(check_id: str) -> ComplianceCheckResult:
    """Toggle whether the payment has been executed ('Paid' on the board).
    Records the change on the audit trail."""
    check = _load_check(check_id)
    now = _now_iso()
    check.paid = not check.paid
    check.paid_at = now if check.paid else None
    _append_decision_event(
        check,
        DecisionEvent(
            type="note_added",
            timestamp=now,
            note="Payment recorded — marked Paid." if check.paid else "Marked unpaid.",
        ),
    )
    return check


@router.post("/checks/{check_id}/retire", response_model=ComplianceCheckResult)
async def toggle_retired_endpoint(check_id: str) -> ComplianceCheckResult:
    """Toggle whether an advance/outstanding payment has been retired —
    closed out by a retirement submission, a reconciliation, or manually.
    Generic: any payment type can use this, not just Travel Advance. This
    is what a 'no_outstanding_advance' deterministic rule checks — an
    unretired check for the same requester blocks a new advance."""
    check = _load_check(check_id)
    now = _now_iso()
    check.retired = not check.retired
    check.retired_at = now if check.retired else None
    _append_decision_event(
        check,
        DecisionEvent(
            type="note_added",
            timestamp=now,
            note="Marked retired/closed." if check.retired else "Marked not retired.",
        ),
    )
    return check


# ─── Decision log endpoints ─────────────────────────────────────────────────


class AddNoteRequest(BaseModel):
    """Officer adds a free-text note to a check (or to a specific rule)."""
    note: str                                 # required — the officer's reason / context
    rule_id: Optional[str] = None             # optional — when note is rule-specific


@router.post("/checks/{check_id}/notes", response_model=ComplianceCheckResult)
async def add_check_note(
    check_id: str, body: AddNoteRequest
) -> ComplianceCheckResult:
    """Append a free-text note to a check's decision log.

    Used when the officer wants to record context — "confirmed via email
    with vendor", "rate card is in renewal", "ED briefed on this on 17/05".
    Optionally tied to a specific rule_id when the note explains a single
    rule's verdict.
    """
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=422, detail="Note can't be empty.")
    check = _load_check(check_id)
    rule_desc = None
    if body.rule_id:
        match = next(
            (r for r in check.results if r.rule_id == body.rule_id),
            None,
        )
        if match:
            rule_desc = match.rule_description
    _append_decision_event(
        check,
        DecisionEvent(
            type="note_added",
            timestamp=_now_iso(),
            note=note,
            rule_id=body.rule_id,
            rule_description=rule_desc,
        ),
    )
    return check


class RuleDecisionRequest(BaseModel):
    """Officer takes an explicit action on a specific rule's verdict.

    Action is one of:
      - dismiss: "this flag is fine — here's why" (most common — vendor
        is pre-approved, document is in renewal, etc.)
      - escalate: "this needs a higher reviewer" (typically ED)
      - clarification_requested: "I've asked the submitter for the
        missing item" (records the action for the audit trail)

    A reason is REQUIRED — the whole point of this endpoint is to make
    the officer commit their justification to the audit log.
    """
    action: Literal["dismiss", "escalate", "clarification_requested"]
    reason: str


@router.post(
    "/checks/{check_id}/rules/{rule_id}/decision",
    response_model=ComplianceCheckResult,
)
async def record_rule_decision(
    check_id: str,
    rule_id: str,
    body: RuleDecisionRequest,
) -> ComplianceCheckResult:
    """Record an officer's explicit decision on one rule of a check."""
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(
            status_code=422,
            detail=(
                "A reason is required — this is the line an auditor will "
                "read when they ask why this rule was dismissed."
            ),
        )
    check = _load_check(check_id)
    match = next((r for r in check.results if r.rule_id == rule_id), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"Rule '{rule_id}' not found in this check.",
        )

    event_type_map: dict[str, DecisionEventType] = {
        "dismiss": "rule_dismissed",
        "escalate": "rule_escalated",
        "clarification_requested": "clarification_requested",
    }
    _append_decision_event(
        check,
        DecisionEvent(
            type=event_type_map[body.action],
            timestamp=_now_iso(),
            note=reason,
            rule_id=rule_id,
            rule_description=match.rule_description,
        ),
    )
    return check


class EscalateRequest(BaseModel):
    """Escalate the whole check to a named reviewer. Replaces the
    email-back-and-forth pattern with a single in-product handoff that
    sets pending_with + appends an event to the audit trail. Optionally
    carries a signature (the officer's drawn signature + typed name)
    so the handoff is audit-defensible."""
    pending_with: str                         # who's now responsible — name or email
    reason: Optional[str] = None              # optional note for the recipient
    signature_data_url: Optional[str] = None
    signed_name: Optional[str] = None


@router.post(
    "/checks/{check_id}/escalate",
    response_model=ComplianceCheckResult,
)
async def escalate_check(
    check_id: str, body: EscalateRequest
) -> ComplianceCheckResult:
    """Hand the check off to a named reviewer. They'll see it in their
    inbox at /compliance/pending. The decision log captures who escalated
    it, to whom, and why — so the audit trail reconstructs the route."""
    target = body.pending_with.strip()
    if not target:
        raise HTTPException(
            status_code=422,
            detail="pending_with is required — specify who you're escalating to.",
        )
    check = _load_check(check_id)
    check.pending_with = target
    # Clear any outstanding clarification — escalating shifts the
    # responsibility to a new person, not a question waiting for an answer.
    check.pending_question = None
    sig_name = body.signed_name.strip() if body.signed_name else None

    # Notify the reviewer by email if we have an address. Best-effort: a
    # mail failure must never block the escalation itself.
    notified: Optional[str] = None
    try:
        if send_escalation_email(check, target, body.reason):
            notified = target
    except Exception as exc:  # noqa: BLE001 — log-and-continue by design
        print(f"[DOCex] escalation email to {target} failed: {exc}")

    _append_decision_event(
        check,
        DecisionEvent(
            type="escalated",
            timestamp=_now_iso(),
            note=(body.reason or f"Escalated to {target}.").strip(),
            signature_data_url=body.signature_data_url,
            signed_name=sig_name,
            notified_email=notified,
        ),
    )
    return check


class ClarificationRequest(BaseModel):
    """Request structured clarification from the submitter / finance team.

    Unlike a free-text note, a clarification has a clear shape — there's
    a SPECIFIC question, optionally tied to a SPECIFIC rule, addressed to
    a SPECIFIC person who is now pending_with. The response (when it
    comes) gets logged with a 'clarification_received' event that closes
    the loop. This is the in-app replacement for the email chain.
    """
    question: str
    pending_with: str                         # who the question is going to
    rule_id: Optional[str] = None             # optional — rule the question relates to
    signature_data_url: Optional[str] = None  # officer raising the question signs
    signed_name: Optional[str] = None


@router.post(
    "/checks/{check_id}/clarification",
    response_model=ComplianceCheckResult,
)
async def request_clarification(
    check_id: str, body: ClarificationRequest
) -> ComplianceCheckResult:
    """Send a structured clarification request to someone. Sets pending_with,
    stores the question, appends an event. The recipient sees the question
    in their inbox at /compliance/pending with a 'respond' affordance.

    This is the workflow that replaces the constant email back-and-forth
    that NGO finance/compliance teams currently fight through: the
    question, the recipient, and the answer all live in one auditable
    record on the check itself.
    """
    q = body.question.strip()
    target = body.pending_with.strip()
    if not q:
        raise HTTPException(status_code=422, detail="A clarification question is required.")
    if not target:
        raise HTTPException(
            status_code=422,
            detail="pending_with is required — who should answer this?",
        )
    check = _load_check(check_id)
    check.pending_with = target
    check.pending_question = q
    rule_desc: Optional[str] = None
    if body.rule_id:
        match = next(
            (r for r in check.results if r.rule_id == body.rule_id), None
        )
        if match:
            rule_desc = match.rule_description
    sig_name = body.signed_name.strip() if body.signed_name else None

    # Email the question to the responsible party if we have an address.
    # Best-effort: a mail failure must never block the request.
    notified: Optional[str] = None
    try:
        if send_clarification_email(check, target, q):
            notified = target
    except Exception as exc:  # noqa: BLE001 — log-and-continue by design
        print(f"[DOCex] clarification email to {target} failed: {exc}")

    _append_decision_event(
        check,
        DecisionEvent(
            type="clarification_requested",
            timestamp=_now_iso(),
            note=f"To {target}: {q}",
            rule_id=body.rule_id,
            rule_description=rule_desc,
            signature_data_url=body.signature_data_url,
            signed_name=sig_name,
            notified_email=notified,
        ),
    )
    return check


class ClarificationResponseRequest(BaseModel):
    """The recipient responds to a clarification — could be a text answer
    and/or "I've uploaded the missing docs." Clears the pending_question
    and logs the response in the decision log."""
    response: str
    signature_data_url: Optional[str] = None
    signed_name: Optional[str] = None


@router.post(
    "/checks/{check_id}/clarification/respond",
    response_model=ComplianceCheckResult,
)
async def respond_to_clarification(
    check_id: str, body: ClarificationResponseRequest
) -> ComplianceCheckResult:
    """Respond to an outstanding clarification. Logs the response, clears
    pending_question, and resets pending_with to the original officer
    (an explicit "I've answered, back to you" handoff)."""
    response_text = body.response.strip()
    if not response_text:
        raise HTTPException(
            status_code=422,
            detail="A response is required.",
        )
    check = _load_check(check_id)
    if not check.pending_question:
        raise HTTPException(
            status_code=400,
            detail="No outstanding clarification to respond to on this check.",
        )
    sig_name = body.signed_name.strip() if body.signed_name else None
    _append_decision_event(
        check,
        DecisionEvent(
            type="clarification_received",
            timestamp=_now_iso(),
            note=response_text,
            signature_data_url=body.signature_data_url,
            signed_name=sig_name,
        ),
    )
    # Hand back to whoever raised the clarification — we don't know exactly
    # who in pre-auth mode, but clearing pending_with surfaces it in the
    # inbox under "needs decision" rather than "awaiting reply".
    check.pending_question = None
    check.pending_with = None
    _check_path(check_id).write_text(check.model_dump_json(indent=2))
    return check


# ─── Pending inbox ──────────────────────────────────────────────────────────


@router.get("/pending", response_model=CheckListResponse)
def list_pending_checks() -> CheckListResponse:
    """Every compliance check that's not yet approved. Sorted by created_at
    descending (newest first). This is the 'queue' an officer opens to
    start their morning — what needs my attention today?

    Doesn't filter by pending_with yet (no auth → we'd need to know who
    the current user is). Post-Supabase, this will filter to checks
    where pending_with matches the logged-in user."""
    checks = _list_checks()
    pending = [c for c in checks if not c.approved]
    return CheckListResponse(checks=[_to_check_summary(c) for c in pending])


# ─── End decision log endpoints ─────────────────────────────────────────────


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


# ─── Verified approval sign-off (email magic-link) ──────────────────────────
#
# A name field is not verification. Instead, DOCex emails each stage's
# approver a unique, expiring, HMAC-signed link. Opening it from their inbox
# proves control of that mailbox; the sign-off records their email, the
# timestamp, and their IP on the audit trail. Microsoft 365 SSO is the
# eventual upgrade; this is the no-login, audit-grade version.

_SIGNOFF_MARKER = "Stage sign-off —"


def _signed_stages(check: ComplianceCheckResult) -> set[str]:
    out: set[str] = set()
    for e in check.decision_log or []:
        note = e.note or ""
        i = note.find(_SIGNOFF_MARKER)
        if i != -1:
            stage = note[i + len(_SIGNOFF_MARKER):].split(":")[0].strip()
            if stage:
                out.add(stage)
    return out


def _workflow_for(check: ComplianceCheckResult) -> list[str]:
    try:
        rb = _load_rulebook(check.rulebook_id)
        return rb.approval_workflow or []
    except Exception:  # noqa: BLE001
        return []


def _apply_signoff(
    check: ComplianceCheckResult,
    *,
    stage: str,
    actor: str,
    action: Literal["approve", "return"],
    note: Optional[str],
    source: str,
    ip: str,
) -> dict:
    """Record a verified sign-off (or return-for-changes) and advance the
    workflow. THE single place sign-offs are applied — shared by the email
    magic-link and any external transport (Power Automate / webhook), so every
    channel converges on one audit representation. Persists the check.
    """
    now = _now_iso()
    workflow = _workflow_for(check)
    signed = _signed_stages(check)

    if action == "approve":
        if stage in signed:
            raise HTTPException(
                status_code=409, detail="This stage has already been signed off."
            )
        _append_decision_event(
            check,
            DecisionEvent(
                type="note_added",
                timestamp=now,
                actor=actor,
                note=f"{_SIGNOFF_MARKER} {stage}: {actor}",
                source=source,
                ip=ip,
            ),
        )
        approved = False
        new_signed = signed | {stage}
        if workflow and all(s in new_signed for s in workflow):
            check.approved = True
            check.approved_at = now
            check.pending_with = None
            check.pending_question = None
            _append_decision_event(
                check,
                DecisionEvent(
                    type="approved",
                    timestamp=now,
                    actor=actor,
                    note=f"Voucher approved — final sign-off by {actor} ({stage}).",
                    source=source,
                    ip=ip,
                ),
            )
            approved = True
        _check_path(check.payment_id).write_text(check.model_dump_json(indent=2))
        return {"ok": True, "approved": approved, "stage": stage}

    # action == "return"
    reason = (note or "Returned for changes.").strip()
    _append_decision_event(
        check,
        DecisionEvent(
            type="clarification_requested",
            timestamp=now,
            actor=actor,
            note=f"Returned for changes ({stage}): {reason}",
            source=source,
            ip=ip,
        ),
    )
    check.pending_with = None  # back to the originating officer to action
    check.pending_question = reason
    _check_path(check.payment_id).write_text(check.model_dump_json(indent=2))
    return {"ok": True, "returned": True}


class RequestSignoffRequest(BaseModel):
    stage: str
    approver_email: str


@router.post("/checks/{check_id}/request-signoff")
async def request_signoff(check_id: str, body: RequestSignoffRequest) -> dict:
    """Email a stage's approver a unique, verified sign-off link.

    Returns whether the email was sent and the link itself (so it can be
    shown/copied when SMTP isn't configured, e.g. in a demo).
    """
    check = _load_check(check_id)
    stage = body.stage.strip()
    email = body.approver_email.strip()
    if not stage:
        raise HTTPException(status_code=422, detail="A stage is required.")
    if not looks_like_email(email):
        raise HTTPException(status_code=422, detail="A valid approver email is required.")

    token = make_token(check_id, stage, email)
    app_url = os.environ.get("APP_URL", "").rstrip("/")
    link = f"{app_url}/approve/{token}" if app_url else f"/approve/{token}"

    # Org-agnostic transport: if an external workflow engine is wired up
    # (APPROVAL_WEBHOOK_URL set), route this sign-off request to it too. The
    # engine (Power Automate / Zapier / Teams flow) surfaces the approval to the
    # approver and POSTs the outcome back to /approve/callback. Inert + harmless
    # if unconfigured — the magic-link email below remains the fallback.
    webhook_sent = emit_approval_request(
        {
            "check_id": check_id,
            "stage": stage,
            "approver_email": email,
            "payment_label": check.payment_label,
            "rulebook_name": check.rulebook_name,
            "overall_verdict": check.overall_verdict,
            "summary": check.overall_summary,
            "deep_link": link,
        }
    )

    emailed = False
    try:
        subject = f"[DOCex] Sign-off needed — {check.payment_label}"
        text = "\n".join([
            f"You're asked to sign off as {stage} on payment voucher:",
            f"  {check.payment_label}",
            "",
            "Open your unique, secure link to review and approve (or return it "
            "for changes). The link is tied to your email address:",
            link,
            "",
            "---",
            "Automated from DOCex. Only you can act on this link.",
        ])
        emailed = _send_raw_email(email, subject, text)
    except Exception as exc:  # noqa: BLE001
        print(f"[DOCex] sign-off email to {email} failed: {exc}")

    _append_decision_event(
        check,
        DecisionEvent(
            type="note_added",
            timestamp=_now_iso(),
            note=f"Sign-off requested from {email} for stage '{stage}'.",
            notified_email=email if emailed else None,
        ),
    )
    check.pending_with = email
    _check_path(check_id).write_text(check.model_dump_json(indent=2))
    return {"ok": True, "emailed": emailed, "webhook": webhook_sent, "link": link}


@router.get("/approve/verify/{token}")
async def approve_verify(token: str) -> dict:
    """Public: validate an approval link and return a minimal voucher summary."""
    try:
        payload = verify_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    check = _load_check(payload["cid"])
    workflow = _workflow_for(check)
    signed = _signed_stages(check)
    stage = payload["stage"]
    return {
        "check_id": check.payment_id,
        "payment_label": check.payment_label,
        "rulebook_name": check.rulebook_name,
        "overall_verdict": check.overall_verdict,
        "overall_summary": check.overall_summary,
        "stage": stage,
        "approver_email": payload["email"],
        "workflow": workflow,
        "signed_stages": sorted(signed),
        "already_signed": stage in signed,
        "is_final_stage": bool(workflow) and stage == workflow[-1],
    }


class ApproveActRequest(BaseModel):
    action: Literal["approve", "return"]
    note: Optional[str] = None


@router.post("/approve/{token}")
async def approve_act(token: str, body: ApproveActRequest, request: Request) -> dict:
    """Public: record a verified sign-off (or a return-for-changes) from the
    approver's unique link. Captures email + timestamp + IP on the audit trail."""
    try:
        payload = verify_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    check = _load_check(payload["cid"])
    stage = payload["stage"]
    email = payload["email"]
    ip = request.client.host if request.client else "unknown"
    return _apply_signoff(
        check,
        stage=stage,
        actor=email,
        action=body.action,
        note=body.note,
        source="email-verified",
        ip=ip,
    )


class ApprovalCallbackRequest(BaseModel):
    """Normalized result posted back by an external workflow engine (Power
    Automate, Zapier, n8n, a Teams/Slack flow…) after an approver acts."""
    check_id: str
    stage: str
    outcome: Literal["approve", "approved", "reject", "rejected", "return", "returned"]
    responder: Optional[str] = None
    comments: Optional[str] = None
    source: Optional[str] = None  # e.g. "power-automate", "slack"
    secret: Optional[str] = None  # fallback if header can't be set


@router.post("/approval-callback")
async def approve_callback(body: ApprovalCallbackRequest, request: Request) -> dict:
    """Public, secret-gated: accept a sign-off decision from an external
    workflow engine and apply it through the same path as the magic-link.

    Auth: shared secret via the ``X-DOCex-Secret`` header (preferred) or the
    ``secret`` body field. Fail-closed — rejected unless APPROVAL_CALLBACK_SECRET
    is configured and matches.
    """
    provided = request.headers.get("X-DOCex-Secret") or body.secret or ""
    if not verify_callback_secret(provided):
        raise HTTPException(status_code=401, detail="Invalid or missing approval callback secret.")

    check = _load_check(body.check_id)
    workflow = _workflow_for(check)
    if workflow and body.stage not in workflow:
        raise HTTPException(
            status_code=422,
            detail=f"Stage '{body.stage}' is not in this voucher's approval workflow.",
        )
    ip = request.client.host if request.client else "webhook"
    actor = (body.responder or "external approver").strip()
    action: Literal["approve", "return"] = (
        "approve" if body.outcome in ("approve", "approved") else "return"
    )
    return _apply_signoff(
        check,
        stage=body.stage,
        actor=actor,
        action=action,
        note=body.comments,
        source=(body.source or "power-automate").strip(),
        ip=ip,
    )
