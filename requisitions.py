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
import threading
import uuid
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

import departments
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
    ON_HOLD = "on_hold"              # paused at its current step, not decided
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


class Payee(BaseModel):
    """One line of a multi-payee requisition — a workshop stipend list, a
    beneficiary payout, a batch of vendor payments raised as one request.

    Mirrors NEEM's own Advance/Reimbursement Request Form ("Section B: PAYEE
    ... Below table can be replicated if the payees are more than one"), so a
    requisition raised this way captures the same fields their paper memo
    already required — nothing invented, nothing dropped.
    """
    name: str = ""                       # as it appears on the bank statement
    account_number: str = ""
    bank_name: str = ""
    amount: float = 0.0
    purpose: str = ""                    # this payee's line item, if it differs
    tin: str = ""
    phone_or_email: str = ""
    payee_type: Literal["staff", "vendor", "beneficiary"] = "vendor"


class BudgetLine(BaseModel):
    """One line of the expense breakdown — mirrors NEEM's own memo table
    ("Description/Item, Unit of Measurement, Budget Line, Quantity,
    Frequency, Unit Cost, Total Amount") rather than inventing a shape of
    our own. `line_total` is ALWAYS code-computed as
    quantity * frequency * unit_cost (DETERMINISTIC-FIRST, CLAUDE.md: code
    owns every number) — a submitter's typed total is never trusted, so the
    route layer discards any client-supplied value and requisitions.py
    recomputes it on every create/edit. See _priced_budget_lines().
    """
    description: str = ""
    unit: str = ""                # "Pieces", "Packs", "Carton", "Person", ...
    budget_line: str = ""         # the org's own budget-line code/label —
                                   # distinct from `project_code` on the
                                   # requisition itself (memo keeps them as
                                   # separate columns)
    quantity: float = 1.0
    frequency: float = 1.0
    unit_cost: float = 0.0
    line_total: float = 0.0       # computed — never accepted from a client


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


class Attachment(BaseModel):
    """A real file on a requisition — the invoice itself, a signed memo, a
    beneficiary list, a photo of a receipt. Deliberately separate from
    `documents: list[str]` below, which is a POLICY checklist ("do we have
    an invoice on file" — a label, ticked or not, checked by
    _check_documents). This is the actual bytes NEEM asked to attach "as
    many files as possible" — the label without the file behind it was
    exactly the gap flagged after the pilot handoff.

    Metadata only. The bytes live wherever attachments.py is configured to
    put them (local disk in dev, Supabase Storage in production) —
    `storage_key` is opaque outside that module; nothing here interprets it.
    """
    id: str
    filename: str = ""
    content_type: str = ""
    size: int = 0
    storage_key: str = ""
    uploaded_by: str = ""
    uploaded_at: str = ""


class ComplianceFinding(BaseModel):
    """One rule's verdict against this requisition's attached documents.

    Deliberately a separate, minimal model rather than importing
    compliance.py's RuleResult directly (see the module docstring's "No LLM
    is called anywhere in this module" — this module never imports the
    compliance engine or its models; api/requisition_routes.py, which DOES
    call compliance.py, translates its RuleResult into this shape at the
    route boundary, the same way it already translates UploadFile into
    Attachment). Keeps requisitions.py self-contained and free to change
    independently of the compliance module's own (larger) schema.
    """
    rule_id: str
    rule_description: str = ""
    verdict: Literal["pass", "flag", "block", "not_applicable", "insufficient_evidence"]
    reasoning: str = ""
    policy_citation: Optional[str] = None      # quote from the policy
    payment_evidence: Optional[str] = None     # quote from the attached document
    applied_to_document: Optional[str] = None  # which attachment this was evaluated against


class ComplianceSummary(BaseModel):
    """Snapshot of the last compliance-rulebook check run against this
    requisition's real attachments (WO-22 made those attachments possible;
    this is what WO-21 uses them for).

    Separate from `checks` (PolicyCheck) below — those are this engine's own
    DETERMINISTIC policy checks (amount ceiling, vendor list, required
    documents — code owns every number, per CLAUDE.md). This is the
    AI-assisted rulebook check from compliance.py: semantic judgement against
    a policy document, attached by reference. A code-level PolicyCheck FAIL
    is never softened by a clean compliance verdict, or vice versa — the two
    live side by side on the requisition, not merged into one verdict.

    Re-running a check overwrites this snapshot with the latest result; the
    full history of every run (verdict, rulebook, timestamp) still survives
    in audit_log, exactly like every other mutation on this record.
    """
    rulebook_id: str
    rulebook_name: str
    overall_verdict: Literal["approved", "flagged", "blocked"]
    overall_summary: str = ""
    results: list[ComplianceFinding] = Field(default_factory=list)
    document_count: int = 0            # how many attachments were actually read
    checked_by: str = ""
    checked_at: str = ""


class Comment(BaseModel):
    """One message on a requisition's discussion thread — separate from
    Approval.notes (the one-shot remark attached to a single decision).
    NEEM's ask was that anyone able to see a request can also discuss it,
    at any point in its life, not only the person currently deciding it —
    so comments carry no step and are not restricted to IN_REVIEW the way
    decide() is. Append-only, like everything else in this model: no edit,
    no delete, so the thread is exactly what an auditor would have seen at
    the time."""
    id: str
    author: str = ""                     # email
    department: str = ""
    text: str = ""
    at: str = ""                         # ISO timestamp


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


