"""
DOCex Bank Verify routes.

Endpoints for the Bank Verify feature — bulk verification of recipient bank
accounts on a payment schedule against the bank-of-record (Paystack
/bank/resolve), with per-row fuzzy name matching.

  POST   /verify/bank-batch        — upload a .xlsx schedule, run verification
  GET    /verify/batches           — list saved verification batches (summaries)
  GET    /verify/batches/{id}      — fetch one batch in full
  DELETE /verify/batches/{id}      — delete a saved batch

Batches are persisted as JSON files in {project_root}/verifications/{id}.json
File-based storage is sufficient for MVP — swaps cleanly to Supabase in
Phase 2 (same Pydantic models, just a different store).

This module deliberately mirrors api/compliance_routes.py — same persistence
pattern, same path-safety checks, same APIRouter shape — so the codebase
stays consistent and the next-flow modules (Roster Builder, GRN Match) can
copy the pattern with minimal cognitive load.
"""
from __future__ import annotations

import datetime as dt
import io
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

# Same sys.path hack the rest of api/ uses to import root-level modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from bank_verify import parse_schedule, verify_batch  # noqa: E402
from models import (  # noqa: E402
    BankVerifyBatchResult,
)
from .schemas import (  # noqa: E402
    BatchVerifyListResponse,
    BatchVerifySummary,
)

router = APIRouter(prefix="/verify", tags=["bank-verify"])


# ─── Batch persistence (file-based) ─────────────────────────────────────────
#
# One JSON file per batch under {project_root}/verifications/. Same shape
# as the rulebooks/checks pattern. Single source of truth: BankVerifyBatchResult.

_VERIFY_DIR = Path(__file__).parent.parent / "verifications"


def _ensure_verify_dir() -> None:
    _VERIFY_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _batch_path(batch_id: str) -> Path:
    # Defensive: server-generated UUIDs, but if a forged id reaches us we
    # don't want it traversing outside the verifications directory.
    if "/" in batch_id or ".." in batch_id or not batch_id.strip():
        raise HTTPException(status_code=400, detail="Invalid batch id.")
    return _VERIFY_DIR / f"{batch_id}.json"


def _save_batch(batch: BankVerifyBatchResult) -> BankVerifyBatchResult:
    """Persist a batch to disk. Sets batch_id + created_at if missing."""
    _ensure_verify_dir()
    if not batch.batch_id:
        batch.batch_id = uuid.uuid4().hex
    if not batch.created_at:
        batch.created_at = _now_iso()
    _batch_path(batch.batch_id).write_text(batch.model_dump_json(indent=2))
    return batch


def _load_batch(batch_id: str) -> BankVerifyBatchResult:
    path = _batch_path(batch_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Verification batch '{batch_id}' not found.",
        )
    try:
        return BankVerifyBatchResult.model_validate_json(path.read_text())
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load batch '{batch_id}': {exc}",
        ) from exc


