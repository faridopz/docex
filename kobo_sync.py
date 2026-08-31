"""
KoboCollect integration for DOCex field receipts.

KoboCollect is an offline-first data collection platform. Fieldworkers in
low/no-signal areas use the KoboCollect mobile app to capture receipts
(photos, amounts, vendor names, dates, project codes) offline. When signal
is available, the app syncs submissions to the KoboCollect server, which
notifies DOCex via webhook.

This module:
  1. Receives KoboCollect submissions (JSON)
  2. Extracts metadata + image/document references
  3. Logs receipt immediately (no lag, simple + scalable)
  4. Validates against policy
  5. Allows finance/fieldworker to complete incomplete data in UI
  6. Integrates with grant code tracking for EVA

Key insight: receipts arrive incomplete (missing vendor, date, etc.) by design.
The system accepts them as DRAFT/FLAGGED, flags issues, and allows correction
in the UI. This is expected behavior, not an error.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
from typing import Optional

from pydantic import BaseModel, Field

import field_receipts
import store

# ─── kobo sync models ───────────────────────────────────────────────────────


class KoboAttachment(BaseModel):
    """Reference to a file attached in KoboCollect submission."""
    filename: str
    download_url: Optional[str] = None
    mimetype: str = "image/jpeg"


class KoboSubmission(BaseModel):
    """
    One submission from KoboCollect.

    KoboCollect JSON structure:
    {
      "id": 12345,
      "meta": {
        "instanceID": "uuid:...",
        "timeend": "2026-08-29T14:30:00Z"
      },
      "receipt_amount": 5000.0,
      "receipt_vendor": "Store Name",
      "receipt_date": "2026-08-15",
      "project_code": "P-101",
      "grant_code": "GR-001",           # EVA: repayment tracking
      "expense_category": "training",
      "receipt_image": "uuid:...",      # attachment ID
      "notes": "Optional notes",
      "org_id": "eva",
      "submitted_by": "fieldworker@eva.org"
    }
    """
    id: int                                     # KoboCollect submission ID
    org_id: str = ""                            # which org is this for
    submitted_by: str = ""                      # fieldworker email or user ID
    timeend: Optional[str] = None               # ISO timestamp from KoboCollect

    # Receipt details
    receipt_amount: Optional[float] = None      # amount fieldworker paid
    receipt_vendor: str = ""                    # vendor name from receipt
    receipt_date: Optional[str] = None          # date on receipt (ISO or any format)
    project_code: str = ""                      # project/activity code
    grant_code: Optional[str] = None            # EVA: grant being spent from
    expense_category: str = "supplies"          # training, supplies, travel, etc.
    notes: str = ""                             # fieldworker's notes

    # Attachment metadata
    receipt_image: Optional[str] = None         # attachment name/UUID
    receipt_image_url: Optional[str] = None     # if direct download URL provided

    # Internal
    kobo_instance_id: Optional[str] = None      # for deduplication


class KoboSyncResult(BaseModel):
    """Response from syncing a KoboCollect submission."""
    success: bool
    receipt_id: str                             # DOCex receipt ID
    status: str                                 # VALIDATED, FLAGGED, DRAFT
    message: str                                # human-readable result
    flags: list[dict] = Field(default_factory=list)  # any issues found
    grant_code: Optional[str] = None            # echoed for tracking


# ─── sync from kobo ─────────────────────────────────────────────────────────


def sync_kobo_submission(
    org_id: str,
    submission: KoboSubmission,
    image_bytes: Optional[bytes] = None,
) -> KoboSyncResult:
    """
    Accept a KoboCollect submission and log it as a receipt.

    Flow:
      1. Parse submission metadata
      2. Create receipt with extracted data
      3. Validate against policy
      4. Return result with receipt ID + any flags
      5. Frontend/fieldworker can correct flags in UI

    Args:
      org_id: Organization ID (from session or header)
      submission: KoboCollect JSON payload
      image_bytes: Optional image data (if not fetching from URL)

    Returns:
      KoboSyncResult with receipt_id, status, and any flags
    """
    org = store.require_org(org_id)

    # Normalize submission org_id
    submission.org_id = org

    # Determine who submitted (fieldworker)
    fieldworker = submission.submitted_by or f"kobo-worker-{submission.id}"

    # If image_bytes not provided, we create a placeholder receipt
    # (frontend can upload the actual image later)
    if image_bytes is None:
        # Create minimal receipt: text-only placeholder
        image_bytes = _kobo_placeholder_receipt(submission)

    # Infer filename
    filename = submission.receipt_image or f"kobo-{submission.id}.jpg"

    # Upload receipt (this validates it immediately)
    try:
        receipt = field_receipts.upload_receipt(
            org_id=org,
            uploaded_by=fieldworker,
            file_content=image_bytes,
            filename=filename,
            amount_submitted=submission.receipt_amount or 0.0,
            project_code=submission.project_code,
            category=submission.expense_category,
            description=submission.notes,
        )
    except Exception as exc:
        return KoboSyncResult(
            success=False,
            receipt_id="",
            status="error",
            message=f"Failed to upload receipt: {exc}",
            grant_code=submission.grant_code,
        )

    # Store grant code in receipt metadata (if provided)
    if submission.grant_code:
        _store_grant_code(org, receipt.id, submission.grant_code)

    # Store kobo instance ID for deduplication (if provided)
    if submission.kobo_instance_id:
        _store_kobo_sync_metadata(org, receipt.id, submission.kobo_instance_id)

    return KoboSyncResult(
        success=True,
        receipt_id=receipt.id,
        status=receipt.status.value,
        message=f"Receipt logged: {receipt.status.value}. "
                f"{len(receipt.flags)} issue(s) flagged." if receipt.flags else
                "Receipt validated successfully.",
        flags=[
            {
                "type": f.type.value,
                "severity": f.severity,
                "message": f.message,
            }
            for f in receipt.flags
        ],
        grant_code=submission.grant_code,
    )


def parse_kobo_json(raw_json: str | dict) -> KoboSubmission:
    """
    Parse KoboCollect JSON into a KoboSubmission.

    Handles both raw JSON strings and already-parsed dicts.
    """
    if isinstance(raw_json, str):
        data = json.loads(raw_json)
    else:
        data = raw_json

    # Map KoboCollect field names to our model
    return KoboSubmission(
        id=data.get("id", 0),
        org_id=data.get("org_id", ""),
        submitted_by=data.get("submitted_by") or data.get("user", ""),
        timeend=data.get("meta", {}).get("timeend") or data.get("timeend"),
        receipt_amount=_to_float(data.get("receipt_amount")),
        receipt_vendor=data.get("receipt_vendor", ""),
        receipt_date=data.get("receipt_date"),
        project_code=data.get("project_code", ""),
        grant_code=data.get("grant_code"),
        expense_category=data.get("expense_category", "supplies"),
        notes=data.get("notes", ""),
        receipt_image=data.get("receipt_image"),
        receipt_image_url=data.get("receipt_image_url"),
        kobo_instance_id=data.get("meta", {}).get("instanceID"),
    )


# ─── helpers ────────────────────────────────────────────────────────────────


def _kobo_placeholder_receipt(submission: KoboSubmission) -> bytes:
    """
    Create a placeholder receipt if no image data provided.

    This allows fieldworkers to submit incomplete receipts from KoboCollect
    (e.g., no photo, just metadata). DOCex accepts them as DRAFT and allows
    fieldworker/finance to complete the data in the UI.

    Note: Only includes fields that are present. Missing fields are left empty
    so validation can flag them properly.

    Note: Avoids including timestamps or other fields that might trigger
    spurious extraction (e.g., a timestamp with ISO date pattern would be
    extracted as a receipt date, causing validation to not flag missing date).
    """
    lines = [
        f"kobo submission {submission.id}",
        f"fieldworker: {submission.submitted_by or 'unknown'}",
    ]

    # Only include fields that have values
    if submission.receipt_vendor:
        lines.append(f"VENDOR: {submission.receipt_vendor}")
    if submission.receipt_date:
        lines.append(f"DATE: {submission.receipt_date}")
    if submission.receipt_amount:
        lines.append(f"AMOUNT: {submission.receipt_amount}")
    if submission.project_code:
        lines.append(f"project: {submission.project_code}")
    if submission.expense_category:
        lines.append(f"category: {submission.expense_category}")
    if submission.grant_code:
        lines.append(f"grant code: {submission.grant_code}")
    if submission.notes:
        lines.append(f"notes: {submission.notes}")

    return "\n".join(lines).encode("utf-8")


def _to_float(value) -> Optional[float]:
    """Convert value to float, return None if not convertible."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ─── grant code tracking (for EVA) ──────────────────────────────────────────


