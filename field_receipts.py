"""
Field receipt validation and tracking engine.

The core problem: NGOs have fieldworkers spending money (training, supplies,
events). Receipts come back late, incomplete, or not at all. Auditors reject
unsupported spend. DOCex prevents this by validating receipts in real-time as
they're uploaded.

The solution: Fieldworker uploads receipt (photo/PDF) + basic metadata (amount,
project, activity). System:
  1. Extracts text/amounts via OCR
  2. Checks data quality (vendor present? date present? amount reasonable?)
  3. Validates policy (budget not exceeded? not a duplicate? not a flagged vendor?)
  4. Flags issues or marks VALIDATED immediately
  5. Notifies fieldworker/finance of any issues
  6. By audit time, every receipt is tracked + explained

All arithmetic is CODE. Policy rules are DATA from org config. No LLM guessing.
Storage is org-scoped, so every organisation's receipts are isolated.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

import fast_extract
import store

# ─── collections ────────────────────────────────────────────────────────────

_RECEIPTS = "field_receipts"
_RECEIPT_POLICY = "receipt_policy"
_RECEIPT_POLICY_ID = "current"


# ─── enums ──────────────────────────────────────────────────────────────────


class ReceiptStatus(str, Enum):
    """Workflow status of a receipt."""
    DRAFT = "draft"              # uploaded, not yet validated
    VALIDATED = "validated"      # passed all checks
    FLAGGED = "flagged"          # has issues that need review
    APPROVED = "approved"        # flagged receipt approved by finance anyway
    REJECTED = "rejected"        # discarded by finance


class ReceiptFlagType(str, Enum):
    """Type of issue flagged on a receipt."""
    MISSING_VENDOR = "missing_vendor"
    MISSING_DATE = "missing_date"
    MISSING_AMOUNT = "missing_amount"
    AMOUNT_MISMATCH = "amount_mismatch"
    DUPLICATE_DETECTED = "duplicate_detected"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNAUTHORIZED_VENDOR = "unauthorized_vendor"
    UNSUPPORTED_CATEGORY = "unsupported_category"
    POLICY_VIOLATION = "policy_violation"
    # Not a fault in the receipt — a statement about how we read it. Set when
    # the figures came from OCR of a photo or scan, so a human confirms them
    # before the amount becomes a payment.
    NEEDS_REVIEW = "needs_review"


# ─── models ─────────────────────────────────────────────────────────────────


class ReceiptFlag(BaseModel):
    """One issue flagged on a receipt."""
    type: ReceiptFlagType
    severity: Literal["warning", "error"]  # warning = fixable, error = reject
    message: str                            # human-readable explanation
    timestamp: Optional[str] = None


class ExtractedData(BaseModel):
    """Data extracted from receipt via OCR."""
    vendor_name: str = ""
    receipt_date: str = ""              # ISO date or empty
    extracted_amount: Optional[float] = None
    confidence: Literal["high", "medium", "low"] = "medium"


class SpendPolicyRule(BaseModel):
    """One policy rule for spend validation."""
    code: str                           # e.g. "MAX_RECEIPT", "VENDOR_APPROVAL"
    name: str = ""
    rule_type: Literal["max_amount", "required_vendor", "forbidden_vendor", "category", "budget_cap"] = "max_amount"
    max_amount: Optional[float] = None
    required_vendors: list[str] = Field(default_factory=list)
    forbidden_vendors: list[str] = Field(default_factory=list)
    allowed_categories: list[str] = Field(default_factory=list)
    budget_code: Optional[str] = None   # e.g. "P-101" for budget cap check
    budget_limit: Optional[float] = None
    active: bool = True


class ReceiptPolicy(BaseModel):
    """Organization's receipt validation rules."""
    org_id: str = ""
    rules: list[SpendPolicyRule] = Field(default_factory=list)
    allow_missing_vendor: bool = False  # if True, warning; if False, error
    allow_missing_date: bool = False
    duplicate_window_days: int = 7      # receipts within 7 days at same vendor flagged as potential dups
    currency: str = "NGN"
    updated_at: Optional[str] = None


