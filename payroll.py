"""
Payroll & refinancing engine.

The monthly question this answers, for any donor-funded NGO:

    For every staff member paid this month:
      gross → statutory deductions → net
      WHICH DONOR and WHICH PROJECT CODE is funding them (and in what split)
      how many people did that work support, directly and indirectly
      what is recovered from donors ("refinancing"), carried as a NEGATIVE
    → then an approval flow, and ONLY once approved can payment go through.

All arithmetic is CODE. No LLM ever computes a salary, a deduction, an
allocation percentage or a recovery amount.

TWO DELIBERATE DESIGN DECISIONS
-------------------------------
1. **No invented tax bands.** Nigerian PAYE is progressive and changes with
   legislation; pension rates vary by scheme. Inventing them would produce
   confident, wrong payslips. Instead each organisation configures its own
   `DeductionRule`s (flat percent, progressive bands, or fixed amount). If a
   payroll runs with NO rules configured, every line is flagged rather than
   silently paying gross as net.

2. **Refinancing sign is configuration, not assumption.** "Total coming in
   refinancing comes as a negative" — the engine carries recovery with the sign
   the org specifies (`refinancing_sign`, default "negative", i.e. a credit that
   offsets the salary cost). Confirm the convention with finance before relying
   on the exported figures; flipping it is one setting, not a rewrite.

Storage is org-scoped (store.py), so every organisation's payroll is isolated.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

import store

_STAFF = "staff"
_POLICY = "payroll_policy"
_RUNS = "payroll_runs"

_TOLERANCE = 0.01          # allocation split tolerance, in percentage points
_POLICY_ID = "current"     # single active policy document per org


# ─── models ─────────────────────────────────────────────────────────────────


class SalaryAllocation(BaseModel):
    """Which donor/project funds what share of one person's salary.
    Percentages across a staff member MUST total 100."""
    project_code: str
    donor: str = ""
    percent: float = 0.0


class StaffRecord(BaseModel):
    id: str
    org_id: str = ""
    name: str
    position: str = ""
    office: str = ""                        # HQ / state / field
    gross_salary: float = 0.0               # monthly gross
    currency: str = "NGN"
    bank_account: str = ""
    bank_code: str = ""
    tax_id: str = ""                        # TIN / PAYE id
    pension_id: str = ""                    # RSA PIN
    allocations: list[SalaryAllocation] = Field(default_factory=list)
    active: bool = True


class DeductionRule(BaseModel):
    """One statutory (or other) deduction. Configured per org — never guessed.

    method:
      "percent" — rate_percent of the basis
      "bands"   — progressive: [(upper_bound, rate_percent), ...]; the final band
                  may use upper_bound = null to mean "and above"
      "fixed"   — a flat amount
    """
    code: str                               # e.g. "PAYE", "PENSION"
    name: str = ""
    method: Literal["percent", "bands", "fixed"] = "percent"
    rate_percent: float = 0.0
    bands: list[tuple[Optional[float], float]] = Field(default_factory=list)
    fixed_amount: float = 0.0
    basis: Literal["gross", "taxable"] = "gross"
    employer_paid: bool = False             # employer cost, not deducted from net
    statutory_reference: str = ""
    active: bool = True


class PayrollPolicy(BaseModel):
    org_id: str = ""
    rules: list[DeductionRule] = Field(default_factory=list)
    # See design note 2. "negative" = recovery shown as a credit against cost.
    refinancing_sign: Literal["negative", "positive"] = "negative"
    currency: str = "NGN"
    updated_at: Optional[str] = None


class DeductionResult(BaseModel):
    code: str
    name: str = ""
    basis_amount: float = 0.0
    amount: float = 0.0
    employer_paid: bool = False
    reference: str = ""


class PayrollLine(BaseModel):
    staff_id: str
    name: str
    position: str = ""
    office: str = ""
    gross: float = 0.0
    deductions: list[DeductionResult] = Field(default_factory=list)
    total_employee_deductions: float = 0.0
    total_employer_contributions: float = 0.0
    net: float = 0.0
    employer_cost: float = 0.0              # gross + employer contributions
    allocations: list[SalaryAllocation] = Field(default_factory=list)
    # WHERE THE SPLIT CAME FROM. An auditor's first question about a payroll
    # line charged to a grant is "how do you know they worked that much on it",
    # and "timesheet" and "budget" are very different answers:
    #
    #   "timesheet" — derived from approved, after-the-fact recorded hours.
    #                 Defensible under 2 CFR 200.430(i).
    #   "budget"    — the percentages someone typed into the staff record.
    #                 A plan, not evidence. Allowed here so payroll still runs,
    #                 but flagged on the line and counted on the run.
    allocation_source: Literal["timesheet", "budget", "none"] = "budget"
    timesheet_id: Optional[str] = None      # the evidence, if there is any
    hours_worked: float = 0.0
    # Amount recovered from donors for this person, carried with the org's sign
    # convention (default negative = a credit offsetting the salary cost).
    refinancing: float = 0.0
    # flags = DEFECTS. Something is wrong and must be fixed before approval.
    flags: list[str] = Field(default_factory=list)
    # notes = DISCLOSURES. Nothing is wrong, but an auditor should be told —
    # chiefly that a split came from a budget rather than recorded hours.
    # Keeping these apart is what lets payroll run for an organisation that has
    # not adopted timesheets, while still saying so on every affected line.
    notes: list[str] = Field(default_factory=list)


class PayrollRun(BaseModel):
    id: str
    org_id: str = ""
    period: str                             # "YYYY-MM"
    currency: str = "NGN"
    lines: list[PayrollLine] = Field(default_factory=list)
    total_gross: float = 0.0
    total_deductions: float = 0.0
    total_net: float = 0.0
    total_employer_cost: float = 0.0
    total_refinancing: float = 0.0          # signed
    by_project: dict[str, float] = Field(default_factory=dict)
    by_donor: dict[str, float] = Field(default_factory=dict)
    beneficiaries_direct: int = 0
    beneficiaries_indirect: int = 0
    staff_count: int = 0
    # How much of this run is backed by evidence. `lines_from_budget` is the
    # number an auditor will ask about, so it is on the run rather than
    # something you have to count by hand.
    lines_from_timesheet: int = 0
    lines_from_budget: int = 0
    flags: list[str] = Field(default_factory=list)
    # Workflow: the run is submitted as a transaction; payment only follows
    # approval. `txn_ref` is the human reference (e.g. PR12).
    status: Literal["draft", "submitted", "paid"] = "draft"
    txn_id: Optional[str] = None
    txn_ref: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def effort_verified(self) -> bool:
        """True when every allocated line came from approved recorded hours."""
        return self.lines_from_budget == 0 and self.lines_from_timesheet > 0


# ─── helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _money(x: float) -> float:
    return round(float(x or 0.0), 2)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ─── staff + policy ─────────────────────────────────────────────────────────


def add_staff(org_id: str, **kwargs) -> StaffRecord:
    org = store.require_org(org_id)
    staff = StaffRecord(id=kwargs.pop("id", None) or _new_id("stf"), org_id=org, **kwargs)
    store.get_store().put(org, _STAFF, staff.id, staff.model_dump())
    return staff


def list_staff(org_id: str, active_only: bool = True) -> list[StaffRecord]:
    org = store.require_org(org_id)
    rows = [StaffRecord.model_validate(r) for r in store.get_store().list(org, _STAFF)]
    return [s for s in rows if s.active] if active_only else rows


def set_policy(org_id: str, policy: PayrollPolicy) -> PayrollPolicy:
    org = store.require_org(org_id)
    policy.org_id = org
    policy.updated_at = _now_iso()
    store.get_store().put(org, _POLICY, _POLICY_ID, policy.model_dump())
    return policy


def get_policy(org_id: str) -> PayrollPolicy:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _POLICY, _POLICY_ID)
    return PayrollPolicy.model_validate(raw) if raw else PayrollPolicy(org_id=org)


# ─── deduction computation ──────────────────────────────────────────────────


def _apply_bands(amount: float, bands: list[tuple[Optional[float], float]]) -> float:
    """Progressive computation: each band's rate applies only to the portion of
    `amount` that falls inside it. Bands are (upper_bound, rate_percent), in
    ascending order; a final band with upper_bound None means 'and above'."""
    total = 0.0
    lower = 0.0
    for upper, rate in bands:
        ceiling = amount if upper is None else min(amount, float(upper))
        if ceiling > lower:
            total += (ceiling - lower) * (float(rate) / 100.0)
            lower = ceiling
        if upper is not None and amount <= float(upper):
            break
    return _money(total)


def compute_deductions(gross: float, policy: PayrollPolicy) -> list[DeductionResult]:
    """Apply every active rule to one gross salary. Pure arithmetic."""
    out: list[DeductionResult] = []
    for rule in policy.rules:
        if not rule.active:
            continue
        basis = _money(gross)   # "taxable" refines this once orgs define reliefs
        if rule.method == "percent":
            amount = _money(basis * (rule.rate_percent / 100.0))
        elif rule.method == "bands":
            amount = _apply_bands(basis, rule.bands)
        else:
            amount = _money(rule.fixed_amount)
        out.append(DeductionResult(
            code=rule.code, name=rule.name or rule.code, basis_amount=basis,
            amount=amount, employer_paid=rule.employer_paid,
            reference=rule.statutory_reference,
        ))
    return out


# ─── the payroll run ────────────────────────────────────────────────────────


def build_run(org_id: str, period: str, *,
              beneficiaries_direct: int = 0,
              beneficiaries_indirect: int = 0,
              staff: Optional[list[StaffRecord]] = None,
              use_timesheets: bool = True) -> PayrollRun:
    """Build the month's payroll: gross → deductions → net, allocated to donors
    and project codes, with refinancing carried at the org's sign convention.

    Never raises on bad data — a staff member whose allocation doesn't total 100%
    is FLAGGED (and excluded from donor/project roll-ups) rather than silently
    mis-charged to a grant. A payroll that quietly charges 97% to a donor is a
    compliance incident, so the run surfaces it and finance fixes it.
    """
    org = store.require_org(org_id)
    policy = get_policy(org)
    people = staff if staff is not None else list_staff(org)

    run_flags: list[str] = []
    if not [r for r in policy.rules if r.active]:
        run_flags.append(
            "No deduction rules configured — net equals gross. Configure PAYE / "
            "pension in the payroll policy before paying."
        )

    lines: list[PayrollLine] = []
    by_project: dict[str, float] = {}
    by_donor: dict[str, float] = {}

    for s in people:
        flags: list[str] = []
        gross = _money(s.gross_salary)
        deductions = compute_deductions(gross, policy)

        employee_total = _money(sum(d.amount for d in deductions if not d.employer_paid))
        employer_total = _money(sum(d.amount for d in deductions if d.employer_paid))
        net = _money(gross - employee_total)
        if net < 0:
            flags.append("Deductions exceed gross — check the rates.")
            net = 0.0

        # WHERE THE SPLIT COMES FROM — actual effort beats a budget, always.
        #
        # 2 CFR 200.430(i) permits charging a grant only for work actually
        # performed. Someone budgeted at 50% who worked 30% must cost the grant
        # 30%. So an approved timesheet for this period overrides whatever
        # percentages sit on the staff record, and the line records which was
        # used — because "how do you know they worked that much on it" is the
        # first question an auditor asks about a payroll line.
        notes: list[str] = []
        allocations = list(s.allocations)
        source: str = "budget" if allocations else "none"
        timesheet_id: Optional[str] = None
        hours_worked = 0.0

        if use_timesheets:
            try:
                import timesheets as _ts
                sheet = _ts.find_timesheet(org, s.id, period)
                if sheet and sheet.status in (_ts.TimesheetStatus.APPROVED,
                                              _ts.TimesheetStatus.PROCESSED):
                    effort = _ts.effort_allocation(sheet)
                    if effort:
                        donors = {a.project_code: a.donor for a in s.allocations}
                        allocations = [
                            SalaryAllocation(project_code=code,
                                             donor=donors.get(code, ""),
                                             percent=pct)
                            for code, pct in sorted(effort.items())
                        ]
                        source = "timesheet"
                        timesheet_id = sheet.id
                        hours_worked = sheet.total_hours
                        unknown = [c for c in effort if c not in donors]
                        if unknown:
                            notes.append(
                                "Hours booked to project code(s) with no donor on the "
                                f"staff record: {', '.join(sorted(unknown))}. The split "
                                "is correct; the donor roll-up will be incomplete.")
                elif sheet:
                    notes.append(
                        f"Timesheet for {period} is {sheet.status.value}, not approved — "
                        "falling back to the budgeted allocation.")
                else:
                    notes.append(
                        f"No timesheet for {period}. This split is BUDGETED, not "
                        "evidenced — a donor may disallow it.")
            except ImportError:
                pass

        # Allocation integrity: must total 100%.
        pct_total = _money(sum(a.percent for a in allocations))
        allocations_valid = bool(allocations) and abs(pct_total - 100.0) <= _TOLERANCE
        if not allocations:
            flags.append("No donor/project allocation — salary is unfunded and uncoded.")
        elif not allocations_valid:
            flags.append(
                f"Allocation totals {pct_total}% (must be 100%) — excluded from "
                "donor and project roll-ups until corrected."
            )
        if not allocations_valid:
            source = "none"

        # Employer cost is what the donor actually funds.
        employer_cost = _money(gross + employer_total)
        if allocations_valid:
            for a in allocations:
                share = _money(employer_cost * (a.percent / 100.0))
                by_project[a.project_code] = _money(by_project.get(a.project_code, 0.0) + share)
                if a.donor:
                    by_donor[a.donor] = _money(by_donor.get(a.donor, 0.0) + share)

        # Refinancing = what is recovered from donors for this person, carried
        # with the configured sign (default negative: a credit against cost).
        recovered = employer_cost if allocations_valid else 0.0
        refinancing = _money(-recovered if policy.refinancing_sign == "negative" else recovered)

        lines.append(PayrollLine(
            staff_id=s.id, name=s.name, position=s.position, office=s.office,
            gross=gross, deductions=deductions,
            total_employee_deductions=employee_total,
            total_employer_contributions=employer_total,
            net=net, employer_cost=employer_cost,
            allocations=allocations, refinancing=refinancing,
            flags=flags, notes=notes,
            allocation_source=source, timesheet_id=timesheet_id,
            hours_worked=hours_worked,
        ))

    run = PayrollRun(
        id=_new_id("pay"), org_id=org, period=period, currency=policy.currency,
        lines=lines,
        total_gross=_money(sum(l.gross for l in lines)),
        total_deductions=_money(sum(l.total_employee_deductions for l in lines)),
        total_net=_money(sum(l.net for l in lines)),
        total_employer_cost=_money(sum(l.employer_cost for l in lines)),
        total_refinancing=_money(sum(l.refinancing for l in lines)),
        by_project=by_project, by_donor=by_donor,
        beneficiaries_direct=beneficiaries_direct,
        beneficiaries_indirect=beneficiaries_indirect,
        staff_count=len(lines),
        lines_from_timesheet=sum(1 for l in lines if l.allocation_source == "timesheet"),
        lines_from_budget=sum(1 for l in lines if l.allocation_source == "budget"),
        flags=run_flags,
        created_at=_now_iso(),
    )

    # Say it once, loudly, on the run. Finding out at audit that half a
    # payroll was charged on budgeted percentages is a bad way to find out.
    if run.lines_from_budget:
        run.flags.append(
            f"{run.lines_from_budget} of {run.staff_count} salaries were allocated from "
            "BUDGETED percentages, not recorded hours. Donors may disallow the "
            "difference between budgeted and actual effort — collect the timesheets "
            "before this run is approved.")
    elif run.lines_from_timesheet:
        run.flags.append(
            f"All {run.lines_from_timesheet} allocations derive from approved timesheets.")
    _save(run)
    return run


def _save(run: PayrollRun) -> PayrollRun:
    run.updated_at = _now_iso()
    store.get_store().put(run.org_id, _RUNS, run.id, run.model_dump())
    return run


def get_run(org_id: str, run_id: str) -> Optional[PayrollRun]:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _RUNS, run_id)
    return PayrollRun.model_validate(raw) if raw else None


def list_runs(org_id: str) -> list[PayrollRun]:
    org = store.require_org(org_id)
    runs = [PayrollRun.model_validate(r) for r in store.get_store().list(org, _RUNS)]
    runs.sort(key=lambda r: r.period, reverse=True)
    return runs


# ─── approval flow ──────────────────────────────────────────────────────────


def submit_for_approval(org_id: str, run_id: str, *,
                        created_by: Optional[str] = None) -> PayrollRun:
    """Open a workflow transaction for the run and route it into review.

    Payment can only follow approval: the run stays 'submitted' until the
    transaction reaches the paid state (see mark_paid), and the transaction
    itself is governed by the same role-gated, in-app approval rules as every
    other payment in DOCex.
    """
    import transactions as tx  # local import: keeps this module import-light

    run = get_run(org_id, run_id)
    if run is None:
        raise ValueError(f"Payroll run '{run_id}' not found.")
    if run.txn_id:
        return run                                  # already submitted

    # `flags` are defects and block; `notes` are disclosures and do not. A line
    # allocated from a budget rather than recorded hours is disclosed on the
    # line and counted on the run — but blocking on it would mean no
    # organisation could run payroll until it had adopted timesheets.
    blocking = [l for l in run.lines if l.flags]
    if blocking:
        detail = "; ".join(
            f"{l.name}: {l.flags[0]}" for l in blocking[:3])
        raise ValueError(
            f"{len(blocking)} payroll line(s) have unresolved issues. {detail}"
            + ("…" if len(blocking) > 3 else "")
        )

    txn = tx.create(
        "payroll_run",
        f"Payroll — {run.period} ({run.staff_count} staff)",
        source_kind="payroll_run", source_id=run.id,
        amount=run.total_net, currency=run.currency, created_by=created_by,
    )
    txn = tx.transition(txn, "compliance_review", department="finance",
                        note=f"Payroll {run.period} submitted for review")
    run.txn_id, run.txn_ref, run.status = txn.id, txn.ref, "submitted"
    return _save(run)


def mark_paid(org_id: str, run_id: str) -> PayrollRun:
    """Record that an APPROVED run has been paid. Refuses unless the linked
    transaction actually reached 'paid' — the approval gate is the state
    machine, not this function's caller."""
    import transactions as tx

    run = get_run(org_id, run_id)
    if run is None:
        raise ValueError(f"Payroll run '{run_id}' not found.")
    if not run.txn_id:
        raise ValueError("This run has not been submitted for approval yet.")
    txn = tx.load(run.txn_id)
    if txn.state != "paid":
        raise ValueError(
            f"Payroll {run.period} is '{txn.state}', not approved for payment. "
            "Payment can only follow approval."
        )
    run.status = "paid"
    return _save(run)
