"""
Effort reporting — timesheets that decide how salary is charged to grants.

WHY THIS IS A COMPLIANCE ENGINE, NOT A CONVENIENCE FEATURE
Personnel costs are typically 60–80% of a donor-funded budget, and time-and-
effort documentation is the single largest source of audit findings against
federal grants. 2 CFR 200.430(i) requires after-the-fact records showing that
salary charged to an award reflects the work actually performed — and those
records must account for **100% of the employee's compensated time**, not only
the grant-funded part.

The rule that follows from it, and that this module enforces:

    SALARY ALLOCATION COMES FROM ACTUAL HOURS, NEVER FROM A BUDGET.

If someone was budgeted at 50% on a grant but actually worked 30%, only 30% is
allowable. `effort_allocation()` therefore derives percentages from recorded
hours; it does not accept them as input. That single decision is what makes the
allocation defensible in an audit.

WHAT THE CLIENT'S OWN POLICY REQUIRES
EVA's POL-FIN-600 (Effort Reporting, signed) specifies a timesheet must:

  * show an AFTER-THE-FACT determination of actual activity
  * report ALL hours worked, broken down by day
  * be prepared per pay period, and no less often than monthly
  * show the **Customer/Job charged** for each activity — the project code
  * carry the employee's name and signature (electronic entry counts)
  * carry the approving supervisor's name
  * name the office location (EVA/HQ, EVA/FCT …)

Supervisors must ensure the coding is correct and approve before it reaches
Finance. Every one of those is a rule below, not a comment.

DETERMINISTIC-FIRST
Every number here is arithmetic. Hours, totals, percentages and the checks that
guard them never involve a model. A wrong allocation does not crash — it
quietly overcharges a donor, which is precisely the failure an auditor is
looking for.
"""
from __future__ import annotations

import calendar
import datetime as dt
import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

import store

_TIMESHEETS = "timesheets"
_POLICY = "config"
_POLICY_ID = "timesheet_policy"

# A day has 24 hours. Anything above that is a typo, and a typo in an effort
# record becomes a mischarged grant.
MAX_HOURS_PER_DAY = 24.0


class TimesheetError(ValueError):
    """Invalid timesheet or illegal transition. Callers map to HTTP 4xx."""


class TimesheetStatus(str, Enum):
    DRAFT = "draft"           # employee still filling it in
    SUBMITTED = "submitted"   # with the supervisor
    APPROVED = "approved"     # supervisor signed; ready for Finance
    RETURNED = "returned"     # sent back for correction
    PROCESSED = "processed"   # payroll has used it — frozen


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _org(org_id: Optional[str] = None) -> str:
    explicit = (org_id or "").strip()
    if explicit:
        return store.require_org(explicit)
    return store.require_org((os.environ.get("DOCEX_ORG") or "default").strip() or "default")


def _hours(x: Optional[float]) -> float:
    return round(float(x or 0.0), 2)


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except Exception as exc:
        raise TimesheetError(f"Invalid date: {value!r}. Use YYYY-MM-DD.") from exc


def period_bounds(period: str) -> tuple[dt.date, dt.date]:
    """First and last day of a 'YYYY-MM' reporting period."""
    try:
        year, month = (int(p) for p in str(period).split("-")[:2])
        last = calendar.monthrange(year, month)[1]
        return dt.date(year, month, 1), dt.date(year, month, last)
    except Exception as exc:
        raise TimesheetError(f"Invalid period: {period!r}. Use YYYY-MM.") from exc


# ─── model ──────────────────────────────────────────────────────────────────


class TimeEntry(BaseModel):
    """One day's work on one project.

    `project_code` is EVA's "Customer/Job" — the thing being charged. It is
    required on every entry because an hour with no code is an hour nobody can
    allocate, and an unallocatable hour is an audit finding.

    Use `NON_PROJECT` for leave, admin, training and anything not chargeable.
    Those hours still have to be recorded: the total must cover 100% of
    compensated time, or the percentages are computed off the wrong base.
    """
    date: str                                # YYYY-MM-DD
    hours: float
    project_code: str                        # or NON_PROJECT
    activity: str = ""                       # what was actually done


NON_PROJECT = "NON_PROJECT"


