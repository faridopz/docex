"""
DOCex core data models.

Canonical Pydantic models for the extraction engine.
Field names here must stay in sync with api/schemas.py and web/types/index.ts.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Question(BaseModel):
    """A single question the user wants answered from the documents."""
    id: str
    text: str  # plain language, e.g. "What states does this organisation work in?"


class ExtractionAnswer(BaseModel):
    """The AI's answer to one question for one applicant."""
    question_id: str
    question_text: str
    answer: Optional[str] = None
    # found     — explicitly stated in a document
    # inferred  — reasonably concluded from context
    # not_found — not mentioned anywhere
    confidence: Literal["found", "inferred", "not_found"]
    source_document: Optional[str] = None  # filename the answer came from
    source_page: Optional[int] = None      # page number (from === PAGE N === markers in PDFs)
    quote: Optional[str] = None            # verbatim excerpt supporting the answer
    search_notes: Optional[str] = None     # reasoning trail — what was searched, what was found/not found


class ApplicantExtraction(BaseModel):
    """Full extraction result for one applicant (who may have submitted many docs)."""
    applicant_id: str
    applicant_name: str
    documents: list[str]       # filenames that were read
    answers: list[ExtractionAnswer]
    error: Optional[str] = None


# ─── Compliance models ──────────────────────────────────────────────────────
#
# Compliance Check is DOCex's second primitive — alongside Extraction. Instead
# of "read a bundle of docs and answer questions", it checks whether a single
# transaction document (payment request, expense claim, vendor invoice) complies
# with a policy document (procurement policy, travel policy, grant agreement).
#
# Two-pass architecture:
#   Pass 1 — interpret the policy into a structured PolicyRulebook (cached &
#            editable, so the officer can correct any misreads before any
#            check runs).
#   Pass 2 — evaluate a payment request against the rulebook, rule by rule,
#            producing a verdict with citations from both sides.


class DeterministicCheckSpec(BaseModel):
    """A field-level rule that can be evaluated in code, no LLM call.

    Used by PolicyRule.deterministic_check when evaluation_type ==
    "deterministic". Evaluated against the structured form_data of a form
    or hybrid intake submission (see PaymentType.form_fields) by
    deterministic_checks.py — mirrors doc_completeness.py's philosophy:
    routine, unambiguous rules should cost zero tokens and return instantly.

      - "date_offset"        — compare two date fields (or a date field
                                against submission time) against a day
                                threshold. e.g. departure_date must be >= 7
                                days after submitted_at.
      - "threshold"          — compare a numeric field against a value
                                with an operator (">=", "<=", ">", "<", "==").
      - "membership"         — field's value must be (or must not be) in a
                                fixed list, e.g. vendor must be on the
                                approved vendor list.
      - "no_outstanding_advance" — block if the requester has a prior
                                submission of the same payment type that
                                hasn't been retired/closed yet.
      - "reference_lookup"   — field holds a reference to another
                                submission (e.g. a Travel Retirement's
                                "advance_reference" pointing at the
                                original advance's payment_id). Blocks if
                                the reference doesn't resolve to a real,
                                unretired submission, or belongs to a
                                different requester. The caller resolves
                                the actual lookup (see
                                api/compliance_routes.py) — this module
                                stays storage-agnostic.
    """
    kind: Literal[
        "date_offset", "threshold", "membership",
        "no_outstanding_advance", "reference_lookup",
    ]
    field: str                                # form field name this check reads
    compare_field: Optional[str] = None       # second field, for date_offset
    operator: Optional[str] = None            # ">=", "<=", ">", "<", "==", "in", "not_in"
    value: Optional[str] = None               # threshold / reference value (string; caller casts)
    values: list[str] = []                    # for membership checks — the allowed/blocked list
    # Some membership lists change constantly (an approved-vendor list gets
    # new vendors added all the time) and shouldn't be frozen into a rule at
    # rulebook-creation time — that would go stale the first time an org
    # edits its vendor list. When set, the API layer replaces `values` with
    # the live list from the named org config field right before evaluation
    # (see api/compliance_routes.py's _resolve_live_deterministic_values),
    # and that resolved snapshot is what gets frozen into the audit trail —
    # so the record still shows exactly what was checked against.
    values_source: Optional[Literal["org_approved_vendors"]] = None


class PolicyRule(BaseModel):
    """A single rule extracted from a compliance policy."""
    id: str
    clause_reference: Optional[str] = None    # e.g. "Section 4.2", "Clause 6.1.b"
    description: str                          # plain-language rule summary
    condition: Optional[str] = None           # when it applies, e.g. "amount > ₦500,000"
    evidence_required: list[str] = []         # what the payment must demonstrate
    # category lets us group rules in the UI — payment-level ("amounts > ₦500k
    # need 3 quotes") vs receipt-level ("receipts must contain vendor address")
    # vs approval-level ("Director sign-off required") — and run the right rules
    # against the right documents in the bundle.
    category: Optional[str] = None            # "procurement" | "receipts" | "approvals" | "vendor" | etc.
    source_quote: Optional[str] = None        # verbatim policy text
    source_page: Optional[int] = None
    # Officer can deactivate rules they don't want checked (e.g. deprecated
    # clauses, rules handled outside DOCex) without deleting them — the
    # rulebook still represents the full policy interpretation.
    active: bool = True
    # ─── Deterministic evaluation (forms) ───────────────────────────────
    # Defaults to "llm" so every existing rulebook (none of which have this
    # field on disk) behaves EXACTLY as before — Pydantic fills the default
    # on load, no migration needed. Only rules explicitly authored with
    # evaluation_type="deterministic" (today: none — wired up per payment
    # type as forms are built) skip the LLM and run in code instead.
    evaluation_type: Literal["llm", "deterministic"] = "llm"
    deterministic_check: Optional[DeterministicCheckSpec] = None


