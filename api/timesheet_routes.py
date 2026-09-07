"""
FastAPI routes for effort reporting (timesheets).

Endpoints:
  GET  /timesheets                       — list (filter by period/staff/status)
  GET  /timesheets/mine                  — the signed-in person's own sheets
  GET  /timesheets/pending               — waiting on me to approve
  GET  /timesheets/summary               — period roll-up: is payroll safe to run
  GET  /timesheets/policy                — expected hours, tolerance, rules
  PUT  /timesheets/policy                — configure it (admin)
  POST /timesheets                       — start a sheet for a period
  GET  /timesheets/{id}                  — detail + validation issues + effort split
  PUT  /timesheets/{id}/entries          — replace the daily entries (draft only)
  POST /timesheets/{id}/submit           — employee signs and sends it
  POST /timesheets/{id}/approve          — supervisor signs it off
  POST /timesheets/{id}/return           — supervisor sends it back with a reason

WHO the actor is always comes from the bearer token, never the request body.
That matters more here than almost anywhere else: the engine refuses
self-approval of effort records, and a body-supplied "supervisor" field would
turn that control into a formality.

Route order: the literal paths (/mine, /pending, /summary, /policy) are
declared BEFORE /timesheets/{ts_id}, or FastAPI would read them as an id.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query

import org_config
import timesheets as ts
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/timesheets", tags=["timesheets"])

_FLAG = "timesheets"


def _gate(ctx: Ctx) -> Ctx:
    """Refuse politely when this client did not buy effort reporting.

    404 rather than 403: to an org without the feature, the endpoint does not
    exist. A 403 would advertise a capability they cannot use.
    """
    if not org_config.feature_enabled(ctx.org_id, _FLAG):
        raise HTTPException(
            status_code=404,
            detail="Effort reporting is not enabled for this organisation.")
    return ctx


def _fail(exc: ts.TimesheetError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


# ─── serialisers ────────────────────────────────────────────────────────────


def _entry_out(e: ts.TimeEntry) -> dict:
    # Chargeability is derived, not stored: an hour is chargeable when it
    # carries a real project code. Leave, admin and training are recorded
    # against NON_PROJECT so the total still covers 100% of paid time.
    return {"date": e.date, "hours": e.hours, "project_code": e.project_code,
            "activity": e.activity,
            "chargeable": e.project_code != ts.NON_PROJECT}


def _summary_out(t: ts.Timesheet) -> dict:
    return {
        "id": t.id,
        "staff_id": t.staff_id,
        "staff_name": t.staff_name,
        "period": t.period,
        "office": t.office,
        "status": t.status.value,
        "total_hours": t.total_hours,
        "days": len({e.date for e in t.entries}),
        "projects": sorted(t.hours_by_project().keys()),
        "submitted_by": t.submitted_by,
        "submitted_at": t.submitted_at,
        "approved_by": t.approved_by,
        "approved_at": t.approved_at,
        "returned_reason": t.returned_reason,
        "updated_at": t.updated_at,
    }


def _detail_out(org_id: str, t: ts.Timesheet) -> dict:
    issues = ts.validate(org_id, t)
    out = _summary_out(t)
    out.update({
        "entries": [_entry_out(e) for e in sorted(t.entries, key=lambda x: x.date)],
        "hours_by_project": t.hours_by_project(),
        "effort_allocation": ts.effort_allocation(t),
        # `blocking` is the distinction that matters to the person filling it
        # in: a blocking issue means the sheet cannot be submitted, a warning
        # means the supervisor should look but the sheet is still valid.
        "issues": [{"code": i.code, "blocking": i.blocking, "message": i.message}
                   for i in issues],
        "blocking": len(ts.blocking(issues)),
    })
    return out


# ─── literal paths (must precede /{ts_id}) ──────────────────────────────────


@router.get("")
async def list_sheets(
    period: Optional[str] = Query(None),
    staff_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: Ctx = Depends(request_context),
):
    _gate(ctx)
    try:
        parsed = ts.TimesheetStatus(status) if status else None
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown status '{status}'.")
    sheets = ts.list_timesheets(ctx.org_id, period=period,
                                staff_id=staff_id, status=parsed)
    return {"timesheets": [_summary_out(t) for t in sheets], "total": len(sheets)}


@router.get("/mine")
async def my_sheets(period: Optional[str] = Query(None),
                    ctx: Ctx = Depends(request_context)):
    """Everything the signed-in person has to fill in or fix."""
    _gate(ctx)
    sheets = ts.list_timesheets(ctx.org_id, period=period, staff_id=ctx.user_id)
    return {"timesheets": [_summary_out(t) for t in sheets], "total": len(sheets)}


@router.get("/pending")
async def awaiting_approval(ctx: Ctx = Depends(request_context)):
    """Submitted sheets waiting on a supervisor.

    Excludes the caller's own sheet, because they cannot approve it anyway —
    showing it in an approval queue would only invite the attempt.
    """
    _gate(ctx)
    sheets = [t for t in ts.list_timesheets(ctx.org_id,
                                            status=ts.TimesheetStatus.SUBMITTED)
              if t.staff_id != ctx.user_id]
    return {"timesheets": [_summary_out(t) for t in sheets], "total": len(sheets)}


@router.get("/summary")
async def period_summary(period: str = Query(...),
                         ctx: Ctx = Depends(request_context)):
    """Finance's pre-payroll check: is every sheet in, and signed?"""
    _gate(ctx)
    try:
        return ts.period_summary(ctx.org_id, period)
    except ts.TimesheetError as exc:
        raise _fail(exc)


