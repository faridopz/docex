"""
DOCex Attendance Payment Agent routes.

Composite agent — chains primitives (parse → match → optional Bank Verify
→ optional email) rather than introducing a new core engine. Endpoints:

  POST   /agents/attendance-payment/run         — full run: parse + match
  GET    /agents/attendance-payment/runs        — list saved runs (summaries)
  GET    /agents/attendance-payment/runs/{id}   — fetch one run in full
  POST   /agents/attendance-payment/runs/{id}/verify
                                                — hand the run's paid bucket
                                                  to Bank Verify and link
                                                  the resulting batch back
  GET    /agents/attendance-payment/runs/{id}/schedule.xlsx
                                                — download the paid bucket as
                                                  a clean payment schedule
  DELETE /agents/attendance-payment/runs/{id}   — delete a saved run

Runs are persisted as JSON files in {project_root}/attendance_runs/{id}.json
Same pattern as the other primitive's persistence — single source of truth
in the Pydantic model, file-per-record on disk.
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

from attendance_agent import (  # noqa: E402
    google_sheets_xlsx_bytes,
    match_and_build_run,
    parse_attendance_log,
    parse_payment_info,
)
from bank_verify import verify_batch  # noqa: E402
from models import (  # noqa: E402
    AttendancePaymentRun,
    BankAccountRow,
    BankVerifyBatchResult,
)
from .bank_verify_routes import _save_batch  # noqa: E402
from .rate_card_routes import _load as _load_rate_card  # noqa: E402

router = APIRouter(prefix="/agents/attendance-payment", tags=["agents"])


# ─── Persistence ────────────────────────────────────────────────────────────

_RUN_DIR = Path(__file__).parent.parent / "attendance_runs"


def _ensure_run_dir() -> None:
    _RUN_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _run_path(run_id: str) -> Path:
    if "/" in run_id or ".." in run_id or not run_id.strip():
        raise HTTPException(status_code=400, detail="Invalid run id.")
    return _RUN_DIR / f"{run_id}.json"


def _save_run(run: AttendancePaymentRun) -> AttendancePaymentRun:
    _ensure_run_dir()
    if not run.run_id:
        run.run_id = uuid.uuid4().hex
    if not run.created_at:
        run.created_at = _now_iso()
    _run_path(run.run_id).write_text(run.model_dump_json(indent=2))
    return run


def _load_run(run_id: str) -> AttendancePaymentRun:
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Attendance run '{run_id}' not found.",
        )
    try:
        return AttendancePaymentRun.model_validate_json(path.read_text())
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load run '{run_id}': {exc}",
        ) from exc


def _list_runs() -> list[AttendancePaymentRun]:
    _ensure_run_dir()
    paths = sorted(
        _RUN_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    runs: list[AttendancePaymentRun] = []
    for path in paths:
        try:
            runs.append(AttendancePaymentRun.model_validate_json(path.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupted run {path.name}: {exc}")
            continue
    return runs


# ─── Routes ─────────────────────────────────────────────────────────────────


def _ingest_source(
    upload: UploadFile | None,
    sheet_url: str | None,
    label: str,
) -> tuple[bytes, str, str]:
    """
    Resolve either a file upload or a Google Sheets URL into raw xlsx bytes.

    Returns (raw_bytes, source_label_for_filename_field, source_format)
    where source_format is "xlsx" or "google_sheets". Raises HTTPException
    on validation / fetch failure with messages the frontend surfaces to
    the user verbatim.
    """
    has_upload = upload is not None and upload.filename
    has_url = bool(sheet_url and sheet_url.strip())
    if has_upload and has_url:
        raise HTTPException(
            status_code=422,
            detail=f"{label}: provide either a file OR a Google Sheets URL, not both.",
        )
    if not has_upload and not has_url:
        raise HTTPException(
            status_code=422,
            detail=f"{label}: missing — provide a file or a Google Sheets URL.",
        )

    if has_upload:
        fn = (upload.filename or "").lower()  # type: ignore[union-attr]
        if not (fn.endswith(".xlsx") or fn.endswith(".xlsm")):
            raise HTTPException(
                status_code=422,
                detail=f"{label} must be an .xlsx file. Got: {upload.filename!r}",  # type: ignore[union-attr]
            )
        # Read into memory (sync; FastAPI's UploadFile.file is sync-friendly
        # and we already have the body buffered at this layer in real apps).
        upload.file.seek(0)  # type: ignore[union-attr]
        return upload.file.read(), upload.filename or label, "xlsx"  # type: ignore[union-attr]

    # Google Sheets path. google_sheets_xlsx_bytes raises ValueError with a
    # human-readable message when the link is malformed or the sheet is
    # private; bubble that up as a 422.
    try:
        raw = google_sheets_xlsx_bytes(sheet_url.strip())  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label}: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"{label}: could not fetch Google Sheet — {exc}",
        ) from exc
    return raw, sheet_url, "google_sheets"  # type: ignore[return-value]


@router.post("/run", response_model=AttendancePaymentRun)
async def run_attendance_agent(
    event_name: Annotated[
        str,
        Form(description="Human-readable event name, e.g. 'Q2 Training — Abuja'"),
    ],
    rate_per_day: Annotated[
        float,
        Form(description=(
            "Default per-diem rate (NGN). Ignored when a rate_card_id is "
            "supplied — the card's default_rate_per_day takes over."
        )),
    ] = 0,
    rate_card_id: Annotated[
        str,
        Form(description=(
            "Optional id of a saved RateCard. When set, per-role rates "
            "from the card override rate_per_day. Falls back to the card's "
            "default for unmapped roles."
        )),
    ] = "",
    attendance: Annotated[
        UploadFile | None,
        File(description="Attendance log .xlsx — one row per attendee, one column per day"),
    ] = None,
    payment_info: Annotated[
        UploadFile | None,
        File(description="Payment info form .xlsx — name + organisation + account + bank"),
    ] = None,
    attendance_sheet_url: Annotated[
        str,
        Form(description=(
            "Alternative to the attendance file upload. Public Google Sheets "
            "share URL — DOCex fetches the xlsx export and parses it."
        )),
    ] = "",
    payment_info_sheet_url: Annotated[
        str,
        Form(description=(
            "Alternative to the payment info file upload. Public Google "
            "Sheets share URL — same shape as the .xlsx form."
        )),
    ] = "",
    persist: Annotated[
        bool,
        Form(description="Save the run to disk so it survives page refreshes"),
    ] = True,
) -> AttendancePaymentRun:
    """
    Run the full Attendance Payment Agent.

    Inputs (each can be EITHER a file upload OR a Google Sheets URL):
      - attendance log (who showed up each day)
      - payment info form (name + org + bank + account, optional role)

    Plus event metadata:
      - event_name
      - rate_per_day OR rate_card_id (card wins when both supplied)

    Returns the full AttendancePaymentRun with three buckets (paid /
    no_attendance / no_payment_info), the rate card snapshot, and the
    accuracy_flags surfaced for review BEFORE Bank Verify fires.
    Persisted by default.
    """
    # Resolve the rate card. Either a saved card (by id) or build a
    # degenerate flat-rate card from rate_per_day. One of them must
    # produce a positive default rate.
    card = None
    if rate_card_id.strip():
        card = _load_rate_card(rate_card_id.strip())
    elif rate_per_day > 0:
        # No rate_card_id, no problem — match_and_build_run will wrap
        # rate_per_day in a degenerate card via build_rate_card_from_flat.
        pass
    else:
        raise HTTPException(
            status_code=422,
            detail="Either rate_card_id or rate_per_day must be set with a positive value.",
        )

    # Resolve both inputs (file OR URL) into raw xlsx bytes.
    att_bytes, att_label, att_source = _ingest_source(
        attendance, attendance_sheet_url, "Attendance log"
    )
    pay_bytes, pay_label, pay_source = _ingest_source(
        payment_info, payment_info_sheet_url, "Payment info form"
    )

    try:
        attendance_records = parse_attendance_log(io.BytesIO(att_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Attendance log: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse attendance log: {exc}",
        ) from exc

    try:
        payment_records = parse_payment_info(io.BytesIO(pay_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Payment info form: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse payment info form: {exc}",
        ) from exc

    if not attendance_records:
        raise HTTPException(
            status_code=422,
            detail="No attendance rows found below the header. Add at least "
                   "one attendee row and try again.",
        )
    if not payment_records:
        raise HTTPException(
            status_code=422,
            detail="No payment info rows found below the header. Add at "
                   "least one row with name + account + bank.",
        )

    run = match_and_build_run(
        event_name=event_name.strip() or "Unnamed event",
        rate_per_day=float(rate_per_day) if rate_per_day > 0 else (card.default_rate_per_day if card else 0.0),
        attendance=attendance_records,
        payment_info=payment_records,
        rate_card=card,
    )
    run.attendance_filename = att_label
    run.payment_info_filename = pay_label
    run.attendance_source = att_source
    run.payment_info_source = pay_source

    if persist:
        run = _save_run(run)

    return run


@router.get("/runs", response_model=dict)
def list_runs() -> dict:
    """List every saved attendance payment run, newest first."""
    runs = _list_runs()
    # Slim summary projection — drops the large per-row arrays for the
    # list view. Frontend fetches the full run when the user opens one.
    summaries = [
        {
            "run_id": r.run_id,
            "event_name": r.event_name,
            "rate_per_day": r.rate_per_day,
            "days_in_event": r.days_in_event,
            "paid_count": r.paid_count,
            "no_attendance_count": r.no_attendance_count,
            "no_payment_info_count": r.no_payment_info_count,
            "total_to_pay": r.total_to_pay,
            "created_at": r.created_at,
            "attendance_filename": r.attendance_filename,
            "payment_info_filename": r.payment_info_filename,
            "bank_verify_batch_id": r.bank_verify_batch_id,
        }
        for r in runs
    ]
    return {"runs": summaries}


@router.get("/runs/{run_id}", response_model=AttendancePaymentRun)
def get_run(run_id: str) -> AttendancePaymentRun:
    """Fetch one saved attendance payment run in full."""
    return _load_run(run_id)


@router.post("/runs/{run_id}/verify", response_model=BankVerifyBatchResult)
def verify_run(run_id: str) -> BankVerifyBatchResult:
    """
    Hand the run's paid bucket to the Bank Verify primitive.

    Composes two primitives — that's the whole point of an agent: the user
    clicks one button and the schedule flows from "draft" to "verified"
    without re-uploading anything. The resulting BankVerifyBatchResult is
    saved with attendance_run_id back-linking to this run, and the run is
    updated with bank_verify_batch_id so each side knows about the other.
    """
    run = _load_run(run_id)

    if not run.matched:
        raise HTTPException(
            status_code=422,
            detail="This run has no payable rows to verify — every "
                   "registered person was bucketed as no_attendance.",
        )

    # Build BankAccountRow inputs from the matched bucket. Carry the
    # amount + notes through so the verified xlsx export shows them.
    rows: list[BankAccountRow] = []
    for m in run.matched:
        if not (m.account_number and m.bank_code):
            continue  # defensive: paid bucket should always have these
        rows.append(
            BankAccountRow(
                recipient_name=m.payment_info_name or m.attendance_name or "Unknown",
                account_number=m.account_number,
                bank_code=m.bank_code,
                bank_name=m.bank_name,
                amount=m.amount,
                notes=(
                    f"{m.days_attended} days @ ₦{run.rate_per_day:,.0f}/day"
                    + (f" · {m.organisation}" if m.organisation else "")
                ),
            )
        )

    if not rows:
        raise HTTPException(
            status_code=422,
            detail="Paid bucket exists but no rows had complete bank info.",
        )

    batch = verify_batch(rows)

    # Tag provenance — purpose=event_payment, source_schedule=event name,
    # attendance_run_id back-link.
    batch.purpose = "event_payment"
    batch.purpose_detail = run.event_name
    batch.source_schedule = (
        f"{run.event_name} — attendance payment schedule"
    )
    batch.attendance_run_id = run.run_id

    batch = _save_batch(batch)

    # Update the run to know about the batch (bidirectional link).
    run.bank_verify_batch_id = batch.batch_id
    _save_run(run)

    return batch


@router.get("/runs/{run_id}/schedule.xlsx")
def export_schedule(run_id: str) -> StreamingResponse:
    """
    Download the run's paid bucket as a clean payment schedule .xlsx.

    Shape matches what Bank Verify accepts as an upload — name + account
    + bank + amount + notes columns — so the user can also use this file
    as an audit-friendly artifact OR re-feed it into a different system.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    run = _load_run(run_id)
    paid = run.matched

    wb = Workbook()
    ws = wb.active
    ws.title = "Payment Schedule"

    # Banner
    title = f"{run.event_name} — Payment Schedule"
    ws.merge_cells("A1:G1")
    ws["A1"] = title
    ws["A1"].font = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", start_color="1F3A5F")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:G2")
    ws["A2"] = (
        f"{run.paid_count} payees  ·  Rate ₦{run.rate_per_day:,.0f}/day  ·  "
        f"Total ₦{run.total_to_pay:,.0f}  ·  Generated {run.created_at or ''}"
    )
    ws["A2"].font = Font(name="Arial", size=10, italic=True, color="666666")
    ws["A2"].alignment = Alignment(horizontal="center")

    headers = [
        "Recipient Name",
        "Organisation",
        "Account Number",
        "Bank",
        "Days",
        "Amount (NGN)",
        "Notes",
    ]
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col_idx, value=h)
        c.font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="2563EB")
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[4].height = 22

    for row_offset, m in enumerate(paid, start=5):
        ws.cell(row=row_offset, column=1, value=m.payment_info_name or "")
        ws.cell(row=row_offset, column=2, value=m.organisation or "")
        c_acct = ws.cell(row=row_offset, column=3, value=m.account_number or "")
        c_acct.number_format = "@"
        ws.cell(row=row_offset, column=4, value=m.bank_name or m.bank_code or "")
        ws.cell(row=row_offset, column=5, value=m.days_attended)
        c_amt = ws.cell(row=row_offset, column=6, value=m.amount)
        c_amt.number_format = '"₦"#,##0'
        ws.cell(row=row_offset, column=7, value=", ".join(m.day_labels) if m.day_labels else "")
        for col in range(1, 8):
            ws.cell(row=row_offset, column=col).alignment = Alignment(vertical="center")

    # Total row
    total_row = 5 + len(paid)
    ws.cell(row=total_row, column=5, value="Total").font = Font(bold=True)
    ws.cell(row=total_row, column=5).alignment = Alignment(horizontal="right")
    ws.cell(row=total_row, column=6, value=f"=SUM(F5:F{total_row - 1})")
    ws.cell(row=total_row, column=6).font = Font(bold=True)
    ws.cell(row=total_row, column=6).number_format = '"₦"#,##0'

    widths = {"A": 30, "B": 22, "C": 16, "D": 14, "E": 8, "F": 16, "G": 30}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe = run.event_name.replace("/", "-").replace(" ", "_")[:60]
    filename = f"{safe}_payment_schedule.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/runs/{run_id}")
def delete_run(run_id: str) -> dict[str, str]:
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Attendance run '{run_id}' not found.",
        )
    path.unlink()
    return {"status": "deleted", "run_id": run_id}