class PolicyRulebook(BaseModel):
    """Structured interpretation of a policy doc — the rulebook used to check payments."""
    id: str
    name: str                                 # e.g. "TA Connect Procurement Policy 2025"
    source_documents: list[str]
    rules: list[PolicyRule]
    # Any caveats Claude returned about ambiguous clauses or sections that
    # could not be confidently structured. The officer sees these alongside
    # the extracted rules and can resolve them manually.
    interpretation_notes: Optional[str] = None
    # ISO 8601 timestamps set by the storage layer (api/compliance_routes.py).
    # Optional so the engine can produce a freshly-interpreted rulebook in
    # memory without the storage layer needing to populate them. Both get
    # set on save; created_at is preserved across edits.
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # ─── Notifications ──────────────────────────────────────────────────
    # When notification_email is set, DOCex emails this address after each
    # compliance check completes whose verdict matches notification_trigger.
    # Configured per rulebook so different policies can route to different
    # people (e.g. procurement rulebook → procurement officer; travel
    # policy → finance manager). Requires SMTP_* env vars to be set on
    # the backend — see notifications.py and .env.example.
    notification_email: Optional[str] = None
    notification_trigger: Optional[
        Literal["always", "flagged_or_blocked", "blocked_only"]
    ] = None
    # ─── Routing / scope (auto-policy-selection) ────────────────────────
    # Optional hints describing WHEN this rulebook applies, used by the
    # policy router to auto-pick the best-fitting rulebook for a payment
    # (e.g. ["procurement", "vendor", "purchase order", "quotation"] for a
    # procurement policy; ["travel", "per diem", "DSA", "flight"] for a
    # travel policy). If empty, the router falls back to the rulebook's
    # name + rule text. `org` namespaces a rulebook to an organisation
    # (display/grouping today; the basis for tenant isolation once auth
    # lands).
    applies_to: list[str] = []
    org: Optional[str] = None
    # ─── Approval workflow (configurable per org/policy) ────────────────
    # The ordered sign-off chain a passed check must go through, as role
    # labels — e.g. ["Compliance Officer", "Head of Finance", "Executive
    # Director"] for TA Connect; another org might be ["Manager",
    # "Director"] or a single approver. Empty = no staged chain (the simple
    # approve toggle applies). This keeps WORKFLOWS as org-configurable as
    # the rules themselves — nothing in the engine is hardcoded to one org.
    approval_workflow: list[str] = []


class FormField(BaseModel):
    """One field in a structured intake form (PaymentType.form_fields).

    Routine, repeatable payment types (Travel Advance) collect a handful of
    structured fields instead of a stack of documents to re-type from; the
    field type drives both the frontend input control and how
    deterministic_checks.py interprets the submitted value.
    """
    name: str                                 # machine key, e.g. "departure_date"
    label: str                                # display label, e.g. "Departure Date"
    type: Literal["text", "date", "currency", "choice", "email", "number"]
    required: bool = True
    choices: list[str] = []                   # populated when type == "choice", for a FIXED list
    # Like DeterministicCheckSpec.values_source — some choice lists are live
    # org config (the approved vendor list) rather than a fixed set typed in
    # once. When set, the frontend renders options from that live org field
    # instead of (or in addition to) `choices`.
    choices_source: Optional[Literal["org_approved_vendors"]] = None


class PaymentType(BaseModel):
    """A category of payment with its own required-document checklist and
    special rules — e.g. Travel Advance, Participant Payment, Procurement.
    Different orgs define their own; this is what lets DOCex enforce 'complete
    documentation' (the #1 cause of delay) per type instead of generically."""
    name: str
    required_documents: list[str] = []
    notes: Optional[str] = None        # special rules, e.g. "retire within 5 days"
    # ─── Structured intake (forms) ──────────────────────────────────────
    # "document" (default) preserves today's behaviour exactly — a required-
    # documents checklist and nothing else. "form" replaces the document
    # checklist with structured fields end to end (e.g. Travel Advance).
    # "hybrid" collects structured fields AND still requires documents
    # (e.g. Travel Retirement: trip/amount fields + a receipt upload).
    #
    # None of this is TA-Connect-specific: every org edits its own
    # payment_types (name, fields, rulebook) via the org-profile screen.
    # The frontend renders whatever form_fields say — it has no per-org
    # hardcoded knowledge of what "Travel Advance" is.
    intake_mode: Literal["document", "form", "hybrid"] = "document"
    form_fields: list[FormField] = []
    # A form/hybrid type usually has no documents for the policy router to
    # rank rulebooks against (compliance_router.py needs payment text). This
    # lets an org point a payment type straight at its rulebook instead —
    # set once, in org-profile, by whoever configures the payment type.
    default_rulebook_id: Optional[str] = None


def default_travel_advance_form_fields() -> list[FormField]:
    """Generic starting field set for a Travel Advance form. Any org can
    rename, remove, or add to these via the org-profile screen — nothing
    downstream (the renderer, the deterministic engine) hardcodes these
    names; they're read generically off whatever fields are configured."""
    return [
        FormField(name="requester_name", label="Your Name", type="text"),
        FormField(name="destination", label="Destination", type="text"),
        FormField(name="departure_date", label="Departure Date", type="date"),
        FormField(name="return_date", label="Return Date", type="date"),
        FormField(name="amount", label="Amount Requested", type="currency"),
        FormField(name="approver_email", label="Approver Email", type="email"),
    ]


def default_travel_advance_rules() -> list[PolicyRule]:
    """Generic starter deterministic rules for a Travel Advance rulebook —
    field-level checks with no LLM involved (see deterministic_checks.py).
    Sourced from common donor-compliance guidance (e.g. USAID partner
    travel-policy implementation tips): request >= 7 days ahead, and only
    one outstanding advance per person at a time. Every value here (which
    field, what threshold) is just PolicyRule data — an org can edit or
    delete these rules the same way it edits any other rulebook rule."""
    return [
        PolicyRule(
            id="advance-7-day-rule",
            description="Travel advance must be requested at least 7 days before departure.",
            condition="departure_date >= 7 days from today",
            category="advance",
            evaluation_type="deterministic",
            deterministic_check=DeterministicCheckSpec(
                kind="date_offset", field="departure_date", operator=">=", value="7",
            ),
        ),
        PolicyRule(
            id="one-advance-at-a-time",
            description="No new travel advance while the requester has an outstanding, unretired advance.",
            condition="requester has no other unretired advance",
            category="advance",
            evaluation_type="deterministic",
            deterministic_check=DeterministicCheckSpec(
                kind="no_outstanding_advance", field="requester_name",
            ),
        ),
    ]


def default_travel_retirement_form_fields() -> list[FormField]:
    """Generic starting field set for a Travel Retirement — a hybrid intake:
    the trip details are structured fields, but a lodging receipt is a real
    document (a photo/scan of what was actually paid), because that's the
    one part a form field can't stand in for as evidence."""
    return [
        FormField(name="advance_reference", label="Advance Reference (from your Travel Advance confirmation)", type="text"),
        FormField(name="requester_name", label="Your Name", type="text"),
        FormField(name="return_date", label="Return Date", type="date"),
        FormField(name="amount_spent", label="Actual Amount Spent", type="currency"),
    ]


