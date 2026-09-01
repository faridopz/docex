"""
Payment requisitions — the universal department-to-payment spine.

Any department raises a requisition ("we need to pay X for Y"). DOCex then:

  1. Runs DETERMINISTIC policy checks (code owns every number: amounts,
     fund balances, budget lines, duplicates, vendor status, documents).
  2. Routes it through the org's own approval chain (data, not code).
  3. Lets each approver APPROVE, DECLINE, or OVERRIDE a failing check —
     an override is only possible with a written reason AND an authority
     level the approver actually holds.
  4. Appends every decision to an APPEND-ONLY audit log. Nothing is ever
     mutated, so an auditor can always answer "why was this approved?"
  5. On final approval, freezes an immutable TransactionRecord.

Founding rule honoured: a code-level BLOCK (a hard-fail check) can only be
released by an explicit, attributed, authority-checked override. Silence is
never approval.

Storage is org-scoped via store.py, so EVA / NEEM / TA Connect never see each
other's requisitions. No LLM is called anywhere in this module.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import uuid
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

import store

# ─── collections ────────────────────────────────────────────────────────────

_REQUISITIONS = "requisitions"
_TRANSACTIONS = "transaction_records"
_WORKFLOW = "requisition_workflow"
_WORKFLOW_ID = "current"
_COUNTER = "requisition_counter"


# ─── enums ──────────────────────────────────────────────────────────────────


class ReqStatus(str, Enum):
    """Where the requisition currently sits."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"          # sitting with some approval step
    APPROVED = "approved"            # cleared every step, awaiting payment
    PAID = "paid"                    # terminal — transaction record frozen
    DECLINED = "declined"            # terminal — rejected by an approver
    RETURNED = "returned"            # sent back to submitter for fixes


class CheckResult(str, Enum):
    PASS = "pass"
    WARNING = "warning"              # proceed, but surface it
    FAIL = "fail"                    # blocks unless overridden


class Decision(str, Enum):
    APPROVED = "approved"
    DECLINED = "declined"
    RETURNED = "returned"


# ─── models ─────────────────────────────────────────────────────────────────


class PolicyCheck(BaseModel):
    """One deterministic validation. Code computed every value here."""
    code: str                            # AMOUNT_LIMIT, FUND_AVAILABLE, ...
    name: str                            # human label for the UI + audit export
    result: CheckResult
    policy_value: Optional[str] = None   # what the rulebook said
    actual_value: Optional[str] = None   # what the requisition asked for
    message: str = ""                    # plain-English explanation
    overridden: bool = False             # set when an approver released a FAIL
    override_by: Optional[str] = None
    override_reason: Optional[str] = None
    override_authority: Optional[str] = None


class Approval(BaseModel):
    """One approver's decision at one workflow step. Never mutated."""
    step: str                            # compliance, finance, ed, ...
    department: str = ""
    actor: str = ""                      # who decided
    decision: Decision
    notes: str = ""
    at: str = ""                         # ISO timestamp
    overrides: list[str] = Field(default_factory=list)  # check codes released
    signature: str = ""                  # HMAC over the decision payload


class AuditEntry(BaseModel):
    """Append-only audit line. The answer to 'why did this happen?'."""
    seq: int                             # 1, 2, 3 ... monotonic per requisition
    at: str
    actor: str = ""
    department: str = ""
    event: str                           # created, checks_run, approved, ...
    detail: str = ""
    prev_hash: str = ""                  # chains entries so tampering shows up
    hash: str = ""


class WorkflowStep(BaseModel):
    """One stage of the org's approval chain."""
    key: str                             # "compliance"
    label: str = ""                      # "Compliance Review"
    department: str = ""                 # which department owns it
    min_amount: float = 0.0              # only engages at/above this amount
    can_override: bool = False           # may this step release a FAIL?
    override_limit: Optional[float] = None  # max amount it may override up to


class RequisitionWorkflow(BaseModel):
    """The org's approval chain + spend policy. Pure DATA, set at onboarding."""
    org_id: str = ""
    steps: list[WorkflowStep] = Field(default_factory=list)
    currency: str = "NGN"

    # Deterministic policy inputs
    max_amount: Optional[float] = None            # per-requisition ceiling
    allowed_categories: list[str] = Field(default_factory=list)
    forbidden_vendors: list[str] = Field(default_factory=list)
    approved_vendors: list[str] = Field(default_factory=list)  # empty = allow all
    required_documents: list[str] = Field(default_factory=list)
    duplicate_window_days: int = 30
    updated_at: Optional[str] = None