class CCRule(BaseModel):
    """Someone copied on a requisition once its amount crosses a threshold —
    informed, never asked to act. Copies a whole department, specific named
    individuals (by email), or both; at least one of `department`/`emails`
    should be set or the rule notifies nobody.

    Deliberately separate from WorkflowStep: `decide()` only ever checks a
    step's department, so being CC'd — by department OR by name — can never
    let someone approve or override a requisition they were only copied on.
    NEEM's own workflow document draws exactly this line — the AED and
    Director of Operations are added to the copy list well before either is
    required to sign off. NEEM asked specifically for named individuals, not
    just a department, once account-holders exist to name.
    """
    min_amount: float = 0.0
    department: str = ""
    label: str = ""                      # "Executive Director", shown in the notification
    # Named individuals, by email, copied in ADDITION to `department` (which
    # may be left blank for a rule that only names people, no department).
    emails: list[str] = Field(default_factory=list)


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
    # A batch of participant/vendor payments raised as one requisition. NEEM
    # names 100 as their real ceiling (their weekly GTBank GAPS schedule has
    # to hold it); kept configurable rather than hard-coded so a different
    # client's actual bank batch limit doesn't silently inherit NEEM's number.
    max_payees: int = 100
    cc_rules: list[CCRule] = Field(default_factory=list)
    # Per-category packs. NEEM's own deck says it plainly: "the correct pack
    # depends on whether it concerns goods, services, an activity, an advance,
    # a reimbursement or a final balance payment." One flat list asks a
    # N40,000 reimbursement for the same evidence as a N3m equipment purchase,
    # which trains people to ignore the check — and an ignored check is worse
    # than no check. A category with no entry falls back to required_documents.
    documents_by_category: dict[str, list[str]] = Field(default_factory=dict)
    duplicate_window_days: int = 30
    # Compliance rulebook (compliance.py / api/compliance_routes.py) this
    # org's requisitions are checked against when an approver runs a
    # compliance check (gated on requisition_compliance_check). None = no
    # rulebook configured — the check endpoint refuses with a clear message
    # rather than silently checking against nothing. Deliberately NOT
    # validated here: rulebooks live in a different store collection this
    # module never otherwise touches, and one can be deleted after a
    # workflow references it — the check endpoint is where that's caught,
    # at the moment it actually matters.
    rulebook_id: Optional[str] = None
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

    # Payee detail beyond the bare name/account — the same fields NEEM's own
    # Advance/Reimbursement Request Form and Payment Voucher already ask for
    # (bank, TIN, phone/email), captured here for the single-vendor path.
    # The multi-payee path already carries these per-row on Payee — this is
    # the single-payee equivalent, not a replacement for it.
    vendor_bank_name: str = ""
    vendor_tin: str = ""
    vendor_phone_or_email: str = ""

    # "This request is for full payment, 70% advance payment, or 30% balance
    # payment" — NEEM's memo template's own wording, kept as a real field
    # rather than free text buried in `description` so the export and any
    # future policy check can read it directly.
    payment_type: Literal["full", "advance", "balance"] = "full"

    # The expense breakdown a memo's item table asks for. Optional: a
    # requisition raised with none just shows `amount` as a single line on
    # export, exactly like every requisition before this field existed.
    # Totals are always code-computed — see BudgetLine and
    # _priced_budget_lines().
    budget_lines: list[BudgetLine] = Field(default_factory=list)

    # Evidence
    receipt_ids: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)

    # Multi-payee batch (workshop stipends, beneficiary payouts, ...). Empty
    # for the ordinary single-vendor requisition — every existing caller is
    # unaffected. When populated, `amount` above is always the sum of these
    # and `vendor_name` is the batch's title/purpose, not a payee's name.
    payees: list[Payee] = Field(default_factory=list)

    # Workflow
    status: ReqStatus = ReqStatus.DRAFT
    current_step: Optional[str] = None   # which step it's waiting on
    checks: list[PolicyCheck] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    # Last compliance-rulebook check run against this requisition's real
    # attachments, if any (see ComplianceSummary). None until a check has
    # been run at least once.
    compliance: Optional[ComplianceSummary] = None

    # Set only while status == ON_HOLD; cleared the moment the hold is
    # released. The full history of every hold/release survives in
    # audit_log regardless — these three describe the CURRENT pause, not a
    # log of past ones, matching how the rest of this model treats live
    # state (e.g. current_step) versus history.
    hold_reason: Optional[str] = None
    held_by: Optional[str] = None
    held_at: Optional[str] = None

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
    payees: list[Payee] = Field(default_factory=list)  # frozen copy, see Requisition.payees

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


def _priced_budget_lines(lines: Optional[list[BudgetLine]]) -> list[BudgetLine]:
    """Recompute every line's total as quantity * frequency * unit_cost,
    discarding whatever the caller put in `line_total`. DETERMINISTIC-FIRST
    (CLAUDE.md): a typed total that disagrees with its own quantity/rate is
    exactly the mistake this engine exists to catch, not repeat — the same
    reasoning create_requisition() already applies to a multi-payee batch's
    total versus its rows.
    """
    out: list[BudgetLine] = []
    for bl in lines or []:
        priced = bl.model_copy()
        priced.line_total = _money(priced.quantity * priced.frequency * priced.unit_cost)
        out.append(priced)
    return out


_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
          "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
          "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")
_CURRENCY_WORDS = {
    "NGN": ("Naira", "Kobo"), "USD": ("Dollars", "Cents"), "GBP": ("Pounds", "Pence"),
    "EUR": ("Euros", "Cents"), "GHS": ("Cedis", "Pesewas"), "KES": ("Shillings", "Cents"),
}


