"""
Advances — the clock, and the consequence.

WHY THIS MATTERS MORE THAN IT LOOKS
An unretired advance is the most common source of ineligible cost in
donor-funded work. Money left the account, the paperwork proving what it bought
never arrived, and at audit the organisation cannot show the expenditure was
eligible — so the donor disallows it and the NGO absorbs the loss from
unrestricted funds it does not have.

Every organisation says advances must be retired. Almost none of them write
down what happens when they are not, which is why almost none of them are.

NEEM DID WRITE IT DOWN
Their Finance Processes deck, slide 10, is unusually specific:

    "For any advance payment made through memo, such advance must be retired
    within 7 days or 5 working days from the date of receipt of payment.
    Failure to retire such advance connotes that no payment will be made to
    that individual and if it is a collective default, then no payment will be
    made for the implementation of that project for any activities succeeding
    the default of retirement. When the default persist till the end of the
    month, then the amount involved will be recovered from the salary(ies) of
    person(s) involved."

That is a three-stage escalation ladder with a stated consequence at each
stage. It is enforceable, and enforcing it is worth more to them than any
report.

    overdue          -> that person cannot be paid again
    collective       -> that project's next activity is blocked
    end of month     -> the amount is recovered from salary

DSA runs on the same clock but from a different start: 5 working days after the
TRIP ENDS, not after the money was received, because you cannot retire a trip
you have not taken. A travel approval form must exist before the trip at all.

WHAT THIS MODULE IS NOT
It does not do the retirement arithmetic — receipts.py already reconciles what
was spent against what was advanced, and does it well. This is the register,
the clock, and the ladder: which advances are outstanding, how late each one
is, who that stops from being paid, and what finance should chase this morning.

EVERY DEADLINE IS CONFIGURATION. NEEM says 7 days. EVA's policy states the
requirement but — as we found reading it — names no window at all, which is a
gap in their policy rather than in ours. TA Connect will differ again. Nothing
here hard-codes a number.
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

import store

_ADVANCES = "advances"
_POLICY = "config"
_POLICY_ID = "advance_policy"


class AdvanceError(ValueError):
    """Invalid advance or an illegal transition — callers map this to 4xx."""


class AdvanceStatus(str, Enum):
    OUTSTANDING = "outstanding"    # money out, nothing back yet
    SUBMITTED = "submitted"        # retirement submitted, finance reviewing
    RETIRED = "retired"            # accepted and settled
    RECOVERED = "recovered"        # never retired; taken from salary
    WRITTEN_OFF = "written_off"    # accepted as a loss, with a reason


class Escalation(int, Enum):
    """How far up NEEM's ladder this advance has climbed.

    Ordered so a screen can sort by it and a person can see the worst first.
    """
    NONE = 0            # within the window
    DUE_SOON = 1        # inside the warning period
    OVERDUE = 2         # past the window
    STAFF_BLOCKED = 3   # that person cannot be paid again
    PROJECT_BLOCKED = 4 # collective default — the project's next activity stops
    RECOVERY = 5        # month end passed — recover from salary


class AdvancePolicy(BaseModel):
    """Each organisation's own rules. Nothing here is a default we invented.

    NEEM's policy reads "7 days or 5 working days", which are two expressions
    of roughly the same period. `use_working_days` decides which is counted;
    working days is the fairer reading and the one their deck emphasises.
    """
    org_id: str = ""
    enabled: bool = False

    retirement_days: int = 7               # calendar days
    working_days: int = 5                  # the working-day equivalent
    use_working_days: bool = True
    warn_days_before: int = 2              # "due soon" window

    # The ladder. Each stage is measured in days PAST the due date, so an
    # organisation with a gentler policy simply sets larger numbers rather
    # than needing different code.
    block_staff_after_days: int = 0        # NEEM: immediately on default
    block_project_after_days: int = 0      # NEEM: on collective default
    collective_default_count: int = 2      # how many overdue makes it collective
    recover_at_month_end: bool = True

    # Optional limits some organisations set instead of, or as well as, a clock.
    max_outstanding_per_person: Optional[float] = None
    max_concurrent_per_person: Optional[int] = None

    updated_at: Optional[str] = None


class Advance(BaseModel):
    """One advance issued to one person."""
    id: str
    org_id: str = ""
    ref: str = ""

    staff_id: str = ""                     # email or payroll id
    staff_name: str = ""
    department: str = ""

    amount: float = 0.0
    currency: str = "NGN"
    purpose: str = ""
    project_code: str = ""
    grant_code: Optional[str] = None
    source_ref: str = ""                   # the requisition that funded it

    issued_at: str = ""                    # the clock starts here
    # For travel: the window runs from the END of the trip, because you cannot
    # retire a trip you have not taken yet.
    activity_end: str = ""
    due_at: str = ""

    status: AdvanceStatus = AdvanceStatus.OUTSTANDING
    retired_at: str = ""
    retired_by: str = ""
    spent: float = 0.0
    balance: float = 0.0                   # advance - spent
    direction: str = ""                    # recover / reimburse / settled
    receipt_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    created_at: str = ""
    updated_at: str = ""

    @property
    def open(self) -> bool:
        return self.status in (AdvanceStatus.OUTSTANDING, AdvanceStatus.SUBMITTED)


# ─── helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _today() -> dt.date:
    return dt.date.today()


def _as_date(value: str) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def _money(x: float) -> float:
    return round(float(x or 0.0), 2)


def add_working_days(start: dt.date, days: int) -> dt.date:
    """Business days only.

    A five-working-day window starting Thursday ends the following Thursday,
    not Tuesday. Counting calendar days would make every advance issued late in
    the week effectively shorter, which is how a fair-sounding policy becomes
    an unfair one.

    Public holidays are not modelled: they differ by state in Nigeria and a
    wrong holiday calendar produces confidently wrong due dates. Weekends alone
    is the honest approximation, and finance can extend an individual advance.
    """
    current = start
    remaining = days
    while remaining > 0:
        current += dt.timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


# ─── policy ─────────────────────────────────────────────────────────────────


def set_policy(org_id: str, policy: AdvancePolicy) -> AdvancePolicy:
    org = store.require_org(org_id)
    if policy.retirement_days < 0 or policy.working_days < 0:
        raise AdvanceError("A retirement window cannot be negative.")
    policy.org_id = org
    policy.updated_at = _now_iso()
    store.get_store().put(org, _POLICY, _POLICY_ID, policy.model_dump())
    return policy


def get_policy(org_id: str) -> AdvancePolicy:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _POLICY, _POLICY_ID)
    return AdvancePolicy.model_validate(raw) if raw else AdvancePolicy(org_id=org)


def due_date(policy: AdvancePolicy, start: dt.date) -> dt.date:
    if policy.use_working_days:
        return add_working_days(start, policy.working_days)
    return start + dt.timedelta(days=policy.retirement_days)


# ─── the register ───────────────────────────────────────────────────────────


def _next_ref(org_id: str) -> str:
    existing = len(store.get_store().list(org_id, _ADVANCES))
    return f"ADV-{existing + 1:04d}"


def issue(org_id: str, *, staff_id: str, amount: float, purpose: str,
          staff_name: str = "", department: str = "", project_code: str = "",
          grant_code: Optional[str] = None, source_ref: str = "",
          issued_at: str = "", activity_end: str = "",
          currency: str = "NGN") -> Advance:
    """Record an advance and start its clock.

    `activity_end` moves the clock's start to the end of the trip or activity —
    the correct reading for DSA, which cannot be retired before the trip has
    happened.
    """
    org = store.require_org(org_id)
    if not (staff_id or "").strip():
        raise AdvanceError("An advance must name who received it.")
    if _money(amount) <= 0:
        raise AdvanceError("An advance must be a positive amount.")

    policy = get_policy(org)
    issued = _as_date(issued_at) or _today()
    clock_starts = _as_date(activity_end) or issued
    if clock_starts < issued:
        raise AdvanceError(
            "The activity cannot end before the advance was issued.")

    adv = Advance(
        id=uuid.uuid4().hex[:12], org_id=org, ref=_next_ref(org),
        staff_id=staff_id.strip(), staff_name=staff_name.strip() or staff_id,
        department=department, amount=_money(amount), currency=currency,
        purpose=purpose.strip(), project_code=project_code,
        grant_code=grant_code, source_ref=source_ref,
        issued_at=issued.isoformat(), activity_end=activity_end[:10],
        due_at=due_date(policy, clock_starts).isoformat(),
        created_at=_now_iso(), updated_at=_now_iso())
    return _save(org, adv)


def _save(org_id: str, adv: Advance) -> Advance:
    adv.updated_at = _now_iso()
    store.get_store().put(org_id, _ADVANCES, adv.id, adv.model_dump())
    return adv


def get(org_id: str, advance_id: str) -> Optional[Advance]:
    raw = store.get_store().get(store.require_org(org_id), _ADVANCES, advance_id)
    return Advance.model_validate(raw) if raw else None


def list_advances(org_id: str, *, staff_id: Optional[str] = None,
                  project_code: Optional[str] = None,
                  open_only: bool = False) -> list[Advance]:
    org = store.require_org(org_id)
    out: list[Advance] = []
    for raw in store.get_store().list(org, _ADVANCES):
        try:
            a = Advance.model_validate(raw)
        except Exception:
            continue
        if staff_id and a.staff_id != staff_id:
            continue
        if project_code and a.project_code != project_code:
            continue
        if open_only and not a.open:
            continue
        out.append(a)
    return sorted(out, key=lambda a: a.due_at)


# ─── the clock ──────────────────────────────────────────────────────────────


def days_overdue(adv: Advance, *, at: Optional[dt.date] = None) -> int:
    """Negative means days remaining; positive means days late."""
    due = _as_date(adv.due_at)
    if due is None:
        return 0
    return ((at or _today()) - due).days


def escalation_of(org_id: str, adv: Advance, *, at: Optional[dt.date] = None,
                  policy: Optional[AdvancePolicy] = None,
                  collective: bool = False) -> Escalation:
    """How far up the ladder this advance has climbed.

    `collective` is decided by the caller across the whole project, because one
    person's lateness is not a collective default — that is a property of the
    project, not of this record.
    """
    if not adv.open:
        return Escalation.NONE
    p = policy or get_policy(org_id)
    if not p.enabled:
        return Escalation.NONE

    today = at or _today()
    late = days_overdue(adv, at=today)

    if late < 0:
        return (Escalation.DUE_SOON if abs(late) <= p.warn_days_before
                else Escalation.NONE)

    # Month end passed while still unretired → recovery from salary.
    due = _as_date(adv.due_at)
    if p.recover_at_month_end and due is not None:
        month_end = (dt.date(due.year + (due.month == 12),
                             (due.month % 12) + 1, 1) - dt.timedelta(days=1))
        if today > month_end:
            return Escalation.RECOVERY

    if collective and late >= p.block_project_after_days:
        return Escalation.PROJECT_BLOCKED
    if late >= p.block_staff_after_days:
        return Escalation.STAFF_BLOCKED
    return Escalation.OVERDUE


def _collective_projects(org_id: str, policy: AdvancePolicy,
                         at: Optional[dt.date] = None) -> set[str]:
    """Projects where enough advances are overdue to count as a collective
    default — the second rung of NEEM's ladder."""
    counts: dict[str, int] = {}
    for a in list_advances(org_id, open_only=True):
        if a.project_code and days_overdue(a, at=at) >= 0:
            counts[a.project_code] = counts.get(a.project_code, 0) + 1
    return {code for code, n in counts.items()
            if n >= max(1, policy.collective_default_count)}


