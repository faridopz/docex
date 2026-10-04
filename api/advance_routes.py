"""
FastAPI routes for advance retirement.

  GET  /advances                  — the register
  GET  /advances/aging            — what finance chases this morning
  GET  /advances/policy           — the org's retirement window and ladder
  PUT  /advances/policy           — set it (admin)
  POST /advances                  — record an advance and start its clock
  GET  /advances/{id}             — one advance
  POST /advances/{id}/retire      — settle it against what was spent
  POST /advances/{id}/recover     — record recovery from salary
  POST /advances/{id}/write-off   — accept the loss, with a written reason
  GET  /advances/block            — is this person or project barred right now?

The aging list is the screen that matters. Not a month-end report — the list of
people to chase today, which is the only form in which this information changes
anyone's behaviour.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query

import advances as adv
import org_config
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/advances", tags=["advances"])

_FLAG = "advance_retirement"


def _gate(ctx: Ctx) -> Ctx:
    if not org_config.feature_enabled(ctx.org_id, _FLAG):
        raise HTTPException(
            status_code=404,
            detail="Advance retirement is not enabled for this organisation.")
    return ctx


def _handles_money(ctx: Ctx) -> bool:
    """Admins and the org's own finance departments (the same rule that
    guards bank details) see every advance and settle them. Everyone else
    sees their own and settles none — declaring your own advance spent is
    exactly the control this exists to provide."""
    import payment_voucher
    return ctx.role == "admin" or (ctx.department or "").lower() in payment_voucher.schedule_departments(ctx.org_id)


def _settler(ctx: Ctx, advance_id: str) -> adv.Advance:
    """Only someone who handles money, and never on their own advance."""
    if not _handles_money(ctx):
        raise HTTPException(status_code=403, detail="Only Finance can settle an advance.")
    a = adv.get(ctx.org_id, advance_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Advance not found.")
    if a.staff_id.strip().lower() == (ctx.user_id or "").strip().lower():
        raise HTTPException(status_code=403,
                            detail="You cannot settle your own advance — someone else in Finance must.")
    return a


def _fail(exc: adv.AdvanceError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _out(a: adv.Advance) -> dict:
    return {
        "id": a.id, "ref": a.ref,
        "staff_id": a.staff_id, "staff_name": a.staff_name,
        "department": a.department,
        "amount": a.amount, "currency": a.currency, "purpose": a.purpose,
        "project_code": a.project_code, "grant_code": a.grant_code,
        "source_ref": a.source_ref,
        "issued_at": a.issued_at, "activity_end": a.activity_end,
        "due_at": a.due_at, "days_overdue": adv.days_overdue(a),
        "status": a.status.value,
        "retired_at": a.retired_at, "retired_by": a.retired_by,
        "spent": a.spent, "balance": a.balance, "direction": a.direction,
        "receipt_ids": a.receipt_ids, "notes": a.notes,
    }


@router.get("")
async def list_advances(staff_id: Optional[str] = Query(None),
                        project_code: Optional[str] = Query(None),
                        open_only: bool = Query(False),
                        ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    if not _handles_money(ctx):
        staff_id = ctx.user_id          # staff see their own, whatever they ask for
    items = adv.list_advances(ctx.org_id, staff_id=staff_id,
                              project_code=project_code, open_only=open_only)
    return {"advances": [_out(a) for a in items], "total": len(items)}


@router.get("/aging")
async def aging(ctx: Ctx = Depends(request_context)):
    """Every outstanding advance, worst first, with the consequence spelled out.
    Staff get the same list narrowed to their own."""
    _gate(ctx)
    result = adv.aging(ctx.org_id)
    result["sees_everyone"] = _handles_money(ctx)
    if not result["sees_everyone"]:
        me = (ctx.user_id or "").lower()
        rows = [r for r in result["rows"] if (r["staff_id"] or "").lower() == me]
        overdue = [r for r in rows if r["days_overdue"] >= 0]
        result.update(
            rows=rows, outstanding=len(rows),
            outstanding_value=round(sum(r["amount"] for r in rows), 2),
            overdue=len(overdue), overdue_value=round(sum(r["amount"] for r in overdue), 2),
            blocked_staff=[s for s in result["blocked_staff"] if s.lower() == me],
            for_recovery=[r for r in result["for_recovery"] if (r["staff_id"] or "").lower() == me])
    return result


@router.get("/block")
async def check_block(staff_id: str = Query(""), project_code: str = Query(""),
                      ctx: Ctx = Depends(request_context)):
    """Is this person or project barred from payment right now?

    Your own status is yours to check; anyone else's is Finance's business
    (30 Sep audit, L3: any user could learn a colleague's overdue amount)."""
    _gate(ctx)
    asking_about_other = staff_id and staff_id.strip().lower() != (ctx.user_id or "").lower()
    if (asking_about_other or (project_code and not staff_id)) and not _handles_money(ctx):
        staff_id, project_code = ctx.user_id, ""
    result = adv.payment_block(ctx.org_id, staff_id=staff_id,
                               project_code=project_code)
    return result or {"blocked": False}


@router.get("/policy")
async def get_policy(ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    return adv.get_policy(ctx.org_id).model_dump()


@router.put("/policy")
async def set_policy(payload: dict = Body(...),
                     ctx: Ctx = Depends(request_context)):
    """The window and the ladder. Every number is the client's own.

    NEEM says 7 days or 5 working days with a three-stage consequence. EVA's
    policy states the requirement but names no window at all — a gap in their
    policy, which stays visible rather than being filled with a guess.
    """
    _gate(ctx)
    require_role(ctx, "admin")
    try:
        policy = adv.AdvancePolicy.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid policy: {exc}")
    try:
        return adv.set_policy(ctx.org_id, policy).model_dump()
    except adv.AdvanceError as exc:
        raise _fail(exc)


@router.post("")
async def issue(
    staff_id: str = Form(...),
    amount: float = Form(...),
    purpose: str = Form(...),
    staff_name: str = Form(""),
    department: str = Form(""),
    project_code: str = Form(""),
    grant_code: str = Form(""),
    source_ref: str = Form(""),
    issued_at: str = Form(""),
    activity_end: str = Form(""),
    ctx: Ctx = Depends(request_context),
):
    """Record an advance and start its clock.

    `activity_end` moves the clock to the end of a trip — the correct reading
    for DSA, which cannot be retired before the trip has happened.
    """
    _gate(ctx)
    if not _handles_money(ctx):
        raise HTTPException(status_code=403, detail="Only Finance can record an advance by hand.")
    try:
        a = adv.issue(ctx.org_id, staff_id=staff_id, amount=amount,
                      purpose=purpose, staff_name=staff_name,
                      department=department, project_code=project_code,
                      grant_code=grant_code or None, source_ref=source_ref,
                      issued_at=issued_at, activity_end=activity_end)
    except adv.AdvanceError as exc:
        raise _fail(exc)
    return _out(a)


@router.get("/{advance_id}")
async def get_advance(advance_id: str, ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    a = adv.get(ctx.org_id, advance_id)
    if a is None or (not _handles_money(ctx)
                     and a.staff_id.strip().lower() != (ctx.user_id or "").strip().lower()):
        raise HTTPException(status_code=404, detail="Advance not found.")
    return _out(a)


@router.post("/{advance_id}/retire")
async def retire(advance_id: str, spent: float = Form(...),
                 receipt_ids: str = Form(""), note: str = Form(""),
                 ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    _settler(ctx, advance_id)
    ids = [r.strip() for r in receipt_ids.split(",") if r.strip()]
    try:
        return _out(adv.retire(ctx.org_id, advance_id, spent=spent,
                               actor=ctx.user_id, receipt_ids=ids, note=note))
    except adv.AdvanceError as exc:
        raise _fail(exc)


@router.post("/{advance_id}/recover")
async def recover(advance_id: str, reason: str = Form(""),
                  ctx: Ctx = Depends(request_context)):
    """Record that an unretired advance was recovered from salary — the last
    rung of the ladder, and its own fact rather than a kind of 'retired'."""
    _gate(ctx)
    require_role(ctx, "admin", "approver")
    _settler(ctx, advance_id)
    try:
        return _out(adv.mark_recovered(ctx.org_id, advance_id,
                                       actor=ctx.user_id, reason=reason))
    except adv.AdvanceError as exc:
        raise _fail(exc)


@router.post("/{advance_id}/write-off")
async def write_off(advance_id: str, reason: str = Form(...),
                    ctx: Ctx = Depends(request_context)):
    """Accept the loss. The organisation is absorbing money it cannot account
    for — that should be possible, and never quiet."""
    _gate(ctx)
    require_role(ctx, "admin")
    _settler(ctx, advance_id)
    try:
        return _out(adv.write_off(ctx.org_id, advance_id,
                                  actor=ctx.user_id, reason=reason))
    except adv.AdvanceError as exc:
        raise _fail(exc)