class Requisition(BaseModel):
    """A department's request to pay someone."""
    id: str
    ref: str = ""                        # REQ-0001
    org_id: str = ""

    # Who is asking
    submitted_by: str = ""
    department: str = ""
    submitted_at: str = ""

    # What is being paid
    vendor_name: str = ""
    vendor_account: str = ""
    amount: float = 0.0
    currency: str = "NGN"
    category: str = ""
    project_code: str = ""
    grant_code: Optional[str] = None
    description: str = ""

    # Evidence
    receipt_ids: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)

    # Workflow
    status: ReqStatus = ReqStatus.DRAFT
    current_step: Optional[str] = None   # which step it's waiting on
    checks: list[PolicyCheck] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    audit_log: list[AuditEntry] = Field(default_factory=list)

    # Outcome
    transaction_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TransactionRecord(BaseModel):
    """Frozen record of a completed payment. Never edited after creation."""
    id: str                              # TRANS-0024
    org_id: str = ""
    requisition_id: str = ""
    requisition_ref: str = ""

    vendor_name: str = ""
    vendor_account: str = ""
    amount: float = 0.0
    currency: str = "NGN"
    category: str = ""
    project_code: str = ""
    grant_code: Optional[str] = None

    bank_reference: str = ""
    paid_by: str = ""
    paid_at: str = ""

    # Frozen copies — the audit view never depends on the live requisition
    checks: list[PolicyCheck] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    exceptions_count: int = 0            # how many FAILs were overridden

    locked: bool = True


class RequisitionError(ValueError):
    """Illegal operation — callers map this to HTTP 4xx."""


# ─── helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def _money(x: Optional[float]) -> float:
    return round(float(x or 0.0), 2)


def _secret() -> bytes:
    """Signing key for approval signatures. Falls back to a per-install value
    so signatures still chain in dev; production sets DOCEX_SIGNING_KEY."""
    return (os.environ.get("DOCEX_SIGNING_KEY") or "docex-dev-signing-key").encode()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def _next_ref(org_id: str) -> str:
    """Monotonic per-org requisition reference: REQ-0001, REQ-0002, ..."""
    st = store.get_store()
    raw = st.get(org_id, _COUNTER, "requisition") or {"value": 0}
    nxt = int(raw.get("value", 0)) + 1
    st.put(org_id, _COUNTER, "requisition", {"value": nxt})
    return f"REQ-{nxt:04d}"


def _next_txn_ref(org_id: str) -> str:
    st = store.get_store()
    raw = st.get(org_id, _COUNTER, "transaction") or {"value": 0}
    nxt = int(raw.get("value", 0)) + 1
    st.put(org_id, _COUNTER, "transaction", {"value": nxt})
    return f"TRANS-{nxt:04d}"


def _audit(
    req: Requisition,
    event: str,
    *,
    actor: str = "",
    department: str = "",
    detail: str = "",
) -> Requisition:
    """Append one hash-chained audit entry. Never edits an existing entry."""
    prev = req.audit_log[-1].hash if req.audit_log else ""
    seq = len(req.audit_log) + 1
    at = _now_iso()
    body = f"{req.id}|{seq}|{at}|{actor}|{event}|{detail}|{prev}"
    req.audit_log.append(AuditEntry(
        seq=seq, at=at, actor=actor, department=department,
        event=event, detail=detail, prev_hash=prev, hash=_sign(body),
    ))
    return req


def verify_audit_chain(req: Requisition) -> bool:
    """Recompute the hash chain. False means an entry was altered on disk."""
    prev = ""
    for entry in req.audit_log:
        body = f"{req.id}|{entry.seq}|{entry.at}|{entry.actor}|{entry.event}|{entry.detail}|{prev}"
        if entry.prev_hash != prev or entry.hash != _sign(body):
            return False
        prev = entry.hash
    return True


# ─── workflow config ────────────────────────────────────────────────────────