# ─── what finance chases this morning ───────────────────────────────────────


def aging(org_id: str, *, at: Optional[dt.date] = None) -> dict:
    """Every outstanding advance, worst first.

    This is the screen. Not a report someone runs at month end — the list of
    people to chase today, which is the only form in which this information
    changes anybody's behaviour.
    """
    org = store.require_org(org_id)
    policy = get_policy(org)
    today = at or _today()
    collective = _collective_projects(org, policy, today)

    rows = []
    for a in list_advances(org, open_only=True):
        level = escalation_of(org, a, at=today, policy=policy,
                              collective=a.project_code in collective)
        late = days_overdue(a, at=today)
        rows.append({
            "id": a.id, "ref": a.ref,
            "staff_id": a.staff_id, "staff_name": a.staff_name,
            "department": a.department,
            "amount": a.amount, "currency": a.currency,
            "purpose": a.purpose, "project_code": a.project_code,
            "issued_at": a.issued_at, "due_at": a.due_at,
            "days_overdue": late,
            "status": a.status.value,
            "escalation": int(level), "escalation_name": level.name.lower(),
            "consequence": _consequence(level),
        })
    rows.sort(key=lambda r: (-r["escalation"], -r["days_overdue"]))

    overdue = [r for r in rows if r["days_overdue"] >= 0]
    return {
        "as_at": today.isoformat(),
        "configured": policy.enabled,
        "outstanding": len(rows),
        "outstanding_value": _money(sum(r["amount"] for r in rows)),
        "overdue": len(overdue),
        "overdue_value": _money(sum(r["amount"] for r in overdue)),
        "blocked_staff": sorted({r["staff_id"] for r in rows
                                 if r["escalation"] >= int(Escalation.STAFF_BLOCKED)}),
        "blocked_projects": sorted(collective),
        "for_recovery": [r for r in rows
                         if r["escalation"] == int(Escalation.RECOVERY)],
        "rows": rows,
    }