def _three_digit_words(n: int) -> str:
    words = []
    if n >= 100:
        words.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        tens_word = _TENS[n // 10]
        if n % 10:
            words.append(f"{tens_word}-{_ONES[n % 10]}")
        else:
            words.append(tens_word)
    elif n > 0:
        words.append(_ONES[n])
    return " ".join(words)


def _int_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    scales = (("Billion", 1_000_000_000), ("Million", 1_000_000), ("Thousand", 1_000))
    parts: list[str] = []
    for name, size in scales:
        if n >= size:
            parts.append(f"{_three_digit_words(n // size)} {name}")
            n %= size
    if n:
        parts.append(_three_digit_words(n))
    return " ".join(parts)


def amount_in_words(amount: float, currency: str = "NGN") -> str:
    """"Sixty Thousand Naira Only" / "One Hundred Twenty Thousand Naira, Fifty
    Kobo Only" — the line NEEM's own memo template asks for by name ("Amount
    in Words") and the Payment Voucher has a blank line for. Computed, never
    typed, so it can never disagree with the figure above it (the same
    DETERMINISTIC-FIRST reasoning as _priced_budget_lines: a number an
    approver reads on a printed voucher must match the number they signed
    against).
    """
    major_name, minor_name = _CURRENCY_WORDS.get(currency, ("Units", "Cents"))
    cents_total = round(abs(amount) * 100)
    major, minor = divmod(cents_total, 100)
    words = f"{_int_to_words(int(major))} {major_name}"
    if minor:
        words += f", {_int_to_words(int(minor))} {minor_name}"
    return f"{words} Only"


def _secret() -> bytes:
    """Signing key for approval signatures. Falls back to a per-install value
    so signatures still chain in dev; production sets DOCEX_SIGNING_KEY."""
    return (os.environ.get("DOCEX_SIGNING_KEY") or "docex-dev-signing-key").encode()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


# Two people submitting a requisition, or two finance officers paying one,
# in the same instant is not an edge case for a multi-user finance tool — it
# is Tuesday. Without a lock, _next_ref/_next_txn_ref is a plain
# read-then-write across two separate store calls: both requests can read the
# same counter value before either writes it back, and both walk away with
# REQ-0006 while the counter only advances by one. The fix mirrors the one
# transactions.py already uses for the same failure shape (see its
# _ref_lock/_next_number): a process-level lock, which covers every thread in
# today's single-instance deployment (render.yaml runs one web service). If
# DOCex ever runs more than one instance, this needs a real database sequence
# — written down here so that failure shows up as a design note, not as two
# payments sharing a reference number that an auditor finds later.
_req_ref_lock = threading.Lock()
_txn_ref_lock = threading.Lock()


def _next_ref(org_id: str) -> str:
    """Monotonic per-org requisition reference: REQ-0001, REQ-0002, ..."""
    with _req_ref_lock:
        st = store.get_store()
        raw = st.get(org_id, _COUNTER, "requisition") or {"value": 0}
        nxt = int(raw.get("value", 0)) + 1
        st.put(org_id, _COUNTER, "requisition", {"value": nxt})
        return f"REQ-{nxt:04d}"


def _next_txn_ref(org_id: str) -> str:
    with _txn_ref_lock:
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
        known = {d.key for d in departments.list_departments(org_id)}
    except Exception:
        return []

    return [
        f"{s.label or s.key} → '{s.department}'"
        for s in wf.steps
        if s.department and s.department not in known
    ]


def validate_workflow(org_id: str, wf: RequisitionWorkflow) -> list[str]:
    """Check a workflow is internally consistent BEFORE it's saved.

    The failure mode these checks exist for is a requisition stuck at a step
    nobody can ever act on — invisible until a real payment hits it, and by
    then it's a client asking why their voucher has gone silent. These are
    the same checks org_config.validate_profile applies at onboarding
    (config → CLI path); this is the same rules on the config → live-editing
    path (org settings screen → PUT /requisitions/workflow), which had none.
    """
    errors: list[str] = []
    known = set(departments.keys(org_id))
    seen_keys: set[str] = set()
    for step in wf.steps:
        key = (step.key or "").strip()
        if not key:
            errors.append("A workflow step is missing its key.")
            continue
        if key in seen_keys:
            errors.append(f"Duplicate workflow step key '{key}'.")
        seen_keys.add(key)
        dept = (step.department or "").strip()
        if not dept:
            errors.append(f"Step '{key}' has no department.")
        elif dept not in known:
            errors.append(
                f"Step '{key}' routes to '{dept}', which is not one of this "
                f"org's departments ({', '.join(sorted(known)) or 'none defined'})."
            )
        if step.can_override and step.override_limit is not None and \
                _money(step.override_limit) < _money(step.min_amount):
            errors.append(
                f"Step '{key}': override_limit ({step.override_limit}) is below "
                f"min_amount ({step.min_amount}) — it could never override anything "
                "it actually sees."
            )
    if wf.max_amount is not None and wf.max_amount <= 0:
        errors.append("max_amount must be positive if set.")
    return errors


def set_workflow(org_id: str, wf: RequisitionWorkflow) -> RequisitionWorkflow:
    org = store.require_org(org_id)
    errors = validate_workflow(org, wf)
    if errors:
        raise RequisitionError("Invalid workflow: " + "; ".join(errors))
    wf.org_id = org
    wf.updated_at = _now_iso()
    store.get_store().put(org, _WORKFLOW, _WORKFLOW_ID, wf.model_dump())
    return wf


def has_workflow_configured(org_id: str) -> bool:
    """True once an admin has actually saved a workflow — as opposed to
    get_workflow()'s unpersisted default_workflow() fallback, which exists so
    the engine never 500s on a brand-new org but does NOT mean anyone has
    configured anything. This is the signal the onboarding wizard uses to
    decide whether to show itself: a store record for real, not a guess."""
    org = store.require_org(org_id)
    return store.get_store().get(org, _WORKFLOW, _WORKFLOW_ID) is not None


def get_workflow(org_id: str) -> RequisitionWorkflow:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _WORKFLOW, _WORKFLOW_ID)
    return RequisitionWorkflow.model_validate(raw) if raw else default_workflow(org)


def required_documents_for(wf: RequisitionWorkflow, category: str) -> list[str]:
    """The document pack for this kind of payment.

    A goods purchase needs a GRN; a workshop needs an attendance list and a
    payment sheet; a travel advance needs a travel approval form beforehand and
    an unreceipted expenses form afterwards. Asking for all of them on every
    payment is how a check becomes noise.

    Falls back to the org-wide list when a category has no pack of its own, so
    an organisation that has not configured packs is unaffected.
    """
    want = (category or "").strip().lower()
    for key, docs in (wf.documents_by_category or {}).items():
        if key.strip().lower() == want:
            return list(docs)
    return list(wf.required_documents)


def _steps_for(wf: RequisitionWorkflow, amount: float) -> list[WorkflowStep]:
    """Only the steps this amount actually has to pass through."""
    return [s for s in wf.steps if _money(amount) >= _money(s.min_amount)]


def _step(wf: RequisitionWorkflow, key: str) -> Optional[WorkflowStep]:
    return next((s for s in wf.steps if s.key == key), None)