_GRANT_CODES = "receipt_grant_codes"
_GRANT_CODE_INDEX = "grant_code_index"  # maps grant_code -> list of receipt_ids
_KOBO_SYNC_META = "kobo_sync_metadata"


def _store_grant_code(org_id: str, receipt_id: str, grant_code: str) -> None:
    """
    Store which grant code a receipt was charged to.

    Used by EVA to track: which receipts came from which grants/projects.
    Enables repayment reconciliation and donor reporting.
    """
    org = store.require_org(org_id)

    # Store mapping: receipt_id -> grant_code
    data = {"receipt_id": receipt_id, "grant_code": grant_code, "timestamp": _now_iso()}
    store.get_store().put(org, _GRANT_CODES, receipt_id, data)

    # Update index: grant_code -> [receipt_ids...]
    index_key = f"grant_{grant_code}"
    index_data = store.get_store().get(org, _GRANT_CODE_INDEX, index_key) or {"receipt_ids": []}
    if receipt_id not in index_data.get("receipt_ids", []):
        index_data["receipt_ids"].append(receipt_id)
    store.get_store().put(org, _GRANT_CODE_INDEX, index_key, index_data)


def get_grant_code(org_id: str, receipt_id: str) -> Optional[str]:
    """Retrieve the grant code associated with a receipt."""
    org = store.require_org(org_id)
    data = store.get_store().get(org, _GRANT_CODES, receipt_id)
    return data.get("grant_code") if data else None


