"""
DOCex rate-card routes.

Rate cards are reusable per-diem schedules — one default rate plus zero-to-
many per-role overrides. The Attendance Payment Agent consults a card at
run time to pick the right rate for each payee. Cards persist as JSON
files under {project_root}/rate_cards/{id}.json, mirroring the existing
file-based persistence pattern (rulebooks, checks, verifications, runs).

Endpoints:
  GET    /rate-cards            — list every saved card
  GET    /rate-cards/{id}       — fetch one card
  POST   /rate-cards            — create a new card
  PUT    /rate-cards/{id}       — replace an existing card
  DELETE /rate-cards/{id}       — delete one
"""
from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import RateCard, RateLine  # noqa: E402
from pydantic import BaseModel  # noqa: E402

router = APIRouter(prefix="/rate-cards", tags=["rate-cards"])


_RATE_CARD_DIR = Path(__file__).parent.parent / "rate_cards"


def _ensure_dir() -> None:
    _RATE_CARD_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _card_path(card_id: str) -> Path:
    if "/" in card_id or ".." in card_id or not card_id.strip():
        raise HTTPException(status_code=400, detail="Invalid rate-card id.")
    return _RATE_CARD_DIR / f"{card_id}.json"


def _save(card: RateCard) -> RateCard:
    _ensure_dir()
    now = _now_iso()
    if not card.created_at:
        card.created_at = now
    card.updated_at = now
    _card_path(card.id).write_text(card.model_dump_json(indent=2))
    return card


def _load(card_id: str) -> RateCard:
    path = _card_path(card_id)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Rate card '{card_id}' not found."
        )
    try:
        return RateCard.model_validate_json(path.read_text())
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load rate card '{card_id}': {exc}",
        ) from exc


def _list_all() -> list[RateCard]:
    _ensure_dir()
    paths = sorted(
        _RATE_CARD_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    cards: list[RateCard] = []
    for path in paths:
        try:
            cards.append(RateCard.model_validate_json(path.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupted rate card {path.name}: {exc}")
            continue
    return cards


# ─── Request bodies ─────────────────────────────────────────────────────────


class RateCardCreate(BaseModel):
    name: str
    default_rate_per_day: float
    roles: list[RateLine] = []
    currency: str = "NGN"
    # Per-diem policy — the day-component split + advance fraction TA Connect
    # finance configures. Optional; defaults reproduce the 75%-on-food rule.
    lodging_weight: float = 0.50
    meals_weight: float = 0.25
    incidentals_weight: float = 0.25
    advance_fraction: float = 1.0


class RateCardUpdate(BaseModel):
    name: str
    default_rate_per_day: float
    roles: list[RateLine] = []
    currency: str = "NGN"
    lodging_weight: float = 0.50
    meals_weight: float = 0.25
    incidentals_weight: float = 0.25
    advance_fraction: float = 1.0


# ─── Routes ─────────────────────────────────────────────────────────────────


@router.get("", response_model=dict)
def list_cards() -> dict:
    cards = _list_all()
    return {"rate_cards": [c.model_dump() for c in cards]}


@router.get("/{card_id}", response_model=RateCard)
def get_card(card_id: str) -> RateCard:
    return _load(card_id)


@router.post("", response_model=RateCard)
def create_card(body: RateCardCreate) -> RateCard:
    if body.default_rate_per_day <= 0:
        raise HTTPException(
            status_code=422,
            detail="default_rate_per_day must be positive.",
        )
    card = RateCard(
        id=uuid.uuid4().hex,
        name=body.name.strip() or "Untitled rate card",
        default_rate_per_day=float(body.default_rate_per_day),
        roles=body.roles,
        currency=body.currency or "NGN",
        lodging_weight=body.lodging_weight,
        meals_weight=body.meals_weight,
        incidentals_weight=body.incidentals_weight,
        advance_fraction=body.advance_fraction,
    )
    return _save(card)


@router.put("/{card_id}", response_model=RateCard)
def update_card(card_id: str, body: RateCardUpdate) -> RateCard:
    existing = _load(card_id)
    existing.name = body.name.strip() or existing.name
    existing.default_rate_per_day = float(body.default_rate_per_day)
    existing.roles = body.roles
    existing.currency = body.currency or existing.currency
    existing.lodging_weight = body.lodging_weight
    existing.meals_weight = body.meals_weight
    existing.incidentals_weight = body.incidentals_weight
    existing.advance_fraction = body.advance_fraction
    return _save(existing)


@router.delete("/{card_id}")
def delete_card(card_id: str) -> dict[str, str]:
    path = _card_path(card_id)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Rate card '{card_id}' not found."
        )
    path.unlink()
    return {"status": "deleted", "id": card_id}