def default_travel_retirement_rules() -> list[PolicyRule]:
    """Generic starter deterministic rules for a Travel Retirement rulebook.
    Both are field-level, no LLM involved (see deterministic_checks.py):
    the retirement must reference a real, unretired, same-requester advance,
    and it must be submitted within a reconciliation window of the return
    date (see docs/DEMO_READINESS notes and USAID partner travel-policy
    guidance: a fixed reconciliation deadline is standard practice)."""
    return [
        PolicyRule(
            id="retirement-references-valid-advance",
            description="Must reference a real, unretired travel advance belonging to the same requester.",
            condition="advance_reference resolves to an unretired advance for this requester",
            category="advance",
            evaluation_type="deterministic",
            deterministic_check=DeterministicCheckSpec(
                kind="reference_lookup", field="advance_reference",
            ),
        ),
        PolicyRule(
            id="retirement-within-5-days",
            description="Travel advance must be retired within 5 days of return.",
            # return_date compared to today (compare_field omitted): the gap
            # (return_date - today) must be >= -5, i.e. today is at most 5
            # days after the return date.
            condition="today is within 5 days of return_date",
            category="retirement",
            evaluation_type="deterministic",
            deterministic_check=DeterministicCheckSpec(
                kind="date_offset", field="return_date", operator=">=", value="-5",
            ),
        ),
    ]


def default_vendor_payment_form_fields() -> list[FormField]:
    """Generic starting field for Vendor Payment's hybrid intake: a vendor
    picker sourced live from the org's approved-vendor list (see
    OrgProfile.approved_vendors) rather than a fixed set — the whole point
    is that this list changes over time without needing a form edit."""
    return [
        FormField(name="vendor", label="Vendor", type="choice", choices_source="org_approved_vendors"),
    ]


def default_vendor_payment_rules() -> list[PolicyRule]:
    """Generic starter deterministic rule for a Vendor Payment rulebook: the
    vendor must be on the org's approved-vendor list. This is the standard
    Approved Vendor List (AVL) control — pre-approval before any spend, not
    an AI judgment call — so it's evaluated in code, for free, before the
    invoice/proof-of-service documents ever reach an LLM."""
    return [
        PolicyRule(
            id="vendor-must-be-approved",
            description="Vendor must be on the organisation's approved vendor list.",
            condition="vendor is in the approved vendor list",
            category="vendor",
            evaluation_type="deterministic",
            deterministic_check=DeterministicCheckSpec(
                kind="membership", field="vendor", operator="in",
                values_source="org_approved_vendors",
            ),
        ),
    ]


def _default_payment_types() -> list[PaymentType]:
    """Common payment types as a starting set. Every org edits these to match
    their own process — nothing here is mandatory or org-specific."""
    return [
        PaymentType(name="Travel Advance",
                    intake_mode="form",
                    form_fields=default_travel_advance_form_fields(),
                    notes="Request 7+ days before; retire within 5 working days of return."),
        PaymentType(name="Travel Retirement",
                    intake_mode="hybrid",
                    form_fields=default_travel_retirement_form_fields(),
                    required_documents=["Lodging receipt(s)"],
                    notes="Unspent funds refunded immediately. Meals/incidentals are per diem — "
                          "no receipt needed for those; lodging is reimbursed on actual cost and needs one."),
        PaymentType(name="Participant Payment",
                    required_documents=["Payment schedule", "Attendance sheet", "Activity report"],
                    notes="Direct bank transfer only."),
        PaymentType(name="Procurement Payment",
                    required_documents=["Purchase order (PO)", "Invoice", "Goods Received Note (GRN)"],
                    notes="Must have PO, invoice, and proof of delivery."),
        PaymentType(name="Consultant Payment",
                    required_documents=["Signed contract", "Invoice", "Deliverables report"],
                    notes="Contract must be signed before work begins."),
        PaymentType(name="Vendor Payment",
                    intake_mode="hybrid",
                    form_fields=default_vendor_payment_form_fields(),
                    required_documents=["Invoice", "Proof of service"],
                    notes="Must be from the approved vendor list."),
    ]


class OrgProfile(BaseModel):
    """An organisation's configuration — the per-org layer that sits above the
    shared engine. This is how DOCex becomes *any* org's AI auditor without
    code changes: everything that varies between clients lives here, not in the
    engine.

      - name:                      the organisation's display name
      - roles:                     the roles in their process (for assignment)
      - default_approval_workflow: ordered sign-off stages NEW rulebooks inherit
                                   (each org's flow chart, e.g. TA Connect's
                                   "Compliance Check → Reviewer → Approval")
      - directory:                 stage/role -> email, so a sign-off request
                                   auto-routes to the right person

    Singleton per instance today; becomes per-tenant (keyed by org_id) once
    multi-tenant auth lands — the shape doesn't change, only the scoping.
    """
    name: str = "Your organisation"
    roles: list[str] = []
    default_approval_workflow: list[str] = []
    directory: dict[str, str] = {}
    payment_types: list[PaymentType] = Field(default_factory=_default_payment_types)
    # What this org calls the intake artifact an officer checks. The request
    # staff submit is a "Payment requisition"; Finance later turns an approved
    # one into a "Payment voucher (PV)". Configurable so each org uses its own
    # term. Default reflects the correct intake artifact.
    payment_subject: str = "Payment requisition"
    # Which product modules this org has switched on. Lets clients buy 1 or all
    # of: compliance (finance/approvals), screening (extraction/templates),
    # knowledge (library Q&A). Drives what the app shows them.
    enabled_modules: list[str] = Field(
        default_factory=lambda: ["compliance", "screening", "knowledge"]
    )
    # The org's maintained approved-vendor list — vendor names only for now
    # (a richer VendorEntry with contact/payment-terms/preferred-status is
    # a natural later extension, per standard AVL practice, but not needed
    # yet). Referenced live by Vendor Payment's membership check
    # (values_source="org_approved_vendors") and by its form field
    # (choices_source="org_approved_vendors") — one list, always current,
    # instead of being copied into a rulebook or a form config that goes
    # stale the moment a vendor is added or removed.
    approved_vendors: list[str] = []
    updated_at: Optional[str] = None


# pass                  — rule satisfied, evidence cited
# flag                  — borderline, needs human judgment
# block                 — clearly violates the rule
# not_applicable        — rule does not apply to this payment
# insufficient_evidence — required info is missing from the payment request
RuleVerdict = Literal[
    "pass",
    "flag",
    "block",
    "not_applicable",
    "insufficient_evidence",
]


class RuleResult(BaseModel):
    """Outcome of evaluating one rule against one payment request."""
    rule_id: str
    rule_description: str                     # carried for portability
    verdict: RuleVerdict
    reasoning: str                            # 1-3 sentences explaining the verdict
    policy_citation: Optional[str] = None     # quote from the policy
    payment_evidence: Optional[str] = None    # quote from the payment
    missing_evidence: list[str] = []          # populated when verdict = insufficient_evidence
    # When a receipt-level rule is evaluated against a specific receipt in the
    # bundle (rather than the payment as a whole), this is the filename. Lets
    # the UI group results by document — "Voucher findings" vs "Receipt #3
    # findings". Null when the rule was evaluated against the payment bundle.
    applied_to_document: Optional[str] = None
    # Same confidence scale as ExtractionAnswer — found/inferred/not_found
    # so the UI can use one consistent vocabulary across both primitives.
    confidence: Literal["found", "inferred", "not_found"]