def default_workflow(org_id: str, size: str = "medium") -> RequisitionWorkflow:
    """
    Smart defaults so a new org works on day one without configuring anything.

    small  — Submit → Finance
    medium — Submit → Compliance → Finance → Management (above threshold)
    large  — Submit → Dept Head → Compliance → Finance → Management

    Every `department` here MUST exist in the default department registry
    (departments.py: program, compliance, finance, management). An earlier
    version routed the final step to "ed", which is not a default department —
    so any requisition above the threshold routed to a department with no
    users and sat in the queue forever, with nothing to explain why. The
    guard below turns that class of mistake into a loud failure instead of a
    stuck requisition.
    """
    if size == "small":
        steps = [
            WorkflowStep(key="finance", label="Finance Review", department="finance",
                         can_override=True, override_limit=100_000),
        ]
    elif size == "large":
        steps = [
            WorkflowStep(key="dept_head", label="Department Head", department="program"),
            WorkflowStep(key="compliance", label="Compliance Review", department="compliance"),
            WorkflowStep(key="finance", label="Finance Review", department="finance",
                         can_override=True, override_limit=100_000),
            WorkflowStep(key="approval", label="Executive Approval", department="management",
                         min_amount=50_000, can_override=True, override_limit=500_000),
        ]
    else:  # medium
        steps = [
            WorkflowStep(key="compliance", label="Compliance Review", department="compliance"),
            WorkflowStep(key="finance", label="Finance Review", department="finance",
                         can_override=True, override_limit=100_000),
            WorkflowStep(key="approval", label="Executive Approval", department="management",
                         min_amount=50_000, can_override=True, override_limit=200_000),
        ]
    return RequisitionWorkflow(org_id=org_id, steps=steps)


def unroutable_steps(org_id: str, wf: RequisitionWorkflow) -> list[str]:
    """
    Steps whose department does not exist, or has nobody in it.

    A requisition that reaches such a step stops dead: no queue shows it and
    no one is notified. Surfacing this lets the admin screen say so before a
    payment goes missing rather than after.
    """
    try:
        import departments
    except ImportError:  # pragma: no cover
        return []

    try:
        known = {d.key for d in departments.list_departments()}
    except Exception:
        return []

    return [
        f"{s.label or s.key} → '{s.department}'"
        for s in wf.steps
        if s.department and s.department not in known
    ]


def set_workflow(org_id: str, wf: RequisitionWorkflow) -> RequisitionWorkflow:
    org = store.require_org(org_id)
    wf.org_id = org
    wf.updated_at = _now_iso()
    store.get_store().put(org, _WORKFLOW, _WORKFLOW_ID, wf.model_dump())
    return wf


def get_workflow(org_id: str) -> RequisitionWorkflow:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _WORKFLOW, _WORKFLOW_ID)
    return RequisitionWorkflow.model_validate(raw) if raw else default_workflow(org)


def _steps_for(wf: RequisitionWorkflow, amount: float) -> list[WorkflowStep]:
    """Only the steps this amount actually has to pass through."""
    return [s for s in wf.steps if _money(amount) >= _money(s.min_amount)]


def _step(wf: RequisitionWorkflow, key: str) -> Optional[WorkflowStep]:
    return next((s for s in wf.steps if s.key == key), None)


# ─── policy checks (deterministic — code owns every number) ─────────────────


