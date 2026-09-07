"""
FastAPI routes for the QuickBooks handoff.

Endpoints:
  GET  /accounting/map                    — this org's account/class mapping
  PUT  /accounting/map                    — configure it (admin)
  GET  /accounting/summary                — what next month's export contains
  GET  /accounting/export/payments        — coded payment register (CSV)
  POST /accounting/export/bank-statement  — a bank CSV QuickBooks will accept

The last one is worth its own note. Nigerian banks cannot be connected to
QuickBooks bank feeds, so the client already downloads a CSV and imports it by
hand — and QuickBooks rejects exactly what those files contain: currency
symbols, comma thousands separators, title rows above the header, more than
four columns. Somebody reformats it in Excel every month.

DOCex already parses those statements properly for reconciliation, so cleaning
one costs us nothing and removes a monthly chore the client has never
complained about because they assume it is simply how it is.
"""
from __future__ import annotations

from typing import Optional

from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                     Query, UploadFile)
from fastapi.responses import PlainTextResponse

import accounting_export as ax
import org_config
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/accounting", tags=["accounting"])

_FLAG = "accounting_export"


def _gate(ctx: Ctx) -> Ctx:
    if not org_config.feature_enabled(ctx.org_id, _FLAG):
        raise HTTPException(
            status_code=404,
            detail="Accounting export is not enabled for this organisation.")
    return ctx


@router.get("/map")
async def get_map(ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    return ax.get_map(ctx.org_id).model_dump()


@router.put("/map")
async def set_map(payload: dict = Body(...), ctx: Ctx = Depends(request_context)):
    """Map DOCex categories to their chart of accounts.

    Never guessed. An invented account name imports cleanly and posts the money
    to the wrong place, which is harder to find than an import that fails.
    """
    _gate(ctx)
    require_role(ctx, "admin")
    try:
        amap = ax.AccountMap.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid mapping: {exc}")
    return ax.set_map(ctx.org_id, amap).model_dump()


@router.get("/summary")
async def summary(period: str = Query(...), ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    try:
        return ax.export_summary(ctx.org_id, period)
    except ax.ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/export/payments", response_class=PlainTextResponse)
async def export_payments(period: str = Query(...),
                          ctx: Ctx = Depends(request_context)):
    """Every approved, paid item for the month — coded, ready to enter.

    Each row carries its DOCex reference, so somebody standing in QuickBooks
    six months later can ask "who approved this?" and get an answer.
    """
    _gate(ctx)
    try:
        csv_text = ax.payment_register_csv(ctx.org_id, period)
    except ax.ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return PlainTextResponse(
        csv_text, media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="docex-payments-{period}.csv"'})


@router.post("/export/bank-statement")
async def export_bank_statement(
    statement: UploadFile = File(...),
    date_format: str = Form(""),
    four_column: bool = Form(False),
    qbo_date_format: str = Form("%d/%m/%Y"),
    ctx: Ctx = Depends(request_context),
):
    """Clean a bank statement into files QuickBooks will accept.

    Reuses the reconciliation importer, so the hard parts — the bank's title
    rows, column detection, proving day-first vs month-first, stripping ₦ and
    commas — are already solved. Returns the files as text rather than a
    download so the caller can show a preview before saving; a wrong date
    format is much cheaper to spot here than after import.
    """
    _gate(ctx)
    import bank_reconciliation as br

    data = await statement.read()
    if not data:
        raise HTTPException(status_code=422, detail="The statement file is empty.")

    cmap = br.get_column_map(ctx.org_id)
    if date_format:
        cmap = (cmap.model_copy(deep=True) if cmap else br.ColumnMap())
        cmap.date_format = date_format
    try:
        lines, used = br.parse_statement(
            data, filename=statement.filename or "statement.csv", column_map=cmap)
        files = ax.bank_statement_csv(lines, date_format=qbo_date_format,
                                      four_column=four_column)
    except (br.ReconciliationError, ax.ExportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "files": files,
        "file_count": len(files),
        "rows": len(lines),
        "columns_used": used.model_dump(),
        "note": ("QuickBooks caps a manual upload at about 1,000 rows, so a "
                 "long statement comes back as several files — upload them in "
                 "order." if len(files) > 1 else
                 "Upload this under Banking → Upload transactions in QuickBooks."),
    }