# ─── Travel retirement (receipts → reconciliation) ──────────────────────────
# A traveller retires an advance by submitting receipts; finance reconciles what
# was actually spent against the advance. ReceiptItem is one parsed receipt (the
# amount is captured at entry or read from a digital receipt — never requires
# OCR of a photo); Reconciliation is the deterministic result (see receipts.py).

class ReceiptItem(BaseModel):
    """One receipt line — captured at entry or auto-read from a digital receipt.
    Any field may be None if unknown; reconcile() surfaces gaps as flags."""
    filename: str = ""
    amount: Optional[float] = None
    date: Optional[str] = None       # ISO 8601 "YYYY-MM-DD"
    vendor: Optional[str] = None
    category: Optional[str] = None   # "lodging" | "meals" | "transport" | "other"


class Reconciliation(BaseModel):
    """Deterministic outcome of reconciling receipts against a travel advance."""
    advance_amount: Optional[float] = None
    total_spent: float = 0.0
    balance: Optional[float] = None                   # advance - spent
    # "recover" (unspent returned) | "reimburse" (overspend owed to traveller)
    # | "settled" (equal) | "out_of_pocket" (no advance; org owes full)
    direction: Literal["recover", "reimburse", "settled", "out_of_pocket"] = "settled"
    receipt_count: int = 0
    readable_count: int = 0
    flags: list[RuleResult] = []
    summary: str = ""


RiskSeverity = Literal["high", "medium", "low"]
RiskStatus = Literal["open", "in_progress", "resolved"]


class RiskEntry(BaseModel):
    """A risk the compliance officer identified on a check, and how it was
    handled. This is the heart of the officer's report and the org's risk
    register: was there a risk, what was it, how severe, what action was
    taken, was it escalated, what's the plan, and is it resolved.
    """
    id: str
    created_at: str
    description: str                          # the risk itself
    severity: RiskSeverity = "medium"
    action_taken: Optional[str] = None        # what the officer did about it
    escalated: bool = False
    escalated_to: Optional[str] = None        # who it was escalated to
    action_plan: Optional[str] = None         # the plan to deal with it
    status: RiskStatus = "open"               # open -> in_progress -> resolved
    resolved_at: Optional[str] = None
    author: Optional[str] = None              # who logged it (None until auth)
    related_rule_id: Optional[str] = None     # the rule/finding that surfaced it
    updated_at: Optional[str] = None


class ComplianceCheckResult(BaseModel):
    """Full compliance check of one payment against one rulebook."""
    payment_id: str
    payment_label: str                        # "Payment Voucher #2025-04-17 — Vendor X"
    documents: list[str]                      # filenames that were read
    rulebook_id: str
    rulebook_name: str
    # approved — no flags or blocks
    # flagged  — one or more flags, no blocks
    # blocked  — one or more blocks
    overall_verdict: Literal["approved", "flagged", "blocked"]
    overall_summary: str                      # 1-2 sentence executive summary
    results: list[RuleResult]
    error: Optional[str] = None
    # Invoice number extracted deterministically at check time (fast_fields).
    # Stored so future checks can detect duplicate payments against it — the
    # basis of payment_checks.duplicate_invoice. Optional/None for payments
    # with no readable invoice.
    invoice_number: Optional[str] = None
    # Populated for Travel Retirement checks — the deterministic reconciliation
    # of submitted receipts against the advance (see receipts.py). None for
    # ordinary payment checks.
    reconciliation: Optional[Reconciliation] = None
    # ─── Persistence + audit metadata ──────────────────────────────────
    # The engine produces transient results; the storage layer in
    # api/compliance_routes.py decides when to commit them to disk. These
    # fields are populated on save, not by the engine itself.
    created_at: Optional[str] = None          # ISO 8601 when the check ran
    approved: bool = False                    # True once the user marked it ED-approved
    approved_at: Optional[str] = None         # ISO 8601 when marked approved
    paid: bool = False                        # True once finance executed the payment
    paid_at: Optional[str] = None             # ISO 8601 when marked paid
    # True once a Travel Retirement (or equivalent) has closed out an
    # advance/outstanding payment. Generic on purpose — any payment type
    # can use this, not just Travel Advance. This is what
    # deterministic_checks.py's "no_outstanding_advance" rule queries: an
    # advance with retired=False is still open.
    retired: bool = False
    retired_at: Optional[str] = None
    # ─── Structured intake (forms) ──────────────────────────────────────
    # Raw field values from a form/hybrid submission (see
    # PaymentType.intake_mode), keyed by FormField.name. Generic — this
    # holds whatever fields whatever org's payment type asked for, not a
    # fixed schema. Lets later submissions look up "does this requester
    # have anything outstanding" without re-parsing documents.
    form_data: dict[str, str] = {}
    # Snapshot of the active rules at check time. Without this, editing
    # the rulebook AFTER a check would silently change the meaning of the
    # audit trail — "this check passed Clause 4.2" loses defensibility if
    # Clause 4.2 gets edited a month later. The snapshot freezes the rules
    # as they were when the verdict was rendered. Three-year-LLMs proof.
    rulebook_snapshot_rules: Optional[list["PolicyRule"]] = None
    # ─── Requisition context ───────────────────────────────────────────
    # Captured from the Payment Requisition Form that originated this
    # payment — the upstream document compliance officers receive after
    # finance has processed the voucher. Without this context, the audit
    # trail can answer "did this payment comply with the rulebook?" but
    # NOT "what was this payment for, who asked for it, who approved?"
    # All fields are optional because legacy checks (pre-Day 14) didn't
    # capture them, and not every flow has all fields available.
    requisition_date: Optional[str] = None
    billing_donor: Optional[str] = None       # which donor's funds — Gates, BMGF, USAID, etc.
    payment_purpose: Optional[str] = None     # 1-2 sentence purpose-of-request narrative
    items_requested: Optional[str] = None     # what was being paid for (free-text)
    requested_by: Optional[str] = None        # name/role of the requisitioner
    approved_by: Optional[str] = None         # name/role who approved the requisition
    # ─── Approval chain ────────────────────────────────────────────────
    # When a check is currently "pending with" someone — the compliance
    # officer escalating to ED, the finance officer being asked for
    # clarification, the next reviewer in a multi-step approval flow —
    # this field carries who's responsible to act next. The Pending Inbox
    # at /compliance/pending lists checks where pending_with matches the
    # logged-in user (or, pre-auth, all not-yet-approved checks).
    #
    # Format: free-text role+name or email. Examples:
    #   "ED — Dr. Adekunle"
    #   "Finance — Bola Adeyemi"
    #   "bola@taconnect-ng.org"
    pending_with: Optional[str] = None
    # The structured question that's currently outstanding (set when a
    # clarification has been requested but not yet answered). Cleared
    # when the next event lands on the check.
    pending_question: Optional[str] = None
    # ─── Human decision log ────────────────────────────────────────────
    # Append-only list of every human action taken on this check. This is
    # the audit trail an auditor actually asks for: "this payment was
    # flagged on 2025-04-17 because the vendor CAC was missing; the
    # officer added a note on 2025-04-18 that CAC was in renewal; the
    # ED approved the check on 2025-04-19." Every event carries its own
    # timestamp + optional actor + optional rule reference + free-text
    # note. New events are always appended; existing events are never
    # mutated — preserving defensibility.
    decision_log: list["DecisionEvent"] = []
    # The officer's risk register for this check — identified risks, how they
    # were handled, escalations, and resolution status. Feeds the report.
    risks: list[RiskEntry] = []


