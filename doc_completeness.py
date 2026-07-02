"""
Document-presence detection — fast, deterministic, code-first.

The #1 cause of payment delays is missing supporting documents. Detecting which
documents are attached does NOT need an LLM: real financial documents announce
what they are in their header ("PURCHASE ORDER", "GOODS RECEIVED NOTE", "TAX
INVOICE"). We match those signatures with regex against the filename + the first
slice of extracted text — milliseconds, zero tokens, zero waiting.

Flow:
  1. classify(filename, text)         -> the category(ies) a file appears to be
  2. check_completeness(required, files) -> present / missing / unclassified

An LLM second-pass is only worth it for files this can't classify
(``unclassified``) — the code handles the overwhelming common case instantly.
"""
from __future__ import annotations

import re

# Canonical category -> signature patterns. Matched case-insensitively against
# the filename plus the document's header text. Tuned for NGO / procurement /
# finance paperwork (incl. Nigerian terms: LPO, GRN, proforma, waybill).
_SIGNATURES: dict[str, list[str]] = {
    "invoice": [r"\binvoice\b", r"tax\s+invoice", r"pro[\s-]?forma"],
    "purchase_order": [
        r"purchase\s+order", r"\bP\.?O\.?\s*(no|number|#)", r"\bLPO\b",
        r"local\s+purchase\s+order",
    ],
    "goods_received_note": [
        r"goods\s+received\s+note", r"\bGRN\b", r"delivery\s+note",
        r"proof\s+of\s+delivery", r"\bwaybill\b",
    ],
    "receipt": [r"\breceipt\b", r"payment\s+receipt", r"official\s+receipt"],
    "quotation": [
        r"\bquotation\b", r"\bquote\b", r"\bRFQ\b",
        r"request\s+for\s+quotation", r"bid\s+(analysis|matrix)",
        r"comparative\s+(bid\s+)?analysis",
    ],
    "contract": [
        r"\bcontract\b", r"\bagreement\b", r"terms\s+of\s+reference",
        r"\bToR\b", r"consultan(t|cy)\s+agreement",
    ],
    "attendance": [
        r"attendance\s+(sheet|list|register)", r"sign[\s-]?in\s+sheet",
        r"participant\s+list",
    ],
    "payment_schedule": [
        r"payment\s+schedule", r"schedule\s+of\s+payment", r"bank\s+details",
        r"account\s+(no|number|name)",
    ],
    "travel_request": [
        r"travel\s+(request|authorisation|authorization)", r"trip\s+request",
        r"travel\s+form",
    ],
    "itinerary": [r"\bitinerary\b", r"flight\s+(details|booking|itinerary)", r"boarding\s+pass"],
    "budget": [r"\bbudget\b", r"approved\s+budget", r"budget\s+line"],
    "activity_report": [r"activity\s+report", r"completion\s+report", r"narrative\s+report"],
    "deliverables_report": [r"deliverabl", r"inception\s+report", r"final\s+report"],
    "approval": [
        r"approv(al|ed)\s+(form|memo|email|note)", r"authorisation\s+(form|memo)",
        r"sign[\s-]?off",
    ],
    "voucher": [r"payment\s+voucher", r"\bP\.?V\.?\s*(no|number|#)", r"requisition"],
}

_STOP = {
    "the", "and", "for", "with", "from", "form", "report", "document", "note",
    "any", "applicable", "signed", "proof", "of", "if", "all", "each",
}


def classify(filename: str, text: str) -> set[str]:
    """Return the set of document categories a file appears to be. One file can
    match several (e.g. a combined invoice + receipt scan)."""
    hay = f"{filename or ''}\n{(text or '')[:1500]}"
    hits: set[str] = set()
    for cat, patterns in _SIGNATURES.items():
        if any(re.search(p, hay, re.I) for p in patterns):
            hits.add(cat)
    return hits


def _label_to_category(label: str) -> str | None:
    for cat, patterns in _SIGNATURES.items():
        if any(re.search(p, label, re.I) for p in patterns):
            return cat
    return None


def check_completeness(
    required_labels: list[str],
    files: list[tuple[str, str]],
) -> dict:
    """Determine which required documents are present in the uploaded bundle.

    required_labels: the payment type's required docs, as free text
                     (e.g. ["Purchase order (PO)", "Invoice", "GRN"])
    files:           list of (filename, extracted_text)

    Returns:
      { present: [...], missing: [...], unclassified_files: [...], complete: bool }
    """
    detected: set[str] = set()
    unclassified: list[str] = []
    file_cats: list[tuple[str, str, set[str]]] = []
    for fn, txt in files:
        cats = classify(fn, txt)
        file_cats.append((fn, txt, cats))
        if cats:
            detected |= cats
        else:
            unclassified.append(fn)

    present: list[str] = []
    missing: list[str] = []
    for label in required_labels:
        cat = _label_to_category(label)
        ok = bool(cat and cat in detected)
        if not ok:
            # Generic fallback: the label's own significant words appear in a file.
            words = [
                w for w in re.findall(r"[a-zA-Z]{4,}", label.lower())
                if w not in _STOP
            ][:2]
            if words:
                for fn, txt, _ in file_cats:
                    hay = f"{fn}\n{txt[:1500]}".lower()
                    if all(w in hay for w in words):
                        ok = True
                        break
        (present if ok else missing).append(label)

    return {
        "present": present,
        "missing": missing,
        "unclassified_files": unclassified,
        "complete": not missing,
    }
