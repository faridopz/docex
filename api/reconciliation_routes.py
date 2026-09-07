"""
FastAPI routes for month-end bank reconciliation.

Endpoints:
  GET  /reconciliation                        — every run, newest period first
  GET  /reconciliation/columns                — this org's saved statement layout
  PUT  /reconciliation/columns                — pin it (admin)
  POST /reconciliation/preview                — read a statement WITHOUT saving
  POST /reconciliation                        — reconcile a period, store the run
  GET  /reconciliation/{id}                   — matches, exceptions, both totals
  POST /reconciliation/{id}/match             — pair by hand, with a reason
  POST /reconciliation/{id}/explain           — justify an exception
  POST /reconciliation/{id}/close             — lock the month

/preview exists because statement layouts differ by bank and the cost of a
wrong column mapping is a reconciliation that looks clean over the wrong
pairing. Preview shows the first rows exactly as the importer read them, so a
human confirms the mapping before a run is stored against the period.

Import errors come back as 422 with the engine's own message, which names the
headers it found and what it wanted. That message is the fix instruction — a
generic "invalid file" would send the client back to us instead of to their
export settings.
"""
from __future__ import annotations

from typing import Optional

from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                     Query, UploadFile)

import bank_reconciliation as br
import org_config
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

_FLAG = "bank_reconciliation"
_MAX_BYTES = 10 * 1024 * 1024        # a month of statement is kilobytes, not megabytes

# Date formats a caller may select. An allowlist rather than free text: this
# string reaches strptime, and the set of sane answers to "day first or month
# first" is small enough to enumerate.
_ALLOWED_DATE_FORMATS = {"%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
                         "%Y-%m-%d", "%d.%m.%Y"}


def _gate(ctx: Ctx) -> Ctx:
    if not org_config.feature_enabled(ctx.org_id, _FLAG):
        raise HTTPException(
            status_code=404,
            detail="Bank reconciliation is not enabled for this organisation.")
    return ctx


def _fail(exc: br.ReconciliationError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=422, detail="The statement file is empty.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Statement is larger than 10MB — that is not a month of one "
                   "account. Export a single account for a single period.")
    return data


def _column_map(saved: Optional[br.ColumnMap], override: str,
                date_format: str = "") -> Optional[br.ColumnMap]:
    """Resolve the mapping for this upload.

    An explicit per-upload mapping wins over the org's saved one. `date_format`
    is handled separately and deliberately: it is the one thing a user routinely
    has to supply on its own.

    Early in a month every date on a statement can read both ways — 07/09 is
    ambiguous, 25/09 is not — so the importer refuses rather than guessing, and
    the person needs to answer "day first or month first" WITHOUT also having to
    describe every column. Folding date_format into the full mapping would mean
    answering that question threw away column auto-detection, which is a poor
    trade for the user and an easy source of a silently wrong import.
    """
    cmap = saved
    if override:
        try:
            import json
            cmap = br.ColumnMap.model_validate(json.loads(override))
        except Exception as exc:
            raise HTTPException(status_code=422,
                                detail=f"Invalid column_map: {exc}")
    if date_format:
        if date_format not in _ALLOWED_DATE_FORMATS:
            raise HTTPException(
                status_code=422,
                detail=("Unsupported date format. Use one of: "
                        + ", ".join(sorted(_ALLOWED_DATE_FORMATS))))
        cmap = (cmap.model_copy(deep=True) if cmap else br.ColumnMap())
        cmap.date_format = date_format
    return cmap


# ─── serialisers ────────────────────────────────────────────────────────────


def _match_out(m: br.Match) -> dict:
    return {
        "transaction_id": m.transaction_id,
        "transaction_ref": m.transaction_ref,
        "bank_line_id": m.bank_line_id,
        "bank_row": m.bank_row,
        "method": m.method.value,
        "amount": m.amount,
        "paid_at": m.paid_at,
        "bank_date": m.bank_date,
        "day_gap": m.day_gap,
        "vendor_name": m.vendor_name,
        "matched_by": m.matched_by,
        "reason": m.reason,
    }


def _exception_out(e: br.ReconException) -> dict:
    return {
        "code": e.code.value,
        "severity": e.severity.value,
        "amount": e.amount,
        "date": e.date,
        "description": e.description,
        "transaction_id": e.transaction_id,
        "transaction_ref": e.transaction_ref,
        "bank_line_id": e.bank_line_id,
        "bank_row": e.bank_row,
        "candidates": e.candidates,
        "note": e.note,
    }


def _line_out(l: br.BankLine) -> dict:
    return {"id": l.id, "row": l.row, "date": l.date,
            "description": l.description, "reference": l.reference,
            "amount": abs(l.amount), "direction": "out" if l.is_debit else "in"}


def _detail_out(run: br.ReconciliationRun) -> dict:
    out = br.summary(run)
    out.update({
        "period_start": run.period_start,
        "period_end": run.period_end,
        "column_map": run.column_map.model_dump(),
        "date_window_days": run.date_window_days,
        "matches": [_match_out(m) for m in run.matches],
        # Highest severity first: the auditor's eye should land on unexplained
        # money, not on a bank charge someone already accounted for.
        "exceptions": [_exception_out(e) for e in sorted(
            run.exceptions,
            key=lambda e: {"high": 0, "medium": 1, "low": 2}[e.severity.value])],
        "bank_lines": [_line_out(l) for l in run.bank_lines],
        "created_at": run.created_at,
        "created_by": run.created_by,
        "closed_at": run.closed_at,
    })
    return out