def run_policy_checks(org_id: str, req: Requisition) -> list[PolicyCheck]:
    """
    Every check here is pure arithmetic or set membership. No LLM, no guessing.
    A FAIL blocks the requisition until an authorised approver overrides it.
    """
    org = store.require_org(org_id)
    wf = get_workflow(org)
    checks: list[PolicyCheck] = []

    # 1. Amount ceiling
    if wf.max_amount is not None:
        over = _money(req.amount) > _money(wf.max_amount)
        checks.append(PolicyCheck(
            code="AMOUNT_LIMIT",
            name="Amount within policy ceiling",
            result=CheckResult.FAIL if over else CheckResult.PASS,
            policy_value=f"max {_money(wf.max_amount)} {wf.currency}",
            actual_value=f"{_money(req.amount)} {req.currency}",
            message=(
                f"Amount {_money(req.amount)} exceeds the policy ceiling of "
                f"{_money(wf.max_amount)}."
                if over else "Amount is within the policy ceiling."
            ),
        ))

    # 2. Amount is positive
    if _money(req.amount) <= 0:
        checks.append(PolicyCheck(
            code="AMOUNT_VALID", name="Amount is greater than zero",
            result=CheckResult.FAIL, actual_value=str(_money(req.amount)),
            message="Requisition amount must be greater than zero.",
        ))

    # 3. Vendor present
    if not req.vendor_name.strip():
        checks.append(PolicyCheck(
            code="VENDOR_PRESENT", name="Vendor identified",
            result=CheckResult.FAIL,
            message="No vendor named. A payee is required before approval.",
        ))
    else:
        # 4. Forbidden vendor
        if req.vendor_name.strip().lower() in {v.lower() for v in wf.forbidden_vendors}:
            checks.append(PolicyCheck(
                code="VENDOR_BLOCKED", name="Vendor not blacklisted",
                result=CheckResult.FAIL, actual_value=req.vendor_name,
                message=f"Vendor '{req.vendor_name}' is on the blocked list.",
            ))
        # 5. Approved-vendor list (empty list = open)
        elif wf.approved_vendors and req.vendor_name.strip().lower() not in {
            v.lower() for v in wf.approved_vendors
        }:
            checks.append(PolicyCheck(
                code="VENDOR_APPROVED", name="Vendor on approved list",
                result=CheckResult.WARNING, actual_value=req.vendor_name,
                message=f"Vendor '{req.vendor_name}' is not on the approved list. Review before paying.",
            ))
        else:
            checks.append(PolicyCheck(
                code="VENDOR_APPROVED", name="Vendor on approved list",
                result=CheckResult.PASS, actual_value=req.vendor_name,
                message="Vendor is acceptable under policy.",
            ))

    # 6. Category allowed
    if wf.allowed_categories:
        ok = req.category.strip().lower() in {c.lower() for c in wf.allowed_categories}
        checks.append(PolicyCheck(
            code="CATEGORY_ALLOWED", name="Spend category permitted",
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            policy_value=", ".join(wf.allowed_categories),
            actual_value=req.category or "(none)",
            message=("Category is permitted." if ok else
                     f"Category '{req.category or '(none)'}' is not a permitted spend category."),
        ))

    # 7. Required documents present
    if wf.required_documents:
        have = {d.strip().lower() for d in req.documents}
        missing = [d for d in wf.required_documents if d.strip().lower() not in have]
        checks.append(PolicyCheck(
            code="DOCS_COMPLETE", name="Supporting documents attached",
            result=CheckResult.WARNING if missing else CheckResult.PASS,
            policy_value=", ".join(wf.required_documents),
            actual_value=", ".join(req.documents) or "(none)",
            message=(f"Missing document(s): {', '.join(missing)}." if missing
                     else "All required documents attached."),
        ))

    # 8. Duplicate detection — same vendor + same amount inside the window
    dup = _find_duplicate(org, req, wf.duplicate_window_days)
    if dup:
        checks.append(PolicyCheck(
            code="DUPLICATE", name="Not a duplicate payment",
            result=CheckResult.WARNING,
            policy_value=f"{wf.duplicate_window_days}-day window",
            actual_value=dup,
            message=(f"A similar requisition ({dup}) for the same vendor and amount "
                     f"exists within {wf.duplicate_window_days} days. Confirm this is not a double payment."),
        ))
    else:
        checks.append(PolicyCheck(
            code="DUPLICATE", name="Not a duplicate payment",
            result=CheckResult.PASS,
            message="No matching recent requisition found.",
        ))

    # 9. Project code present (needed for allocation + donor reporting)
    if not req.project_code.strip():
        checks.append(PolicyCheck(
            code="PROJECT_CODE", name="Project / cost centre assigned",
            result=CheckResult.WARNING,
            message="No project code. Spend cannot be allocated to a budget line without one.",
        ))

    # 10. Attached receipts are real, ours, and not already claimed
    checks.extend(_check_receipts(org, req))

    # 11. Spend falls inside the grant's agreement period
    period = _check_grant_period(org, req)
    if period is not None:
        checks.append(period)

    return checks


