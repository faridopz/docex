"""
FastAPI routes for bank accounts and withholding tax.

Both in one router because they answer the same question from two sides: which
account did the money leave from, and what was deducted before it went. Neither
is a workflow — they are the facts a payment needs to be reconcilable.

Bank accounts:
  GET  /treasury/accounts               — the register, numbers masked
  POST /treasury/accounts               — register one (admin)
  GET  /treasury/accounts/portfolio     — every account, this month, one screen
  POST /treasury/accounts/identify      — which account is this statement for?
  POST /treasury/accounts/{id}/close    — deactivate, keeping the history

Withholding tax:
  GET  /treasury/wht/policy             — the org's schedule
  PUT  /treasury/wht/policy             — set it (admin)
  POST /treasury/wht/preview            — what would be withheld, and why
  GET  /treasury/wht/liability          — what was withheld in a period

Account numbers are stored but MASKED in every response. A screen has no
reason to display a full account number, and the fewer places it appears the
fewer places it can leak.
"""
from __future__ import annotations

from typing import Optional

from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                     Query, UploadFile)

import bank_accounts as ba
import org_config
import withholding as wht
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/treasury", tags=["treasury"])

_ACCOUNTS_FLAG = "bank_reconciliation"    # accounts exist to be reconciled
_WHT_FLAG = "withholding_tax"


def _gate(ctx: Ctx, flag: str, what: str) -> Ctx:
    if not org_config.feature_enabled(ctx.org_id, flag):
        raise HTTPException(status_code=404,
                            detail=f"{what} is not enabled for this organisation.")
    return ctx


def _account_out(a: ba.BankAccount) -> dict:
    return {
        "id": a.id, "code": a.code, "name": a.name, "label": a.label,
        "bank_name": a.bank_name,
        # Masked, always. The full number never leaves the server.
        "account_number": a.masked,
        "project_code": a.project_code, "purpose": a.purpose,
        "entity": a.entity, "currency": a.currency, "active": a.active,
        "notes": a.notes, "updated_at": a.updated_at,
    }


# ─── bank accounts ──────────────────────────────────────────────────────────


@router.get("/accounts")
async def list_accounts(active_only: bool = Query(True),
                        ctx: Ctx = Depends(request_context)):
    _gate(ctx, _ACCOUNTS_FLAG, "Bank reconciliation")
    items = ba.list_accounts(ctx.org_id, active_only=active_only)
    return {"accounts": [_account_out(a) for a in items], "total": len(items)}


@router.post("/accounts")
async def add_account(
    code: str = Form(""),
    name: str = Form(...),
    account_number: str = Form(...),
    bank_name: str = Form(""),
    project_code: str = Form(""),
    purpose: str = Form("project"),
    currency: str = Form("NGN"),
    entity: str = Form(""),
    notes: str = Form(""),
    ctx: Ctx = Depends(request_context),
):
    """Register an account. Admin only — the register decides which payments a
    statement is reconciled against, so it is not a casual edit."""
    _gate(ctx, _ACCOUNTS_FLAG, "Bank reconciliation")
    require_role(ctx, "admin")
    try:
        acct = ba.add(ctx.org_id, code=code, name=name,
                      account_number=account_number, bank_name=bank_name,
                      project_code=project_code, purpose=purpose,
                      currency=currency, entity=entity, notes=notes)
    except ba.BankAccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _account_out(acct)


@router.get("/accounts/portfolio")
async def portfolio(period: Optional[str] = Query(None),
                    ctx: Ctx = Depends(request_context)):
    """Every account with this month's activity and whether it is reconciled.

    Twenty accounts reconciled by hand is the cost this replaces, so the honest
    measure of the feature is whether one screen shows which are done.
    """
    _gate(ctx, _ACCOUNTS_FLAG, "Bank reconciliation")
    return ba.portfolio(ctx.org_id, period)


@router.post("/accounts/identify")
async def identify(statement: UploadFile = File(...),
                   ctx: Ctx = Depends(request_context)):
    """Read the account number out of a statement's header and name the account.

    Saves a person remembering that 0459639450 is UNFPA. When the file does not
    say, it returns detected=False rather than guessing — choosing wrongly
    between twenty accounts produces a report that looks right and is not.
    """
    _gate(ctx, _ACCOUNTS_FLAG, "Bank reconciliation")
    data = await statement.read()
    if not data:
        raise HTTPException(status_code=422, detail="The statement file is empty.")
    text = data[:8192].decode("utf-8-sig", errors="replace")
    return ba.identify(ctx.org_id, text)


@router.post("/accounts/{account_id}/close")
async def close_account(account_id: str, reason: str = Form(""),
                        ctx: Ctx = Depends(request_context)):
    """Deactivate, never delete — last year's reconciliations reference it."""
    _gate(ctx, _ACCOUNTS_FLAG, "Bank reconciliation")
    require_role(ctx, "admin")
    try:
        return _account_out(ba.deactivate(ctx.org_id, account_id, reason=reason))
    except ba.BankAccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ─── withholding tax ────────────────────────────────────────────────────────


@router.get("/wht/policy")
async def get_wht_policy(ctx: Ctx = Depends(request_context)):
    _gate(ctx, _WHT_FLAG, "Withholding tax")
    p = wht.get_policy(ctx.org_id)
    out = p.model_dump()
    # Said out loud, because "no deduction" and "no rule" look identical on a
    # payslip and are very different at audit.
    out["note"] = wht.starter_rules_note()
    return out


@router.put("/wht/policy")
async def set_wht_policy(payload: dict = Body(...),
                         ctx: Ctx = Depends(request_context)):
    """Set the organisation's withholding schedule.

    DOCex ships no rates. Nigerian WHT differs by payment type and by whether
    the payee is a company or an individual, and it changes with legislation —
    a default would be a confident wrong deduction on a real invoice.
    """
    _gate(ctx, _WHT_FLAG, "Withholding tax")
    require_role(ctx, "admin")
    try:
        policy = wht.WHTPolicy.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid policy: {exc}")
    try:
        return wht.set_policy(ctx.org_id, policy).model_dump()
    except wht.WHTError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/wht/preview")
async def preview_wht(
    gross: float = Form(...),
    category: str = Form(...),
    payee_type: str = Form("company"),
    ctx: Ctx = Depends(request_context),
):
    """What would be withheld from this payment, and why.

    Shown on the requisition form before submission, so the person raising it
    sees the vendor will receive the net — rather than the vendor discovering
    it when the money lands.
    """
    _gate(ctx, _WHT_FLAG, "Withholding tax")
    return wht.compute(ctx.org_id, gross=gross, category=category,
                       payee_type=payee_type).model_dump()


@router.get("/wht/liability")
async def wht_liability(period: str = Query(...),
                        ctx: Ctx = Depends(request_context)):
    """What was withheld in a period, and therefore owed to the authority.

    Read from what was WITHHELD, not from what was remitted — the gap between
    those two is the under-remittance an auditor looks for.
    """
    _gate(ctx, _WHT_FLAG, "Withholding tax")
    return wht.liability(ctx.org_id, period)
