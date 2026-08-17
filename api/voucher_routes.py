"""
DOCex voucher routes.

Build one payment voucher from many participants' inputs (each computed through
the deterministic per-diem engine), then submit it — which opens a workflow
transaction (ref like V7), routes it into compliance review, and notifies the
compliance team.

Endpoints:
  POST /vouchers            — build a draft voucher from participant inputs
  GET  /vouchers            — list voucher summaries
  GET  /vouchers/{id}       — one voucher with all lines
  POST /vouchers/{id}/submit — open the workflow transaction + notify compliance
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import notification_center as nc  # noqa: E402
import transactions as tx  # noqa: E402
import vouchers as vouchers_mod  # noqa: E402
from models import RateCard, ReceiptItem, Voucher  # noqa: E402
from per_diem import (  # noqa: E402
    DayCoverage,
    ParticipantPayable,
    PerDiemPolicy,
    build_participant_payable,
    policy_from_rate_card,
    uniform_days,
)

router = APIRouter(tags=["vouchers"])

_RATE_CARD_DIR = Path(__file__).parent.parent / "rate_cards"


def _load_card(card_id: str) -> RateCard:
    if "/" in card_id or ".." in card_id or not card_id.strip():
        raise HTTPException(status_code=400, detail="Invalid rate-card id.")
    path = _RATE_CARD_DIR / f"{card_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Rate card '{card_id}' not found.")
    return RateCard.model_validate_json(path.read_text())


class ParticipantInput(BaseModel):
    participant_name: str
    role: Optional[str] = None
    rate_card_id: Optional[str] = None
    rate_per_day: Optional[float] = None
    days: Optional[list[DayCoverage]] = None
    num_days: Optional[int] = None
    default_covered: list[str] = []
    receipts: list[ReceiptItem] = []


class VoucherCreate(BaseModel):
    event_name: str
    currency: str = "NGN"
    created_by: Optional[str] = None
    participants: list[ParticipantInput]


def _payable_for(p: ParticipantInput) -> ParticipantPayable:
    # Resolve policy (saved card preferred, else inline flat rate).
    if p.rate_card_id:
        policy: PerDiemPolicy = policy_from_rate_card(_load_card(p.rate_card_id), p.role)
    elif p.rate_per_day and p.rate_per_day > 0:
        policy = PerDiemPolicy(rate_per_day=float(p.rate_per_day))
    else:
        raise HTTPException(
            status_code=422,
            detail=f"{p.participant_name}: provide rate_card_id or a positive rate_per_day.",
        )
    # Resolve days (explicit list preferred, else uniform shortcut).
    if p.days:
        days = p.days
    elif p.num_days is not None:
        days = uniform_days(p.num_days, covered=p.default_covered)  # type: ignore[arg-type]
    else:
        raise HTTPException(
            status_code=422,
            detail=f"{p.participant_name}: provide days or num_days.",
        )
    return build_participant_payable(
        participant_name=p.participant_name.strip() or "Participant",
        policy=policy, days=days, receipts=p.receipts,
    )


@router.post("/vouchers", response_model=Voucher)
def create_voucher(body: VoucherCreate) -> Voucher:
    if not body.participants:
        raise HTTPException(status_code=422, detail="At least one participant is required.")
    payables = [_payable_for(p) for p in body.participants]
    roles = [p.role for p in body.participants]
    return vouchers_mod.build_voucher(
        body.event_name, payables,
        currency=body.currency, created_by=body.created_by, roles=roles,
    )


@router.get("/vouchers", response_model=dict)
def list_vouchers() -> dict:
    return {"vouchers": [s.model_dump() for s in vouchers_mod.list_all()]}


@router.get("/vouchers/{voucher_id}", response_model=Voucher)
def get_voucher(voucher_id: str) -> Voucher:
    try:
        return vouchers_mod.load(voucher_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/vouchers/{voucher_id}/submit", response_model=Voucher)
def submit_voucher(voucher_id: str, created_by: Optional[str] = None) -> Voucher:
    try:
        voucher = vouchers_mod.submit(voucher_id, created_by=created_by)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Fire the compliance-assignment notification for the transition submit()
    # performed. Defensive: never let a notification failure fail the submit.
    try:
        if voucher.txn_id:
            txn = tx.load(voucher.txn_id)
            nc.notify_transition(txn, txn.history[-1])
    except Exception as exc:  # pragma: no cover
        print(f"Warning: voucher submit notification failed: {exc}")
    return voucher
