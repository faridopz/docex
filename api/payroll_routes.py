"""
FastAPI routes for payroll.

Endpoints:
  GET  /payroll/staff                    — the staff register
  POST /payroll/staff                    — add someone (admin)
  GET  /payroll/policy                   — deduction rules + refinancing sign
  PUT  /payroll/policy                   — configure them (admin)
  GET  /payroll/runs                     — every run, newest first
  POST /payroll/runs                     — build a month (does not pay anything)
  GET  /payroll/runs/{id}                — full run: lines, allocations, flags
  POST /payroll/runs/{id}/submit         — open the approval transaction
  POST /payroll/runs/{id}/paid           — record payment of an APPROVED run

Building a run computes; it never pays. Payment follows the same role-gated
approval path as every other payment in DOCex, which is why /submit hands the
run to `transactions` rather than doing anything itself.

Two things this API is careful to surface rather than hide:

  * `effort_verified` — whether the salary split came from approved timesheets
    or from budgeted percentages. Charging a grant on a budget is the most
    common audit finding in donor-funded payroll, so it is on the run summary,
    not buried in a line.
  * `flags` vs `notes` — flags are defects and block submission; notes are
    disclosures and do not. The client sees both, labelled differently.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query

import org_config
import payroll
from .context import Ctx, request_context, require_role

router = APIRouter(prefix="/payroll", tags=["payroll"])

_FLAG = "payroll"


def _gate(ctx: Ctx) -> Ctx:
    if not org_config.feature_enabled(ctx.org_id, _FLAG):
        raise HTTPException(
            status_code=404,
            detail="Payroll is not enabled for this organisation.")
    return ctx


# ─── serialisers ────────────────────────────────────────────────────────────


def _line_out(l: payroll.PayrollLine) -> dict:
    return {
        "staff_id": l.staff_id,
        "name": l.name,
        "gross": l.gross,
        "deductions": [{"code": d.code, "name": d.name, "amount": d.amount}
                       for d in l.deductions],
        # Employee deductions come out of gross to reach net; employer
        # contributions sit on top of it. Collapsing them into one
        # "deductions" number is how payslips end up wrong, so both are sent.
        "total_employee_deductions": l.total_employee_deductions,
        "total_employer_contributions": l.total_employer_contributions,
        "net": l.net,
        "employer_cost": l.employer_cost,
        "refinancing": l.refinancing,
        "allocations": [{"project_code": a.project_code, "donor": a.donor,
                         "percent": a.percent} for a in l.allocations],
        # How we know this split is right — the whole point of the timesheet link.
        "allocation_source": l.allocation_source,
        "timesheet_id": l.timesheet_id,
        "hours_worked": l.hours_worked,
        "flags": l.flags,      # defects — block approval
        "notes": l.notes,      # disclosures — do not block
    }


def _run_summary(r: payroll.PayrollRun) -> dict:
    return {
        "id": r.id,
        "period": r.period,
        "status": r.status,
        "staff_count": r.staff_count,
        "total_gross": r.total_gross,
        "total_net": r.total_net,
        "total_deductions": r.total_deductions,
        "total_employer_cost": r.total_employer_cost,
        "total_refinancing": r.total_refinancing,
        "currency": r.currency,
        "lines_from_timesheet": r.lines_from_timesheet,
        "lines_from_budget": r.lines_from_budget,
        "effort_verified": r.effort_verified,
        "flags": r.flags,
        "txn_id": r.txn_id,
        "txn_ref": r.txn_ref,
        "created_at": r.created_at,
    }


def _run_detail(r: payroll.PayrollRun) -> dict:
    out = _run_summary(r)
    out.update({
        "lines": [_line_out(l) for l in r.lines],
        "by_project": r.by_project,
        "by_donor": r.by_donor,
        "beneficiaries_direct": getattr(r, "beneficiaries_direct", 0),
        "beneficiaries_indirect": getattr(r, "beneficiaries_indirect", 0),
    })
    return out


# ─── staff + policy ─────────────────────────────────────────────────────────


@router.get("/staff")
async def list_staff(active_only: bool = Query(True),
                     ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    people = payroll.list_staff(ctx.org_id, active_only=active_only)
    return {"staff": [s.model_dump() for s in people], "total": len(people)}


@router.post("/staff")
async def add_staff(payload: dict = Body(...), ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    require_role(ctx, "admin")
    try:
        return payroll.add_staff(ctx.org_id, **payload).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid staff record: {exc}")


@router.get("/policy")
async def get_policy(ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    return payroll.get_policy(ctx.org_id).model_dump()


@router.put("/policy")
async def set_policy(payload: dict = Body(...), ctx: Ctx = Depends(request_context)):
    """Deduction rules are configuration, never code.

    DOCex ships no PAYE bands: they change with legislation and vary by scheme,
    and inventing them would produce confident, wrong payslips.
    """
    _gate(ctx)
    require_role(ctx, "admin")
    try:
        policy = payroll.PayrollPolicy.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid policy: {exc}")
    return payroll.set_policy(ctx.org_id, policy).model_dump()


# ─── runs ───────────────────────────────────────────────────────────────────


@router.get("/runs")
async def list_runs(ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    runs = payroll.list_runs(ctx.org_id)
    return {"runs": [_run_summary(r) for r in runs], "total": len(runs)}


@router.post("/runs")
async def build_run(
    period: str = Form(...),
    beneficiaries_direct: int = Form(0),
    beneficiaries_indirect: int = Form(0),
    use_timesheets: bool = Form(True),
    ctx: Ctx = Depends(request_context),
):
    """Compute the month. Nothing is paid and nothing is approved by this call."""
    _gate(ctx)
    require_role(ctx, "admin", "approver", "reviewer")
    try:
        run = payroll.build_run(
            ctx.org_id, period,
            beneficiaries_direct=beneficiaries_direct,
            beneficiaries_indirect=beneficiaries_indirect,
            use_timesheets=use_timesheets)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _run_detail(run)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, ctx: Ctx = Depends(request_context)):
    _gate(ctx)
    run = payroll.get_run(ctx.org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found.")
    return _run_detail(run)


@router.post("/runs/{run_id}/submit")
async def submit_run(run_id: str, ctx: Ctx = Depends(request_context)):
    """Hand the run to the approval workflow. Refused while any line has a
    defect — a disclosure alone does not block."""
    _gate(ctx)
    require_role(ctx, "admin", "approver", "reviewer")
    try:
        run = payroll.submit_for_approval(ctx.org_id, run_id, created_by=ctx.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _run_detail(run)


@router.post("/runs/{run_id}/paid")
async def mark_paid(run_id: str, ctx: Ctx = Depends(request_context)):
    """Record payment. Refused unless the linked transaction actually reached
    'paid' — the gate is the state machine, not this endpoint."""
    _gate(ctx)
    require_role(ctx, "admin", "approver")
    try:
        run = payroll.mark_paid(ctx.org_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _run_detail(run)