def _consequence(level: Escalation) -> str:
    """What the policy says happens now — in the words a person acts on."""
    return {
        Escalation.NONE: "Within the retirement window.",
        Escalation.DUE_SOON: "Due shortly — send the receipts now.",
        Escalation.OVERDUE: "Past the retirement window.",
        Escalation.STAFF_BLOCKED:
            "Overdue. No further payment can be made to this person until it "
            "is retired.",
        Escalation.PROJECT_BLOCKED:
            "Collective default on this project. No payment for the project's "
            "next activity until the outstanding advances are retired.",
        Escalation.RECOVERY:
            "Still unretired at month end. The policy provides for recovery "
            "from salary.",
    }[level]


# ─── the block ──────────────────────────────────────────────────────────────


def payment_block(org_id: str, staff_id: str = "",
                  project_code: str = "", *,
                  at: Optional[dt.date] = None) -> Optional[dict]:
    """Is this person, or this project, barred from being paid right now?

    Returns None when clear. This is what makes the policy real rather than
    aspirational — it is checked on a new requisition, where it costs the
    person the thing they want, at the moment they want it.
    """
    org = store.require_org(org_id)
    policy = get_policy(org)
    if not policy.enabled:
        return None

    today = at or _today()
    collective = _collective_projects(org, policy, today)

    if staff_id:
        for a in list_advances(org, staff_id=staff_id, open_only=True):
            level = escalation_of(org, a, at=today, policy=policy)
            if level >= Escalation.STAFF_BLOCKED:
                return {
                    "blocked": True, "scope": "staff",
                    "advance_ref": a.ref, "amount": a.amount,
                    "days_overdue": days_overdue(a, at=today),
                    "reason": (f"{a.staff_name} has an unretired advance "
                               f"({a.ref}, {a.currency} {a.amount:,.2f}, "
                               f"{days_overdue(a, at=today)} days overdue). "
                               "Policy: no further payment until it is retired."),
                }

    if project_code and project_code in collective:
        outstanding = [a for a in list_advances(org, project_code=project_code,
                                                open_only=True)
                       if days_overdue(a, at=today) >= 0]
        return {
            "blocked": True, "scope": "project",
            "project_code": project_code, "count": len(outstanding),
            "amount": _money(sum(a.amount for a in outstanding)),
            "reason": (f"{len(outstanding)} advances on {project_code} are "
                       "overdue — a collective default. Policy: no payment for "
                       "the project's next activity until they are retired."),
        }
    return None


