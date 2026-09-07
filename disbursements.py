"""
The payment ledger — one record of every naira that left the account, whatever
authorised it.

WHY THIS EXISTS
DOCex grew two separate money paths. Requisitions freeze an immutable
TransactionRecord when they are paid. Vouchers and payroll runs go through
transactions.py, which tracks workflow state but has nowhere to put a bank
reference, no payee name, and no payment date except buried in an event log.

Reconciliation read only the first one. So a payroll run that was properly
raised, reviewed and approved appeared on the bank statement as "money left the
account with no approved request" — the most serious finding the system can
produce, fired at a payment that was entirely correct. A control that cries
wolf is worse than no control, because the third false alarm is when people
stop reading them.

The fix is not to teach reconciliation about every payment path. It is to
recognise that all those paths produce the SAME FACT — we sent this much money
to this payee on this date with this reference — and to give that fact one
home. Reconciliation reads disbursements and knows nothing about requisitions,
vouchers or payroll. A new payment path added next year is reconciled the day
it ships, provided it records what it paid.

ONE AUTHORISATION, MANY PAYMENTS
A requisition is one payment: one record, one bank debit. Payroll is not. A run
covering twelve staff is ONE approval and, on the statement, usually twelve
debits — or one, if the organisation uploads a bulk file to the bank. Both are
normal, and the difference is invisible from inside DOCex. So a disbursement is
one *intended outflow*: twelve staff paid individually make twelve
disbursements sharing a `batch_id`; the same run paid as a lump sum makes one,
marked `bulk`. Reconciliation then matches what actually happened rather than
what we assumed would.

DERIVED, NOT DUPLICATED
Requisition payments are NOT copied in here. The frozen TransactionRecord
already holds every field a disbursement needs, so `list_disbursements` reads
it and converts on the fly. Copying would mean two records of one payment that
can drift apart, and a ledger that disagrees with the audit trail is worse than
no ledger. Only payments with nowhere else to live — vouchers, payroll,
anything recorded directly — are stored here.

No LLM. Every value is copied from a record or supplied by the person who made
the payment.
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import Enum
from typing import Iterable, Optional

from pydantic import BaseModel, Field

import store

_DISBURSEMENTS = "disbursements"


class SourceKind(str, Enum):
    """What authorised the money leaving."""
    REQUISITION = "requisition"
    VOUCHER = "voucher"
    PAYROLL = "payroll"
    # Recorded directly — a bank charge someone chose to log, an opening
    # correction. Deliberately available, deliberately named so it stands out
    # in a list: money out with no workflow behind it should look unusual.
    DIRECT = "direct"


class Settlement(str, Enum):
    INDIVIDUAL = "individual"   # one payee, one transfer
    BULK = "bulk"               # many payees, one debit on the statement


class DisbursementError(ValueError):
    """Invalid payment record — callers map this to HTTP 4xx."""


class Disbursement(BaseModel):
    """One outflow of money, as reconciliation needs to see it.

    Every field here exists because matching or explaining a bank line needs
    it. `bank_reference` is the strongest matching signal there is, which is
    why recording a payment without one is allowed but reported.
    """
    id: str
    org_id: str = ""

    # What authorised it, and how to get back there from a bank line.
    source_kind: SourceKind = SourceKind.DIRECT
    source_id: str = ""
    source_ref: str = ""              # REQ-0001, V7, PR3 — what a human quotes

    payee_name: str = ""
    payee_account: str = ""
    amount: float = 0.0
    currency: str = "NGN"

    paid_at: str = ""                 # ISO date or datetime
    paid_by: str = ""
    bank_reference: str = ""

    # Set when one authorisation produced several transfers, so the screen can
    # show "12 of 12 salary payments matched" instead of twelve loose rows.
    batch_id: str = ""
    settlement: Settlement = Settlement.INDIVIDUAL
    memo: str = ""

    created_at: str = ""

    @property
    def paid_date(self) -> str:
        return (self.paid_at or "")[:10]


# ─── helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _money(x: float) -> float:
    return round(float(x or 0.0), 2)


def _period_bounds(period: str) -> tuple[str, str]:
    try:
        year, month = (int(p) for p in period.split("-")[:2])
        start = dt.date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise DisbursementError(
            f"Period must look like '2026-08', got '{period}'.") from exc
    end = (dt.date(year + (month == 12), (month % 12) + 1, 1)
           - dt.timedelta(days=1))
    return start.isoformat(), end.isoformat()


# ─── recording ──────────────────────────────────────────────────────────────


def record(
    org_id: str,
    *,
    source_kind: SourceKind | str,
    source_id: str,
    source_ref: str = "",
    payee_name: str,
    amount: float,
    paid_at: str = "",
    paid_by: str = "",
    bank_reference: str = "",
    payee_account: str = "",
    currency: str = "NGN",
    batch_id: str = "",
    settlement: Settlement | str = Settlement.INDIVIDUAL,
    memo: str = "",
) -> Disbursement:
    """Record one payment.

    Refuses a zero or negative amount and an unnamed payee: a ledger line that
    cannot say who was paid or how much is not evidence of anything, and it
    would sit in reconciliation for ever as an item nobody can resolve.
    """
    org = store.require_org(org_id)
    if not (payee_name or "").strip():
        raise DisbursementError("A payment must name who was paid.")
    if _money(amount) <= 0:
        raise DisbursementError(
            f"A payment must be a positive amount (got {amount}). Record a "
            "refund or reversal as its own credit, not as a negative payment.")

    d = Disbursement(
        id=uuid.uuid4().hex[:12],
        org_id=org,
        source_kind=SourceKind(source_kind),
        source_id=source_id,
        source_ref=source_ref or source_id,
        payee_name=payee_name.strip(),
        payee_account=payee_account.strip(),
        amount=_money(amount),
        currency=currency,
        paid_at=paid_at or _now_iso(),
        paid_by=paid_by,
        bank_reference=(bank_reference or "").strip(),
        batch_id=batch_id,
        settlement=Settlement(settlement),
        memo=memo,
        created_at=_now_iso(),
    )
    store.get_store().put(org, _DISBURSEMENTS, d.id, d.model_dump())
    return d


def record_batch(
    org_id: str,
    *,
    source_kind: SourceKind | str,
    source_id: str,
    source_ref: str = "",
    lines: Iterable[dict],
    paid_at: str = "",
    paid_by: str = "",
    currency: str = "NGN",
    bulk_reference: str = "",
    bulk_payee: str = "",
) -> list[Disbursement]:
    """Record a payroll run or participant voucher.

    Two shapes, because organisations pay both ways and the statement looks
    completely different:

      * `bulk_reference` given → the whole run left as ONE transfer. One
        disbursement for the total, marked bulk, with the payee count in the
        memo so a human reading the reconciliation knows what the lump sum was.
      * otherwise → one disbursement per line, sharing a batch_id.

    Each line: {"payee_name", "amount", optional "bank_reference",
    "payee_account", "memo"}.
    """
    rows = [dict(l) for l in lines]
    if not rows:
        raise DisbursementError("A payment batch needs at least one line.")

    batch_id = uuid.uuid4().hex[:12]
    when = paid_at or _now_iso()

    if bulk_reference.strip():
        total = _money(sum(_money(r.get("amount", 0)) for r in rows))
        payee = bulk_payee.strip() or f"{source_ref or source_id} ({len(rows)} payees)"
        return [record(
            org_id, source_kind=source_kind, source_id=source_id,
            source_ref=source_ref, payee_name=payee, amount=total,
            paid_at=when, paid_by=paid_by, bank_reference=bulk_reference,
            currency=currency, batch_id=batch_id, settlement=Settlement.BULK,
            memo=f"Bulk transfer covering {len(rows)} payee(s).")]

    return [record(
        org_id, source_kind=source_kind, source_id=source_id,
        source_ref=source_ref,
        payee_name=str(r.get("payee_name") or "").strip(),
        amount=r.get("amount", 0),
        paid_at=when, paid_by=paid_by,
        bank_reference=str(r.get("bank_reference") or ""),
        payee_account=str(r.get("payee_account") or ""),
        currency=currency, batch_id=batch_id,
        settlement=Settlement.INDIVIDUAL,
        memo=str(r.get("memo") or ""),
    ) for r in rows]


# ─── reading ────────────────────────────────────────────────────────────────


def _from_requisitions(org_id: str) -> list[Disbursement]:
    """Convert frozen requisition payments into disbursements, on the fly.

    Not stored. The TransactionRecord is already the immutable evidence and
    already holds every field needed; copying it here would create a second
    record of one payment, and two records of one payment eventually disagree.
    """
    try:
        import requisitions as rq
    except ImportError:                                    # pragma: no cover
        return []

    out: list[Disbursement] = []
    for txn in rq.list_transactions(org_id):
        out.append(Disbursement(
            # Deterministic id derived from the transaction, so the same
            # payment keeps the same identity across calls — the reconciliation
            # screen stores these ids in matches and explanations.
            id=f"req-{txn.id}",
            org_id=org_id,
            source_kind=SourceKind.REQUISITION,
            source_id=txn.requisition_id or txn.id,
            source_ref=txn.requisition_ref or txn.id,
            payee_name=txn.vendor_name,
            payee_account=txn.vendor_account,
            amount=_money(txn.amount),
            currency=txn.currency or "NGN",
            paid_at=txn.paid_at,
            paid_by=txn.paid_by,
            bank_reference=txn.bank_reference,
            memo=txn.category or "",
            created_at=txn.paid_at,
        ))
    return out


def list_disbursements(
    org_id: str,
    *,
    period: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    source_kind: Optional[SourceKind | str] = None,
) -> list[Disbursement]:
    """Every payment in the window, from every path, newest first."""
    org = store.require_org(org_id)

    if period:
        start, end = _period_bounds(period)

    out: list[Disbursement] = list(_from_requisitions(org))
    for raw in store.get_store().list(org, _DISBURSEMENTS):
        try:
            out.append(Disbursement.model_validate(raw))
        except Exception:
            continue

    if source_kind is not None:
        want = SourceKind(source_kind)
        out = [d for d in out if d.source_kind == want]
    if start:
        out = [d for d in out if d.paid_date >= start]
    if end:
        out = [d for d in out if d.paid_date <= end]

    out.sort(key=lambda d: (d.paid_at or "", d.source_ref), reverse=True)
    return out


def get(org_id: str, disbursement_id: str) -> Optional[Disbursement]:
    org = store.require_org(org_id)
    if disbursement_id.startswith("req-"):
        return next((d for d in _from_requisitions(org)
                     if d.id == disbursement_id), None)
    raw = store.get_store().get(org, _DISBURSEMENTS, disbursement_id)
    return Disbursement.model_validate(raw) if raw else None


def coverage(org_id: str, period: str) -> dict:
    """How reconcilable this month's payments are, before anyone uploads a
    statement.

    A payment with no bank reference can still be matched on amount, date and
    payee — but it is the first thing to become ambiguous when two payments
    share a figure. Surfacing the count lets an organisation fix a habit
    ("finance stopped pasting the transfer reference in March") rather than
    fight the symptom every month end.
    """
    items = list_disbursements(org_id, period=period)
    by_source: dict[str, dict] = {}
    for d in items:
        row = by_source.setdefault(d.source_kind.value, {"count": 0, "value": 0.0})
        row["count"] += 1
        row["value"] = _money(row["value"] + d.amount)

    no_ref = [d for d in items if not d.bank_reference]
    return {
        "period": period,
        "payments": len(items),
        "value": _money(sum(d.amount for d in items)),
        "by_source": by_source,
        "without_bank_reference": len(no_ref),
        "batches": len({d.batch_id for d in items if d.batch_id}),
        "bulk_payments": len([d for d in items if d.settlement == Settlement.BULK]),
    }