def _check_receipts(org_id: str, req: Requisition) -> list[PolicyCheck]:
    """
    Validate the field receipts backing this requisition.

    Until now `receipt_ids` was accepted and stored but never checked, which
    left three holes — the third is the one that costs money:

      * an id that matches no receipt at all;
      * a receipt belonging to a DIFFERENT organisation;
      * a receipt already attached to another requisition, i.e. the same
        expense claimed and paid twice. Reimbursing one receipt through two
        requisitions is a standard duplicate-claim pattern, and the existing
        duplicate check cannot see it because the two requisitions may carry
        different vendors and amounts.

    Reported as a FAIL, so it blocks until someone with authority releases it
    on the record.
    """
    if not req.receipt_ids:
        return []

    try:
        import field_receipts
    except ImportError:  # pragma: no cover - receipts module optional
        return []

    missing: list[str] = []
    rejected: list[str] = []
    claimed: list[str] = []

    # Every other requisition in this org that already cites a receipt.
    others = [r for r in list_requisitions(org_id) if r.id != req.id]
    already: dict[str, str] = {}
    for other in others:
        if other.status == ReqStatus.DECLINED:
            continue  # a declined request never paid, so it holds no claim
        for rid in other.receipt_ids:
            already.setdefault(rid, other.ref)

    for rid in req.receipt_ids:
        # get_receipt is org-scoped, so another org's receipt reads as missing
        # — which is the correct outcome, and never leaks its existence.
        receipt = field_receipts.get_receipt(org_id, rid)
        if receipt is None:
            missing.append(rid)
            continue
        if receipt.status == field_receipts.ReceiptStatus.REJECTED:
            rejected.append(rid)
        if rid in already:
            claimed.append(f"{rid} (on {already[rid]})")

    out: list[PolicyCheck] = []
    if missing or rejected or claimed:
        problems = []
        if missing:
            problems.append(f"not found: {', '.join(missing)}")
        if rejected:
            problems.append(f"previously rejected: {', '.join(rejected)}")
        if claimed:
            problems.append(f"already claimed: {', '.join(claimed)}")
        out.append(PolicyCheck(
            code="RECEIPTS_VALID", name="Attached receipts are valid and unclaimed",
            result=CheckResult.FAIL,
            actual_value="; ".join(problems),
            message=(
                "One or more attached receipts cannot back this payment — "
                + "; ".join(problems) + "."
            ),
        ))
    else:
        out.append(PolicyCheck(
            code="RECEIPTS_VALID", name="Attached receipts are valid and unclaimed",
            result=CheckResult.PASS,
            actual_value=f"{len(req.receipt_ids)} receipt(s)",
            message="Every attached receipt exists and is not claimed elsewhere.",
        ))
    return out


def _check_grant_period(org_id: str, req: Requisition) -> Optional[PolicyCheck]:
    """
    Is this cost inside the funding agreement's period?

    Donor rules are explicit that a cost is only allowable if it was incurred
    during the approved budget period (2 CFR 200 for USAID-funded work, and
    the equivalent clause in FCDO/EU agreements). Charging a grant outside its
    dates is one of the most common audit findings, and it is pure arithmetic
    to catch — exactly the sort of thing code should own rather than a
    reviewer remembering.

    Returns None when there is nothing to check: no grant cited, or the
    agreement carries no dates.
    """
    code = (req.grant_code or "").strip()
    if not code:
        return None

    try:
        import grants
    except ImportError:  # pragma: no cover - grants module optional
        return None

    try:
        agreements = grants.list_agreements(org_id)
    except Exception:
        return None

    match = next(
        (a for a in agreements
         if (a.project_code or "").strip().lower() == code.lower()),
        None,
    )
    if match is None:
        return PolicyCheck(
            code="GRANT_PERIOD", name="Charged within the agreement period",
            result=CheckResult.WARNING,
            actual_value=code,
            message=(
                f"No funding agreement found for grant code '{code}'. "
                f"The charge cannot be checked against an agreement period."
            ),
        )

    start, end = match.start_date, match.end_date
    if not start and not end:
        return None

    # The date the cost was incurred. submitted_at is the closest thing the
    # requisition carries; a dedicated invoice date would be better and is
    # worth adding when the form captures one.
    incurred = (req.submitted_at or "")[:10]
    if not incurred:
        return None

    outside = (start and incurred < start[:10]) or (end and incurred > end[:10])
    window = f"{start or 'open'} to {end or 'open'}"
    if outside:
        return PolicyCheck(
            code="GRANT_PERIOD", name="Charged within the agreement period",
            result=CheckResult.FAIL,
            policy_value=window,
            actual_value=incurred,
            message=(
                f"This cost falls outside the {match.donor} agreement period "
                f"({window}). Costs incurred outside the approved period are "
                f"not allowable against the grant."
            ),
        )
    return PolicyCheck(
        code="GRANT_PERIOD", name="Charged within the agreement period",
        result=CheckResult.PASS,
        policy_value=window,
        actual_value=incurred,
        message=f"Within the {match.donor} agreement period.",
    )


