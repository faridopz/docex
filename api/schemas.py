"""
DOCex FastAPI schemas.

Input schemas live here (QuestionIn for validation).
Output schemas re-export the core models directly — no duplication.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel

# Re-export core models as the API response types
# This keeps field names in sync automatically
from sys import path
from pathlib import Path
path.insert(0, str(Path(__file__).parent.parent))
from models import (  # noqa: E402
    ApplicantExtraction,
    BankVerifyBatchResult,
    BankVerifyResult,
    ComplianceCheckBatchResult,
    ComplianceCheckResult,
    ExtractionAnswer,
    PolicyRule,
    PolicyRulebook,
)


class QuestionIn(BaseModel):
    """Input validation for a single question."""
    id: str
    text: str


class SingleExtractionResponse(BaseModel):
    """Response for POST /extract/single."""
    applicant_name: str
    documents: list[str]
    answers: list[ExtractionAnswer]
    error: Optional[str] = None


class BatchExtractionResponse(BaseModel):
    """Response for POST /extract/batch."""
    total: int
    succeeded: int
    failed: int
    applicants: list[ApplicantExtraction]


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"


# ── Follow-up drafts ───────────────────────────────────────────────────────

class FollowupApplicantIn(BaseModel):
    """One applicant's extraction result, sent back for follow-up drafting."""
    applicant_id: str
    applicant_name: str
    documents: list[str]
    answers: list[ExtractionAnswer]
    error: Optional[str] = None


class FollowupRequest(BaseModel):
    """Request body for POST /draft-followups."""
    applicants: list[FollowupApplicantIn]
    questions: list[QuestionIn]
    # Optional. Lets the drafter adapt vocabulary and ask shape to the
    # workflow — e.g. for quarterly-report-review, say "partner" instead
    # of "applicant" and "addendum for next cycle" instead of "resubmit
    # before approval". See _build_followup_system in api/main.py.
    template_id: Optional[str] = None


class FollowupDraft(BaseModel):
    """One drafted follow-up note."""
    applicant_id: str
    applicant_name: str
    note: str


class FollowupResponse(BaseModel):
    """Response for POST /draft-followups."""
    drafts: list[FollowupDraft]


# ── Compliance Check schemas ──────────────────────────────────────────────
#
# The check endpoints return the core models from models.py directly
# (PolicyRulebook, ComplianceCheckResult, ComplianceCheckBatchResult) so we
# only need extra schemas for: (a) the rulebook editor PUT body and (b) the
# summary list view, which is a slimmer projection of PolicyRulebook for
# the saved-rulebooks landing page.


class RulebookUpdateIn(BaseModel):
    """Body for PUT /compliance/rulebooks/{id}.

    Full replacement of the rules list — the frontend sends the entire
    edited rulebook back rather than a diff. Simpler to reason about and
    matches the natural shape of the rules editor (you save the whole form).
    """
    # If None or empty, keep the current name. Otherwise rename.
    name: Optional[str] = None
    rules: list[PolicyRule]
    interpretation_notes: Optional[str] = None
    # Notification settings — fully optional, opt-in per rulebook.
    notification_email: Optional[str] = None
    notification_trigger: Optional[str] = None  # "always" | "flagged_or_blocked" | "blocked_only"
    # Ordered approval stages (org-configurable). None = leave unchanged; a
    # list (even empty) replaces the current workflow.
    approval_workflow: Optional[list[str]] = None


class RulebookSummary(BaseModel):
    """Item in GET /compliance/rulebooks — slimmer projection for the list view."""
    id: str
    name: str
    rule_count: int
    active_rule_count: int
    source_documents: list[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RulebookListResponse(BaseModel):
    """Response for GET /compliance/rulebooks."""
    rulebooks: list[RulebookSummary]


class CheckSummary(BaseModel):
    """Slimmer projection of a ComplianceCheckResult for list views.

    Excludes the rule-by-rule results and the rulebook snapshot — those
    can be huge and aren't needed for a list. The full check is fetched
    by ID when the user clicks into it.
    """
    payment_id: str
    payment_label: str
    rulebook_id: str
    rulebook_name: str
    overall_verdict: str          # "approved" | "flagged" | "blocked"
    overall_summary: str
    document_count: int
    created_at: Optional[str] = None
    approved: bool = False
    approved_at: Optional[str] = None
    error: Optional[str] = None
    # Approval-chain hints surfaced into the summary so the Pending Inbox
    # can show who a check is sitting with — and whether someone is
    # awaiting a clarification — without fetching each check in full.
    pending_with: Optional[str] = None
    pending_question: Optional[str] = None


class CheckListResponse(BaseModel):
    """Response for GET /compliance/checks."""
    checks: list[CheckSummary]


# ── Bank Verify schemas ───────────────────────────────────────────────────
#
# Bank Verify endpoints return the core models from models.py directly
# (BankVerifyResult, BankVerifyBatchResult). We only need a slimmer summary
# projection for the saved-batches list view, mirroring CheckSummary.


class BatchVerifySummary(BaseModel):
    """Slimmer projection of a BankVerifyBatchResult for list views.

    Excludes the per-row results array (can run to hundreds of rows in real
    payment schedules). Frontend fetches the full batch by id when the user
    clicks into it. Purpose surfaces in the list so the user can filter
    "show me grantee disbursements" or "show me event payments" without
    drilling into each batch.
    """
    batch_id: str
    source_schedule: Optional[str] = None
    purpose: Optional[str] = None
    purpose_detail: Optional[str] = None
    total: int
    verified: int
    warning: int
    mismatch: int
    unverifiable: int
    created_at: Optional[str] = None


class BatchVerifyListResponse(BaseModel):
    """Response for GET /verify/batches."""
    batches: list[BatchVerifySummary]
