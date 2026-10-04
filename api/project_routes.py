"""
Projects & grants — the budget, what has gone out, what is promised, what is
left. Figures come from projects.py, computed from the records each time.

Who:
  read    approvers (budget holders need to see their grants), Finance, admins
  change  Finance approvers and admins: a budget is a financial record

Feature flag: `projects`. Off, the area does not exist (404).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

import grants
import org_config
import projects
from .context import Ctx, request_context

router = APIRouter(prefix="/projects", tags=["projects"])


def _gate(ctx: Ctx) -> None:
    if not org_config.feature_enabled(ctx.org_id, "projects"):
        raise HTTPException(status_code=404, detail="Not Found")


def _is_finance(ctx: Ctx) -> bool:
    import payment_voucher
    return (ctx.department or "").lower() in payment_voucher.schedule_departments(ctx.org_id)


def _may_read(ctx: Ctx) -> None:
    _gate(ctx)
    if not (ctx.role in ("admin", "approver") or _is_finance(ctx)):
        raise HTTPException(status_code=403,
                            detail="Grant budgets are visible to approvers and Finance.")


def _may_write(ctx: Ctx) -> None:
    _gate(ctx)
    if not (ctx.role == "admin" or (ctx.role == "approver" and _is_finance(ctx))):
        raise HTTPException(status_code=403,
                            detail="Only a Finance approver or an administrator can change a project's budget.")


def _find(ctx: Ctx, code: str) -> grants.Agreement:
    ag = grants.find_agreement(ctx.org_id, code)
    if ag is None:
        raise HTTPException(status_code=404, detail=f"No project with the code {code}.")
    return ag


_FIELDS = ("donor", "project_code", "title", "value", "currency", "signed_date", "start_date",
           "end_date", "document_ref", "status", "budget_lines", "staff")


def _clean(body: dict, *, creating: bool) -> dict:
    out = {k: body[k] for k in _FIELDS if k in body}
    if not creating:
        out.pop("project_code", None)
    for k in ("signed_date", "start_date", "end_date", "document_ref"):
        if k in out and not out[k]:
            out[k] = None
    if "value" in out:
        try:
            out["value"] = round(float(out["value"] or 0), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="The budget must be a number.")
    if "budget_lines" in out:
        out["budget_lines"] = [grants.BudgetLine(**bl) for bl in out["budget_lines"] or []]
    if "staff" in out:
        out["staff"] = [grants.PlannedStaff(**st) for st in out["staff"] or []]
    if out.get("status") and out["status"] not in ("active", "closed", "suspended"):
        raise HTTPException(status_code=422, detail="Status is active, closed or suspended.")
    return out


@router.get("")
async def list_projects(ctx: Ctx = Depends(request_context)):
    _may_read(ctx)
    return {"projects": [f.model_dump() for f in projects.all_figures(ctx.org_id)],
            "can_edit": ctx.role == "admin" or (ctx.role == "approver" and _is_finance(ctx))}


@router.post("")
async def create_project(body: dict = Body(...), ctx: Ctx = Depends(request_context)):
    _may_write(ctx)
    try:
        ag = grants.create_agreement(ctx.org_id, **_clean(body, creating=True))
    except (grants.AgreementError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"agreement": ag.model_dump(), "figures": projects.figures(ctx.org_id, ag).model_dump()}


@router.get("/lookup/{code}")
async def lookup(code: str, ctx: Ctx = Depends(request_context)):
    """For the request form: does this code name a project, and what are its
    budget lines? Names only — no money — so anyone raising a request can
    pick the right line without seeing the grant's finances."""
    _gate(ctx)
    ag = grants.find_agreement(ctx.org_id, code)
    if ag is None:
        return {"found": False}
    return {"found": True, "project_code": ag.project_code, "donor": ag.donor, "title": ag.title,
            "status": ag.status,
            "budget_lines": [{"code": bl.code, "label": bl.label} for bl in ag.budget_lines]}


@router.get("/{code}")
async def get_project(code: str, date_from: str = Query(""), date_to: str = Query(""),
                      ctx: Ctx = Depends(request_context)):
    _may_read(ctx)
    ag = _find(ctx, code)
    return {
        "agreement": ag.model_dump(),
        "figures": projects.figures(ctx.org_id, ag).model_dump(),
        "payments": projects.payments(ctx.org_id, ag, date_from=date_from, date_to=date_to),
        "exceptions": projects.exceptions(ctx.org_id, ag, date_from=date_from, date_to=date_to),
        "approved_time": projects.approved_time(ctx.org_id, ag, period_from=date_from[:7],
                                                period_to=date_to[:7]),
        "salary": projects.salary_charged(ctx.org_id, ag, period_from=date_from[:7],
                                          period_to=date_to[:7]),
        "can_edit": ctx.role == "admin" or (ctx.role == "approver" and _is_finance(ctx)),
    }


@router.put("/{code}")
async def update_project(code: str, body: dict = Body(...), ctx: Ctx = Depends(request_context)):
    _may_write(ctx)
    ag = _find(ctx, code)
    try:
        ag = grants.update_agreement(ctx.org_id, ag.id, **_clean(body, creating=False))
    except (grants.AgreementError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"agreement": ag.model_dump(), "figures": projects.figures(ctx.org_id, ag).model_dump()}


@router.get("/{code}/report.pdf")
async def donor_report(code: str, date_from: str = Query(""), date_to: str = Query(""),
                       ctx: Ctx = Depends(request_context)):
    """The one-click donor report: budget against actual, approved staff
    time, salaries, payments with vouchers, exceptions with reasons."""
    _may_read(ctx)
    ag = _find(ctx, code)
    for d in (date_from, date_to):
        if d and len(d) != 10:
            raise HTTPException(status_code=422, detail="Dates are YYYY-MM-DD.")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=422, detail="The end date is before the start date.")
    import donor_report as dr
    pdf = dr.build(ctx.org_id, ag, date_from=date_from, date_to=date_to, generated_by=ctx.user_id)
    import attachments
    name = f"{ag.project_code}-donor-report-{date_from or 'start'}-to-{date_to or 'date'}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": attachments.content_disposition(name)})