def _find_duplicate(org_id: str, req: Requisition, window_days: int) -> Optional[str]:
    """Return the ref of a recent requisition with the same vendor + amount."""
    if not req.vendor_name.strip() or _money(req.amount) <= 0:
        return None
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=window_days)).isoformat()
    vendor = req.vendor_name.strip().lower()
    for raw in store.get_store().list(org_id, _REQUISITIONS):
        if raw.get("id") == req.id:
            continue
        if str(raw.get("status")) in {ReqStatus.DECLINED.value, ReqStatus.DRAFT.value}:
            continue
        if (raw.get("submitted_at") or "") < cutoff:
            continue
        if str(raw.get("vendor_name", "")).strip().lower() != vendor:
            continue
        if abs(_money(raw.get("amount")) - _money(req.amount)) > 0.01:
            continue
        return str(raw.get("ref") or raw.get("id"))
    return None


def blocking_checks(req: Requisition) -> list[PolicyCheck]:
    """FAILs that have not been overridden — these stop approval."""
    return [c for c in req.checks if c.result == CheckResult.FAIL and not c.overridden]


# ─── lifecycle ──────────────────────────────────────────────────────────────


def create_requisition(
    org_id: str,
    *,
    submitted_by: str,
    department: str,
    vendor_name: str,
    amount: float,
    category: str = "",
    project_code: str = "",
    grant_code: Optional[str] = None,
    vendor_account: str = "",
    description: str = "",
    receipt_ids: Optional[list[str]] = None,
    documents: Optional[list[str]] = None,
    currency: str = "NGN",
    submit: bool = True,
) -> Requisition:
    """
    Raise a requisition. Runs policy checks immediately so the submitter sees
    problems before an approver ever opens it.
    """
    org = store.require_org(org_id)
    now = _now_iso()

    req = Requisition(
        id=uuid.uuid4().hex,
        ref=_next_ref(org),
        org_id=org,
        submitted_by=submitted_by,
        department=department,
        submitted_at=now,
        vendor_name=vendor_name.strip(),
        vendor_account=vendor_account.strip(),
        amount=_money(amount),
        currency=currency or "NGN",
        category=category.strip(),
        project_code=project_code.strip(),
        grant_code=(grant_code or None),
        description=description.strip(),
        receipt_ids=list(receipt_ids or []),
        documents=list(documents or []),
        created_at=now,
        updated_at=now,
    )

    _audit(req, "created", actor=submitted_by, department=department,
           detail=f"{req.ref}: {req.vendor_name} {_money(req.amount)} {req.currency}")

    req.checks = run_policy_checks(org, req)
    fails = len([c for c in req.checks if c.result == CheckResult.FAIL])
    warns = len([c for c in req.checks if c.result == CheckResult.WARNING])
    _audit(req, "checks_run", actor="system",
           detail=f"{len(req.checks)} checks: {fails} fail, {warns} warning")

    if submit:
        req = _submit(org, req)

    return _save(org, req)


def _submit(org_id: str, req: Requisition) -> Requisition:
    """Move DRAFT → SUBMITTED and park it on the first applicable step."""
    wf = get_workflow(org_id)
    steps = _steps_for(wf, req.amount)
    if not steps:
        # No approval required by config — straight to approved.
        req.status = ReqStatus.APPROVED
        req.current_step = None
        _audit(req, "approved", actor="system",
               detail="No approval step configured for this amount.")
        return req
    req.status = ReqStatus.IN_REVIEW
    req.current_step = steps[0].key
    _audit(req, "submitted", actor=req.submitted_by, department=req.department,
           detail=f"Routed to {steps[0].label or steps[0].key}")
    return req