@router.get("/policy")
async def get_policy(ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    return ts.get_policy(ctx.org_id).model_dump()


@router.put("/policy")
async def set_policy(payload: dict = Body(...),
                     ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    require_role(ctx, "admin")
    try:
        policy = ts.TimesheetPolicy.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid policy: {exc}")
    return ts.set_policy(ctx.org_id, policy).model_dump()


# ─── create + act ───────────────────────────────────────────────────────────


@router.post("")
async def create_sheet(
    staff_id: str = Form(""),
    period: str = Form(...),
    staff_name: str = Form(""),
    office: str = Form(""),
    entries: str = Form("[]"),
    ctx: Ctx = Depends(request_context),
):
    """Start a timesheet. Defaults to the caller — filling one in for someone
    else is an admin action, since it puts words in their mouth."""
    _gate(ctx)
    subject = (staff_id or "").strip() or ctx.user_id
    if subject != ctx.user_id:
        require_role(ctx, "admin", "approver")
    try:
        parsed = json.loads(entries or "[]")
        if not isinstance(parsed, list):
            raise ValueError("entries must be a JSON array")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid entries: {exc}")

    try:
        sheet = ts.create_timesheet(ctx.org_id, staff_id=subject, period=period,
                                    staff_name=staff_name or ctx.user.name or "",
                                    office=office, entries=parsed)
    except ts.TimesheetError as exc:
        raise _fail(exc)
    return _detail_out(ctx.org_id, sheet)


@router.get("/{ts_id}")
async def get_sheet(ts_id: str, ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    sheet = ts.get_timesheet(ctx.org_id, ts_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    return _detail_out(ctx.org_id, sheet)


@router.put("/{ts_id}/entries")
async def replace_entries(ts_id: str, entries: str = Form(...),
                          ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    try:
        parsed = json.loads(entries)
        if not isinstance(parsed, list):
            raise ValueError("entries must be a JSON array")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid entries: {exc}")
    try:
        sheet = ts.set_entries(ctx.org_id, ts_id, parsed, actor=ctx.user_id)
    except ts.TimesheetError as exc:
        raise _fail(exc)
    return _detail_out(ctx.org_id, sheet)


@router.post("/{ts_id}/submit")
async def submit(ts_id: str, ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    try:
        sheet = ts.submit(ctx.org_id, ts_id, actor=ctx.user_id)
    except ts.TimesheetError as exc:
        raise _fail(exc)
    return _detail_out(ctx.org_id, sheet)


@router.post("/{ts_id}/approve")
async def approve(ts_id: str, ctx: Ctx = Depends(request_context)):
    """Supervisor sign-off. The engine refuses self-approval; the actor comes
    from the token, so there is nothing to spoof."""
    _gate(ctx)
    require_role(ctx, "approver", "admin", "reviewer")
    try:
        sheet = ts.approve(ctx.org_id, ts_id, supervisor=ctx.user_id)
    except ts.TimesheetError as exc:
        raise _fail(exc)
    return _detail_out(ctx.org_id, sheet)


@router.post("/{ts_id}/return")
async def send_back(ts_id: str, reason: str = Form(...),
                    ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    require_role(ctx, "approver", "admin", "reviewer")
    try:
        sheet = ts.send_back(ctx.org_id, ts_id, supervisor=ctx.user_id, reason=reason)
    except ts.TimesheetError as exc:
        raise _fail(exc)
    return _detail_out(ctx.org_id, sheet)
