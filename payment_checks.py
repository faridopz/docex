"""
Deterministic payment-check engine — classic accounts-payable controls in code.

The counterpart to deterministic_checks.py: that module evaluates structured
FORM submissions; this one runs the controls that apply to DOCUMENT-based
payments (invoice / PO / GRN uploads) — the checks an auditor does by eye and a
computer does perfectly:

  - Three-way match — the invoice, purchase order and goods-received note must
    agree on amount, and the PO number must cross-reference.
  - Duplicate payment — the same invoice number must not have been paid before.

These are arithmetic and lookup problems: an LLM does them slower, costs tokens,
and can miscompare digits. Code does them instantly, for free, and never
hallucinates a match. It emits the same ``RuleResult`` objects the LLM check
produces, so deterministic findings merge straight into the existing verdict.

Storage-agnostic: the caller supplies ``prior_invoice_numbers`` for duplicate
detection (the API layer has the check history). Never raises — a bad field
resolves to a clear ``insufficient_evidence`` result, never an exception.
"""
from __future__ import annotations

import re
from typing import Optional

import doc_completeness
import fast_fields
from models import RuleResult

# Amounts within this fraction of each other count as matching — absorbs
# rounding and minor FX/VAT-inclusive vs exclusive differences without masking a
# real discrepancy.
_TOLERANCE = 0.01  # 1%


def _amount(profile: dict) -> Optional[float]:
    f = profile["fields"].get("fields", {}).get("total_amount")
    if not f:
        return None
    try:
        return float(f["value"])
    except (TypeError, ValueError, KeyError):
        return None


def _field(profile: dict, key: str) -> Optional[str]:
    f = profile["fields"].get("fields", {}).get(key)
    if f and f.get("value") is not None:
        return str(f["value"]).strip()
    return None


def _profiles(documents: list[tuple[str, str]]) -> list[dict]:
    """Classify + field-extract every document once, up front."""
    out: list[dict] = []
    for filename, text in documents:
        out.append(
            {
                "name": filename,
                "cats": doc_completeness.classify(filename, text),
                "fields": fast_fields.extract_fields(text),
            }
        )
    return out


def _pick(profiles: list[dict], category: str) -> list[dict]:
    return [p for p in profiles if category in p["cats"]]


def _po_match(a: str, b: str) -> bool:
    """Tolerant PO-number comparison. Field extraction can yield 'PO-8890' from
    one document and '8890' from another, so we compare after stripping
    non-alphanumerics and, failing that, on the digit core — genuinely
    different POs (8890 vs 1111) still differ."""
    na = re.sub(r"[^a-z0-9]", "", a.lower())
    nb = re.sub(r"[^a-z0-9]", "", b.lower())
    if na == nb:
        return True
    da, db = re.sub(r"\D", "", na), re.sub(r"\D", "", nb)
    return bool(da) and da == db


