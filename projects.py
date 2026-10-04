"""
Projects & grants: what each donor-funded project has, has spent, and has left.

Nothing here is stored. Every figure is computed, each time, from the records
that already prove it:

    paid       frozen payment records (requisitions.TransactionRecord) charged
               to the project
    salary     payroll runs that have been paid, by each person's project split
    committed  requests approved or still in review, not yet paid — plus
               payroll runs submitted but not yet paid
    remaining  budget − paid − salary − committed

A payment belongs to a project when its grant code names the project, or,
with no grant code, its project code does. A request that itemises by budget
line is charged line by line; anything else is shown as "not assigned to a
line" rather than guessed into one.

Why computed rather than kept as running totals: a running total drifts the
first time something is edited outside the happy path, and then nobody can
say which number is right. A competitor demoed "6429.8% of budget used";
every figure here can be traced to the payments, salaries and requests
behind it, and the API returns those records alongside the totals.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field

import grants
import store

UNASSIGNED = "__unassigned__"

# Requests still heading for payment. A draft is not yet a request; returned
# is back with its author; declined is dead.
_COMMITTED_STATUSES = {"submitted", "in_review", "on_hold", "approved"}


def _money(x: float) -> float:
    return round(float(x or 0.0), 2)


def _status(x) -> str:
    return str(getattr(x, "value", x) or "")


# ─── which project is this charged to? ─────────────────────────────────────


def charge_code(codes: set[str], grant_code: Optional[str], project_code: Optional[str]) -> str:
    """The project (lower-cased code) a payment is charged to, or ''.
    The grant code wins when it names a project; it is the more specific of
    the two fields on a request."""
    g = (grant_code or "").strip().lower()
    if g and g in codes:
        return g
    p = (project_code or "").strip().lower()
    return p if p in codes else ""


def _line_key(ag: grants.Agreement, label: str) -> str:
    want = (label or "").strip().lower()
    if not want:
        return UNASSIGNED
    for bl in ag.budget_lines:
        if want in ((bl.code or "").strip().lower(), (bl.label or "").strip().lower()):
            return bl.code
    return UNASSIGNED


def split_by_line(ag: grants.Agreement, amount: float, budget_lines) -> dict[str, float]:
    """How a request's amount falls across the project's budget lines.
    Lines the request names go to those lines; the rest is unassigned."""
    out: dict[str, float] = {}
    assigned = 0.0
    for bl in budget_lines or []:
        total = _money(getattr(bl, "line_total", 0.0))
        if total <= 0:
            continue
        key = _line_key(ag, getattr(bl, "budget_line", ""))
        out[key] = _money(out.get(key, 0.0) + total)
        assigned += total
    rest = _money(amount - assigned)
    if rest > 0.005:
        out[UNASSIGNED] = _money(out.get(UNASSIGNED, 0.0) + rest)
    return out


# ─── the figures ───────────────────────────────────────────────────────────


class LineFigures(BaseModel):
    code: str
    label: str = ""
    budget: float = 0.0
    paid: float = 0.0
    committed: float = 0.0
    remaining: Optional[float] = None       # None for "not assigned"


class ProjectFigures(BaseModel):
    agreement_id: str
    project_code: str
    donor: str
    title: str = ""
    currency: str = "NGN"
    status: str = "active"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: float = 0.0
    paid: float = 0.0
    salary: float = 0.0
    committed: float = 0.0
    remaining: float = 0.0
    used_percent: Optional[float] = None    # (paid + salary) / budget
    lines: list[LineFigures] = Field(default_factory=list)
    payments_count: int = 0
    open_requests_count: int = 0
    other_currency: list[str] = Field(default_factory=list)


def _load(org: str):
    import requisitions as rq
    txns = rq.list_transactions(org)
    reqs = rq.list_requisitions(org)
    try:
        import payroll
        runs = payroll.list_runs(org)
    except Exception:
        runs = []
    return txns, reqs, runs


def figures(org_id: str, ag: grants.Agreement, *, exclude_request_id: str = "",
            _cache=None) -> ProjectFigures:
    org = store.require_org(org_id)
    txns, reqs, runs = _cache or _load(org)
    codes = {(a.project_code or "").strip().lower() for a in grants.list_agreements(org)}
    me = (ag.project_code or "").strip().lower()
    req_by_id = {r.id: r for r in reqs}

    lines: dict[str, LineFigures] = {
        bl.code: LineFigures(code=bl.code, label=bl.label, budget=_money(bl.amount))
        for bl in ag.budget_lines}
    lines[UNASSIGNED] = LineFigures(code=UNASSIGNED, label="Not assigned to a budget line")
    other_ccy: set[str] = set()

    paid = 0.0
    n_paid = 0
    for t in txns:
        if charge_code(codes, t.grant_code, t.project_code) != me:
            continue
        if (t.currency or ag.currency) != ag.currency:
            other_ccy.add(t.currency)
            continue
        n_paid += 1
        paid += t.amount
        src = req_by_id.get(t.requisition_id)
        for key, amt in split_by_line(ag, t.amount, src.budget_lines if src else []).items():
            lines[key].paid = _money(lines[key].paid + amt)

    committed = 0.0
    n_open = 0
    for r in reqs:
        if r.id == exclude_request_id or _status(r.status) not in _COMMITTED_STATUSES:
            continue
        if charge_code(codes, r.grant_code, r.project_code) != me:
            continue
        if (r.currency or ag.currency) != ag.currency:
            other_ccy.add(r.currency)
            continue
        n_open += 1
        committed += r.amount
        for key, amt in split_by_line(ag, r.amount, r.budget_lines).items():
            lines[key].committed = _money(lines[key].committed + amt)

    salary = 0.0
    for run in runs:
        share = 0.0
        for code, amt in (run.by_project or {}).items():
            if (code or "").strip().lower() == me:
                share += amt
        if not share:
            continue
        if run.status == "paid":
            salary += share
        elif run.status == "submitted":
            committed += share

    budget = _money(ag.value)
    out_lines = []
    for key, lf in lines.items():
        if key == UNASSIGNED:
            if lf.paid or lf.committed:
                out_lines.append(lf)
            continue
        lf.remaining = _money(lf.budget - lf.paid - lf.committed)
        out_lines.append(lf)

    return ProjectFigures(
        agreement_id=ag.id, project_code=ag.project_code, donor=ag.donor, title=ag.title,
        currency=ag.currency, status=ag.status, start_date=ag.start_date, end_date=ag.end_date,
        budget=budget, paid=_money(paid), salary=_money(salary), committed=_money(committed),
        remaining=_money(budget - paid - salary - committed),
        used_percent=(round((paid + salary) / budget * 100, 1) if budget > 0 else None),
        lines=out_lines, payments_count=n_paid, open_requests_count=n_open,
        other_currency=sorted(other_ccy),
    )


def all_figures(org_id: str) -> list[ProjectFigures]:
    org = store.require_org(org_id)
    cache = _load(org)
    return sorted((figures(org, ag, _cache=cache) for ag in grants.list_agreements(org)),
                  key=lambda f: (f.status != "active", f.project_code.lower()))


# ─── the records behind the figures ────────────────────────────────────────


def _in_window(iso: str, date_from: str, date_to: str) -> bool:
    d = (iso or "")[:10]
    return bool(d) and (not date_from or d >= date_from) and (not date_to or d <= date_to)


def payments(org_id: str, ag: grants.Agreement, *, date_from: str = "", date_to: str = "") -> list[dict]:
    """Every payment charged to the project, with the voucher number Finance
    already issued (never allocates a new one) and masked bank numbers."""
    import requisitions as rq
    org = store.require_org(org_id)
    codes = {(a.project_code or "").strip().lower() for a in grants.list_agreements(org)}
    me = (ag.project_code or "").strip().lower()
    st = store.get_store()
    out = []
    for t in rq.list_transactions(org):
        if charge_code(codes, t.grant_code, t.project_code) != me:
            continue
        if not _in_window(t.paid_at, date_from, date_to):
            continue
        pv = (st.get(org, "voucher_numbers", t.requisition_id) or {}).get("pv_number", "")
        out.append({
            "transaction_id": t.id, "requisition_id": t.requisition_id,
            "requisition_ref": t.requisition_ref, "paid_at": t.paid_at[:10],
            "payee": t.vendor_name, "category": t.category, "amount": _money(t.amount),
            "currency": t.currency, "voucher_number": pv, "bank_reference": t.bank_reference,
            "exceptions": t.exceptions_count,
        })
    return sorted(out, key=lambda p: (p["paid_at"], p["requisition_ref"]))


def exceptions(org_id: str, ag: grants.Agreement, *, date_from: str = "", date_to: str = "") -> list[dict]:
    """Every policy check that was released on a payment to this project, with
    the reason and who released it — read from the frozen payment record, so
    it is what applied at the time, not today's policy."""
    import requisitions as rq
    org = store.require_org(org_id)
    codes = {(a.project_code or "").strip().lower() for a in grants.list_agreements(org)}
    me = (ag.project_code or "").strip().lower()
    out = []
    for t in rq.list_transactions(org):
        if charge_code(codes, t.grant_code, t.project_code) != me or not _in_window(t.paid_at, date_from, date_to):
            continue
        for c in t.checks:
            if c.overridden:
                out.append({"requisition_ref": t.requisition_ref, "paid_at": t.paid_at[:10],
                            "payee": t.vendor_name, "amount": _money(t.amount),
                            "check": c.name, "message": c.message,
                            "reason": c.override_reason or "", "released_by": c.override_by or "",
                            "authority": c.override_authority or ""})
    return sorted(out, key=lambda e: (e["paid_at"], e["requisition_ref"]))


