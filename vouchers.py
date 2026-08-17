"""
DOCex vouchers — consolidate participant payables into one payment voucher and
route it for approval.

Finance raises one voucher for a whole event (e.g. "Q3 Workshop — 42
participants"), which rolls up every participant's deterministic payable
(per_diem.ParticipantPayable) into lines + a total. Submitting the voucher opens
a Transaction (kind="voucher") so it flows through the cross-department state
machine with a reference like V7 and a live status trail; the Transaction owns
the workflow status, this module owns the money math + line snapshots.

Totals are summed in code (never by an LLM). Persisted as JSON under
{root}/vouchers/, mirroring the existing file-based pattern.
"""
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Optional

import transactions as tx
from models import Voucher, VoucherLine, VoucherSummary
from per_diem import ParticipantPayable

_ROOT = Path(__file__).parent
_VOUCHER_DIR = _ROOT / "vouchers"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _ensure_dir() -> None:
    _VOUCHER_DIR.mkdir(parents=True, exist_ok=True)


def _path(voucher_id: str) -> Path:
    if not voucher_id or "/" in voucher_id or "\\" in voucher_id or ".." in voucher_id:
        raise ValueError(f"Invalid voucher id: {voucher_id!r}")
    return _VOUCHER_DIR / f"{voucher_id}.json"


def _line_from_payable(p: ParticipantPayable, role: Optional[str] = None) -> VoucherLine:
    return VoucherLine(
        participant_name=p.participant_name,
        role=role,
        days=p.per_diem.days,
        per_diem_entitlement=p.per_diem.entitlement,
        reimbursable_total=p.reimbursable_total,
        amount=p.total_payable,
        flag_count=len(p.flags),
        summary=p.summary,
    )


def build_voucher(
    event_name: str,
    payables: list[ParticipantPayable],
    *,
    currency: str = "NGN",
    created_by: Optional[str] = None,
    roles: Optional[list[Optional[str]]] = None,
) -> Voucher:
    """Roll a list of participant payables into a draft voucher. Pure math;
    does NOT open a transaction (call submit() for that). `roles` optionally
    aligns 1:1 with `payables` to stamp each line's role."""
    lines: list[VoucherLine] = []
    for i, p in enumerate(payables):
        role = roles[i] if roles and i < len(roles) else None
        lines.append(_line_from_payable(p, role))

    total = round(sum(l.amount for l in lines), 2)
    flagged = sum(1 for l in lines if l.flag_count > 0)
    now = _now_iso()

    voucher = Voucher(
        id=uuid.uuid4().hex,
        event_name=event_name.strip() or "Untitled event",
        lines=lines,
        total=total,
        currency=currency or "NGN",
        participant_count=len(lines),
        flagged_count=flagged,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    return _save(voucher)


def _save(voucher: Voucher) -> Voucher:
    _ensure_dir()
    voucher.updated_at = _now_iso()
    if not voucher.created_at:
        voucher.created_at = voucher.updated_at
    _path(voucher.id).write_text(voucher.model_dump_json(indent=2))
    return voucher


def load(voucher_id: str) -> Voucher:
    path = _path(voucher_id)
    if not path.exists():
        raise ValueError(f"Voucher '{voucher_id}' not found.")
    return Voucher.model_validate_json(path.read_text())


def list_all() -> list[VoucherSummary]:
    _ensure_dir()
    out: list[VoucherSummary] = []
    for p in _VOUCHER_DIR.glob("*.json"):
        try:
            v = Voucher.model_validate_json(p.read_text())
            out.append(VoucherSummary(
                id=v.id, event_name=v.event_name, total=v.total, currency=v.currency,
                participant_count=v.participant_count, flagged_count=v.flagged_count,
                txn_ref=v.txn_ref, created_at=v.created_at,
            ))
        except Exception as exc:
            print(f"Warning: skipping corrupt voucher {p.name}: {exc}")
    out.sort(key=lambda s: s.created_at or "", reverse=True)
    return out


def submit(voucher_id: str, *, created_by: Optional[str] = None) -> Voucher:
    """Open the workflow transaction for a voucher and route it into compliance
    review. Idempotent-ish: re-submitting a voucher that already has a
    transaction returns it unchanged rather than opening a duplicate."""
    voucher = load(voucher_id)
    if voucher.txn_id:
        return voucher  # already submitted

    txn = tx.create(
        "voucher",
        f"Voucher — {voucher.event_name} ({voucher.participant_count} participants)",
        source_kind="voucher",
        source_id=voucher.id,
        amount=voucher.total,
        currency=voucher.currency,
        created_by=created_by or voucher.created_by,
    )
    # Move it from 'submitted' straight to compliance review — a raised voucher
    # is ready to be checked. This also fires the compliance notification via
    # the caller/route layer.
    txn = tx.transition(txn, "compliance_review", department="finance",
                        note="Voucher submitted for review")

    voucher.txn_id = txn.id
    voucher.txn_ref = txn.ref
    return _save(voucher)