# Event types are deliberately concrete. Each represents one human action.
# Adding a new type later is safe (Pydantic literal can extend; older
# records' enum values continue to validate).
DecisionEventType = Literal[
    "check_run",              # the check was created/run for the first time
    "note_added",             # officer added a free-text note (check-level or rule-level)
    "rule_dismissed",         # officer marked a specific rule's flag as "OK, here's why"
    "rule_escalated",         # officer escalated a rule to a higher reviewer
    "clarification_requested", # officer requested missing info from submitter/vendor
    "clarification_received", # the requested clarification was received (response/upload)
    "escalated",              # the whole check was escalated to a named reviewer
    "approved",               # check marked approved
    "unapproved",             # approval revoked (rare but audit-relevant)
    "risk_identified",        # officer logged a risk on this check
    "risk_updated",           # a risk's action/plan/status changed
    "risk_resolved",          # a risk was marked resolved
]


class DecisionEvent(BaseModel):
    """One entry in a compliance check's human decision log."""
    type: DecisionEventType
    timestamp: str                            # ISO 8601 when the action happened
    actor: Optional[str] = None               # who did it (None until auth lands)
    note: Optional[str] = None                # free-text reason / context
    # When the event is about one specific rule (e.g. a dismissal), this
    # references that rule. Null for check-level events.
    rule_id: Optional[str] = None
    rule_description: Optional[str] = None    # snapshot of the rule text for portability
    # ─── Signature (Day 15) ─────────────────────────────────────────────
    # When an approver "physically" signs an action — draws on the canvas
    # pad OR types their name as a signature — both pieces land here. The
    # data_url is a base64 PNG of the canvas; signed_name is the typed
    # name that accompanies it. Both optional — most events (notes,
    # dismissals) don't carry signatures. Approve, escalate, and the final
    # clarification response are the typical signed actions.
    signature_data_url: Optional[str] = None  # data:image/png;base64,...
    signed_name: Optional[str] = None         # typed name accompanying signature
    # ─── Outbound notification (Sprint 2) ───────────────────────────────
    # When an escalation or clarification is emailed to the responsible
    # party, the address it was sent to is recorded here. This closes the
    # audit loop ("we told tunde@vendor.com on 03/06") and lets the UI show
    # a delivery confirmation. Null when no email was sent (recipient was a
    # name not an address, or SMTP isn't configured).
    notified_email: Optional[str] = None
    # ─── Provenance (audit-grade: who/where) ────────────────────────────
    # `source` records HOW the action was taken — "in-app", "email-verified"
    # (a magic-link sign-off), or "system" (e.g. the check ran). `ip` records
    # WHERE it came from for verified actions. Together with actor + timestamp
    # they give the who / what / when / where an auditor expects.
    source: Optional[str] = None
    ip: Optional[str] = None


class ComplianceCheckBatchResult(BaseModel):
    """Batch result — many payments against one rulebook."""
    total: int
    approved: int
    flagged: int
    blocked: int
    checks: list[ComplianceCheckResult]


# ─── Bank Verify models ─────────────────────────────────────────────────────
#
# Bank Verify is DOCex's third primitive — alongside Extraction and Compliance.
# It targets the NGO programs-team pain of manually verifying recipient bank
# accounts against payment schedules by typing each account number into a bank
# app one at a time.
#
# Architecture (mirrors compliance.py's two-pass approach):
#   Pass 1 — resolve each account number against a bank-resolution endpoint
#            (Paystack /bank/resolve), capturing the registered account
#            holder name from the bank record.
#   Pass 2 — fuzzy-match the resolved name against the recipient name on the
#            payment schedule, producing a per-row verdict.


class BankAccountRow(BaseModel):
    """One row from a payment schedule, before verification."""
    recipient_name: str                  # name as written on the payment schedule
    account_number: str                  # NUBAN (10 digits in Nigeria)
    bank_code: str                       # Paystack bank code, e.g. "058" for GTBank
    bank_name: Optional[str] = None      # display only — e.g. "GTBank"
    amount: Optional[float] = None       # payment amount in NGN (carried for audit trail)
    notes: Optional[str] = None          # purpose / description column from the schedule


# verified      — resolved name closely matches the recipient name
# warning       — partial match; could be name variant, requires human review
# mismatch      — resolved name clearly differs from the recipient name
# unverifiable  — bank API could not resolve (invalid account, network error, etc.)
BankVerifyVerdict = Literal["verified", "warning", "mismatch", "unverifiable"]


class BankVerifyResult(BaseModel):
    """Outcome of verifying one BankAccountRow against the bank record."""
    recipient_name: str
    account_number: str
    bank_code: str
    bank_name: Optional[str] = None
    # The source-of-truth name returned by the bank (None if unverifiable).
    resolved_name: Optional[str] = None
    verdict: BankVerifyVerdict
    # 0-100 fuzzy similarity between recipient_name and resolved_name. Null
    # when unverifiable (no resolved name to compare against).
    match_score: Optional[int] = None
    # Filled when verdict is "unverifiable" — the upstream error message, or
    # our own description ("bank code not recognised", "account too short").
    error_message: Optional[str] = None
    timestamp: Optional[str] = None       # ISO 8601 when this verification ran
    # Pass-through from BankAccountRow so the downstream Excel export can
    # re-emit the original schedule shape with verdict columns appended.
    # Finance officers want their working file back, augmented — not a
    # foreign export. Carrying these here is cheaper than rejoining rows
    # to results by index downstream.
    amount: Optional[float] = None
    notes: Optional[str] = None