class ReceiptLine(BaseModel):
    """One receipt."""
    id: str
    org_id: str = ""
    uploaded_by: str = ""               # user ID or email
    uploaded_at: str = ""               # ISO timestamp

    # Metadata from upload form
    amount_submitted: float = 0.0       # what fieldworker said they spent
    project_code: str = ""              # which project/activity
    category: str = ""                  # training, supplies, travel, etc.
    description: str = ""               # optional note

    # File metadata
    original_filename: str = ""
    file_size_bytes: int = 0
    file_type: str = ""                 # image/jpeg, application/pdf, etc.

    # Extracted data (via OCR)
    extracted: ExtractedData = Field(default_factory=ExtractedData)

    # Validation results
    status: ReceiptStatus = ReceiptStatus.DRAFT
    flags: list[ReceiptFlag] = Field(default_factory=list)

    # If flagged, finance can review and decide
    reviewed_by: str = ""               # who reviewed flagged receipt
    review_decision: Optional[Literal["approved", "rejected"]] = None  # if flagged
    review_notes: str = ""

    # Audit trail
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ─── helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _money(x: float) -> float:
    return round(float(x or 0.0), 2)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ─── policy management ──────────────────────────────────────────────────────


def set_policy(org_id: str, policy: ReceiptPolicy) -> ReceiptPolicy:
    """Store org's receipt validation rules."""
    org = store.require_org(org_id)
    policy.org_id = org
    policy.updated_at = _now_iso()
    store.get_store().put(org, _RECEIPT_POLICY, _RECEIPT_POLICY_ID, policy.model_dump())
    return policy


def get_policy(org_id: str) -> ReceiptPolicy:
    """Retrieve org's receipt validation rules."""
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _RECEIPT_POLICY, _RECEIPT_POLICY_ID)
    return ReceiptPolicy.model_validate(raw) if raw else ReceiptPolicy(org_id=org)


# ─── receipt upload & extraction ────────────────────────────────────────────


