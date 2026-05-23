"""
DOCex core data models.

Canonical Pydantic models for the extraction engine.
Field names here must stay in sync with api/schemas.py and web/types/index.ts.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


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
    # ─── Persistence + audit metadata ──────────────────────────────────
    # The engine produces transient results; the storage layer in
    # api/compliance_routes.py decides when to commit them to disk. These
    # fields are populated on save, not by the engine itself.
    created_at: Optional[str] = None          # ISO 8601 when the check ran
    approved: bool = False                    # True once the user marked it ED-approved
    approved_at: Optional[str] = None         # ISO 8601 when marked approved
    # Snapshot of the active rules at check time. Without this, editing
    # the rulebook AFTER a check would silently change the meaning of the
    # audit trail — "this check passed Clause 4.2" loses defensibility if
    # Clause 4.2 gets edited a month later. The snapshot freezes the rules
    # as they were when the verdict was rendered. Three-year-LLMs proof.
    rulebook_snapshot_rules: Optional[list["PolicyRule"]] = None


class ComplianceCheckBatchResult(BaseModel):
    """Batch result — many payments against one rulebook."""
    total: int
    approved: int
    flagged: int
    blocked: int
    checks: list[ComplianceCheckResult]