class BankVerifyBatchResult(BaseModel):
    """Batch verification result — many rows verified at once."""
    total: int
    verified: int
    warning: int
    mismatch: int
    unverifiable: int
    results: list[BankVerifyResult]
    # ─── Persistence + audit metadata ──────────────────────────────────
    # Like ComplianceCheckResult, the engine produces transient results;
    # the storage layer (api/bank_verify_routes.py, coming Day 2) decides
    # when to write them. These fields are populated on save.
    batch_id: Optional[str] = None        # uuid set on save
    source_schedule: Optional[str] = None # original payment schedule filename
    created_at: Optional[str] = None      # ISO 8601 when the batch ran
    # Foreign keys to upstream agents. When this batch was created by an
    # agent (Attendance Payment Agent, Sub-award Agent, etc.) rather than
    # by a direct user upload, attendance_run_id is the run that produced
    # the schedule. Audit-essential — answers "where did this verification
    # come from?" three months later without spelunking.
    attendance_run_id: Optional[str] = None
    # ─── Purpose / context ─────────────────────────────────────────────
    # WHY this verification ran. Tagged at upload time so the audit trail
    # answers "show me all grantee disbursement verifications for Q2" in
    # one filter. Also drives notification routing (vendor → procurement,
    # grantee → sub-award, event → programs) and unlocks per-purpose
    # threshold tuning later (grantee disbursements run at a tighter
    # warning band than event per-diems).
    #
    # Standard values:
    #   "event_payment"          — per-diem/honoraria to event attendees
    #   "grantee_disbursement"   — payout to an awarded sub-award partner
    #   "vendor_payment"         — payment to a procurement vendor
    #   "partner_reimbursement"  — reimbursing a partner organisation
    #   "other"                  — anything else; purpose_detail explains
    #
    # Free-text rather than an enum so users can capture nuance the
    # standard categories miss ("Q2 grantee top-up disbursement",
    # "supplier final invoice after delivery"). Validation lives in the
    # API layer where we suggest standard values but accept custom.
    purpose: Optional[str] = None
    purpose_detail: Optional[str] = None  # optional free-text elaboration


# ─── Knowledge Hub models ─────────────────────────────────────────────────
#
# DOCex's fifth primitive — slide-deck ingestion + chat. Targets the NGO
# knowledge-management pain: check-in slides, donor reports, training
# decks, board presentations all accumulate in shared drives where they
# go to die. The Knowledge Hub parses them once, stores them queryably,
# and lets the team chat across the corpus with Claude.
#
# MVP scope: per-deck chat. Slide-N citations. Each deck is one logical
# unit (e.g. "Gates Foundation March 2026 Check-in"). Multi-deck chat +
# saved insights are Phase 2.
#
# Why model slides individually rather than dumping deck text as one blob:
# (a) citations need slide numbers, (b) the user wants to navigate by slide,
# (c) future semantic retrieval will rank by slide.


class Slide(BaseModel):
    """One chunk of a document — slide for PPTX, page for PDF, section for DOCX.

    Kept the name "Slide" for backward compatibility with persisted records
    on disk that were written before multi-format support landed. Future
    refactor (when we touch the on-disk schema for other reasons) can
    rename to KnowledgeChunk or similar. The frontend handles the label
    variation ("Slide N" vs "Page N" vs "Section N") based on the parent
    document's content_type.
    """
    number: int                               # 1-indexed chunk number
    title: Optional[str] = None               # heading / first heading-like text
    body: list[str] = []                      # all other text as lines
    speaker_notes: Optional[str] = None       # PPTX-only: speaker notes pane
    table_text: list[str] = []                # flattened table rows
    # Future: image OCR, embeddings vector, auto-extracted topic.


# Document type — drives which parser ran AND how the frontend labels
# chunks. "pptx" stays the default for backward-compat with existing
# decks persisted before this field existed.
DocumentContentType = Literal["pptx", "docx", "pdf"]


class SlideDeck(BaseModel):
    """A persisted document in the Knowledge Hub library.

    Originally "slide deck" — the Knowledge Hub started PPTX-only — but
    now holds any document type (DOCX proposals, PDF training manuals,
    PPTX check-ins). The model name stays SlideDeck for backward
    compatibility with the JSON files on disk; the frontend surfaces it
    as "Document" in the UI.

    The chunk vocabulary varies by format:
      - PPTX: slides numbered 1..N (with optional speaker notes)
      - PDF:  pages numbered 1..N
      - DOCX: sections numbered 1..N, split by heading hierarchy
    """
    id: str
    name: str                                 # user-facing label (defaults to filename)
    source_filename: str                      # original filename
    # Format the doc came from. Default keeps every persisted record from
    # before this field as a slide-deck so we never break old data.
    content_type: DocumentContentType = "pptx"
    slide_count: int                          # total chunks, regardless of format
    slides: list[Slide]
    # Optional metadata captured at upload time. Lets the user/team
    # categorise documents ("Gates Foundation", "Q2 2026", "Inception") for
    # later filtering and library-wide chat.
    tags: list[str] = []
    description: Optional[str] = None
    # Folder path — a slash-delimited string like "Reports/2026/Q1" or
    # "Policies/Anti-Fraud". One folder per document (vs many-to-many for
    # tags). Empty/None means "root" — appears at the top level of the
    # library tree. We use a single string rather than a separate Folder
    # model because:
    #   (a) folders don't need their own metadata (no permissions yet)
    #   (b) reordering is trivial (just rename the prefix)
    #   (c) renders as a tree by client-side splitting on "/"
    # This makes folders feel like a filesystem without the overhead of one.
    folder: Optional[str] = None
    # Provenance for documents pulled from an external system (e.g. an
    # ERPNext knowledge base). Format "<source>:<external-id>", e.g.
    # "erpnext:<File.name>". Used to dedupe on re-sync so the same document
    # isn't ingested twice. Null for manually uploaded documents.
    source_ref: Optional[str] = None
    # Persistence + audit metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Citation = a slide reference attached to a chat answer. The frontend
# renders these as clickable chips next to the answer so the user can
# verify Claude's source.
#
# In per-document chat, deck_id and deck_name are redundant (the user is
# already on the document's page) but we carry them anyway so the same
# shape works for library-wide chat. In library-wide chat, deck_id is
# essential — that's how the chip knows which document to deep-link to.
class SlideCitation(BaseModel):
    slide_number: int
    excerpt: Optional[str] = None             # short verbatim quote from the slide
    deck_id: Optional[str] = None             # which document this slide belongs to
    deck_name: Optional[str] = None           # display name for library-wide citation chips