def list_receipts_by_grant_code(org_id: str, grant_code: str) -> list[str]:
    """List all receipt IDs associated with a grant code."""
    org = store.require_org(org_id)
    index_key = f"grant_{grant_code}"
    index_data = store.get_store().get(org, _GRANT_CODE_INDEX, index_key)
    return index_data.get("receipt_ids", []) if index_data else []


def _store_kobo_sync_metadata(org_id: str, receipt_id: str, kobo_instance_id: str) -> None:
    """Store KoboCollect instance ID for deduplication."""
    # Sanitize kobo_instance_id for use as a record key (remove colons, replace dashes)
    safe_id = kobo_instance_id.replace(":", "_").replace("-", "_")
    data = {"receipt_id": receipt_id, "kobo_instance_id": kobo_instance_id, "timestamp": _now_iso()}
    store.get_store().put(org_id, _KOBO_SYNC_META, safe_id, data)


def get_receipt_by_kobo_instance_id(org_id: str, kobo_instance_id: str) -> Optional[str]:
    """Check if a KoboCollect submission was already synced (deduplication)."""
    org = store.require_org(org_id)
    # Sanitize kobo_instance_id for lookup
    safe_id = kobo_instance_id.replace(":", "_").replace("-", "_")
    data = store.get_store().get(org, _KOBO_SYNC_META, safe_id)
    return data.get("receipt_id") if data else None


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