def cc_recipients(wf: RequisitionWorkflow, amount: float) -> list[CCRule]:
    """Which CC rules this amount triggers.

    Every matching rule fires — unlike approval steps, being CC'd is
    additive rather than a ladder, so crossing both a 2,000,000 and a
    5,000,000 threshold copies both departments, not just the higher one.
    A rule with neither a department nor any named emails notifies nobody,
    so it's excluded rather than returned as a no-op the caller has to
    notice on its own. Pure and side-effect-free: the caller (the route
    layer, matching where every other notification is emitted — see
    notify_transition's callers) decides how to act on the result.
    """
    return [r for r in wf.cc_rules
            if (r.department or r.emails) and _money(amount) >= _money(r.min_amount)]


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

    # 3. Vendor / title present. In multi-payee mode this is the batch's
    # title ("Workshop stipends — Abuja cohort"), not one payee's name — the
    # payee list gets its own validation (_check_payees) instead of the
    # single-vendor checks below, which are meaningless against a title.
    if not req.vendor_name.strip():
        checks.append(PolicyCheck(
            code="VENDOR_PRESENT", name="Vendor identified",
            result=CheckResult.FAIL,
            message="No vendor named. A payee is required before approval.",
        ))
    elif req.payees:
        checks.extend(_check_payees(req))
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

        # 5b. Vendor register: is this payee verified?
        vendor_check = _check_vendor_register(org_id, req)
        if vendor_check is not None:
            checks.append(vendor_check)

    # 5c. Outstanding advances. Checked here, on a NEW request, because that is
    #     where the policy costs the person the thing they want at the moment
    #     they want it. A rule enforced only in a month-end report is a rule
    #     nobody changes their behaviour for.
    advance_check = _check_outstanding_advances(org_id, req)
    if advance_check is not None:
        checks.append(advance_check)

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

    # 7. Required documents present — for THIS kind of payment
    required = required_documents_for(wf, req.category)
    if required:
        have = {d.strip().lower() for d in req.documents}
        missing = [d for d in required if d.strip().lower() not in have]
        specific = (req.category or "").strip().lower() in {
            k.strip().lower() for k in wf.documents_by_category}
        # A FAIL, not a warning. It was a warning, which meant a requisition
        # with no memo, no invoice, nothing attached could be approved with no
        # override and no written reason — the nineteen document packs in
        # NEEM's profile were advisory. Their Finance/Audit step exists to
        # "check the pack and return it until satisfied"; a warning is clicked
        # past, a FAIL with an override reason is recorded. That reason
        # ("invoice to follow, vendor confirmed by phone") is exactly the
        # audit line the override mechanism was built to capture.
        checks.append(PolicyCheck(
            code="DOCS_COMPLETE", name="Supporting documents attached",
            result=CheckResult.FAIL if missing else CheckResult.PASS,
            policy_value=", ".join(required),
            actual_value=", ".join(req.documents) or "(none)",
            message=(
                (f"Missing document(s) for a {req.category} payment: "
                 f"{', '.join(missing)}." if specific else
                 f"Missing document(s): {', '.join(missing)}.")
                if missing else
                (f"All documents required for a {req.category} payment are "
                 "attached." if specific else "All required documents attached.")),
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


def _check_vendor_register(org_id: str, req: Requisition) -> Optional[PolicyCheck]:
    """Is the payee a known, checked vendor?

    Gated on the `vendor_register` feature flag, and silent when the register
    is empty — an organisation that has not adopted it should not have every
    requisition suddenly carrying a warning about a screen they have never
    opened.

    The severity ladder is deliberate:

      * bank account says a DIFFERENT name  → FAIL. This is what diverted-
        payment fraud looks like from the inside: a genuine invoice from a
        genuine supplier, with the account number changed. Every other field on
        the requisition is correct, so nothing else in the chain would catch it.
      * vendor blocked                      → FAIL.
      * account never checked, or unknown payee → WARNING. Informative, not
        blocking: plenty of legitimate one-off payees never enter a register.
      * TIN structurally invalid            → WARNING, and the message says
        exactly what a format check does and does not prove.
    """
    try:
        import org_config
        if not org_config.feature_enabled(org_id, "vendor_register"):
            return None
        import vendors as _v
    except ImportError:                                       # pragma: no cover
        return None

    try:
        register = _v.list_vendors(org_id)
    except Exception:                                         # pragma: no cover
        return None
    if not register:
        return None

    vendor = _v.find_by_name(org_id, req.vendor_name)
    if vendor is None:
        return PolicyCheck(
            code="VENDOR_VERIFIED", name="Payee verified",
            result=CheckResult.WARNING, actual_value=req.vendor_name,
            message=(f"'{req.vendor_name}' is not in the vendor register, so "
                     "their bank account has not been verified. Add them, or "
                     "confirm the account details by hand before paying."),
        )

    if vendor.blocked:
        return PolicyCheck(
            code="VENDOR_VERIFIED", name="Payee verified",
            result=CheckResult.FAIL, actual_value=vendor.name,
            message=f"{vendor.name} is blocked: {vendor.blocked_reason}",
        )

    bank = vendor.bank
    if bank.status == _v.VerificationStatus.MISMATCH:
        return PolicyCheck(
            code="VENDOR_VERIFIED", name="Payee verified",
            result=CheckResult.FAIL, actual_value=vendor.name,
            policy_value=bank.resolved_name,
            message=(f"The bank holds account {bank.account_number} in the name "
                     f"'{bank.resolved_name}', not '{vendor.name}'. Do not pay "
                     "until this is explained."),
        )
    if bank.status == _v.VerificationStatus.WARNING:
        return PolicyCheck(
            code="VENDOR_VERIFIED", name="Payee verified",
            result=CheckResult.WARNING, actual_value=vendor.name,
            policy_value=bank.resolved_name,
            message=(f"The bank holds this account as '{bank.resolved_name}' — "
                     f"close to '{vendor.name}' but not identical. Confirm it is "
                     "the same organisation."),
        )
    if bank.status != _v.VerificationStatus.VERIFIED:
        return PolicyCheck(
            code="VENDOR_VERIFIED", name="Payee verified",
            result=CheckResult.WARNING, actual_value=vendor.name,
            message=(f"{vendor.name} is in the register but their bank account "
                     "has not been verified. Run the check before paying."),
        )

    if vendor.tax.status == _v.VerificationStatus.INVALID:
        return PolicyCheck(
            code="VENDOR_VERIFIED", name="Payee verified",
            result=CheckResult.WARNING, actual_value=vendor.name,
            message=(f"Bank account confirmed, but the tax ID on file is not "
                     f"valid: {vendor.tax.message}"),
        )

    tin_note = ("tax ID confirmed with the authority"
                if vendor.tax.externally_verified else
                "tax ID format checked only — not confirmed with the authority"
                if vendor.tin else "no tax ID on file")
    return PolicyCheck(
        code="VENDOR_VERIFIED", name="Payee verified",
        result=CheckResult.PASS, actual_value=vendor.name,
        policy_value=bank.resolved_name,
        message=(f"Bank account {bank.account_number} confirmed as "
                 f"'{bank.resolved_name}'; {tin_note}."),
    )


def _check_payees(req: Requisition) -> list[PolicyCheck]:
    """Validate a multi-payee batch the way a single vendor is validated above.

    A row with no name or no positive amount is not a payment — it is a blank
    line that slipped through the form, and paying it means either nothing
    happens (harmless) or the wrong person gets paid (not harmless). FAIL,
    same as an unnamed vendor, so it needs an override with a reason rather
    than a shrug at payment time.
    """
    bad = [f"row {i + 1}" for i, p in enumerate(req.payees)
           if not p.name.strip() or _money(p.amount) <= 0]
    if bad:
        return [PolicyCheck(
            code="PAYEES_VALID", name="Every payee has a name and an amount",
            result=CheckResult.FAIL,
            actual_value=", ".join(bad),
            message=(f"Incomplete payee row(s): {', '.join(bad)}. Each payee "
                     "needs a name and an amount greater than zero."),
        )]
    return [PolicyCheck(
        code="PAYEES_VALID", name="Every payee has a name and an amount",
        result=CheckResult.PASS,
        actual_value=f"{len(req.payees)} payee(s)",
        message="Every payee row is complete.",
    )]


def _check_outstanding_advances(org_id: str,
                                req: Requisition) -> Optional[PolicyCheck]:
    """Does an unretired advance bar this payment?

    NEEM's policy, written down in their own deck: an overdue advance means no
    further payment to that individual; a collective default blocks the
    project's next activity. This turns both into a FAIL that an authorised
    approver can still override with a written reason — because sometimes the
    activity genuinely cannot wait, and that decision should carry a name.

    Silent when the feature is off or no advance is outstanding.
    """
    try:
        import org_config
        if not org_config.feature_enabled(org_id, "advance_retirement"):
            return None
        import advances as _adv
    except ImportError:                                        # pragma: no cover
        return None

    try:
        block = _adv.payment_block(org_id, staff_id=req.submitted_by,
                                   project_code=req.project_code)
    except Exception:                                          # pragma: no cover
        return None
    if not block:
        return None

    return PolicyCheck(
        code="ADVANCE_OUTSTANDING",
        name="No unretired advance blocking payment",
        result=CheckResult.FAIL,
        policy_value=("No further payment while an advance is overdue"
                      if block["scope"] == "staff" else
                      "No payment for a project in collective default"),
        actual_value=(block.get("advance_ref") or block.get("project_code", "")),
        message=block["reason"],
    )


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
    vendor_bank_name: str = "",
    vendor_tin: str = "",
    vendor_phone_or_email: str = "",
    payment_type: str = "full",
    budget_lines: Optional[list[BudgetLine]] = None,
    description: str = "",
    receipt_ids: Optional[list[str]] = None,
    documents: Optional[list[str]] = None,
    payees: Optional[list[Payee]] = None,
    currency: str = "NGN",
    submit: bool = True,
) -> Requisition:
    """
    Raise a requisition. Runs policy checks immediately so the submitter sees
    problems before an approver ever opens it.

    `payees`, when given, raises a multi-payee batch instead of a single
    payment — a workshop's stipend list, a beneficiary payout run. Gated on
    the `multi_payee_requisitions` flag so an org that hasn't adopted it can't
    have a batch land in front of an approver who's never seen the shape
    before. `amount` is always recomputed as the sum of the payees; whatever
    was passed for it is ignored, on purpose — one caller passing a total
    that disagrees with its own line items is exactly the mistake this
    engine exists to catch, not repeat.
    """
    org = store.require_org(org_id)
    now = _now_iso()
    payees = list(payees or [])

    if payees:
        try:
            import org_config
            multi_payee_on = org_config.feature_enabled(org, "multi_payee_requisitions")
        except ImportError:  # pragma: no cover
            multi_payee_on = False
        if not multi_payee_on:
            raise RequisitionError(
                "This organisation has not enabled multi-payee requisitions "
                "('multi_payee_requisitions' feature flag). Raise this as a "
                "single-vendor requisition, or enable the flag first."
            )
        cap = get_workflow(org).max_payees or 100
        if len(payees) > cap:
            raise RequisitionError(
                f"This requisition names {len(payees)} payees, above this "
                f"organisation's limit of {cap} in one batch. Split it into "
                "more than one requisition."
            )
        amount = sum(p.amount for p in payees)

    payment_type = (payment_type or "full").strip().lower()
    if payment_type not in ("full", "advance", "balance"):
        raise RequisitionError(
            f"payment_type must be 'full', 'advance', or 'balance', not '{payment_type}'."
        )

    req = Requisition(
        id=uuid.uuid4().hex,
        ref=_next_ref(org),
        org_id=org,
        submitted_by=submitted_by,
        department=department,
        submitted_at=now,
        vendor_name=vendor_name.strip(),
        vendor_account=vendor_account.strip(),
        vendor_bank_name=vendor_bank_name.strip(),
        vendor_tin=vendor_tin.strip(),
        vendor_phone_or_email=vendor_phone_or_email.strip(),
        payment_type=payment_type,
        budget_lines=_priced_budget_lines(budget_lines),
        amount=_money(amount),
        currency=currency or "NGN",
        category=category.strip(),
        project_code=project_code.strip(),
        grant_code=(grant_code or None),
        description=description.strip(),
        receipt_ids=list(receipt_ids or []),
        documents=list(documents or []),
        payees=payees,
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


_DRAFT_EDITABLE = (
    "vendor_name", "vendor_account", "vendor_bank_name", "vendor_tin",
    "vendor_phone_or_email", "payment_type", "budget_lines", "amount",
    "currency", "category", "project_code", "grant_code", "description",
    "receipt_ids", "documents", "payees",
)


def update_draft(org_id: str, req_id: str, *, actor: str, **fields) -> Requisition:
    """Edit a draft and re-run its policy checks.

    ONLY drafts. Once something is submitted it is a claim someone else is
    acting on, and silently changing the amount underneath an approver is the
    kind of thing an audit trail exists to prevent. Editing a submitted
    requisition means returning it first, which is recorded.

    Checks re-run on every edit, so the person filling the form sees the
    consequence of a change immediately rather than discovering it at submit.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"No requisition {req_id}.")
    if req.status != ReqStatus.DRAFT:
        raise RequisitionError(
            f"{req.ref} is {req.status.value}, not a draft. Return it first if it "
            "needs changing — an approver may already have acted on these figures."
        )

    changed: list[str] = []
    for key, value in fields.items():
        if value is None or key not in _DRAFT_EDITABLE:
            continue
        if key == "amount":
            value = _money(value)
        elif key == "budget_lines":
            value = _priced_budget_lines(value)
        elif key == "payment_type":
            value = (value or "full").strip().lower()
            if value not in ("full", "advance", "balance"):
                raise RequisitionError(
                    f"payment_type must be 'full', 'advance', or 'balance', not '{value}'."
                )
        if getattr(req, key) != value:
            setattr(req, key, value)
            changed.append(key)

    # Editing the payee list changes what's owed — the total must always be
    # their sum, never a stale figure left over from before the edit. This is
    # also the ONLY other place (besides create_requisition) a draft's payee
    # list can be set, so the same flag + cap enforcement applies here — a
    # draft created single-vendor and edited into a batch afterwards must not
    # be able to skip the check just because it took the update_draft path.
    if "payees" in changed and req.payees:
        try:
            import org_config
            multi_payee_on = org_config.feature_enabled(org, "multi_payee_requisitions")
        except ImportError:  # pragma: no cover
            multi_payee_on = False
        if not multi_payee_on:
            raise RequisitionError(
                "This organisation has not enabled multi-payee requisitions "
                "('multi_payee_requisitions' feature flag)."
            )
        cap = get_workflow(org).max_payees or 100
        if len(req.payees) > cap:
            raise RequisitionError(
                f"This draft names {len(req.payees)} payees, above this "
                f"organisation's limit of {cap} in one batch."
            )
        new_total = _money(sum(p.amount for p in req.payees))
        if req.amount != new_total:
            req.amount = new_total
            if "amount" not in changed:
                changed.append("amount")

    if changed:
        _audit(req, "draft_edited", actor=actor, department=req.department,
               detail="Changed: " + ", ".join(sorted(changed)))
        req.checks = run_policy_checks(org, req)
        fails = len([c for c in req.checks if c.result == CheckResult.FAIL])
        warns = len([c for c in req.checks if c.result == CheckResult.WARNING])
        _audit(req, "checks_run", actor="system",
               detail=f"{len(req.checks)} checks: {fails} fail, {warns} warning")
        req.updated_at = _now_iso()
    return _save(org, req)


def submit_draft(org_id: str, req_id: str, *, actor: str) -> Requisition:
    """Send a draft into the approval chain.

    Re-runs the checks first. A draft written last week may have become
    non-compliant since — a grant can close, a vendor can be blocked, an
    identical invoice can arrive in between. Submitting on stale checks would
    put a stale answer in front of an approver.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"No requisition {req_id}.")
    if req.status != ReqStatus.DRAFT:
        raise RequisitionError(f"{req.ref} has already been submitted.")
    if not req.vendor_name.strip():
        raise RequisitionError("A draft needs a vendor before it can be submitted.")
    if _money(req.amount) <= 0:
        raise RequisitionError("A draft needs an amount above zero before it can be submitted.")

    req.checks = run_policy_checks(org, req)
    fails = len([c for c in req.checks if c.result == CheckResult.FAIL])
    warns = len([c for c in req.checks if c.result == CheckResult.WARNING])
    _audit(req, "checks_run", actor="system",
           detail=f"re-checked at submit — {len(req.checks)} checks: {fails} fail, {warns} warning")
    req = _submit(org, req)
    req.updated_at = _now_iso()
    return _save(org, req)


def discard_draft(org_id: str, req_id: str, *, actor: str) -> bool:
    """Delete a draft. Only ever a draft — anything submitted is part of the
    record and gets declined, not deleted."""
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        return False
    if req.status != ReqStatus.DRAFT:
        raise RequisitionError(
            f"{req.ref} is {req.status.value} and part of the record. "
            "Decline it instead — submitted requisitions are never deleted."
        )
    return store.get_store().delete(org, _REQUISITIONS, req_id)


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

    # ─── the step belongs to a department; only that department may act ────
    #
    # This check was missing. `department or step.department` below quietly
    # accepted whoever showed up, so a reviewer in Programmes could approve the
    # Finance/Audit step, then Admin, then the AED — the whole chain, alone,
    # in one role. The approval route was decorative, and the only thing
    # between that and money leaving was the role check on payment.
    #
    # No test caught it, because every test drove the engine with one actor
    # and never asked whether a SECOND person from the wrong department would
    # be refused. Found by walking the product as two users would.
    #
    # Deliberately no administrator bypass. An admin who needs to unstick a
    # requisition sitting with the wrong department should reassign it — a
    # visible, recorded act — not silently stand in for that department.
    if department and step.department and department != step.department:
        raise RequisitionError(
            f"{req.ref} is with {step.department} ({step.label or step.key}); "
            f"you are in {department}. Only {step.department} can act at this step."
        )

    # ─── nobody approves their own request ──────────────────────────────────
    #
    # The department check above is not enough on its own. A finance officer
    # raises a requisition; finance is the first step; they approve it. Same
    # person, both sides of the control. This is the first question an
    # auditor asks and it needed to be a refusal, not a convention.
    #
    # Declining or returning your own request is allowed — withdrawing
    # something you raised is not a conflict of interest.
    if decision == Decision.APPROVED and actor and actor == req.submitted_by:
        raise RequisitionError(
            f"{req.ref} was raised by you. A requisition cannot be approved by "
            "the person who submitted it."
        )

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


def place_on_hold(
    org_id: str, req_id: str, *, actor: str, department: str = "", reason: str = "",
) -> Requisition:
    """
    Pause a requisition at its CURRENT step without deciding it.

    Distinct from decide()'s RETURNED on purpose: a return sends the
    requisition back to the submitter and leaves the approval chain — it is a
    verdict ("this needs fixing before I'll look at it again"). A hold is not
    a verdict. It stays exactly where it is, with the same approver, waiting
    on something outside the requisition itself (a call to make, a document
    coming by courier, a second signature offline). Modelling it as its own
    status rather than a decision keeps `decide()`'s three outcomes
    (approve/decline/return) the closed set the audit summary already
    assumes, and keeps `current_step` untouched so release_hold() resumes
    exactly where the requisition paused — never re-entering the chain at
    the wrong step.

    Requires a written reason: NEEM's own process (and the general principle
    that nothing in this engine blocks silently) means "why" is not optional
    for a hold any more than it is for a policy override.

    Gated on the `requisition_hold` flag for the same reason multi-payee
    batches are gated — an org that has never turned this on should not have
    its approvers discover a hold button, and should not have to explain a
    status their reviewers have never been trained on.
    """
    org = store.require_org(org_id)
    try:
        import org_config
        hold_on = org_config.feature_enabled(org, "requisition_hold")
    except ImportError:  # pragma: no cover
        hold_on = False
    if not hold_on:
        raise RequisitionError(
            "This organisation has not enabled putting requisitions on hold "
            "('requisition_hold' feature flag)."
        )

    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if req.status != ReqStatus.IN_REVIEW:
        raise RequisitionError(
            f"{req.ref} is not awaiting review (status: {req.status.value}); only a "
            "requisition currently with an approver can be put on hold."
        )
    if not reason.strip():
        raise RequisitionError("Putting a requisition on hold requires a written reason.")

    wf = get_workflow(org)
    step = _step(wf, req.current_step or "")
    if step is None:
        raise RequisitionError(f"{req.ref} has no active approval step.")
    # Same department boundary as decide(): only whoever the requisition is
    # actually sitting with may pause it. See the long comment in decide()
    # for why this is not admin-bypassable.
    if department and step.department and department != step.department:
        raise RequisitionError(
            f"{req.ref} is with {step.department} ({step.label or step.key}); "
            f"you are in {department}. Only {step.department} can act at this step."
        )

    req.status = ReqStatus.ON_HOLD
    req.hold_reason = reason.strip()
    req.held_by = actor
    req.held_at = _now_iso()
    _audit(req, "held", actor=actor, department=department or step.department,
           detail=f"{step.label or step.key}: on hold — {req.hold_reason}")
    return _save(org, req)


def release_hold(
    org_id: str, req_id: str, *, actor: str, department: str = "", notes: str = "",
) -> Requisition:
    """Resume a held requisition at the SAME step it was paused on.

    Whoever holds a requisition is who releases it — same department
    boundary as place_on_hold() and decide(). This does not re-run policy
    checks: nothing about the requisition's own facts changed while it sat
    idle, only time passed, so there is nothing new for the checks to find.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if req.status != ReqStatus.ON_HOLD:
        raise RequisitionError(f"{req.ref} is not on hold (status: {req.status.value}).")

    wf = get_workflow(org)
    step = _step(wf, req.current_step or "")
    if step is not None and department and step.department and department != step.department:
        raise RequisitionError(
            f"{req.ref} is with {step.department} ({step.label or step.key}); "
            f"you are in {department}. Only {step.department} can act at this step."
        )

    prior_reason = req.hold_reason or "(no reason recorded)"
    req.status = ReqStatus.IN_REVIEW
    req.hold_reason = None
    req.held_by = None
    req.held_at = None
    where = f"Resumed at {step.label or step.key}" if step is not None else "Resumed"
    _audit(req, "hold_released",
           actor=actor, department=department or (step.department if step else ""),
           detail=f"{where} (was held: {prior_reason})" + (f" — {notes.strip()}" if notes.strip() else ""))
    return _save(org, req)


def add_comment(org_id: str, req_id: str, *, actor: str, department: str = "", text: str = "") -> Requisition:
    """Add one message to a requisition's discussion thread.

    Deliberately unrestricted by status or step: NEEM's ask was that anyone
    who can see a request can discuss it, which per the org-wide visibility
    principle is now everyone signed in — not just whoever currently holds
    it. A paid or declined requisition can still be commented on (an
    auditor asking a question later is a completely ordinary case). Not
    role-gated for the same reason viewing a requisition isn't: a comment
    moves no money and grants no authority, so there is nothing here for a
    role to protect.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if not text.strip():
        raise RequisitionError("A comment needs some text.")

    req.comments.append(Comment(
        id=uuid.uuid4().hex, author=actor, department=department,
        text=text.strip(), at=_now_iso(),
    ))
    _audit(req, "commented", actor=actor, department=department,
           detail=text.strip()[:200])
    req.updated_at = _now_iso()
    return _save(org, req)


MAX_ATTACHMENTS_PER_REQUISITION = 50


def add_attachment(
    org_id: str, req_id: str, *, actor: str, filename: str, content_type: str,
    size: int, storage_key: str, attachment_id: Optional[str] = None,
) -> Requisition:
    """Record that a file was stored against this requisition.

    Pure metadata — by the time this is called, the bytes are already
    sitting in whatever backend attachments.py is configured with; this
    only appends the reference so it shows up on the record and in the
    audit log. Never restricted by status: a bank confirmation slip added
    after payment, or a follow-up document an auditor asked for, are both
    completely ordinary.

    Gated on `requisition_attachments` — an org that hasn't turned this on
    should not have submitters discover an upload control with nowhere
    configured to put the files.
    """
    org = store.require_org(org_id)
    try:
        import org_config
        attachments_on = org_config.feature_enabled(org, "requisition_attachments")
    except ImportError:  # pragma: no cover
        attachments_on = False
    if not attachments_on:
        raise RequisitionError(
            "This organisation has not enabled file attachments on requisitions "
            "('requisition_attachments' feature flag)."
        )

    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if not filename.strip() or not storage_key.strip():
        raise RequisitionError("A stored file needs a filename and a storage key.")
    if len(req.attachments) >= MAX_ATTACHMENTS_PER_REQUISITION:
        raise RequisitionError(
            f"{req.ref} already has {len(req.attachments)} attachments, at this "
            f"organisation's limit of {MAX_ATTACHMENTS_PER_REQUISITION}."
        )

    att = Attachment(
        id=attachment_id or uuid.uuid4().hex, filename=filename.strip(),
        content_type=content_type, size=size, storage_key=storage_key,
        uploaded_by=actor, uploaded_at=_now_iso(),
    )
    req.attachments.append(att)
    _audit(req, "attached", actor=actor,
           detail=f"{att.filename} ({att.size:,} bytes)")
    req.updated_at = _now_iso()
    return _save(org, req)


def record_compliance_result(
    org_id: str, req_id: str, *, actor: str, summary: ComplianceSummary,
) -> Requisition:
    """Attach the result of a compliance-rulebook check to this requisition.

    The check itself — loading the rulebook, extracting text from the
    attachments, and the actual Claude call — runs entirely in
    api/requisition_routes.py, which then translates compliance.py's
    ComplianceCheckResult into a ComplianceSummary and calls this. Keeping
    the LLM call there (never here) preserves this module's own invariant
    that no LLM is ever called from requisitions.py.

    Gated on requisition_compliance_check. Deliberately NOT restricted by
    status or role, the same reasoning as add_attachment/add_comment:
    recording a check result is evidence, not a decision — it moves no
    money and grants no authority. Overwrites any previous snapshot; every
    run's verdict is still preserved in audit_log regardless.
    """
    org = store.require_org(org_id)
    try:
        import org_config
        checks_on = org_config.feature_enabled(org, "requisition_compliance_check")
    except ImportError:  # pragma: no cover
        checks_on = False
    if not checks_on:
        raise RequisitionError(
            "This organisation has not enabled compliance-rulebook checks on "
            "requisitions ('requisition_compliance_check' feature flag)."
        )

    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")

    # This module owns timestamps/attribution for everything it persists —
    # the route builds the verdicts, but who ran it and when is set here,
    # the same way add_comment stamps `at` rather than trusting the caller.
    summary.checked_by = actor
    summary.checked_at = _now_iso()

    req.compliance = summary
    _audit(
        req, "compliance_checked", actor=actor,
        detail=(
            f"{summary.overall_verdict} against '{summary.rulebook_name}' "
            f"({len(summary.results)} rule(s), {summary.document_count} document(s))"
        ),
    )
    req.updated_at = _now_iso()
    return _save(org, req)


def route_to(
    org_id: str, req_id: str, *, target_step: str, actor: str,
    department: str = "", reason: str = "",
) -> Requisition:
    """Move a requisition to a different stage of the chain — forward to
    escalate it, or backward to send it to an earlier stage for another look.

    The gap this fills. `decide()` offers three outcomes and each moves the
    requisition exactly one way: approve advances one step, return sends it
    all the way back to the SUBMITTER, decline ends it. Real chains need a
    fourth move. Finance cannot settle a question and wants the AED to look
    at it now rather than after two more hops. The AED wants Finance to
    re-check a figure — which is not "return for fixes", because the
    submitter did nothing wrong and bouncing it to them loses the reviews
    already done. Both are routing, not judgement, and neither was
    expressible.

    decide()'s own comment already anticipated this: "a requisition sitting
    with the wrong department should reassign it — a visible, recorded act —
    not silently stand in for that department." This is that act.

    What it deliberately does NOT do:

      - It never erases an approval. The log is append-only, so a stage
        revisited after being sent back simply carries two decisions, and
        the later one describes where things stand.
      - It cannot route to a step that does not engage at this amount.
        Sending a N50,000 payment to a step that only starts at N7,000,000
        would invent an approval the policy never asked for.
      - It cannot skip the reason. Routing is a deviation from the chain the
        org configured; an auditor comparing the trail to the policy will
        find the jump, and "why" should already be sitting there. Same
        principle as a hold and an override.

    Skipping forward leaves the passed-over stages undecided, and that is
    visible rather than hidden — the route display marks them skipped, which
    is exactly what an auditor needs to see.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if req.status != ReqStatus.IN_REVIEW:
        raise RequisitionError(
            f"{req.ref} is not awaiting review (status: {req.status.value}); only a "
            "requisition currently with an approver can be sent to another stage."
        )
    if not reason.strip():
        raise RequisitionError(
            "Sending a requisition to another stage requires a written reason."
        )

    wf = get_workflow(org)
    current = _step(wf, req.current_step or "")
    if current is None:
        raise RequisitionError(f"{req.ref} has no active approval step.")

    # Same department boundary as decide() and place_on_hold(): only whoever
    # the requisition is actually sitting with may move it on. Otherwise this
    # becomes the side door around the approval chain that those two guards
    # exist to close.
    if department and current.department and department != current.department:
        raise RequisitionError(
            f"{req.ref} is with {current.department} ({current.label or current.key}); "
            f"you are in {department}. Only {current.department} can move it from here."
        )

    target = _step(wf, target_step.strip())
    if target is None:
        raise RequisitionError(f"No approval step '{target_step}' in this workflow.")
    if target.key == current.key:
        raise RequisitionError(f"{req.ref} is already with {current.label or current.key}.")

    engaged = _steps_for(wf, req.amount)
    engaged_keys = [s.key for s in engaged]
    if target.key not in engaged_keys:
        raise RequisitionError(
            f"'{target.label or target.key}' does not apply to a "
            f"{_money(req.amount)} {req.currency} payment — it engages from "
            f"{_money(target.min_amount)}. Routing there would invent an approval "
            "this organisation's policy does not require."
        )

    forward = engaged_keys.index(target.key) > engaged_keys.index(current.key)
    skipped = (
        [s for s in engaged
         if engaged_keys.index(current.key) < engaged_keys.index(s.key) < engaged_keys.index(target.key)]
        if forward else []
    )

    req.current_step = target.key
    # "rerouted", NOT "routed". decide() already writes "routed" every time a
    # requisition advances normally to its next step. Sharing that name would
    # mix ordinary progression in with deliberate deviations from the chain,
    # and the entire reason for recording a deviation is that someone can
    # find it later — an auditor filtering the log for departures from the
    # configured route must not have to read every normal hop to spot one.
    _audit(
        req, "rerouted", actor=actor, department=department,
        detail=(
            f"{'Escalated' if forward else 'Sent back'} from "
            f"{current.label or current.key} to {target.label or target.key}"
            + (f", skipping {', '.join(s.label or s.key for s in skipped)}" if skipped else "")
            + f" — {reason.strip()}"
        ),
    )
    req.updated_at = _now_iso()
    return _save(org, req)


def note_event(
    org_id: str, req_id: str, *, actor: str, event: str,
    department: str = "", detail: str = "",
) -> Requisition:
    """Append one line to a requisition's audit log without changing anything
    else about it.

    For acts that are part of the record but are not decisions and move no
    money — "sign-off was requested from this person for that step" being the
    first of them. Those belong in the chain: an auditor asking why a payment
    was approved by someone outside the department needs to see that someone
    inside it delegated the step, by name, before the approval happened.

    Deliberately narrow. It cannot set a status, an approval or a check —
    only append an attributed line — so it can never become a side door
    around decide()'s authority rules.
    """
    org = store.require_org(org_id)
    req = get_requisition(org, req_id)
    if req is None:
        raise RequisitionError(f"Requisition '{req_id}' not found.")
    if not (event or "").strip():
        raise RequisitionError("An audit entry needs an event name.")
    _audit(req, event.strip(), actor=actor, department=department, detail=detail.strip())
    req.updated_at = _now_iso()
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
    # The person who raised it may not be the person who releases the money.
    # Approvals in between do not cure this: the submitter choosing WHEN and
    # WITH WHICH reference a payment goes out is still one person on both ends.
    if actor and actor == req.submitted_by:
        raise RequisitionError(
            f"{req.ref} was raised by you. Payment must be released by someone else."
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
        payees=[p.model_copy(deep=True) for p in req.payees],
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
    """Look up by internal id (the normal case — every link inside the app
    already carries it) or by the human-readable ref ("REQ-0001") — the
    shape a notification, an email, or someone pasting a reference actually
    has. The direct id lookup is tried first and is the only cost on the
    common path; a ref only falls through to a scan of the org's
    requisitions, same cost list_requisitions() already pays elsewhere.

    Without this, every requisition notification silently linked nowhere —
    Notification.txn_ref stores the ref, never the id, and there was no way
    to resolve one back to the other.
    """
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _REQUISITIONS, req_id)
    if raw:
        return Requisition.model_validate(raw)
    if req_id.strip().upper().startswith("REQ-"):
        target = req_id.strip().upper()
        for other in store.get_store().list(org, _REQUISITIONS):
            if str(other.get("ref", "")).upper() == target:
                try:
                    return Requisition.model_validate(other)
                except Exception:
                    return None
    return None


def list_requisitions(
    org_id: str,
    *,
    status: Optional[ReqStatus] = None,
    step: Optional[str] = None,
    department: Optional[str] = None,
    grant_code: Optional[str] = None,
    submitted_from: Optional[str] = None,  # ISO timestamp, inclusive — for audit-period exports
    submitted_to: Optional[str] = None,    # ISO timestamp, inclusive
) -> list[Requisition]:
    """Newest first. `step` powers each department's 'waiting on me' view.
    `submitted_from`/`submitted_to` bound by `submitted_at` (the record's
    raise time, set even for a draft — see create_requisition) — plain ISO
    string comparison, the same idiom the duplicate-window check already
    uses, since ISO 8601 timestamps sort correctly as strings."""
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
        if submitted_from is not None and (req.submitted_at or "") < submitted_from:
            continue
        if submitted_to is not None and (req.submitted_at or "") > submitted_to:
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