class KnowledgeAnswer(BaseModel):
    """Claude's response to a user question about a deck."""
    question: str
    answer: str                               # natural-language response with [Slide N] markers inline
    citations: list[SlideCitation] = []       # parsed citations with excerpts
    deck_id: str
    deck_name: str
    error: Optional[str] = None
    created_at: Optional[str] = None
    # When library-wide chat truncates due to Claude's context cap, the
    # engine populates this with the names of the documents it had to skip.
    # The frontend surfaces this as a soft warning chip so the user knows
    # the answer didn't see every document. Empty / not set for per-doc chat.
    truncated_decks: list[str] = []


# ─── DOCex Assistant models ───────────────────────────────────────────────
#
# The Assistant is the agentic narrator that briefs the user on what just
# happened in any agent run. Every result page (Bank Verify, Attendance
# Payment, Compliance Check, Self-Check) gets one of these cards at the
# top. The goal is to turn a verdict table into a conversation — Claude
# reads the result, summarises in plain English, and proposes actions.
#
# Why a dedicated primitive rather than inlining the prompt at each call
# site: (a) one place to refine tone and structure, (b) one place to
# improve the prompt as we learn what makes briefings land, (c) the
# briefing surface composes into the future Self-Improvement Agent and
# the Flow Builder.


# Urgency drives visual weight in the UI. high = primary CTA / red;
# medium = secondary CTA / amber; low = informational / gray.
SuggestedActionUrgency = Literal["high", "medium", "low"]


class SuggestedAction(BaseModel):
    """One next-step suggestion the Assistant proposes after a run."""
    label: str                                # short verb phrase, e.g. "Block this payment"
    urgency: SuggestedActionUrgency
    reason: Optional[str] = None              # 1-sentence why


class AssistantBrief(BaseModel):
    """The Assistant's response to a result. Returned by /assistant/summarize."""
    narrative: str                            # 2-4 sentence plain-English summary
    actions: list[SuggestedAction] = []       # 0-5 ranked next steps
    headline: Optional[str] = None            # optional one-line takeaway
    # Provenance — what context the Assistant was given. Helps debugging
    # when the brief reads wrong ("oh, we didn't pass it the rule_results").
    context_kind: str                         # "bank_verify_batch" | "attendance_run" | "compliance_check" | "diagnostic"
    context_id: Optional[str] = None


# ─── Self-Check Agent models ──────────────────────────────────────────────
#
# Runtime diagnostic that exercises every primitive and reports health.
# Categories: environment, filesystem, engines, API routes, end-to-end
# smoke, data integrity. V1 of the longer-term Self-Improvement Agent —
# this one observes, that one will also propose.

# pass — check ran and confirmed the thing works
# warn — check ran and the thing works but is suboptimal (e.g. test-mode
#        Paystack key, no rate cards saved, no sample data)
# fail — check ran and the thing is broken (e.g. missing API key,
#        unwritable persistence dir, engine import error)
# skip — check intentionally skipped (e.g. live-mode-only checks when
#        in test mode)
CheckStatus = Literal["pass", "warn", "fail", "skip"]


class CheckResult(BaseModel):
    """One diagnostic check's outcome."""
    id: str                                   # stable kebab-case key, e.g. "env-anthropic-key"
    category: str                             # "environment" | "filesystem" | "engines" | "api" | "smoke" | "data"
    title: str                                # short human-readable label
    status: CheckStatus
    summary: str                              # one-sentence outcome (the verdict)
    evidence: Optional[str] = None            # what the check actually saw — file path, count, value, exception
    fix_hint: Optional[str] = None            # actionable next step when status != pass
    duration_ms: int = 0                      # how long the check took


class DiagnosticReport(BaseModel):
    """Full result of running the Self-Check Agent suite."""
    started_at: str                           # ISO 8601
    finished_at: str
    duration_ms: int
    total: int                                # len(checks)
    passed: int
    warned: int
    failed: int
    skipped: int
    # Overall verdict — derived from per-check statuses.
    # "healthy" (no fails, ≤2 warns), "degraded" (no fails, >2 warns),
    # "broken" (any fail).
    overall: Literal["healthy", "degraded", "broken"]
    checks: list[CheckResult]
    report_id: Optional[str] = None           # uuid, set on save


# ─── Rate Card models ─────────────────────────────────────────────────────
#
# Rate cards let an org define their standard per-diem schedule once and
# reuse it across every event. Each card holds one default rate + zero-to-
# many per-role overrides. The Attendance Payment Agent consults a card
# at run time: look up each payee's role in the card, fall back to the
# default rate when no role match.
#
# Why per-role rather than per-person: in practice, NGOs price events by
# function (Facilitator vs Participant vs M&E Officer), not by individual.
# The role-based shape is what finance officers actually maintain in their
# spreadsheets, and what auditors expect to see.
#
# File-based persistence under {project_root}/rate_cards/{id}.json,
# matching the existing rulebook + verification persistence pattern.


class RateLine(BaseModel):
    """One role-specific rate in a rate card."""
    role: str                                 # e.g. "Facilitator", "Participant"
    amount_per_day: float                     # NGN per day attended


class RateCard(BaseModel):
    """A reusable schedule of per-diem rates."""
    id: str
    name: str                                 # e.g. "TA Connect Standard Rates 2026"
    # Default rate applied when an attendee has no role, or their role
    # isn't in the per-role list. Always required — drives the no-role
    # fallback path.
    default_rate_per_day: float
    # Per-role overrides. Empty list is legal — a card with just a default
    # rate is effectively the flat-rate behaviour the agent had before.
    roles: list[RateLine] = []
    # Optional: which currency / display label. Defaults to NGN; not used
    # for math, just display on the schedule and review pages.
    currency: str = "NGN"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ─── Attendance Payment Agent models ──────────────────────────────────────
#
# The Attendance Payment Agent is DOCex's first *composite* agent — it
# chains multiple primitives rather than being a primitive itself. The
# flow it automates:
#
#   1. Parse the attendance log (who showed up which days)
#   2. Parse the payment info form (name + org + bank for everyone)
#   3. Fuzzy cross-match names across both files (same blended scorer
#      the Bank Verify primitive uses)
#   4. Bucket each person: paid / no_attendance / no_payment_info
#   5. Calculate days_attended × rate
#   6. Hand off to Bank Verify primitive (purpose=event_payment)
#   7. Email finance with the verified schedule
#
# Models below cover steps 1-5. Steps 6-7 reuse BankVerify* models above.
#
# Targets the Programs team's end-to-end pain: today this whole flow is
# ~3-4 hours of cross-checking spreadsheets by hand, plus the dreaded
# bank-app thumb-typing. The agent collapses it to ~3 minutes.


class AttendanceRecord(BaseModel):
    """One person's attendance across all days of an event."""
    name: str                                 # as written on the attendance log
    days_attended: int                        # number of days marked present
    day_labels: list[str] = []                # which specific days (e.g. ["Day 1", "Day 3"])