def approved_time(org_id: str, ag: grants.Agreement, *, period_from: str = "", period_to: str = "") -> list[dict]:
    """The per-project log of approved staff time: one row per person per
    period, from timesheets a supervisor signed. Nothing unapproved."""
    try:
        import timesheets as ts
    except ImportError:  # pragma: no cover
        return []
    org = store.require_org(org_id)
    me = (ag.project_code or "").strip().lower()
    out = []
    for sheet in ts.list_timesheets(org):
        if sheet.status not in (ts.TimesheetStatus.APPROVED, ts.TimesheetStatus.PROCESSED):
            continue
        if (period_from and sheet.period < period_from) or (period_to and sheet.period > period_to):
            continue
        hours = sum(e.hours for e in sheet.entries if (e.project_code or "").strip().lower() == me)
        if hours <= 0:
            continue
        out.append({"timesheet_id": sheet.id, "staff_id": sheet.staff_id,
                    "staff_name": sheet.staff_name or sheet.staff_id, "period": sheet.period,
                    "hours": round(hours, 2), "total_hours": sheet.total_hours,
                    "share_percent": round(hours / sheet.total_hours * 100, 1) if sheet.total_hours else 0.0,
                    "approved_by": sheet.approved_by, "approved_at": (sheet.approved_at or "")[:10]})
    return sorted(out, key=lambda r: (r["period"], r["staff_name"].lower()))