# ─── retiring ───────────────────────────────────────────────────────────────


def retire(org_id: str, advance_id: str, *, spent: float,
           actor: str, receipt_ids: Optional[list[str]] = None,
           note: str = "") -> Advance:
    """Settle an advance against what was actually spent.

    The arithmetic of comparing receipts to the advance belongs to receipts.py;
    this records the outcome and stops the clock. `direction` names who owes
    whom, because "balance: 12,000" tells a finance officer nothing on its own.
    """
    org = store.require_org(org_id)
    adv = get(org, advance_id)
    if adv is None:
        raise AdvanceError(f"Advance '{advance_id}' not found.")
    if not adv.open:
        raise AdvanceError(
            f"{adv.ref} is already {adv.status.value} and cannot be retired again.")

    spent = _money(spent)
    if spent < 0:
        raise AdvanceError("Spend cannot be negative.")

    balance = _money(adv.amount - spent)
    adv.spent = spent
    adv.balance = balance
    adv.direction = ("settled" if abs(balance) < 0.01
                     else "recover" if balance > 0 else "reimburse")
    adv.status = AdvanceStatus.RETIRED
    adv.retired_at = _now_iso()
    adv.retired_by = actor
    adv.receipt_ids = list(receipt_ids or [])
    if note:
        adv.notes.append(note)
    adv.notes.append(
        "Retired {} days {} the due date.".format(
            abs(days_overdue(adv)),
            "after" if days_overdue(adv) > 0 else "before"))
    return _save(org, adv)