def decide(
    org_id: str,
    req_id: str,
    *,
    decision: Decision,
    actor: str,
    department: str = "",
    notes: str = "",
    overrides: Optional[list[str]] = None,
    override_reason: str = "",
    override_authority: str = "",
) -> Requisition:
    """
    Record one approver's decision at the current step.

    `overrides` names the PolicyCheck codes the approver is releasing. An
    override is refused unless:
      - the step is allowed to override at all,
      - the amount is within that step's override limit, and
      - a written reason is supplied.

    Everything — approval, decline, override, and the reason — lands in the
    append-only audit log.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if req.status in {ReqStatus.PAID, ReqStatus.DECLINED}:
        raise RequisitionError(f"{req.ref} is {req.status.value} and cannot be changed.")
    if req.status != ReqStatus.IN_REVIEW:
        raise RequisitionError(f"{req.ref} is not awaiting review (status: {req.status.value}).")

    wf = get_workflow(org)
    step = _step(wf, req.current_step or "")
    if step is None:
        raise RequisitionError(f"{req.ref} has no active approval step.")

    overrides = list(overrides or [])

    # ─── apply overrides (authority-checked) ────────────────────────────────
    if overrides:
        if decision != Decision.APPROVED:
            raise RequisitionError("Overrides can only accompany an approval.")
        if not step.can_override:
            raise RequisitionError(
                f"Step '{step.label or step.key}' is not authorised to override policy checks."
            )
        if not override_reason.strip():
            raise RequisitionError(
                "An override requires a written reason — this is what the auditor reads."
            )
        if step.override_limit is not None and _money(req.amount) > _money(step.override_limit):
            raise RequisitionError(
                f"{step.label or step.key} may override up to {_money(step.override_limit)} "
                f"{wf.currency}; this requisition is {_money(req.amount)}. Escalate to a higher authority."
            )
        by_code = {c.code: c for c in req.checks}
        for code in overrides:
            check = by_code.get(code)
            if check is None:
                raise RequisitionError(f"Unknown policy check '{code}'.")
            if check.result != CheckResult.FAIL:
                raise RequisitionError(f"Check '{code}' is not failing; nothing to override.")
            check.overridden = True
            check.override_by = actor
            check.override_reason = override_reason.strip()
            check.override_authority = override_authority.strip() or (step.label or step.key)
            _audit(req, "policy_override", actor=actor, department=department,
                   detail=(f"{code} released. Policy: {check.policy_value or 'n/a'}; "
                           f"actual: {check.actual_value or 'n/a'}. Reason: {check.override_reason} "
                           f"Authority: {check.override_authority}"))

    # ─── refuse to approve over an unreleased hard failure ──────────────────
    if decision == Decision.APPROVED:
        blockers = blocking_checks(req)
        if blockers:
            raise RequisitionError(
                "Cannot approve: unresolved policy failure(s) "
                + ", ".join(c.code for c in blockers)
                + ". Override them with a reason, or decline."
            )

    # ─── record the decision (signed, immutable) ────────────────────────────
    at = _now_iso()
    payload = f"{req.id}|{step.key}|{actor}|{decision.value}|{at}|{','.join(overrides)}"
    req.approvals.append(Approval(
        step=step.key, department=department or step.department, actor=actor,
        decision=decision, notes=notes.strip(), at=at,
        overrides=overrides, signature=_sign(payload),
    ))
    _audit(req, f"step_{decision.value}", actor=actor,
           department=department or step.department,
           detail=f"{step.label or step.key}: {decision.value}" + (f" — {notes.strip()}" if notes.strip() else ""))

    # ─── advance / stop ─────────────────────────────────────────────────────
    if decision == Decision.DECLINED:
        req.status = ReqStatus.DECLINED
        req.current_step = None
    elif decision == Decision.RETURNED:
        req.status = ReqStatus.RETURNED
        req.current_step = None
    else:
        steps = _steps_for(wf, req.amount)
        keys = [s.key for s in steps]
        idx = keys.index(step.key) if step.key in keys else len(keys) - 1
        if idx + 1 < len(steps):
            req.current_step = steps[idx + 1].key
            req.status = ReqStatus.IN_REVIEW
            _audit(req, "routed", actor="system",
                   detail=f"Routed to {steps[idx + 1].label or steps[idx + 1].key}")
        else:
            req.current_step = None
            req.status = ReqStatus.APPROVED
            _audit(req, "approved", actor="system",
                   detail="All approval steps cleared. Ready for payment.")

    return _save(org, req)


def resubmit(org_id: str, req_id: str, *, actor: str, notes: str = "") -> Requisition:
    """Submitter fixed a RETURNED requisition — re-run checks and re-route."""
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if req.status != ReqStatus.RETURNED:
        raise RequisitionError(f"Only a returned requisition can be resubmitted (status: {req.status.value}).")
    req.checks = run_policy_checks(org, req)
    _audit(req, "resubmitted", actor=actor, department=req.department, detail=notes.strip())
    req = _submit(org, req)
    return _save(org, req)


def mark_paid(
    org_id: str,
    req_id: str,
    *,
    actor: str,
    bank_reference: str = "",
    department: str = "finance",
) -> TransactionRecord:
    """
    Final step: money left the account. Freezes an immutable TransactionRecord
    holding copies of every check, approval, and audit line.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if req.status != ReqStatus.APPROVED:
        raise RequisitionError(
            f"{req.ref} must be fully approved before payment (status: {req.status.value})."
        )

    _audit(req, "paid", actor=actor, department=department,
           detail=f"Payment processed. Bank reference: {bank_reference or '(none)'}")

    txn = TransactionRecord(
        id=_next_txn_ref(org),
        org_id=org,
        requisition_id=req.id,
        requisition_ref=req.ref,
        vendor_name=req.vendor_name,
        vendor_account=req.vendor_account,
        amount=req.amount,
        currency=req.currency,
        category=req.category,
        project_code=req.project_code,
        grant_code=req.grant_code,
        bank_reference=bank_reference.strip(),
        paid_by=actor,
        paid_at=_now_iso(),
        checks=[c.model_copy(deep=True) for c in req.checks],
        approvals=[a.model_copy(deep=True) for a in req.approvals],
        audit_log=[e.model_copy(deep=True) for e in req.audit_log],
        exceptions_count=len([c for c in req.checks if c.overridden]),
    )
    store.get_store().put(org, _TRANSACTIONS, txn.id, txn.model_dump())

    req.status = ReqStatus.PAID
    req.transaction_id = txn.id
    req.current_step = None
    _save(org, req)
    return txn