def salary_charged(org_id: str, ag: grants.Agreement, *, period_from: str = "", period_to: str = "") -> list[dict]:
    """Salary charged to the project from paid payroll runs: one row per
    person per month, saying whether the split came from approved hours or
    from the budget (an auditor asks exactly that)."""
    try:
        import payroll
    except ImportError:  # pragma: no cover
        return []
    org = store.require_org(org_id)
    me = (ag.project_code or "").strip().lower()
    out = []
    for run in payroll.list_runs(org):
        if run.status != "paid":
            continue
        if (period_from and run.period < period_from) or (period_to and run.period > period_to):
            continue
        for line in run.lines:
            pct = sum(a.percent for a in line.allocations if (a.project_code or "").strip().lower() == me)
            if pct <= 0:
                continue
            out.append({"period": run.period, "staff_id": line.staff_id, "name": line.name,
                        "percent": round(pct, 2), "cost": _money(line.employer_cost * pct / 100.0),
                        "basis": line.allocation_source})
    return sorted(out, key=lambda r: (r["period"], r["name"].lower()))


# ─── the check on a request ────────────────────────────────────────────────


def funds_checks(org_id: str, req) -> list:
    """FUNDS_AVAILABLE (and, per named line, BUDGET_LINE_AVAILABLE) for a
    request charged to a project with a budget. A FAIL, not a wall: someone
    with the authority can release it with a written reason — budget
    realignments are real — and it then shows on the audit page."""
    import requisitions as rq
    org = store.require_org(org_id)
    ags = grants.list_agreements(org)
    codes = {(a.project_code or "").strip().lower() for a in ags}
    code = charge_code(codes, req.grant_code, req.project_code)
    if not code:
        return []
    ag = next(a for a in ags if (a.project_code or "").strip().lower() == code)
    if ag.value <= 0 or (req.currency or ag.currency) != ag.currency:
        return []
    f = figures(org, ag, exclude_request_id=req.id)
    cur = ag.currency
    out = []
    left = f.remaining
    if req.amount > left + 0.005:
        out.append(rq.PolicyCheck(
            code="FUNDS_AVAILABLE", name="Enough left on the grant",
            result=rq.CheckResult.FAIL, policy_value=f"{cur} {max(left, 0):,.2f} left",
            actual_value=f"{cur} {req.amount:,.2f}",
            message=(f"Only {cur} {max(left, 0):,.2f} is left on {ag.project_code} ({ag.donor}): "
                     f"budget {cur} {f.budget:,.2f}, paid {cur} {f.paid:,.2f}, salaries "
                     f"{cur} {f.salary:,.2f}, already committed {cur} {f.committed:,.2f}. "
                     "Reduce the request, charge another grant, or have someone with "
                     "authority release it with a reason.")))
    else:
        out.append(rq.PolicyCheck(
            code="FUNDS_AVAILABLE", name="Enough left on the grant",
            result=rq.CheckResult.PASS, policy_value=f"{cur} {left:,.2f} left",
            actual_value=f"{cur} {req.amount:,.2f}",
            message=f"{cur} {left - req.amount:,.2f} will be left on {ag.project_code} after this."))

    wanted = split_by_line(ag, req.amount, req.budget_lines)
    by_code = {lf.code: lf for lf in f.lines}
    for key, amt in wanted.items():
        lf = by_code.get(key)
        if key == UNASSIGNED or lf is None or lf.budget <= 0:
            continue
        line_left = lf.remaining if lf.remaining is not None else 0.0
        if amt > line_left + 0.005:
            out.append(rq.PolicyCheck(
                code="BUDGET_LINE_AVAILABLE", name=f"Enough left on budget line {lf.code}",
                result=rq.CheckResult.FAIL, policy_value=f"{cur} {max(line_left, 0):,.2f} left",
                actual_value=f"{cur} {amt:,.2f}",
                message=(f"Budget line {lf.code} ({lf.label or lf.code}) has {cur} "
                         f"{max(line_left, 0):,.2f} left of {cur} {lf.budget:,.2f}; this request "
                         f"puts {cur} {amt:,.2f} on it.")))
    return out


def today_iso() -> str:
    return dt.date.today().isoformat()