def _list_batches() -> list[BankVerifyBatchResult]:
    """List every persisted batch, newest first. Skips corrupted files
    rather than failing the whole list — one bad file shouldn't hide the
    rest of a team's audit history."""
    _ensure_verify_dir()
    paths = sorted(
        _VERIFY_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    batches: list[BankVerifyBatchResult] = []
    for path in paths:
        try:
            batches.append(BankVerifyBatchResult.model_validate_json(path.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupted batch {path.name}: {exc}")
            continue
    return batches


def _to_summary(b: BankVerifyBatchResult) -> BatchVerifySummary:
    return BatchVerifySummary(
        batch_id=b.batch_id or "",
        source_schedule=b.source_schedule,
        purpose=b.purpose,
        purpose_detail=b.purpose_detail,
        total=b.total,
        verified=b.verified,
        warning=b.warning,
        mismatch=b.mismatch,
        unverifiable=b.unverifiable,
        created_at=b.created_at,
    )


# ─── Routes ─────────────────────────────────────────────────────────────────


@router.post("/bank-batch", response_model=BankVerifyBatchResult)
async def verify_bank_batch(
    schedule: Annotated[UploadFile, File(description="Payment schedule .xlsx")],
    purpose: Annotated[
        str,
        Form(description=(
            "WHY this verification ran. Standard values: 'event_payment', "
            "'grantee_disbursement', 'vendor_payment', 'partner_reimbursement', "
            "'other'. Free-text allowed for custom purposes."
        )),
    ] = "other",
    purpose_detail: Annotated[
        str,
        Form(description="Optional free-text elaboration of the purpose."),
    ] = "",
    delay_ms: Annotated[int, Form(description="Delay between Paystack calls (ms)")] = 200,
    persist: Annotated[bool, Form(description="Save the batch result to disk")] = True,
) -> BankVerifyBatchResult:
    """
    Verify every row of a payment schedule against the bank-of-record.

    Workflow:
      1. Upload an .xlsx schedule (recipient name + account + bank columns).
      2. Auto-detect header row + columns by keyword (parse_schedule).
      3. For each row, call Paystack /bank/resolve and fuzzy-match the
         returned name against the schedule's recipient name.
      4. Return a BankVerifyBatchResult with per-row verdicts + summary.

    Calls are sequential with a polite delay between them (default 200ms ≈
    5 QPS) to stay under Paystack's test-mode rate limit of ~60 RPM. When
    we move to live keys with higher limits, drop delay_ms to 50 or lower.

    Persistence is on by default — the batch is saved to {project_root}/
    verifications/{batch_id}.json so it survives page refreshes and gets
    a stable URL for the auditor to revisit. Pass persist=false to skip
    save (useful for one-off dry runs).
    """
    if not schedule.filename or not schedule.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=422,
            detail="Schedule must be an .xlsx (or .xlsm) file. "
                   f"Got: {schedule.filename!r}",
        )

    # Read the upload into memory once. openpyxl needs random access and
    # FastAPI's SpooledTemporaryFile can be exhausted mid-read by a streaming
    # parser — buffering into BytesIO is safer for files under ~10MB which is
    # the realistic ceiling for a payment schedule.
    raw = await schedule.read()
    buf = io.BytesIO(raw)

    try:
        rows = parse_schedule(buf)
    except ValueError as exc:
        # Header-row detection failed — bubble the human-readable message
        # back so the user can rename their columns or trim a stray title row.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse schedule: {exc}",
        ) from exc

    if not rows:
        raise HTTPException(
            status_code=422,
            detail="No data rows found below the header. Check that the "
                   "schedule has at least one row of recipient data.",
        )

    # Run the actual verification. delay_ms is capped at 5 seconds upstream;
    # 0 is allowed (fastest possible — only safe in live mode with high rate
    # limits, will get 429s in test mode at ~60 RPM).
    batch = verify_batch(rows, delay_ms=max(0, min(int(delay_ms), 5_000)))

    # Tag with provenance so the audit trail knows which schedule produced
    # this batch. Survives the round-trip to disk via Pydantic.
    batch.source_schedule = schedule.filename
    # Tag the purpose so "show me all grantee disbursement verifications
    # for Q2" is one filter, not a hunt through filenames.
    batch.purpose = purpose.strip() or "other"
    batch.purpose_detail = purpose_detail.strip() or None

    if persist:
        batch = _save_batch(batch)

    return batch


@router.get("/batches", response_model=BatchVerifyListResponse)
def list_batches() -> BatchVerifyListResponse:
    """List every saved verification batch, newest first."""
    batches = _list_batches()
    return BatchVerifyListResponse(
        batches=[_to_summary(b) for b in batches],
    )


@router.get("/batches/{batch_id}", response_model=BankVerifyBatchResult)
def get_batch(batch_id: str) -> BankVerifyBatchResult:
    """Fetch one saved verification batch in full."""
    return _load_batch(batch_id)


@router.get("/batches/{batch_id}/export.xlsx")
def export_batch_xlsx(batch_id: str) -> StreamingResponse:
    """
    Export a saved verification batch as an .xlsx file.

    Re-emits the original schedule rows with four columns appended:
      - Verdict             (verified / warning / mismatch / unverifiable)
      - Match Score         (0-100, blank when unverifiable)
      - Bank-of-Record Name (what Paystack returned, blank when unverifiable)
      - Notes               (error message when unverifiable, else blank)

    Why this matters: finance officers live in Excel. They don't want to
    copy-paste verdicts from a web UI back into their working file — they
    want the working file BACK, augmented. That's the artifact that gets
    pasted into the payment-approval email thread, attached to the bank
    instruction, or filed in the audit folder. The web UI is the workbench;
    this download is the deliverable.

    The export is generated on the fly from the persisted JSON so it stays
    in sync if the underlying batch is ever edited (it isn't, today, but
    will be once we add a 'mark as cleared' workflow).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    batch = _load_batch(batch_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Verified Schedule"

    # Banner row (matches the input schedule aesthetic so the file looks
    # like a continuation of theirs, not a foreign export).
    title = f"Bank Verify Results — {batch.source_schedule or batch_id}"
    ws.merge_cells("A1:I1")
    ws["A1"] = title
    ws["A1"].font = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", start_color="1F3A5F")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:I2")
    ws["A2"] = (
        f"Generated {batch.created_at or ''}  ·  "
        f"{batch.verified} verified  ·  {batch.warning} warning  ·  "
        f"{batch.mismatch} mismatch  ·  {batch.unverifiable} unverifiable"
    )
    ws["A2"].font = Font(name="Arial", size=10, italic=True, color="666666")
    ws["A2"].alignment = Alignment(horizontal="center")

    # Header row
    headers = [
        "Recipient Name",
        "Account Number",
        "Bank",
        "Bank Code",
        "Amount (NGN)",
        "Verdict",
        "Match Score",
        "Bank-of-Record Name",
        "Notes",
    ]
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col_idx, value=h)
        c.font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="2563EB")
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[4].height = 22

    # Verdict colour-coding so the file is readable at a glance — matches
    # the colour vocabulary the CLI uses (green/yellow/red/grey).
    verdict_fill = {
        "verified":     PatternFill("solid", start_color="D1FAE5"),  # emerald-100
        "warning":      PatternFill("solid", start_color="FEF3C7"),  # amber-100
        "mismatch":     PatternFill("solid", start_color="FEE2E2"),  # red-100
        "unverifiable": PatternFill("solid", start_color="F3F4F6"),  # gray-100
    }

    for row_offset, r in enumerate(batch.results, start=5):
        values = [
            r.recipient_name,
            r.account_number,
            r.bank_name or "",
            r.bank_code,
            r.amount if r.amount is not None else "",
            r.verdict,
            r.match_score if r.match_score is not None else "",
            r.resolved_name or "",
            r.error_message or "",
        ]
        for col_idx, value in enumerate(values, start=1):
            c = ws.cell(row=row_offset, column=col_idx, value=value)
            c.font = Font(name="Arial", size=11)
            c.alignment = Alignment(vertical="center")
            # Tint the verdict cell + extend the tint across the row so the
            # eye groups the row's status visually rather than hunting for
            # one column. Light tints only — the text stays black.
            fill = verdict_fill.get(r.verdict)
            if fill:
                c.fill = fill
        # Format the account number as text (preserve leading zeros)
        ws.cell(row=row_offset, column=2).number_format = "@"
        # Format amount with ₦ if present
        if r.amount is not None:
            amt = ws.cell(row=row_offset, column=5)
            amt.number_format = '"₦"#,##0'
            amt.alignment = Alignment(horizontal="right", vertical="center")

    # Column widths tuned for the content
    widths = {
        "A": 32, "B": 16, "C": 14, "D": 12, "E": 14,
        "F": 14, "G": 12, "H": 32, "I": 40,
    }
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # Stream back as a downloadable file. BytesIO so we don't touch disk —
    # the persisted JSON is the source of truth, this is a derived view.
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = (batch.source_schedule or f"bank-verify-{batch_id}").rsplit(".", 1)[0]
    filename = f"{safe_name}_verified.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str) -> dict[str, str]:
    """Delete one saved verification batch. Idempotent — deleting a
    non-existent batch returns 404."""
    path = _batch_path(batch_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Verification batch '{batch_id}' not found.",
        )
    path.unlink()
    return {"status": "deleted", "batch_id": batch_id}