# ─── literal paths (before /{run_id}) ───────────────────────────────────────


@router.get("")
async def list_runs(period: Optional[str] = Query(None),
                    ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    runs = br.list_runs(ctx.org_id, period=period)
    return {"runs": [br.summary(r) for r in runs], "total": len(runs)}


@router.get("/columns")
async def get_columns(ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    cmap = br.get_column_map(ctx.org_id)
    return {"column_map": cmap.model_dump() if cmap else None,
            "configured": cmap is not None}


@router.put("/columns")
async def set_columns(payload: dict = Body(...), ctx: Ctx = Depends(request_context)):
    """Pin the client's bank layout once, so every month imports identically."""
    _gate(ctx)
    require_role(ctx, "admin")
    try:
        cmap = br.ColumnMap.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid column map: {exc}")
    return br.set_column_map(ctx.org_id, cmap).model_dump()


@router.post("/preview")
async def preview(
    statement: UploadFile = File(...),
    column_map: str = Form(""),
    date_format: str = Form(""),
    rows: int = Form(10),
    ctx: Ctx = Depends(request_context),
):
    """Read the statement and show what the importer saw. Stores nothing."""
    _gate(ctx)
    data = await _read(statement)
    try:
        lines, cmap = br.parse_statement(
            data, filename=statement.filename or "statement.csv",
            column_map=_column_map(br.get_column_map(ctx.org_id), column_map,
                                   date_format))
    except br.ReconciliationError as exc:
        raise _fail(exc)

    debits = [l for l in lines if l.is_debit]
    return {
        "column_map": cmap.model_dump(),
        "auto_detected": cmap.detected,
        "lines_total": len(lines),
        "debits": len(debits),
        "credits": len(lines) - len(debits),
        "debit_value": round(sum(abs(l.amount) for l in debits), 2),
        "first_date": min((l.date for l in lines), default=""),
        "last_date": max((l.date for l in lines), default=""),
        "sample": [_line_out(l) for l in lines[:max(1, min(rows, 50))]],
        # Say it plainly: detection is a convenience, not a guarantee.
        "confirm": ("Check the sample rows below against the statement before "
                    "reconciling. If a column was read wrongly, set the column "
                    "map rather than proceeding."),
    }


@router.post("")
async def run_reconciliation(
    period: str = Form(...),
    statement: UploadFile = File(...),
    column_map: str = Form(""),
    date_format: str = Form(""),
    date_window_days: int = Form(br.DEFAULT_DATE_WINDOW_DAYS),
    settlement_days: int = Form(br.DEFAULT_SETTLEMENT_DAYS),
    ctx: Ctx = Depends(request_context),
):
    """Reconcile a month and store the run as evidence."""
    _gate(ctx)
    require_role(ctx, "admin", "approver", "reviewer")
    data = await _read(statement)
    try:
        run = br.reconcile(
            ctx.org_id, period, data,
            filename=statement.filename or "statement.csv",
            column_map=_column_map(br.get_column_map(ctx.org_id), column_map,
                                   date_format),
            date_window_days=date_window_days,
            settlement_days=settlement_days,
            actor=ctx.user_id)
    except br.ReconciliationError as exc:
        raise _fail(exc)
    return _detail_out(run)


@router.get("/{run_id}")
async def get_run(run_id: str, ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    run = br.get_run(ctx.org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Reconciliation not found.")
    return _detail_out(run)


@router.post("/{run_id}/match")
async def match(run_id: str, transaction_id: str = Form(...),
                bank_line_id: str = Form(...), reason: str = Form(...),
                ctx: Ctx = Depends(request_context)):
    """Pair a payment with a bank line the engine would not pair itself."""
    _gate(ctx)
    require_role(ctx, "admin", "approver", "reviewer")
    try:
        run = br.manual_match(ctx.org_id, run_id, transaction_id=transaction_id,
                              bank_line_id=bank_line_id, actor=ctx.user_id,
                              reason=reason)
    except br.ReconciliationError as exc:
        raise _fail(exc)
    return _detail_out(run)


@router.post("/{run_id}/explain")
async def explain(run_id: str, reason: str = Form(...),
                  bank_line_id: str = Form(""), transaction_id: str = Form(""),
                  ctx: Ctx = Depends(request_context)):
    """Record why an unmatched item is acceptable. It is downgraded, not removed."""
    _gate(ctx)
    require_role(ctx, "admin", "approver", "reviewer")
    if not (bank_line_id or transaction_id):
        raise HTTPException(
            status_code=422,
            detail="Name the item being explained: bank_line_id or transaction_id.")
    try:
        run = br.explain_exception(ctx.org_id, run_id, bank_line_id=bank_line_id,
                                   transaction_id=transaction_id,
                                   actor=ctx.user_id, reason=reason)
    except br.ReconciliationError as exc:
        raise _fail(exc)
    return _detail_out(run)


@router.post("/{run_id}/close")
async def close(run_id: str, force_reason: str = Form(""),
                ctx: Ctx = Depends(request_context)):
    """Lock the month. Closing over unexplained money needs a written reason,
    and that reason is stored against the closer's name."""
    _gate(ctx)
    require_role(ctx, "admin", "approver")
    try:
        run = br.close_period(ctx.org_id, run_id, actor=ctx.user_id,
                              force_reason=force_reason)
    except br.ReconciliationError as exc:
        raise _fail(exc)
    return _detail_out(run)