class PaymentInfoRecord(BaseModel):
    """One person's registration / payment info, before matching."""
    name: str                                 # as written on the payment info form
    organisation: Optional[str] = None        # the partner org they represent
    account_number: str                       # NUBAN (10 digits in Nigeria)
    bank_code: str                            # Paystack 3-digit code or fintech code
    bank_name: Optional[str] = None           # display only — e.g. "GTBank", "Opay"
    role: Optional[str] = None                # "Facilitator", "Participant", etc.


# paid               — registered AND attended ≥1 day; will be on the schedule
# no_attendance      — registered but attendance log shows 0 days; blocked
# no_payment_info    — attended but no bank info on file; needs chasing
AttendeeStatus = Literal["paid", "no_attendance", "no_payment_info"]


class MatchedAttendee(BaseModel):
    """One person reconciled across the attendance log and payment info."""
    # Identity — payment_info_name is the canonical name (it's what we'll
    # use on the payment schedule, since that name was self-reported with
    # bank details so it matches the bank record best).
    payment_info_name: Optional[str] = None
    attendance_name: Optional[str] = None
    # 0-100 fuzzy similarity between the two names. Null when the person
    # is on only one side of the match (no_attendance or no_payment_info).
    match_score: Optional[int] = None
    # The status drives whether this row appears on the payment schedule.
    status: AttendeeStatus
    # Attendance + payment fields. Filled when available; null otherwise.
    days_attended: int = 0
    day_labels: list[str] = []
    organisation: Optional[str] = None
    account_number: Optional[str] = None
    bank_code: Optional[str] = None
    bank_name: Optional[str] = None
    # Role from the payment info form (e.g. "Facilitator", "Participant").
    # Null when no role column existed in the input file. Drives rate
    # lookup against the active RateCard.
    role: Optional[str] = None
    # The exact rate that was applied to this row, per day. Carried on
    # the result so the audit trail can answer "why did this person get
    # ₦45k for 3 days?" → "Facilitator role, ₦15k/day from card X" without
    # re-running the engine.
    applied_rate_per_day: float = 0.0
    # Calculated amount (days_attended × applied_rate_per_day). Zero for
    # non-paid statuses — they don't get paid by definition.
    amount: float = 0.0


class AttendancePaymentRun(BaseModel):
    """A full run of the Attendance Payment Agent."""
    event_name: str                           # e.g. "Q2 Training Workshop — Abuja"
    rate_per_day: float                       # NGN per day attended
    days_in_event: int                        # how many days the event ran
    # All people, bucketed by status. We carry them all (not just the
    # paid ones) because the no_attendance + no_payment_info buckets are
    # the actionable findings the programs officer most needs to see.
    matched: list[MatchedAttendee]            # bucket: paid
    no_attendance: list[MatchedAttendee]      # bucket: no_attendance
    no_payment_info: list[MatchedAttendee]    # bucket: no_payment_info
    # Roll-ups for the dashboard / summary card.
    total_to_pay: float                       # sum of matched amounts
    paid_count: int                           # len(matched)
    no_attendance_count: int                  # len(no_attendance)
    no_payment_info_count: int                # len(no_payment_info)
    # Persistence + audit metadata. Populated when saved to disk by the
    # storage layer in api/attendance_agent_routes.py.
    run_id: Optional[str] = None              # uuid set on save
    created_at: Optional[str] = None          # ISO 8601 when the run completed
    attendance_filename: Optional[str] = None # source attendance log filename
    payment_info_filename: Optional[str] = None
    # Foreign key to the downstream Bank Verify batch when the user clicks
    # "verify these accounts" from the run page. Lets us pivot from a
    # payment run to its verification, and vice-versa, in one click.
    bank_verify_batch_id: Optional[str] = None
    # ─── Rate context ──────────────────────────────────────────────────
    # Snapshot of the rate card that was applied. Carried on the run so
    # the audit trail survives even if the underlying card is later edited
    # — same defensive pattern as ComplianceCheckResult.rulebook_snapshot_rules.
    rate_card_id: Optional[str] = None
    rate_card_name: Optional[str] = None
    rate_card_snapshot: Optional[RateCard] = None
    # ─── Accuracy gate ─────────────────────────────────────────────────
    # Flags surfaced to the user BEFORE Bank Verify runs. Each flag is a
    # human-readable warning that warrants review. Examples:
    #   - "2 rows share account number 7042310445"
    #   - "Aisha Bello attended 5 days but the event is 3 days long"
    #   - "3 paid rows have match score below 85 — confirm identity"
    # The frontend renders these in a red panel above the verify button
    # to make the team's existing 'eyeball check' step explicit.
    accuracy_flags: list[str] = []
    # Source format of each input file — "xlsx" or "google_sheets". Lets
    # the UI badge the run with the input type and lets us tune parsers
    # per format. Default to xlsx for backward compat.
    attendance_source: str = "xlsx"
    payment_info_source: str = "xlsx"


# ─── Attendance Collections (native intake + self-check-in) ─────────────────
#
# An alternative to importing an attendance log + payment form: collect the
# data natively. The organiser creates a Collection (event + day labels +
# rate), then either fills the grid themselves OR shares a public check-in
# link where attendees self-enter their name + bank details. When ready, the
# Collection is built into a normal AttendancePaymentRun via match_and_build_run
# — so everything downstream (Bank Verify, schedule export) is unchanged.


class CollectedAttendee(BaseModel):
    """One attendee inside a Collection (entered manually or self-served)."""
    id: str
    name: str
    organisation: Optional[str] = None
    account_number: str = ""
    bank_code: str = ""
    bank_name: Optional[str] = None
    role: Optional[str] = None
    # Which day labels this person was present for (subset of the
    # collection's day_labels). Length = days attended.
    present_days: list[str] = []
    # "organizer" (added in the grid) or "self" (via the public link).
    source: Literal["organizer", "self"] = "organizer"


class AttendanceCollection(BaseModel):
    """A native attendance-collection session."""
    id: str
    event_name: str
    day_labels: list[str] = []
    rate_per_day: float = 0.0
    rate_card_id: Optional[str] = None
    # Opaque token used in the public self-check-in URL. Distinct from id so
    # the share link never exposes the internal id.
    share_token: str
    created_at: Optional[str] = None
    attendees: list[CollectedAttendee] = []
    # Set once the collection has been built into a payment run.
    run_id: Optional[str] = None


class AttendanceCollectionSummary(BaseModel):
    id: str
    event_name: str
    attendee_count: int
    day_count: int
    created_at: Optional[str] = None
    run_id: Optional[str] = None


class PublicCollectionInfo(BaseModel):
    """The minimal, non-sensitive view returned to the public check-in page."""
    event_name: str
    day_labels: list[str]
    already_submitted: int  # how many have checked in so far (social proof)