def upload_receipt(
    org_id: str,
    uploaded_by: str,
    file_content: bytes,
    filename: str,
    amount_submitted: float,
    project_code: str,
    category: str = "",
    description: str = "",
) -> ReceiptLine:
    """
    Upload a receipt, extract data via OCR, validate, and return result.

    The receipt starts as DRAFT. After validation, it's either VALIDATED or FLAGGED.
    If FLAGGED, finance must review and decide: APPROVED or REJECTED.
    """
    org = store.require_org(org_id)

    # Extract text from file.
    #
    # A file whose bytes don't match its extension (a photo saved as .pdf, a
    # truncated upload, a KoboCollect placeholder named .jpg) makes the parser
    # return an empty string rather than raise. Left alone, every field then
    # looks "missing" and the reviewer is told the vendor is absent when the
    # truth is that the FILE was unreadable — two very different problems.
    # So: fall back to plain text, and remember whether we read anything at all.
    # fast_extract now sniffs magic bytes, OCRs photos and scans, and reports
    # WHY it came back empty. The old blind decode fallback here is gone: on a
    # photographed receipt it returned the PNG header as text, and the vendor
    # heuristic duly recorded a supplier called "PNG".
    extracted_text = ""
    extract_status = "unreadable"
    try:
        extracted_text, extract_status = fast_extract.extract_status(filename, file_content)
        extracted_text = (extracted_text or "").strip()
    except Exception:
        extracted_text, extract_status = "", "unreadable"

    # Text recovered by OCR is a machine's reading of a photograph, not a
    # text layer. A misread digit in an amount is worse than a blank, so it
    # is marked for human confirmation rather than trusted outright.
    from_ocr = extract_status == "ocr"
    unreadable = not extracted_text

    # Parse amounts and dates from extracted text (simple regex patterns)
    extracted_amount = _extract_amount(extracted_text)
    extracted_date = _extract_date(extracted_text)
    vendor_name = _extract_vendor(extracted_text)

    receipt = ReceiptLine(
        id=_new_id("rcp"),
        org_id=org,
        uploaded_by=uploaded_by,
        uploaded_at=_now_iso(),
        amount_submitted=_money(amount_submitted),
        project_code=project_code.strip(),
        category=category.strip(),
        description=description.strip(),
        original_filename=filename,
        file_size_bytes=len(file_content),
        file_type=_infer_mimetype(filename),
        extracted=ExtractedData(
            vendor_name=vendor_name,
            receipt_date=extracted_date,
            extracted_amount=extracted_amount,
            # OCR never earns "medium": the figures came off pixels, so a
            # reviewer should look even when every field parsed cleanly.
            confidence=(
                "low" if from_ocr
                else "medium" if extracted_amount and extracted_date
                else "low"
            ),
        ),
        status=ReceiptStatus.DRAFT,
        created_at=_now_iso(),
    )

    # Validate
    receipt = validate_receipt(org, receipt)

    # If nothing could be read out of the file at all, say exactly that. It
    # replaces the misleading "vendor missing / date missing" pair with the
    # single true statement, so the reviewer re-requests the file instead of
    # hand-typing fields off a document nobody can open.
    if unreadable:
        receipt.flags = [f for f in receipt.flags if f.type not in {
            ReceiptFlagType.MISSING_VENDOR,
            ReceiptFlagType.MISSING_DATE,
        }]
        # "This scan needs typing up" and "this file is damaged" call for
        # different actions. Telling someone to re-upload a perfectly good
        # photo, or to squint at a corrupt one, both waste their time.
        if extract_status == "scanned":
            if fast_extract.ocr_available():
                message = (
                    f"'{filename}' is a scan or photo and no text could be read from "
                    f"it — it may be blurred, dark, or rotated. Enter the vendor, "
                    f"date and amount below, or upload a clearer picture."
                )
            else:
                message = (
                    f"'{filename}' is a scan or photo, and text recognition is not "
                    f"installed on this server. Enter the vendor, date and amount "
                    f"below. (Admin: install the tesseract-ocr package.)"
                )
        else:
            message = (
                f"'{filename}' could not be read (0 bytes of text recovered from "
                f"{len(file_content)} bytes). The file may be damaged or incomplete. "
                f"Re-upload it, or enter the vendor, date and amount manually."
            )
        receipt.flags.insert(0, ReceiptFlag(
            type=ReceiptFlagType.MISSING_AMOUNT,
            severity="error",
            message=message,
            timestamp=_now_iso(),
        ))
        receipt.status = ReceiptStatus.FLAGGED

    elif from_ocr:
        # Readable, but read off pixels. Surface it so the amount gets a
        # second pair of eyes before it becomes a payment.
        receipt.flags.append(ReceiptFlag(
            type=ReceiptFlagType.NEEDS_REVIEW,
            severity="warning",
            message=(
                f"Read from a photo or scan by text recognition. Please confirm the "
                f"amount and date against the image before approving."
            ),
            timestamp=_now_iso(),
        ))
        if receipt.status == ReceiptStatus.VALIDATED:
            receipt.status = ReceiptStatus.FLAGGED

    # Save
    store.get_store().put(org, _RECEIPTS, receipt.id, receipt.model_dump())
    return receipt


