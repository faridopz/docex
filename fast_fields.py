"""
Fast structured-field extraction — our own code, no LLM.

The insight (confirmed by enterprise IE research): an LLM extracts fields by
*generating* them token-by-token — slow. Structured financial documents put
their key fields behind predictable labels ("Invoice No:", "Total:", "TIN:"),
so we can *copy* them out with labelled-regex in near-constant time. Each field
carries a confidence; only fields we can't extract confidently need to fall
back to the LLM (the "selective invocation" pattern).

Operates on already-extracted text (from fast_extract). Pure stdlib.
Tuned for NGO / procurement / Nigerian finance docs (₦, NGN, TIN, 10-digit
NUBAN accounts).
"""
from __future__ import annotations

import re

# currency amount, e.g. ₦420,000.00 / NGN 420000 / N420,000 / $1,200.50
_AMOUNT = re.compile(
    r"(?:₦|NGN|N|\$|USD)\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
    re.I,
)
_TOTAL_LABEL = re.compile(
    r"(?:grand\s+total|total\s+amount|amount\s+due|total)\s*[:\-]?\s*"
    r"(?:₦|NGN|N|\$|USD)?\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)",
    re.I,
)

_LABELLED: dict[str, list[str]] = {
    "invoice_number": [r"invoice\s*(?:no|number|#|ref)\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})"],
    "po_number": [
        r"(?:purchase\s*order|\bP\.?O\.?\b|\bLPO\b)\s*(?:no|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})",
    ],
    "grn_number": [r"(?:\bGRN\b|goods\s*received\s*note)\s*(?:no|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})"],
    "tin": [r"\bTIN\b\s*[:\-]?\s*([0-9][0-9\-]{7,})"],
    "account_number": [r"account\s*(?:no|number)\b\s*[:\-]?\s*([0-9]{10})"],
    "vat": [r"\b(?:VAT|value\s+added\s+tax)\b\s*[:\-]?\s*(?:₦|NGN|N)?\s?([0-9,]+(?:\.[0-9]{1,2})?)"],
}

_DATE = re.compile(
    r"\b("
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}"
    r")\b",
    re.I,
)


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def extract_fields(text: str) -> dict:
    """Return {field: {value, confidence}} plus a `needs_llm` list of the fields
    we couldn't extract confidently (candidates for the LLM fallback).

    confidence: "high" (matched behind an explicit label) | "medium"
    (unlabelled pattern) | absent (not found).
    """
    t = text or ""
    out: dict[str, dict] = {}

    # Labelled fields — high confidence.
    for field, patterns in _LABELLED.items():
        for pat in patterns:
            m = re.search(pat, t, re.I)
            if m:
                out[field] = {"value": m.group(1).strip(), "confidence": "high"}
                break

    # Total amount: prefer a labelled total (high); else the largest amount on
    # the doc (medium — a reasonable heuristic for the payable figure).
    mtotal = _TOTAL_LABEL.search(t)
    if mtotal and _num(mtotal.group(1)) is not None:
        out["total_amount"] = {"value": _num(mtotal.group(1)), "confidence": "high"}
    else:
        amounts = [n for n in (_num(m.group(1)) for m in _AMOUNT.finditer(t)) if n]
        if amounts:
            out["total_amount"] = {"value": max(amounts), "confidence": "medium"}

    # Dates — first match, medium (labelling dates reliably is harder).
    mdate = _DATE.search(t)
    if mdate:
        out["date"] = {"value": mdate.group(1).strip(), "confidence": "medium"}

    # Which of the fields we care about are still missing → LLM fallback list.
    wanted = ["total_amount", "invoice_number", "po_number", "date", "vendor"]
    needs_llm = [f for f in wanted if f not in out]

    return {"fields": out, "needs_llm": needs_llm}
