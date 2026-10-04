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
from typing import Literal, Optional

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
    date: str                                # YYYY-MM-DD; for a week or month, its first day
    hours: float
    project_code: str                        # or NON_PROJECT
    activity: str = ""                       # what was actually done
    # How much time this line covers. "day" is the default and the most
    # precise. "week" and "month" let someone who thinks "I spent this week
    # on TB" say so honestly, rather than inventing daily figures to fill a
    # grid. A week starts on a Monday (or the 1st, for the first part-week).
    span: Literal["day", "week", "month"] = "day"


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
    # With a second approval configured: the supervisor's signature, kept
    # while the sheet waits for the second (approved_by is the final one).
    supervisor_approved_by: str = ""
    supervisor_approved_at: str = ""
    # Reopened by Finance after the grace period: editable until this date.
    unlocked_until: str = ""
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
        """Hours per calendar day, from day entries only: a week or month
        line is not a day's work and must not trip the 24-hour check."""
        out: dict[str, float] = {}
        for e in self.entries:
            if e.span != "day":
                continue
            out[e.date] = _hours(out.get(e.date, 0.0) + e.hours)
        return out

    @property
    def span(self) -> str:
        """How this sheet is recorded: day, week or month (or mixed)."""
        spans = {e.span for e in self.entries}
        return next(iter(spans)) if len(spans) == 1 else ("day" if not spans else "mixed")


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
    # How staff may record time. Default: any of the three. An organisation
    # whose donor wants daily records sets this to ["day"].
    allowed_spans: list[str] = Field(default_factory=lambda: ["day", "week", "month"])
    # Days after the month ends during which staff may still change entries.
    # None = no lock. After that, Finance or an admin reopens a sheet.
    grace_days: Optional[int] = None
    # A department key ("finance", "hr") whose approver signs after the
    # supervisor; "" = the supervisor's signature is enough.
    second_approval: str = ""
    # Who must record time: "everyone" (all active staff) or "project_staff"
    # (people named on a project) — decides the "hasn't started" list.
    who_records: Literal["everyone", "project_staff"] = "everyone"
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

    spans = {e.span for e in ts.entries}
    if len(spans) > 1:
        issues.append(EffortIssue(
            code="MIXED_SPANS", blocking=True,
            message=("Record this month one way — by day, by week, or as a monthly total — "
                     "not a mix. Mixing them lets the same hours be counted twice.")))
    for sp in sorted(spans - set(policy.allowed_spans or ["day"])):
        issues.append(EffortIssue(
            code="SPAN_NOT_ALLOWED", blocking=True,
            message=f"Your organisation records time {' or '.join('by ' + x for x in policy.allowed_spans)}, "
                    f"not by {sp}."))
    for e in ts.entries:
        if e.span == "day":
            continue
        try:
            d = _parse_date(e.date)
        except TimesheetError:
            continue
        if e.span == "week":
            if not (d.weekday() == 0 or d == start):
                issues.append(EffortIssue(
                    code="WEEK_START", blocking=True,
                    message=f"{e.date}: a week is recorded from its Monday (or the 1st)."))
            last = min(end, d + dt.timedelta(days=6 - d.weekday()))
            limit = ((last - d).days + 1) * MAX_HOURS_PER_DAY
        else:
            if d != start:
                issues.append(EffortIssue(
                    code="MONTH_START", blocking=True,
                    message=f"{e.date}: a monthly total is recorded on the 1st."))
            limit = ((end - start).days + 1) * MAX_HOURS_PER_DAY
        total_here = _hours(sum(x.hours for x in ts.entries if x.date == e.date and x.span == e.span))
        if total_here > limit:
            issues.append(EffortIssue(
                code="IMPOSSIBLE_SPAN", blocking=True,
                message=f"{e.date}: {total_here:g} hours in a {e.span} that has {limit:g}."))

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


# ─── the grace period ───────────────────────────────────────────────────────


def lock_date(org_id: str, ts: Timesheet) -> Optional[dt.date]:
    """The last day staff may change this sheet, or None for no lock."""
    grace = get_policy(org_id).grace_days
    if grace is None:
        return None
    _, end = period_bounds(ts.period)
    last = end + dt.timedelta(days=max(0, int(grace)))
    if ts.unlocked_until:
        try:
            last = max(last, dt.date.fromisoformat(ts.unlocked_until[:10]))
        except ValueError:
            pass
    return last


def is_locked(org_id: str, ts: Timesheet, *, at: Optional[dt.date] = None) -> bool:
    last = lock_date(org_id, ts)
    return last is not None and (at or dt.date.today()) > last


def _require_unlocked(org_id: str, ts: Timesheet) -> None:
    if is_locked(org_id, ts):
        raise TimesheetError(
            f"{ts.period} closed for changes on {lock_date(org_id, ts).isoformat()}. "
            "Ask Finance to reopen it if something needs correcting.")


def reopen(org_id: str, ts_id: str, *, actor: str, days: int = 5) -> Timesheet:
    """Finance lets one person correct a closed month for a few days."""
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    if ts.status not in (TimesheetStatus.DRAFT, TimesheetStatus.RETURNED):
        raise TimesheetError(f"This timesheet is {ts.status.value}; only an unsubmitted one is reopened.")
    ts.unlocked_until = (dt.date.today() + dt.timedelta(days=max(1, int(days)))).isoformat()
    ts.updated_at = _now_iso()
    return _save(org, ts)


# ─── quick entry ────────────────────────────────────────────────────────────