def validate_receipt(org_id: str, receipt: ReceiptLine) -> ReceiptLine:
    """
    Run all validation checks and flag issues.

    Returns receipt with status set to VALIDATED or FLAGGED, and flags list populated.
    """
    org = store.require_org(org_id)
    policy = get_policy(org)
    receipt.org_id = org

    flags: list[ReceiptFlag] = []

    # ─── data quality gates ──────────────────────────────────────────────────

    # Vendor name
    if not receipt.extracted.vendor_name:
        severity = "error" if not policy.allow_missing_vendor else "warning"
        flags.append(ReceiptFlag(
            type=ReceiptFlagType.MISSING_VENDOR,
            severity=severity,
            message="Vendor name could not be extracted from receipt. Please review and correct.",
            timestamp=_now_iso(),
        ))

    # Receipt date
    if not receipt.extracted.receipt_date:
        severity = "error" if not policy.allow_missing_date else "warning"
        flags.append(ReceiptFlag(
            type=ReceiptFlagType.MISSING_DATE,
            severity=severity,
            message="Receipt date could not be extracted. Please review and correct.",
            timestamp=_now_iso(),
        ))

    # Amount
    if receipt.amount_submitted <= 0:
        flags.append(ReceiptFlag(
            type=ReceiptFlagType.MISSING_AMOUNT,
            severity="error",
            message="Amount must be greater than 0.",
            timestamp=_now_iso(),
        ))

    # Amount mismatch (if OCR extracted an amount)
    if receipt.extracted.extracted_amount is not None:
        diff = abs(receipt.extracted.extracted_amount - receipt.amount_submitted)
        if diff > 0.01:  # allow 1 cent rounding
            flags.append(ReceiptFlag(
                type=ReceiptFlagType.AMOUNT_MISMATCH,
                severity="warning",
                message=f"Extracted amount {receipt.extracted.extracted_amount} differs from submitted {receipt.amount_submitted}. Review for accuracy.",
                timestamp=_now_iso(),
            ))

    # ─── policy checks ──────────────────────────────────────────────────────

    # Run each policy rule
    for rule in policy.rules:
        if not rule.active:
            continue

        if rule.rule_type == "max_amount":
            if rule.max_amount and receipt.amount_submitted > rule.max_amount:
                flags.append(ReceiptFlag(
                    type=ReceiptFlagType.POLICY_VIOLATION,
                    severity="error",
                    message=f"Amount {receipt.amount_submitted} exceeds policy max {rule.max_amount} ({rule.name}).",
                    timestamp=_now_iso(),
                ))

        elif rule.rule_type == "forbidden_vendor":
            if receipt.extracted.vendor_name.lower() in [v.lower() for v in rule.forbidden_vendors]:
                flags.append(ReceiptFlag(
                    type=ReceiptFlagType.UNAUTHORIZED_VENDOR,
                    severity="error",
                    message=f"Vendor '{receipt.extracted.vendor_name}' is not approved ({rule.name}).",
                    timestamp=_now_iso(),
                ))

        elif rule.rule_type == "required_vendor":
            if rule.required_vendors and receipt.extracted.vendor_name.lower() not in [v.lower() for v in rule.required_vendors]:
                flags.append(ReceiptFlag(
                    type=ReceiptFlagType.UNAUTHORIZED_VENDOR,
                    severity="warning",
                    message=f"Vendor '{receipt.extracted.vendor_name}' not in approved list ({rule.name}). Review for exception.",
                    timestamp=_now_iso(),
                ))

        elif rule.rule_type == "category":
            if rule.allowed_categories and receipt.category.lower() not in [c.lower() for c in rule.allowed_categories]:
                flags.append(ReceiptFlag(
                    type=ReceiptFlagType.UNSUPPORTED_CATEGORY,
                    severity="warning",
                    message=f"Category '{receipt.category}' not in approved list ({rule.name}).",
                    timestamp=_now_iso(),
                ))

    # ─── duplicate detection ────────────────────────────────────────────────

    recent_receipts = _get_recent_receipts(org, days=policy.duplicate_window_days)
    for other in recent_receipts:
        if other.id == receipt.id:
            continue  # don't compare against itself
        # Same vendor + similar amount within window = potential duplicate
        if (
            other.extracted.vendor_name.lower() == receipt.extracted.vendor_name.lower()
            and abs(other.amount_submitted - receipt.amount_submitted) < 0.01
        ):
            flags.append(ReceiptFlag(
                type=ReceiptFlagType.DUPLICATE_DETECTED,
                severity="warning",
                message=f"Similar receipt from {other.extracted.vendor_name} for {other.amount_submitted} found {other.uploaded_at}. Verify not a duplicate.",
                timestamp=_now_iso(),
            ))
            break  # only flag once

    # ─── determine final status ──────────────────────────────────────────────

    receipt.flags = flags
    has_errors = any(f.severity == "error" for f in flags)
    receipt.status = ReceiptStatus.FLAGGED if (flags or has_errors) else ReceiptStatus.VALIDATED
    receipt.updated_at = _now_iso()

    return receipt