def mark_recovered(org_id: str, advance_id: str, *, actor: str,
                   reason: str = "") -> Advance:
    """Record that an unretired advance was recovered from salary.

    The last rung. Kept as its own status rather than folded into "retired",
    because an advance recovered from someone's pay is a different fact from
    one properly accounted for, and an auditor should be able to count them.
    """
    org = store.require_org(org_id)
    adv = get(org, advance_id)
    if adv is None:
        raise AdvanceError(f"Advance '{advance_id}' not found.")
    if not adv.open:
        raise AdvanceError(f"{adv.ref} is already {adv.status.value}.")
    adv.status = AdvanceStatus.RECOVERED
    adv.retired_at = _now_iso()
    adv.retired_by = actor
    adv.balance = adv.amount
    adv.direction = "recover"
    adv.notes.append(f"Recovered from salary by {actor}"
                     + (f": {reason}" if reason else "."))
    return _save(org, adv)


def write_off(org_id: str, advance_id: str, *, actor: str, reason: str) -> Advance:
    """Accept the loss. A written reason is required and permanent.

    Writing off an advance means the organisation is absorbing money it cannot
    account for. That should be possible — sometimes a person leaves — and it
    should never be quiet.
    """
    if not (reason or "").strip():
        raise AdvanceError(
            "Writing off an advance requires a written reason. The "
            "organisation is absorbing money it cannot account for.")
    org = store.require_org(org_id)
    adv = get(org, advance_id)
    if adv is None:
        raise AdvanceError(f"Advance '{advance_id}' not found.")
    adv.status = AdvanceStatus.WRITTEN_OFF
    adv.retired_at = _now_iso()
    adv.retired_by = actor
    adv.notes.append(f"WRITTEN OFF by {actor}: {reason.strip()}")
    return _save(org, adv)