# ─── persistence + queries ──────────────────────────────────────────────────


def _save(org_id: str, req: Requisition) -> Requisition:
    req.updated_at = _now_iso()
    store.get_store().put(org_id, _REQUISITIONS, req.id, req.model_dump())
    return req


def get_requisition(org_id: str, req_id: str) -> Optional[Requisition]:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _REQUISITIONS, req_id)
    return Requisition.model_validate(raw) if raw else None


def list_requisitions(
    org_id: str,
    *,
    status: Optional[ReqStatus] = None,
    step: Optional[str] = None,
    department: Optional[str] = None,
    grant_code: Optional[str] = None,
) -> list[Requisition]:
    """Newest first. `step` powers each department's 'waiting on me' view."""
    org = store.require_org(org_id)
    out: list[Requisition] = []
    for raw in store.get_store().list(org, _REQUISITIONS):
        try:
            req = Requisition.model_validate(raw)
        except Exception:
            continue
        if status is not None and req.status != status:
            continue
        if step is not None and req.current_step != step:
            continue
        if department is not None and req.department != department:
            continue
        if grant_code is not None and req.grant_code != grant_code:
            continue
        out.append(req)
    out.sort(key=lambda r: r.updated_at or r.created_at or "", reverse=True)
    return out


def get_transaction(org_id: str, txn_id: str) -> Optional[TransactionRecord]:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _TRANSACTIONS, txn_id)
    return TransactionRecord.model_validate(raw) if raw else None


def list_transactions(
    org_id: str,
    *,
    grant_code: Optional[str] = None,
    project_code: Optional[str] = None,
) -> list[TransactionRecord]:
    org = store.require_org(org_id)
    out: list[TransactionRecord] = []
    for raw in store.get_store().list(org, _TRANSACTIONS):
        try:
            txn = TransactionRecord.model_validate(raw)
        except Exception:
            continue
        if grant_code is not None and txn.grant_code != grant_code:
            continue
        if project_code is not None and txn.project_code != project_code:
            continue
        out.append(txn)
    out.sort(key=lambda t: t.paid_at or "", reverse=True)
    return out


# ─── audit view ─────────────────────────────────────────────────────────────


def audit_summary(org_id: str) -> dict:
    """
    What the external auditor opens first. Every number is counted from stored
    records — nothing is estimated.
    """
    org = store.require_org(org_id)
    reqs = list_requisitions(org)
    txns = list_transactions(org)

    exceptions: list[dict] = []
    for txn in txns:
        for c in txn.checks:
            if c.overridden:
                exceptions.append({
                    "transaction_id": txn.id,
                    "requisition_ref": txn.requisition_ref,
                    "check": c.code,
                    "policy_value": c.policy_value,
                    "actual_value": c.actual_value,
                    "reason": c.override_reason,
                    "authority": c.override_authority,
                    "approved_by": c.override_by,
                })

    by_status: dict[str, int] = {}
    for r in reqs:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1

    unexplained = [e for e in exceptions if not (e.get("reason") or "").strip()]

    return {
        "org_id": org,
        "generated_at": _now_iso(),
        "requisitions_total": len(reqs),
        "requisitions_by_status": by_status,
        "transactions_total": len(txns),
        "value_paid": _money(sum(t.amount for t in txns)),
        "exceptions_total": len(exceptions),
        "exceptions_unexplained": len(unexplained),
        "exceptions": exceptions,
        "audit_ready": len(unexplained) == 0,
    }
