"""
DOCex Attendance Collections — native intake + public self-check-in.

An alternative to importing an attendance log + payment form. The organiser
creates a Collection (event + day labels + rate), fills the grid manually
AND/OR shares a public check-in link where attendees self-enter their name
and bank details. When ready, the Collection is converted into a normal
AttendancePaymentRun via match_and_build_run, so Bank Verify, schedule
export, and everything downstream are unchanged.

Endpoints:
  POST   /agents/attendance-payment/collections                 — create
  GET    /agents/attendance-payment/collections                 — list (summaries)
  GET    /agents/attendance-payment/collections/{id}            — organiser view
  PUT    /agents/attendance-payment/collections/{id}            — update (grid edits)
  DELETE /agents/attendance-payment/collections/{id}            — delete
  POST   /agents/attendance-payment/collections/{id}/run        — build a run
  GET    /agents/attendance-payment/collections/public/{token}  — public info
  POST   /agents/attendance-payment/collections/public/{token}/attendees
                                                                 — self check-in

Collections persist as JSON in {project_root}/attendance_collections/{id}.json
— same file-per-record pattern as runs and rulebooks.
"""
from __future__ import annotations

import datetime as dt
import secrets
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from attendance_agent import match_and_build_run  # noqa: E402
from models import (  # noqa: E402
    AttendanceCollection,
    AttendanceCollectionSummary,
    AttendanceRecord,
    CollectedAttendee,
    PaymentInfoRecord,
    PublicCollectionInfo,
)
from .attendance_agent_routes import _save_run  # noqa: E402
from .rate_card_routes import _load as _load_rate_card  # noqa: E402

router = APIRouter(
    prefix="/agents/attendance-payment/collections", tags=["agents"]
)

_DIR = Path(__file__).parent.parent / "attendance_collections"


def _ensure_dir() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _path(collection_id: str) -> Path:
    if "/" in collection_id or ".." in collection_id or not collection_id.strip():
        raise HTTPException(status_code=400, detail="Invalid collection id.")
    return _DIR / f"{collection_id}.json"


def _save(c: AttendanceCollection) -> AttendanceCollection:
    _ensure_dir()
    _path(c.id).write_text(c.model_dump_json(indent=2))
    return c


def _load(collection_id: str) -> AttendanceCollection:
    path = _path(collection_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Collection not found.")
    try:
        return AttendanceCollection.model_validate_json(path.read_text())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Failed to load collection: {exc}"
        ) from exc


def _load_by_token(token: str) -> AttendanceCollection:
    _ensure_dir()
    for p in _DIR.glob("*.json"):
        try:
            c = AttendanceCollection.model_validate_json(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        if secrets.compare_digest(c.share_token, token):
            return c
    raise HTTPException(status_code=404, detail="Check-in link not found.")


# ─── Request bodies ─────────────────────────────────────────────────────────


class CreateCollectionRequest(BaseModel):
    event_name: str
    day_labels: list[str] = []
    rate_per_day: float = 0.0
    rate_card_id: str | None = None


class UpdateCollectionRequest(BaseModel):
    event_name: str | None = None
    day_labels: list[str] | None = None
    rate_per_day: float | None = None
    rate_card_id: str | None = None
    attendees: list[CollectedAttendee] | None = None


class SelfCheckInRequest(BaseModel):
    name: str
    organisation: str | None = None
    account_number: str = ""
    bank_code: str = ""
    bank_name: str | None = None
    role: str | None = None
    present_days: list[str] = []


# ─── Organiser routes ───────────────────────────────────────────────────────


@router.post("", response_model=AttendanceCollection)
async def create_collection(body: CreateCollectionRequest) -> AttendanceCollection:
    name = body.event_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="An event name is required.")
    collection = AttendanceCollection(
        id=uuid.uuid4().hex,
        event_name=name,
        day_labels=[d.strip() for d in body.day_labels if d.strip()] or ["Day 1"],
        rate_per_day=max(0.0, body.rate_per_day),
        rate_card_id=body.rate_card_id or None,
        share_token=secrets.token_urlsafe(9),
        created_at=_now_iso(),
        attendees=[],
    )
    return _save(collection)