def resolve_flags(org_id: str, receipt_id: str, decision: Literal["approved", "rejected"], reviewed_by: str = "", notes: str = "") -> ReceiptLine:
    """
    Finance reviews a flagged receipt and decides: approve anyway or reject.
    Raises ValueError if receipt is not in FLAGGED state.
    """
    org = store.require_org(org_id)
    receipt = get_receipt(org, receipt_id)
    if receipt is None:
        raise ValueError(f"Receipt '{receipt_id}' not found.")

    if receipt.status != ReceiptStatus.FLAGGED:
        raise ValueError(f"Cannot resolve: receipt is '{receipt.status}', not 'flagged'.")

    if decision == "approved":
        receipt.status = ReceiptStatus.APPROVED
    else:
        receipt.status = ReceiptStatus.REJECTED

    receipt.reviewed_by = reviewed_by
    receipt.review_decision = decision
    receipt.review_notes = notes
    receipt.updated_at = _now_iso()

    store.get_store().put(org, _RECEIPTS, receipt.id, receipt.model_dump())
    return receipt


# ─── retrieval ──────────────────────────────────────────────────────────────


def get_receipt(org_id: str, receipt_id: str) -> Optional[ReceiptLine]:
    """Retrieve a single receipt."""
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _RECEIPTS, receipt_id)
    return ReceiptLine.model_validate(raw) if raw else None


def list_receipts(org_id: str, status: Optional[ReceiptStatus] = None, project_code: Optional[str] = None) -> list[ReceiptLine]:
    """List receipts for an org, optionally filtered by status or project."""
    org = store.require_org(org_id)
    rows = [ReceiptLine.model_validate(r) for r in store.get_store().list(org, _RECEIPTS)]

    if status:
        rows = [r for r in rows if r.status == status]
    if project_code:
        rows = [r for r in rows if r.project_code == project_code]

    # Newest first
    rows.sort(key=lambda r: r.uploaded_at or r.created_at or "", reverse=True)
    return rows


# ─── helpers (private) ──────────────────────────────────────────────────────


def _get_recent_receipts(org_id: str, days: int = 7) -> list[ReceiptLine]:
    """Get receipts from the last N days for duplicate detection."""
    org = store.require_org(org_id)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    cutoff_iso = cutoff.isoformat(timespec="seconds")

    all_receipts = list_receipts(org)
    return [r for r in all_receipts if (r.uploaded_at or "") >= cutoff_iso]


