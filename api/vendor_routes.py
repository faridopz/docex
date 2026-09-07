"""
FastAPI routes for the vendor register.

Endpoints:
  GET  /vendors                     — the register
  GET  /vendors/summary             — how much of it is verified
  POST /vendors                     — add a vendor (TIN format-checked on entry)
  POST /vendors/check-tin           — format-check a TIN without saving anything
  GET  /vendors/{id}                — one vendor with both checks
  POST /vendors/{id}/verify         — run the bank + tax checks
  POST /vendors/{id}/block          — stop payments, with a written reason
  POST /vendors/{id}/unblock        — release

The response is careful about one word. A tax ID that passed a FORMAT check is
never described as "verified": `tin_externally_verified` is a separate boolean,
false unless a provider actually confirmed it. An auditor asking "did you
verify their TIN" must not get a yes from a regular expression.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query

import org_config
import vendors as vd
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/vendors", tags=["vendors"])

_FLAG = "vendor_register"


def _gate(ctx: Ctx) -> Ctx:
    if not org_config.feature_enabled(ctx.org_id, _FLAG):
        raise HTTPException(
            status_code=404,
            detail="The vendor register is not enabled for this organisation.")
    return ctx


def _fail(exc: vd.VendorError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _out(v: vd.Vendor) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "trading_name": v.trading_name,
        "tin": v.tin,
        "email": v.email,
        "phone": v.phone,
        "category": v.category,
        "active": v.active,
        "blocked": v.blocked,
        "blocked_reason": v.blocked_reason,
        "bank": {
            "status": v.bank.status.value,
            "account_number": v.bank.account_number,
            "bank_code": v.bank.bank_code,
            "bank_name": v.bank.bank_name,
            "resolved_name": v.bank.resolved_name,
            "match_score": v.bank.match_score,
            "checked_at": v.bank.checked_at,
            "message": v.bank.message,
        },
        "tax": {
            "status": v.tax.status.value,
            "method": v.tax.method,
            "checked_at": v.tax.checked_at,
            "message": v.tax.message,
            # The distinction the whole module exists to protect. A format
            # check is not a confirmation, and this boolean is the only thing
            # a caller should treat as one.
            "externally_verified": v.tax.externally_verified,
        },
        "payment_ready": v.payment_ready,
        "fully_verified": v.fully_verified,
        "updated_at": v.updated_at,
    }


@router.get("")
async def list_vendors(active_only: bool = Query(False),
                       ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    items = vd.list_vendors(ctx.org_id, active_only=active_only)
    return {"vendors": [_out(v) for v in items], "total": len(items)}


@router.get("/summary")
async def summary(ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    return vd.register_summary(ctx.org_id)


@router.post("/check-tin")
async def check_tin(tin: str = Form(...), ctx: Ctx = Depends(request_context)):
    """Format-check a tax ID without creating anything — useful while typing."""
    _gate(ctx)
    result = vd.check_tin_format(tin)
    return {"status": result.status.value, "tin": result.tin,
            "message": result.message,
            "externally_verified": result.externally_verified,
            "lookup_configured": vd.tin_lookup_available()}


@router.post("")
async def create_vendor(
    name: str = Form(...),
    tin: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    category: str = Form(""),
    ctx: Ctx = Depends(request_context),
):
    _gate(ctx)
    require_role(ctx, "admin", "approver", "reviewer")
    try:
        v = vd.create(ctx.org_id, name=name, tin=tin, email=email, phone=phone,
                      address=address, category=category,
                      created_by=ctx.user_id)
    except vd.VendorError as exc:
        raise _fail(exc)
    return _out(v)


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: str, ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    v = vd.get(ctx.org_id, vendor_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return _out(v)


@router.post("/{vendor_id}/verify")
async def verify(
    vendor_id: str,
    account_number: str = Form(""),
    bank_code: str = Form(""),
    bank_name: str = Form(""),
    ctx: Ctx = Depends(request_context),
):
    """Ask the bank who owns the account, and re-check the tax ID.

    The bank check is the one that catches a diverted payment: a real invoice
    from a real supplier with the account number altered passes every other
    control in the system, and fails this one.
    """
    _gate(ctx)
    require_role(ctx, "admin", "approver", "reviewer")
    try:
        v = vd.run_checks(ctx.org_id, vendor_id, account_number=account_number,
                          bank_code=bank_code, bank_name=bank_name,
                          checked_by=ctx.user_id)
    except vd.VendorError as exc:
        raise _fail(exc)
    return _out(v)


@router.post("/{vendor_id}/block")
async def block(vendor_id: str, reason: str = Form(...),
                ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    require_role(ctx, "admin", "approver")
    try:
        return _out(vd.block(ctx.org_id, vendor_id, reason=reason,
                             actor=ctx.user_id))
    except vd.VendorError as exc:
        raise _fail(exc)


@router.post("/{vendor_id}/unblock")
async def unblock(vendor_id: str, ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    require_role(ctx, "admin", "approver")
    try:
        return _out(vd.unblock(ctx.org_id, vendor_id))
    except vd.VendorError as exc:
        raise _fail(exc)