@router.get("", response_model=list[AttendanceCollectionSummary])
async def list_collections() -> list[AttendanceCollectionSummary]:
    _ensure_dir()
    paths = sorted(
        _DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    out: list[AttendanceCollectionSummary] = []
    for p in paths:
        try:
            c = AttendanceCollection.model_validate_json(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        out.append(
            AttendanceCollectionSummary(
                id=c.id,
                event_name=c.event_name,
                attendee_count=len(c.attendees),
                day_count=len(c.day_labels),
                created_at=c.created_at,
                run_id=c.run_id,
            )
        )
    return out


@router.get("/{collection_id}", response_model=AttendanceCollection)
async def get_collection(collection_id: str) -> AttendanceCollection:
    return _load(collection_id)


@router.put("/{collection_id}", response_model=AttendanceCollection)
async def update_collection(
    collection_id: str, body: UpdateCollectionRequest
) -> AttendanceCollection:
    c = _load(collection_id)
    if body.event_name is not None and body.event_name.strip():
        c.event_name = body.event_name.strip()
    if body.day_labels is not None:
        c.day_labels = [d.strip() for d in body.day_labels if d.strip()] or c.day_labels
    if body.rate_per_day is not None:
        c.rate_per_day = max(0.0, body.rate_per_day)
    if body.rate_card_id is not None:
        c.rate_card_id = body.rate_card_id or None
    if body.attendees is not None:
        # Keep only present_days that are valid day labels.
        valid = set(c.day_labels)
        for a in body.attendees:
            a.present_days = [d for d in a.present_days if d in valid]
        c.attendees = body.attendees
    return _save(c)


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str) -> dict:
    path = _path(collection_id)
    if path.exists():
        path.unlink()
    return {"deleted": collection_id}


@router.post("/{collection_id}/run")
async def build_run(collection_id: str) -> dict:
    """Convert the collection into an AttendancePaymentRun and return its id."""
    c = _load(collection_id)
    if not c.attendees:
        raise HTTPException(
            status_code=422,
            detail="No attendees yet — add people or share the check-in link first.",
        )

    attendance = [
        AttendanceRecord(
            name=a.name,
            days_attended=len(a.present_days),
            day_labels=list(a.present_days),
        )
        for a in c.attendees
    ]
    payment_info = [
        PaymentInfoRecord(
            name=a.name,
            organisation=a.organisation,
            account_number=a.account_number,
            bank_code=a.bank_code,
            bank_name=a.bank_name,
            role=a.role,
        )
        for a in c.attendees
        if a.account_number.strip()
    ]

    card = None
    if c.rate_card_id:
        card = _load_rate_card(c.rate_card_id)
    elif c.rate_per_day <= 0:
        raise HTTPException(
            status_code=422,
            detail="Set a per-day rate (or a rate card) before building the run.",
        )

    run = match_and_build_run(
        event_name=c.event_name,
        rate_per_day=c.rate_per_day if c.rate_per_day > 0 else (card.default_rate_per_day if card else 0.0),
        attendance=attendance,
        payment_info=payment_info,
        rate_card=card,
    )
    run.attendance_filename = f"{c.event_name} (collected)"
    run.payment_info_filename = f"{c.event_name} (collected)"
    run.attendance_source = "collection"
    run.payment_info_source = "collection"
    saved = _save_run(run)

    c.run_id = saved.run_id
    _save(c)
    return {"run_id": saved.run_id}


# ─── Public self-check-in routes (token-gated, no auth) ─────────────────────


@router.get("/public/{token}", response_model=PublicCollectionInfo)
async def public_info(token: str) -> PublicCollectionInfo:
    c = _load_by_token(token)
    return PublicCollectionInfo(
        event_name=c.event_name,
        day_labels=c.day_labels,
        already_submitted=len(c.attendees),
    )


@router.post("/public/{token}/attendees")
async def self_check_in(token: str, body: SelfCheckInRequest) -> dict:
    c = _load_by_token(token)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Please enter your name.")
    valid = set(c.day_labels)
    attendee = CollectedAttendee(
        id=uuid.uuid4().hex,
        name=name,
        organisation=(body.organisation or "").strip() or None,
        account_number=body.account_number.strip(),
        bank_code=body.bank_code.strip(),
        bank_name=(body.bank_name or "").strip() or None,
        role=(body.role or "").strip() or None,
        present_days=[d for d in body.present_days if d in valid],
        source="self",
    )
    c.attendees.append(attendee)
    _save(c)
    return {"ok": True}
