"""
FastAPI routes for field receipt upload, validation, and tracking.

Endpoints:
  POST /field-receipts/upload   — upload receipt + metadata, auto-validate
  POST /field-receipts/from-kobo — accept KoboCollect submission, log immediately
  GET  /field-receipts          — list receipts for org (filterable)
  GET  /field-receipts/{id}     — receipt detail + flags
  PUT  /field-receipts/{id}     — update flagged receipt (correct data)
  POST /field-receipts/{id}/resolve — approve/reject a flagged receipt
  GET  /field-receipts/policy   — get org's validation rules
  PUT  /field-receipts/policy   — update org's validation rules

Auth: User must be signed in (except /from-kobo for webhook). Field receipts are org-scoped.
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import field_receipts
import kobo_sync
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/field-receipts", tags=["field-receipts"])


# ─── upload ──────────────────────────────────────────────────────────────────


@router.post("/upload")
async def upload_receipt_endpoint(
    file: Annotated[UploadFile, File(description="Receipt image or PDF")],
    amount_submitted: Annotated[float, Form(description="Amount spent (in org's currency)")],
    project_code: Annotated[str, Form(description="Project/activity code")],
    category: Annotated[str, Form(description="Spend category (training, supplies, travel, etc.)")] = "",
    description: Annotated[str, Form(description="Optional note about the receipt")] = "",
    ctx: Ctx = Depends(request_context),
):
    """
    Upload a receipt image/PDF with metadata.

    System extracts data via OCR, validates against policy, and returns the receipt
    with status (VALIDATED or FLAGGED) and any flags that need review.
    """

    try:
        file_content = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}") from exc

    try:
        receipt = field_receipts.upload_receipt(
            org_id=ctx.org_id,
            uploaded_by=ctx.user_id,
            file_content=file_content,
            filename=file.filename or "receipt",
            amount_submitted=amount_submitted,
            project_code=project_code,
            category=category,
            description=description,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to process receipt: {exc}") from exc

    return {
        "id": receipt.id,
        "status": receipt.status,
        "amount_submitted": receipt.amount_submitted,
        "project_code": receipt.project_code,
        "extracted": {
            "vendor_name": receipt.extracted.vendor_name,
            "receipt_date": receipt.extracted.receipt_date,
            "extracted_amount": receipt.extracted.extracted_amount,
        },
        "flags": [
            {"type": f.type, "severity": f.severity, "message": f.message}
            for f in receipt.flags
        ],
    }


# ─── kobo sync ───────────────────────────────────────────────────────────────


@router.post("/from-kobo")
async def sync_kobo_submission_endpoint(
    submission_json: Annotated[str, Form(description="KoboCollect submission JSON")],
    image_file: Annotated[Optional[UploadFile], File(description="Optional receipt image")] = None,
    api_key: Annotated[Optional[str], Form(description="API key for webhook auth")] = None,
):
    """
    Accept a KoboCollect submission and log it as a receipt.

    Fieldworkers in low/no-signal areas use KoboCollect to capture receipts offline.
    When signal is available, KoboCollect syncs to our server.

    This endpoint:
      1. Accepts KoboCollect JSON payload
      2. Extracts metadata (amount, vendor, date, project code, grant code)
      3. Logs receipt immediately (no lag, simple + scalable)
      4. Validates against org's policy
      5. Returns receipt ID + any flags

    The receipt may be VALIDATED (no issues) or FLAGGED (missing data, policy issue).
    Fieldworker/finance can complete missing data in the UI (this is expected).

    Auth: Requires organization context (from JSON) + optional API key for webhook validation.
    """
    # This endpoint is called by KoboCollect's webhook, not by a signed-in
    # user, so it cannot use the bearer-token dependency. It is instead gated
    # on a shared secret: without DOCEX_KOBO_KEY set, the endpoint is closed.
    expected = (os.environ.get("DOCEX_KOBO_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="KoboCollect sync is not enabled. Set DOCEX_KOBO_KEY on the server.",
        )
    if not api_key or not hmac.compare_digest(api_key.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid KoboCollect API key.")

    image_bytes = None

    try:
        # Parse KoboCollect JSON
        submission = kobo_sync.parse_kobo_json(submission_json)
        org_id = submission.org_id

        if not org_id:
            raise HTTPException(status_code=400, detail="submission_json must include org_id")

        # Check for duplicate (deduplication)
        if submission.kobo_instance_id:
            existing = kobo_sync.get_receipt_by_kobo_instance_id(org_id, submission.kobo_instance_id)
            if existing:
                return {
                    "success": False,
                    "receipt_id": existing,
                    "message": "This KoboCollect submission was already synced.",
                    "status": "duplicate",
                }

        # Read image file if provided
        if image_file:
            try:
                image_bytes = await image_file.read()
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to read image: {exc}") from exc

        # Sync submission
        result = kobo_sync.sync_kobo_submission(
            org_id=org_id,
            submission=submission,
            image_bytes=image_bytes,
        )

        return result.model_dump()

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to sync KoboCollect submission: {exc}") from exc


# ─── list ────────────────────────────────────────────────────────────────────


@router.get("")
async def list_receipts_endpoint(
    status: Optional[str] = None,
    project_code: Optional[str] = None,
    ctx: Ctx = Depends(request_context),
):
    """
    List receipts for the signed-in user's org.

    Filters:
      - status: draft, validated, flagged, approved, rejected
      - project_code: e.g., P-101
    """

    try:
        status_enum = None
        if status:
            status_enum = field_receipts.ReceiptStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from None

    receipts = field_receipts.list_receipts(
        org_id=ctx.org_id,
        status=status_enum,
        project_code=project_code,
    )

    return {
        "total": len(receipts),
        "receipts": [
            {
                "id": r.id,
                "uploaded_at": r.uploaded_at,
                "amount_submitted": r.amount_submitted,
                "project_code": r.project_code,
                "category": r.category,
                "vendor_name": r.extracted.vendor_name,
                "status": r.status,
                "flag_count": len(r.flags),
            }
            for r in receipts
        ],
    }


# ─── policy management ──────────────────────────────────────────────────────


@router.get("/policy")
async def get_policy_endpoint(ctx: Ctx = Depends(request_context)):
    """
    Get the org's receipt validation policy.
    """

    policy = field_receipts.get_policy(ctx.org_id)
    return {
        "currency": policy.currency,
        "duplicate_window_days": policy.duplicate_window_days,
        "allow_missing_vendor": policy.allow_missing_vendor,
        "allow_missing_date": policy.allow_missing_date,
        "rules": [
            {
                "code": r.code,
                "name": r.name,
                "rule_type": r.rule_type,
                "max_amount": r.max_amount,
                "forbidden_vendors": r.forbidden_vendors,
                "allowed_categories": r.allowed_categories,
                "active": r.active,
            }
            for r in policy.rules
        ],
    }


@router.put("/policy")
async def update_policy_endpoint(
    body: dict,
    ctx: Ctx = Depends(request_context),
):
    """
    Update the org's receipt validation policy (admin only).
    """

    require_role(ctx, "admin", "approver")

    try:
        policy = field_receipts.ReceiptPolicy.model_validate(body)
        policy.org_id = ctx.org_id
        policy = field_receipts.set_policy(ctx.org_id, policy)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid policy: {exc}") from exc

    return {"message": "Policy updated.", "policy": policy.model_dump()}


# ─── detail ──────────────────────────────────────────────────────────────────


@router.get("/{receipt_id}")
async def get_receipt_endpoint(receipt_id: str, ctx: Ctx = Depends(request_context)):
    """
    Get full details of a receipt including extracted data and all flags.
    """

    receipt = field_receipts.get_receipt(ctx.org_id, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")

    return {
        "id": receipt.id,
        "uploaded_at": receipt.uploaded_at,
        "uploaded_by": receipt.uploaded_by,
        "amount_submitted": receipt.amount_submitted,
        "project_code": receipt.project_code,
        "category": receipt.category,
        "description": receipt.description,
        "original_filename": receipt.original_filename,
        "file_size_bytes": receipt.file_size_bytes,
        "extracted": {
            "vendor_name": receipt.extracted.vendor_name,
            "receipt_date": receipt.extracted.receipt_date,
            "extracted_amount": receipt.extracted.extracted_amount,
            "confidence": receipt.extracted.confidence,
        },
        "status": receipt.status,
        "flags": [
            {"type": f.type, "severity": f.severity, "message": f.message, "timestamp": f.timestamp}
            for f in receipt.flags
        ],
        "reviewed_by": receipt.reviewed_by,
        "review_decision": receipt.review_decision,
        "review_notes": receipt.review_notes,
        "created_at": receipt.created_at,
        "updated_at": receipt.updated_at,
    }


# ─── update (correct flagged data) ───────────────────────────────────────────


@router.put("/{receipt_id}")
async def update_receipt_endpoint(
    receipt_id: str,
    vendor_name: Annotated[str, Form(description="Corrected vendor name")] = "",
    receipt_date: Annotated[str, Form(description="Corrected receipt date (YYYY-MM-DD)")] = "",
    amount_submitted: Annotated[Optional[float], Form(description="Corrected amount")] = None,
    ctx: Ctx = Depends(request_context),
):
    """
    Update a flagged receipt to correct OCR/extraction errors.

    Fieldworker can fix vendor name, date, or amount if OCR got it wrong.
    After update, receipt is re-validated.
    """

    receipt = field_receipts.get_receipt(ctx.org_id, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")

    if receipt.status not in [
        field_receipts.ReceiptStatus.FLAGGED,
        field_receipts.ReceiptStatus.DRAFT,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Can only update FLAGGED or DRAFT receipts (current: {receipt.status}).",
        )

    # Update fields
    if vendor_name:
        receipt.extracted.vendor_name = vendor_name.strip()
    if receipt_date:
        receipt.extracted.receipt_date = receipt_date.strip()
    if amount_submitted is not None:
        receipt.amount_submitted = amount_submitted

    # Re-validate
    receipt = field_receipts.validate_receipt(ctx.org_id, receipt)

    # Save
    import store
    store.get_store().put(ctx.org_id, field_receipts._RECEIPTS, receipt.id, receipt.model_dump())

    return {
        "id": receipt.id,
        "status": receipt.status,
        "flags": [
            {"type": f.type, "severity": f.severity, "message": f.message}
            for f in receipt.flags
        ],
        "message": "Receipt updated and re-validated." if not receipt.flags else "Receipt updated but still has flags.",
    }


# ─── resolve (approve/reject flagged) ────────────────────────────────────────


@router.post("/{receipt_id}/resolve")
async def resolve_receipt_endpoint(
    receipt_id: str,
    decision: Annotated[str, Form(description="'approved' or 'rejected'")],
    notes: Annotated[str, Form(description="Optional review notes")] = "",
    ctx: Ctx = Depends(request_context),
):
    """
    Finance reviews a flagged receipt and approves or rejects it.

    - approved: flags are overridden, receipt proceeds to Zoho sync
    - rejected: receipt is discarded, fieldworker must resubmit
    """

    if decision not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Decision must be 'approved' or 'rejected'.")

    try:
        receipt = field_receipts.resolve_flags(
            org_id=ctx.org_id,
            receipt_id=receipt_id,
            decision=decision,  # type: ignore
            reviewed_by=ctx.user_id,
            notes=notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "id": receipt.id,
        "status": receipt.status,
        "reviewed_by": receipt.reviewed_by,
        "decision": receipt.review_decision,
        "notes": receipt.review_notes,
    }
