"""
DOCex per-diem routes.

TA Connect finance configures the per-diem *policy* on a rate card (daily rate
by role + the day-component split + advance fraction). This endpoint takes the
per-participant inputs a worker enters for one payment — how many days, what the
org covered each day, and the participant's reimbursable receipts — and returns
the deterministic payable (per_diem.py). No rate or rule lives here; it all
comes from the saved rate card and the submitted inputs.

Endpoints:
  POST /per-diem/compute   — compute one participant's payable
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import RateCard, ReceiptItem  # noqa: E402
from per_diem import (  # noqa: E402
    DayCoverage,
    ParticipantPayable,
    PerDiemPolicy,
    build_participant_payable,
    policy_from_rate_card,
    uniform_days,
)

router = APIRouter(prefix="/per-diem", tags=["per-diem"])

_RATE_CARD_DIR = Path(__file__).parent.parent / "rate_cards"


def _load_card(card_id: str) -> RateCard:
    if "/" in card_id or ".." in card_id or not card_id.strip():
        raise HTTPException(status_code=400, detail="Invalid rate-card id.")
    path = _RATE_CARD_DIR / f"{card_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Rate card '{card_id}' not found.")
    try:
        return RateCard.model_validate_json(path.read_text())
    except Exception as exc:  # pragma: no cover - corruption guard
        raise HTTPException(status_code=500, detail=f"Failed to load rate card: {exc}") from exc


class DayCoverageIn(BaseModel):
    label: str = "Day"
    covered: list[str] = []          # subset of: lodging / meals / incidentals


class PerDiemComputeRequest(BaseModel):
    participant_name: str
    event_name: str = ""
    role: Optional[str] = None
    # Policy source: a saved rate card (preferred) OR an inline flat rate.
    rate_card_id: Optional[str] = None
    rate_per_day: Optional[float] = None
    # Day inputs: either an explicit per-day list, or a uniform shortcut
    # (num_days + default_covered applied to every day).
    days: Optional[list[DayCoverageIn]] = None
    num_days: Optional[int] = None
    default_covered: list[str] = []
    # Reimbursable receipts (transport, printing, ...). category drives whether
    # a receipt counts toward reimbursables; lodging/meals the org paid are
    # ignored by default inside the engine.
    receipts: list[ReceiptItem] = []


@router.post("/compute", response_model=ParticipantPayable)
def compute(body: PerDiemComputeRequest) -> ParticipantPayable:
    # 1. Resolve the policy — from the saved card, or an inline rate.
    if body.rate_card_id:
        policy: PerDiemPolicy = policy_from_rate_card(_load_card(body.rate_card_id), body.role)
    elif body.rate_per_day is not None and body.rate_per_day > 0:
        policy = PerDiemPolicy(rate_per_day=float(body.rate_per_day))
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide a rate_card_id or a positive rate_per_day.",
        )

    # 2. Build the day list — explicit days win; else uniform shortcut.
    if body.days:
        days = [DayCoverage(label=d.label, covered=d.covered) for d in body.days]  # type: ignore[arg-type]
    elif body.num_days is not None:
        days = uniform_days(body.num_days, covered=body.default_covered)  # type: ignore[arg-type]
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either `days` or `num_days`.",
        )

    # 3. Deterministic compute.
    return build_participant_payable(
        participant_name=body.participant_name.strip() or "Participant",
        policy=policy,
        days=days,
        receipts=body.receipts,
        event_name=body.event_name,
    )
