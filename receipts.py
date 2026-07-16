"""
Travel-retirement reconciliation — deterministic math over extracted receipts.

The retirement flow: a traveller who took an advance (or paid out of pocket)
submits their receipts; finance reconciles what was ACTUALLY spent against the
advance and reimburses the difference (or recovers the unspent balance).

Summing receipts and computing a balance is arithmetic — code does it exactly,
instantly, and never miscounts. Reading the receipts themselves (usually phone
photos) is the part that needs OCR/vision; this module works on already-parsed
``ReceiptItem`` data, so it stays fast, unit-testable, and independent of HOW
the receipts were read (Claude vision, Textract, or manual entry).

Never raises: a receipt whose amount couldn't be read becomes a flag, not an
exception — finance still gets a usable reconciliation with the gap surfaced.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from models import ReceiptItem, Reconciliation, RuleResult


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value or not str(value).strip():
        return None
    try:
        return datetime.fromisoformat(str(value).strip()[:10]).date()
    except ValueError:
        return None


def _flag(rid: str, desc: str, verdict: str, reasoning: str, evidence: str = "") -> RuleResult:
    return RuleResult(
        rule_id=rid, rule_description=desc, verdict=verdict,
        reasoning=reasoning, payment_evidence=evidence or None, confidence="found",
    )


def reconcile(
    advance_amount: Optional[float],
    receipts: list[ReceiptItem],
    *,
    trip_start: Optional[str] = None,
    trip_end: Optional[str] = None,
    per_category_caps: Optional[dict[str, float]] = None,
) -> Reconciliation:
    """Reconcile submitted receipts against a travel advance.

    advance_amount: the advance taken (None = paid out of pocket, org owes full).
    receipts:       parsed ReceiptItems.
    trip_start/end: optional ISO dates — receipts dated outside the window flag.
    per_category_caps: optional {category: cap} — a category total over cap flags.

    Returns a Reconciliation with the balance, who owes whom, and per-receipt
    flags (unreadable amount, out-of-window date, duplicates, over-cap category).
    """
    caps = per_category_caps or {}
    flags: list[RuleResult] = []

    readable = [r for r in receipts if r.amount is not None]
    total_spent = round(sum(float(r.amount) for r in readable), 2)

    # Unreadable receipts — surface each so finance knows the total is incomplete.
    for r in receipts:
        if r.amount is None:
            flags.append(_flag(
                f"receipt-unreadable-{r.filename}",
                "Every submitted receipt must have a readable amount.",
                "insufficient_evidence",
                f"Couldn't read an amount from '{r.filename}' — enter it manually or re-upload a clearer photo.",
                evidence=r.filename,
            ))

    # Duplicate receipts — same amount + date + vendor submitted twice.
    seen: set[tuple] = set()
    for r in readable:
        key = (round(float(r.amount), 2), (r.date or "").strip(), (r.vendor or "").strip().lower())
        if key in seen:
            flags.append(_flag(
                f"receipt-duplicate-{r.filename}",
                "A receipt must not be claimed twice.",
                "block",
                f"'{r.filename}' looks like a duplicate ({r.vendor or 'vendor'}, {r.amount:,.2f}, {r.date or 'no date'}).",
                evidence=r.filename,
            ))
        seen.add(key)

    # Dates outside the trip window.
    ts, te = _parse_date(trip_start), _parse_date(trip_end)
    if ts or te:
        for r in readable:
            d = _parse_date(r.date)
            if d is None:
                continue
            if (ts and d < ts) or (te and d > te):
                flags.append(_flag(
                    f"receipt-date-{r.filename}",
                    "Receipts must fall within the trip dates.",
                    "flag",
                    f"'{r.filename}' is dated {r.date}, outside the trip window "
                    f"{trip_start or '?'} → {trip_end or '?'}.",
                    evidence=r.filename,
                ))

    # Per-category caps (e.g. lodging per night, meals per diem).
    if caps:
        totals: dict[str, float] = {}
        for r in readable:
            cat = (r.category or "other").strip().lower()
            totals[cat] = totals.get(cat, 0.0) + float(r.amount)
        for cat, cap in caps.items():
            spent = totals.get(cat.strip().lower(), 0.0)
            if spent > cap:
                flags.append(_flag(
                    f"receipt-cap-{cat}",
                    f"{cat.title()} spend must not exceed its cap.",
                    "flag",
                    f"{cat.title()} totals {spent:,.2f}, over the {cap:,.2f} cap.",
                ))

    # Balance + direction.
    if advance_amount is None:
        balance = None
        direction = "out_of_pocket"      # org owes the full total_spent
    else:
        balance = round(advance_amount - total_spent, 2)
        if abs(balance) < 0.01:
            direction = "settled"
        elif balance > 0:
            direction = "recover"        # traveller returns the unspent balance
        else:
            direction = "reimburse"      # org owes the traveller the overspend

    # Human summary.
    if direction == "out_of_pocket":
        summary = f"Paid out of pocket — reimburse {total_spent:,.2f} across {len(readable)} receipt(s)."
    elif direction == "settled":
        summary = f"Fully retired — {total_spent:,.2f} spent equals the {advance_amount:,.2f} advance."
    elif direction == "recover":
        summary = f"Unspent balance of {balance:,.2f} to be returned ({total_spent:,.2f} spent of {advance_amount:,.2f} advance)."
    else:
        summary = f"Overspent by {abs(balance):,.2f} — reimburse the traveller ({total_spent:,.2f} spent of {advance_amount:,.2f} advance)."

    return Reconciliation(
        advance_amount=advance_amount,
        total_spent=total_spent,
        balance=balance,
        direction=direction,
        receipt_count=len(receipts),
        readable_count=len(readable),
        flags=flags,
        summary=summary,
    )