class Timesheet(BaseModel):
    id: str
    org_id: str = ""
    staff_id: str
    staff_name: str = ""
    period: str                              # YYYY-MM
    office: str = ""                         # EVA/HQ, EVA/FCT …

    entries: list[TimeEntry] = Field(default_factory=list)
    status: TimesheetStatus = TimesheetStatus.DRAFT

    # Signatures. Electronic entry of a name counts as a signature under
    # EVA's policy, so recording who and when IS the signature.
    submitted_by: str = ""
    submitted_at: str = ""
    approved_by: str = ""                    # the supervisor
    approved_at: str = ""
    returned_reason: str = ""

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def total_hours(self) -> float:
        return _hours(sum(e.hours for e in self.entries))

    @property
    def project_hours(self) -> float:
        """Chargeable hours only — excludes leave, admin and training."""
        return _hours(sum(e.hours for e in self.entries
                          if e.project_code != NON_PROJECT))

    def hours_by_project(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self.entries:
            out[e.project_code] = _hours(out.get(e.project_code, 0.0) + e.hours)
        return out

    def hours_by_day(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self.entries:
            out[e.date] = _hours(out.get(e.date, 0.0) + e.hours)
        return out


class TimesheetPolicy(BaseModel):
    """Org-configured rules. Data, not code — every client differs."""
    org_id: str = ""
    standard_hours_per_period: float = 160.0     # ~ a working month
    # How far the total may drift from standard before it is flagged. Some
    # months are longer; overtime and part-time are normal. A WARNING, not a
    # block — the auditable requirement is that the record is honest, not that
    # it hits a target.
    tolerance_hours: float = 24.0
    require_activity_description: bool = False
    updated_at: Optional[str] = None


def set_policy(org_id: str, policy: TimesheetPolicy) -> TimesheetPolicy:
    org = _org(org_id)
    policy.org_id = org
    policy.updated_at = _now_iso()
    store.get_store().put(org, _POLICY, _POLICY_ID, policy.model_dump())
    return policy


def get_policy(org_id: str) -> TimesheetPolicy:
    raw = store.get_store().get(_org(org_id), _POLICY, _POLICY_ID)
    return TimesheetPolicy.model_validate(raw) if raw else TimesheetPolicy(org_id=_org(org_id))


# ─── validation ─────────────────────────────────────────────────────────────


class EffortIssue(BaseModel):
    code: str
    blocking: bool
    message: str


def validate(org_id: str, ts: Timesheet, *, at: Optional[dt.date] = None) -> list[EffortIssue]:
    """Every rule EVA's policy and 2 CFR 200.430 impose, as data.

    Blocking issues stop submission. Warnings inform the supervisor but do not
    prevent an honest record being filed — an unusual month is not a fraud.
    """
    issues: list[EffortIssue] = []
    policy = get_policy(org_id)
    start, end = period_bounds(ts.period)
    today = at or dt.date.today()

    # AFTER-THE-FACT. The policy's first requirement, and the one most often
    # broken by "planned effort" spreadsheets. A period that has not finished
    # cannot yet be reported on.
    if today <= end:
        issues.append(EffortIssue(
            code="NOT_AFTER_THE_FACT", blocking=True,
            message=(f"The period {ts.period} ends {end.isoformat()} and has not finished. "
                     "Effort must be reported after the fact, not forecast."),
        ))

    if not ts.entries:
        issues.append(EffortIssue(
            code="NO_ENTRIES", blocking=True,
            message="A timesheet with no hours cannot be submitted."))
        return issues

    for e in ts.entries:
        d = _parse_date(e.date)
        if not (start <= d <= end):
            issues.append(EffortIssue(
                code="DATE_OUTSIDE_PERIOD", blocking=True,
                message=f"{e.date} is outside {ts.period} ({start} to {end})."))
        if _hours(e.hours) <= 0:
            issues.append(EffortIssue(
                code="NON_POSITIVE_HOURS", blocking=True,
                message=f"{e.date}: hours must be greater than zero."))
        if not (e.project_code or "").strip():
            issues.append(EffortIssue(
                code="MISSING_PROJECT_CODE", blocking=True,
                message=(f"{e.date}: no Customer/Job code. Every hour must be "
                         f"chargeable to something, or to {NON_PROJECT}.")))
        if policy.require_activity_description and not e.activity.strip():
            issues.append(EffortIssue(
                code="MISSING_ACTIVITY", blocking=False,
                message=f"{e.date}: no description of the activity."))

    for day, hours in ts.hours_by_day().items():
        if hours > MAX_HOURS_PER_DAY:
            issues.append(EffortIssue(
                code="IMPOSSIBLE_DAY", blocking=True,
                message=f"{day}: {hours} hours recorded. A day has {MAX_HOURS_PER_DAY:.0f}."))

    total = ts.total_hours
    drift = abs(total - policy.standard_hours_per_period)
    if drift > policy.tolerance_hours:
        issues.append(EffortIssue(
            code="HOURS_OUTSIDE_TOLERANCE", blocking=False,
            message=(f"{total:g} hours against a standard of "
                     f"{policy.standard_hours_per_period:g}. Overtime and part-time "
                     "are normal — confirm this is right before approving.")))
    return issues


def blocking(issues: list[EffortIssue]) -> list[EffortIssue]:
    return [i for i in issues if i.blocking]


# ─── the number that matters ────────────────────────────────────────────────


def effort_allocation(ts: Timesheet, *, chargeable_only: bool = True) -> dict[str, float]:
    """Percentage of effort per project code, from ACTUAL recorded hours.

    This is the function payroll uses to decide how much of a salary each grant
    carries. It takes no percentages as input, by design: 2 CFR 200.430 allows
    a grant to be charged only for work actually performed, so a budgeted
    figure must never be able to reach the ledger.

    `chargeable_only=True` computes the split across project work, which is
    what payroll needs to apportion the chargeable part of a salary. Pass False
    to see the honest picture including leave and admin — that is the view an
    auditor asks for, because it proves 100% of time is accounted for.

    Percentages are rounded to 4 places and the largest share absorbs any
    rounding remainder, so the result always sums to exactly 100.
    """
    by_project = ts.hours_by_project()
    if not chargeable_only:
        base = ts.total_hours
        buckets = by_project
    else:
        base = ts.project_hours
        buckets = {k: v for k, v in by_project.items() if k != NON_PROJECT}

    if base <= 0 or not buckets:
        return {}

    alloc = {code: round(hours / base * 100.0, 4) for code, hours in buckets.items()}
    # Force an exact 100. Floating point will otherwise leave 99.9999, and a
    # payroll run that refuses to balance over a rounding error is a support
    # ticket every single month.
    remainder = round(100.0 - sum(alloc.values()), 4)
    if remainder and alloc:
        biggest = max(alloc, key=lambda k: alloc[k])
        alloc[biggest] = round(alloc[biggest] + remainder, 4)
    return alloc


def allocate_amount(ts: Timesheet, amount: float) -> dict[str, float]:
    """Split a salary across projects by actual effort.

    The returned amounts sum to exactly `amount` — the largest share carries
    the rounding remainder, so a payroll run always balances to the naira.
    """
    alloc = effort_allocation(ts)
    if not alloc:
        return {}
    out = {code: round(float(amount) * pct / 100.0, 2) for code, pct in alloc.items()}
    remainder = round(float(amount) - sum(out.values()), 2)
    if remainder:
        biggest = max(out, key=lambda k: out[k])
        out[biggest] = round(out[biggest] + remainder, 2)
    return out


# ─── lifecycle ──────────────────────────────────────────────────────────────


def create_timesheet(org_id: str, *, staff_id: str, period: str,
                     staff_name: str = "", office: str = "",
                     entries: Optional[list[dict]] = None) -> Timesheet:
    """Start a timesheet. One per employee per period — a second would let the
    same hours be charged twice."""
    import uuid
    org = _org(org_id)
    period_bounds(period)                    # validates the format
    if not (staff_id or "").strip():
        raise TimesheetError("A timesheet needs a staff member.")

    existing = find_timesheet(org, staff_id, period)
    if existing is not None:
        raise TimesheetError(
            f"{staff_id} already has a timesheet for {period} ({existing.status.value}). "
            "Edit that one rather than creating a second.")

    ts = Timesheet(
        id=uuid.uuid4().hex, org_id=org, staff_id=staff_id.strip(),
        staff_name=staff_name.strip(), period=period, office=office.strip(),
        entries=[TimeEntry(**e) for e in (entries or [])],
        created_at=_now_iso(), updated_at=_now_iso(),
    )
    return _save(org, ts)


def set_entries(org_id: str, ts_id: str, entries: list[dict], *, actor: str) -> Timesheet:
    """Replace the entries on a draft or returned timesheet."""
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    if ts.status not in (TimesheetStatus.DRAFT, TimesheetStatus.RETURNED):
        raise TimesheetError(
            f"This timesheet is {ts.status.value} and cannot be edited. "
            "A supervisor must return it first — an approved record is evidence.")
    ts.entries = [TimeEntry(**e) for e in entries]
    ts.updated_at = _now_iso()
    return _save(org, ts)


def submit(org_id: str, ts_id: str, *, actor: str) -> Timesheet:
    """Employee signs and sends it to their supervisor.

    Recording the name and time IS the signature — EVA's policy accepts
    electronic entry as one.
    """
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    if ts.status not in (TimesheetStatus.DRAFT, TimesheetStatus.RETURNED):
        raise TimesheetError(f"Already {ts.status.value}.")

    problems = blocking(validate(org, ts))
    if problems:
        raise TimesheetError(
            "This timesheet cannot be submitted:\n  - "
            + "\n  - ".join(p.message for p in problems))

    ts.status = TimesheetStatus.SUBMITTED
    ts.submitted_by = actor
    ts.submitted_at = _now_iso()
    ts.returned_reason = ""
    ts.updated_at = ts.submitted_at
    return _save(org, ts)


def approve(org_id: str, ts_id: str, *, supervisor: str) -> Timesheet:
    """Supervisor signs it off, and it becomes evidence.

    A supervisor may not approve their own timesheet. Self-approval of effort
    records is one of the findings auditors look for specifically, so it is
    refused here rather than left to good behaviour.
    """
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    if ts.status != TimesheetStatus.SUBMITTED:
        raise TimesheetError(f"Only a submitted timesheet can be approved (this is {ts.status.value}).")
    if not (supervisor or "").strip():
        raise TimesheetError("An approval must name the supervisor.")
    if supervisor.strip().lower() in (ts.staff_id.strip().lower(),
                                      (ts.submitted_by or "").strip().lower()):
        raise TimesheetError(
            "A timesheet cannot be approved by the person who submitted it. "
            "Self-approved effort records are a standard audit finding.")

    ts.status = TimesheetStatus.APPROVED
    ts.approved_by = supervisor.strip()
    ts.approved_at = _now_iso()
    ts.updated_at = ts.approved_at
    return _save(org, ts)


def send_back(org_id: str, ts_id: str, *, supervisor: str, reason: str) -> Timesheet:
    """Return it for correction. A reason is required — 'fix it' is not
    feedback, and the reason is part of the record."""
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    if ts.status != TimesheetStatus.SUBMITTED:
        raise TimesheetError(f"Only a submitted timesheet can be returned (this is {ts.status.value}).")
    if not (reason or "").strip():
        raise TimesheetError("Returning a timesheet requires a written reason.")
    ts.status = TimesheetStatus.RETURNED
    ts.returned_reason = reason.strip()
    ts.updated_at = _now_iso()
    return _save(org, ts)


def mark_processed(org_id: str, ts_id: str) -> Timesheet:
    """Payroll has used this timesheet. It is now frozen — the allocation it
    produced is on a payment, and changing it afterwards would break the tie
    between what was paid and what was worked."""
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    if ts.status != TimesheetStatus.APPROVED:
        raise TimesheetError(
            f"Only an approved timesheet can be processed (this is {ts.status.value}). "
            "Payroll must never allocate from unapproved effort.")
    ts.status = TimesheetStatus.PROCESSED
    ts.updated_at = _now_iso()
    return _save(org, ts)


# ─── reading ────────────────────────────────────────────────────────────────


def _save(org_id: str, ts: Timesheet) -> Timesheet:
    store.get_store().put(_org(org_id), _TIMESHEETS, ts.id, ts.model_dump())
    return ts


def get_timesheet(org_id: str, ts_id: str) -> Optional[Timesheet]:
    raw = store.get_store().get(_org(org_id), _TIMESHEETS, ts_id)
    return Timesheet.model_validate(raw) if raw else None


def list_timesheets(org_id: str, *, period: Optional[str] = None,
                    staff_id: Optional[str] = None,
                    status: Optional[TimesheetStatus] = None) -> list[Timesheet]:
    out: list[Timesheet] = []
    for raw in store.get_store().list(_org(org_id), _TIMESHEETS):
        try:
            ts = Timesheet.model_validate(raw)
        except Exception:
            continue
        if period and ts.period != period:
            continue
        if staff_id and ts.staff_id != staff_id:
            continue
        if status and ts.status != status:
            continue
        out.append(ts)
    return sorted(out, key=lambda t: (t.period, t.staff_id), reverse=True)


def find_timesheet(org_id: str, staff_id: str, period: str) -> Optional[Timesheet]:
    found = list_timesheets(org_id, period=period, staff_id=staff_id)
    return found[0] if found else None


def period_summary(org_id: str, period: str) -> dict:
    """What Finance needs to see before running payroll for a month."""
    sheets = list_timesheets(org_id, period=period)
    by_project: dict[str, float] = {}
    for ts in sheets:
        if ts.status not in (TimesheetStatus.APPROVED, TimesheetStatus.PROCESSED):
            continue
        for code, hours in ts.hours_by_project().items():
            by_project[code] = _hours(by_project.get(code, 0.0) + hours)

    counts = {s.value: 0 for s in TimesheetStatus}
    for ts in sheets:
        counts[ts.status.value] += 1

    outstanding = [t.staff_id for t in sheets
                   if t.status in (TimesheetStatus.DRAFT, TimesheetStatus.RETURNED,
                                   TimesheetStatus.SUBMITTED)]
    return {
        "period": period,
        "timesheets": len(sheets),
        "by_status": counts,
        "hours_by_project": by_project,
        "total_hours": _hours(sum(by_project.values())),
        # Payroll should not run while effort is unapproved: allocating from a
        # timesheet nobody signed is the finding this whole module prevents.
        "ready_for_payroll": not outstanding and bool(sheets),
        "outstanding_staff": sorted(set(outstanding)),
    }