def three_way_match(profiles: list[dict]) -> Optional[RuleResult]:
    """Invoice ↔ PO ↔ GRN amount agreement + PO-number cross-reference.

    Returns None (the check simply doesn't apply) unless at least an invoice
    AND a purchase order are present — no noise on payments this doesn't fit.
    """
    # An invoice usually CITES its PO number ("Purchase Order: PO-8890"), so it
    # classifies as both invoice AND purchase_order. Exclude anything that's an
    # invoice from the PO/GRN candidates so we never compare the invoice to
    # itself — pick the standalone PO and GRN documents.
    inv_docs = [p for p in profiles if "invoice" in p["cats"]]
    po_docs = [p for p in profiles if "purchase_order" in p["cats"] and "invoice" not in p["cats"]]
    grn_docs = [p for p in profiles if "goods_received_note" in p["cats"] and "invoice" not in p["cats"]]
    inv = inv_docs[0] if inv_docs else None
    po = po_docs[0] if po_docs else None
    grn = grn_docs[0] if grn_docs else None
    if inv is None or po is None:
        return None

    rid = "det-three-way-match"
    desc = "Invoice, purchase order and goods-received note must agree (three-way match)."

    inv_amt, po_amt = _amount(inv), _amount(po)
    if inv_amt is None or po_amt is None:
        missing = []
        if inv_amt is None:
            missing.append("invoice amount")
        if po_amt is None:
            missing.append("purchase order amount")
        return RuleResult(
            rule_id=rid, rule_description=desc, verdict="insufficient_evidence",
            reasoning="Couldn't read " + " and ".join(missing) + " to compare — verify manually.",
            missing_evidence=missing, confidence="not_found",
        )

    tol = max(inv_amt, po_amt) * _TOLERANCE
    amounts_agree = abs(inv_amt - po_amt) <= tol

    # PO-number cross-reference: the invoice's cited PO vs the PO document's own.
    inv_po = _field(inv, "po_number")
    po_po = _field(po, "po_number")
    po_refs_ok = (not (inv_po and po_po)) or _po_match(inv_po, po_po)

    grn_note = " GRN present." if grn else " No GRN attached — two-way match only."
    evidence = f"invoice={inv_amt:,.2f}; po={po_amt:,.2f}"

    # An amount disagreement is a hard block. A PO-reference discrepancy alone is
    # a flag: PO formats vary and extraction can differ, so surface it for review
    # rather than hard-stopping a payment whose amounts actually agree.
    if not amounts_agree:
        extra = (
            f"; the invoice also cites PO {inv_po} but the PO document is {po_po}"
            if (inv_po and po_po and not po_refs_ok) else ""
        )
        return RuleResult(
            rule_id=rid, rule_description=desc, verdict="block",
            reasoning=(
                f"Three-way match failed: invoice {inv_amt:,.2f} ≠ PO {po_amt:,.2f} "
                f"(difference {abs(inv_amt - po_amt):,.2f}){extra}."
            ),
            payment_evidence=evidence, confidence="found",
        )

    if not po_refs_ok:
        return RuleResult(
            rule_id=rid, rule_description=desc, verdict="flag",
            reasoning=(
                f"Amounts agree ({inv_amt:,.2f}), but the invoice cites PO {inv_po} "
                f"while the PO document is {po_po} — confirm they're the same order."
            ),
            payment_evidence=evidence, confidence="found",
        )

    return RuleResult(
        rule_id=rid, rule_description=desc, verdict="pass",
        reasoning=(
            f"Invoice ({inv_amt:,.2f}) and PO ({po_amt:,.2f}) amounts agree"
            + (f", PO ref {inv_po} matches." if inv_po and po_po else ".")
            + grn_note
        ),
        payment_evidence=evidence, confidence="found",
    )


def duplicate_invoice(
    profiles: list[dict], prior_invoice_numbers: Optional[list[str]]
) -> Optional[RuleResult]:
    """Block if this invoice number was already processed. Returns None if
    there's no invoice or no readable invoice number (nothing to compare)."""
    inv = _pick(profiles, "invoice")
    if not inv:
        return None
    num = _field(inv[0], "invoice_number")
    if not num:
        return None

    rid = "det-duplicate-invoice"
    desc = "An invoice must not be paid twice (duplicate-payment control)."
    priors = {p.strip().lower() for p in (prior_invoice_numbers or []) if p and p.strip()}
    if num.strip().lower() in priors:
        return RuleResult(
            rule_id=rid, rule_description=desc, verdict="block",
            reasoning=f"Invoice number {num} has already been processed — possible duplicate payment.",
            payment_evidence=f"invoice_number={num}", confidence="found",
        )
    return RuleResult(
        rule_id=rid, rule_description=desc, verdict="pass",
        reasoning=f"Invoice number {num} has not been processed before.",
        payment_evidence=f"invoice_number={num}", confidence="found",
    )


def primary_invoice_number(documents: list[tuple[str, str]]) -> Optional[str]:
    """The invoice number on the payment's invoice, if readable — stored on the
    check so later payments can be tested against it for duplicates."""
    for p in _profiles(documents):
        if "invoice" in p["cats"]:
            num = _field(p, "invoice_number")
            if num:
                return num
    return None


def run_document_checks(
    documents: list[tuple[str, str]],
    *,
    prior_invoice_numbers: Optional[list[str]] = None,
) -> list[RuleResult]:
    """Run every applicable deterministic AP control over a payment's documents.

    Returns only the checks that actually apply (a payment with no invoice/PO
    yields an empty list — the LLM/other rules still run). Order is stable.
    """
    profiles = _profiles(documents)
    results: list[RuleResult] = []
    for finding in (
        three_way_match(profiles),
        duplicate_invoice(profiles, prior_invoice_numbers),
    ):
        if finding is not None:
            results.append(finding)
    return results