def _extract_amount(text: str) -> Optional[float]:
    """
    Extract the payable amount from OCR'd text.

    Labelled totals win. Taking simply the first number on the page reads the
    year out of "DATE: 2026-08-15" and reports a 2,026 receipt — a wrong number
    that looks plausible, which is worse than no number at all. So we look for
    an explicit TOTAL/AMOUNT/GRAND TOTAL label first, and only fall back to a
    bare number once date-like runs have been stripped out.
    """
    import re

    # 1. Labelled amount — the reliable signal. TOTAL beats AMOUNT (a receipt
    #    often lists AMOUNT per line item but TOTAL once).
    #
    #    Two traps here, both of which under-report the payable:
    #
    #    * "SUBTOTAL" contains "TOTAL". Without the lookbehind, a VAT invoice
    #      reading SUBTOTAL 375,000 / VAT 28,125 / TOTAL 403,125 returned the
    #      SUBTOTAL — the vendor gets underpaid by exactly the tax, which is
    #      the sort of error that surfaces as a supplier dispute months later.
    #    * Totals sit at the BOTTOM of a document, so where a label appears
    #      more than once we take the last occurrence, not the first.
    for label in (r"GRAND\s*TOTAL", r"TOTAL\s*DUE", r"NET\s*PAYABLE",
                  r"TOTAL", r"AMOUNT\s*PAID", r"AMOUNT"):
        matches = list(re.finditer(
            # (?<![A-Za-z]) stops SUBTOTAL matching TOTAL.
            # Thousand-separated form FIRST, and it must actually contain a
            # separator (+ not *). Regex alternation takes the first branch
            # that matches, not the longest — with `*` here, "5000" matched
            # the leading "500" and silently under-reported the amount by 10x.
            rf"(?<![A-Za-z]){label}\s*[:\-]?\s*(?:NGN|USD|GBP|EUR|₦|\$|£|€)?\s*"
            r"([0-9]{1,3}(?:[,\s][0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
            text, re.IGNORECASE,
        ))
        if matches:
            try:
                return float(re.sub(r"[,\s]", "", matches[-1].group(1)))
            except Exception:
                pass

    # 2. Unlabelled fallback. Remove ISO / slashed dates first so their digits
    #    can't be mistaken for money.
    cleaned = re.sub(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", " ", text)
    cleaned = re.sub(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", " ", cleaned)

    candidates: list[float] = []
    for raw in re.findall(
        r"(?:NGN|USD|GBP|EUR|₦|\$|£|€)?\s*"
        r"([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{2})",
        cleaned,
    ):
        try:
            candidates.append(float(raw.replace(",", "")))
        except Exception:
            continue

    # The largest well-formed figure on a receipt is the total far more often
    # than the first one is.
    return max(candidates) if candidates else None


def _extract_date(text: str) -> str:
    """Extract a date from OCR'd text. Returns ISO format YYYY-MM-DD or empty string."""
    import re
    # Match common date patterns: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, etc.
    patterns = [
        r"(\d{4})-(\d{2})-(\d{2})",       # YYYY-MM-DD
        r"(\d{2})/(\d{2})/(\d{4})",       # DD/MM/YYYY or MM/DD/YYYY
        r"(\d{2})-(\d{2})-(\d{4})",       # DD-MM-YYYY or MM-DD-YYYY
        r"DATE:\s*(\d{4}-\d{2}-\d{2})",   # DATE: YYYY-MM-DD
        r"DATE:\s*(\d{2}/\d{2}/\d{4})",   # DATE: DD/MM/YYYY
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0) if len(match.groups()) == 0 else match.group(1) if match.lastindex == 1 else match.group(0)
    return ""


def _extract_vendor(text: str) -> str:
    """Extract vendor name from OCR'd text. Look for VENDOR: pattern or capitalized lines."""
    import re
    # First try explicit "VENDOR:" pattern
    match = re.search(r"VENDOR:\s*([^\n]+)", text, re.IGNORECASE)
    if match:
        # Strip leading punctuation. A spreadsheet with "Vendor:" in one cell
        # and the name in the next extracts as "Vendor:: Sahel Catering", and
        # the stray colon then travels all the way to the payment record.
        vendor = match.group(1).strip().lstrip(":-–—").strip()
        if vendor:
            return vendor[:100]  # truncate to 100 chars

    # Fallback: the first plausible capitalised line is usually the vendor's
    # name at the top of the receipt. But it must not be one of the OTHER
    # labelled fields — "DATE: 2026-08-16" is a date, and returning it as the
    # vendor manufactures a confident wrong answer instead of admitting the
    # vendor is absent. Blank is the honest result; the reviewer can then
    # actually see the gap and fill it in.
    _META_LABELS = (
        "date", "amount", "total", "subtotal", "tax", "vat", "invoice",
        "receipt", "ref", "reference", "qty", "quantity", "item", "items",
        "project", "category", "grant", "notes", "note", "fieldworker",
        "kobo", "submitted", "balance", "change", "cash", "card",
    )
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) <= 2 or len(line) >= 100:
            continue
        head = line.split(":", 1)[0].strip().lower() if ":" in line else ""
        if head and head in _META_LABELS:
            continue
        if line.lower().startswith(_META_LABELS):
            continue
        if not line[0].isupper():
            continue
        return line[:50]
    return ""


def _infer_mimetype(filename: str) -> str:
    """Guess MIME type from filename."""
    filename_lower = filename.lower()
    if filename_lower.endswith(".pdf"):
        return "application/pdf"
    elif filename_lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    elif filename_lower.endswith(".png"):
        return "image/png"
    elif filename_lower.endswith(".gif"):
        return "image/gif"
    else:
        return "application/octet-stream"