def hours_per_day(org_id: str, period: str) -> float:
    """A full working day, from the org's monthly standard divided by the
    month's working days (not an assumed 8)."""
    start, end = period_bounds(period)
    working = sum(1 for i in range((end - start).days + 1)
                  if (start + dt.timedelta(days=i)).weekday() < 5) or 1
    return round(get_policy(org_id).standard_hours_per_period / working, 2)


def quick_log(org_id: str, *, staff_id: str, staff_name: str = "", date: str,
              project_code: str, hours: float, activity: str = "") -> Timesheet:
    """Record one day's work on one project, in one step.

    Opens the month's sheet if there isn't one. Replaces an existing entry
    for the same day and project (people correct themselves; they don't mean
    to log it twice). Refuses plainly where the sheet can't take it."""
    org = _org(org_id)
    d = _parse_date(date)
    if d > dt.date.today():
        raise TimesheetError("Time is recorded after it is worked, not before.")
    code = (project_code or "").strip()
    if not code:
        raise TimesheetError("Pick the project you worked on.")
    hours = _hours(hours)
    if hours <= 0 or hours > MAX_HOURS_PER_DAY:
        raise TimesheetError("Hours must be more than 0 and no more than 24.")
    period = d.strftime("%Y-%m")
    ts = find_timesheet(org, staff_id, period)
    if ts is None:
        ts = create_timesheet(org, staff_id=staff_id, staff_name=staff_name, period=period)
    if ts.status not in (TimesheetStatus.DRAFT, TimesheetStatus.RETURNED):
        raise TimesheetError(
            f"Your {period} timesheet is {ts.status.value}, so it can't take new entries.")
    if ts.entries and ts.span != "day":
        raise TimesheetError(
            f"Your {period} timesheet is recorded by {ts.span}; add this on the timesheet itself.")
    _require_unlocked(org, ts)
    ts.entries = [e for e in ts.entries if not (e.date == d.isoformat() and e.project_code == code)]
    ts.entries.append(TimeEntry(date=d.isoformat(), hours=hours, project_code=code,
                                activity=(activity or "").strip()))
    ts.entries.sort(key=lambda e: (e.date, e.project_code))
    ts.updated_at = _now_iso()
    return _save(org, ts)


def fill_from_split(org_id: str, ts_id: str, split: dict[str, float]) -> Timesheet:
    """Fill every empty working day up to today from a percentage split
    (the person's planned level of effort). Days already recorded are left
    alone; anything under 100% goes to leave/admin, so the day is whole."""
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    if ts.status not in (TimesheetStatus.DRAFT, TimesheetStatus.RETURNED):
        raise TimesheetError(f"This timesheet is {ts.status.value} and can't be changed.")
    if ts.entries and ts.span != "day":
        raise TimesheetError("This month is recorded by week or month; fill it in there.")
    _require_unlocked(org, ts)
    split = {k: float(v) for k, v in (split or {}).items() if float(v or 0) > 0}
    total = sum(split.values())
    if not split or total > 100.0001:
        raise TimesheetError("There is no usual split to fill from (or it adds up to more than 100%).")
    if total < 100:
        split[NON_PROJECT] = split.get(NON_PROJECT, 0.0) + (100 - total)
    per_day = hours_per_day(org, ts.period)
    start, end = period_bounds(ts.period)
    last = min(end, dt.date.today())
    taken = set(ts.hours_by_day())
    added = 0
    d = start
    while d <= last:
        if d.weekday() < 5 and d.isoformat() not in taken:
            for code, pct in split.items():
                h = _hours(per_day * pct / 100.0)
                if h > 0:
                    ts.entries.append(TimeEntry(date=d.isoformat(), hours=h, project_code=code))
            added += 1
        d += dt.timedelta(days=1)
    if not added:
        raise TimesheetError("Every working day so far already has time on it.")
    ts.entries.sort(key=lambda e: (e.date, e.project_code))
    ts.updated_at = _now_iso()
    return _save(org, ts)


def set_entries(org_id: str, ts_id: str, entries: list[dict], *, actor: str) -> Timesheet:
    """Replace the entries on a draft or returned timesheet."""
    org = _org(org_id)
    ts = get_timesheet(org, ts_id)
    if ts is None:
        raise TimesheetError(f"No timesheet {ts_id}.")
    _require_unlocked(org, ts)
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

    policy = get_policy(org)
    if (policy.second_approval or "").strip() and not ts.supervisor_approved_by:
        # First of two signatures: the supervisor's. The sheet stays
        # submitted, now waiting on the second approver.
        ts.supervisor_approved_by = supervisor.strip()
        ts.supervisor_approved_at = _now_iso()
        ts.updated_at = ts.supervisor_approved_at
        return _save(org, ts)
    if ts.supervisor_approved_by and supervisor.strip().lower() == ts.supervisor_approved_by.lower():
        raise TimesheetError("The second approval must come from someone other than the supervisor who signed first.")

    ts.status = TimesheetStatus.APPROVED
    ts.approved_by = supervisor.strip()
    ts.approved_at = _now_iso()
    ts.updated_at = ts.approved_at
    return _save(org, ts)


def awaiting_stage(ts: Timesheet, org_id: str) -> str:
    """For a submitted sheet: 'supervisor' or 'second' (the department key
    that signs second is in the policy)."""
    if ts.status != TimesheetStatus.SUBMITTED:
        return ""
    policy = get_policy(org_id)
    return "second" if (policy.second_approval and ts.supervisor_approved_by) else "supervisor"


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
    # A corrected sheet is signed afresh: an earlier first signature was on
    # figures that are about to change.
    ts.supervisor_approved_by = ""
    ts.supervisor_approved_at = ""
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
