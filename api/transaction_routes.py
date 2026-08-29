"""
DOCex transaction + notification routes.

The cross-department workflow API: open a transaction (gets a ref like C24),
move it through the state machine, view it, and read the per-department
notification feed. Every state change fans out a notification to the department
that now needs to act — the Uber-style tracking the team asked for.

Endpoints:
  POST   /transactions                 — open a transaction
  GET    /transactions                 — list (filter by ?department= / ?state=)
  GET    /transactions/{ref}           — one transaction + full history
  POST   /transactions/{ref}/transition — move state (emits notifications)
  POST   /transactions/{ref}/view      — record a department view
  POST   /transactions/{ref}/note      — append a note
  GET    /transactions/{ref}/next      — allowed next states (for UI buttons)

  GET    /notifications                — inbox for ?department= (?unread_only=)
  POST   /notifications/{id}/read      — mark one read
  POST   /notifications/read-all       — mark all read for ?department=
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import notification_center as nc  # noqa: E402
import transactions as tx  # noqa: E402
from models import (  # noqa: E402
    Department,
    Notification,
    Transaction,
    TransactionSummary,
    TxnKind,
    TxnState,
    User,
)

from .auth_routes import current_user  # noqa: E402

router = APIRouter(tags=["transactions"])

# The states that constitute AUTHORISING money: sending an item for final
# approval, and marking it paid. Restricted to approver/admin so a reviewer
# can move work forward but cannot authorise payment on their own.
_AUTHORISING_STATES = {"approval", "paid"}


# ─── request bodies ─────────────────────────────────────────────────────────


class TransactionCreate(BaseModel):
    kind: TxnKind
    title: str
    source_kind: Optional[TxnKind] = None
    source_id: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "NGN"
    created_by: Optional[str] = None


class TransitionRequest(BaseModel):
    to_state: TxnState
    actor: Optional[str] = None
    department: Optional[Department] = None
    note: Optional[str] = None


class ViewRequest(BaseModel):
    department: Optional[Department] = None
    actor: Optional[str] = None


class NoteRequest(BaseModel):
    note: str
    actor: Optional[str] = None
    department: Optional[Department] = None


# ─── transactions ───────────────────────────────────────────────────────────


@router.post("/transactions", response_model=Transaction)
def create_transaction(body: TransactionCreate) -> Transaction:
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="title is required.")
    return tx.create(
        body.kind, body.title,
        source_kind=body.source_kind, source_id=body.source_id,
        amount=body.amount, currency=body.currency, created_by=body.created_by,
    )


@router.get("/transactions", response_model=dict)
def list_transactions(
    department: Optional[Department] = Query(default=None),
    state: Optional[TxnState] = Query(default=None),
) -> dict:
    rows: list[TransactionSummary] = tx.list_all(department=department, state=state)
    return {"transactions": [r.model_dump() for r in rows]}


def _load_or_404(ref: str) -> Transaction:
    try:
        return tx.load_by_ref(ref)
    except tx.TransactionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/transactions/{ref}", response_model=Transaction)
def get_transaction(ref: str) -> Transaction:
    return _load_or_404(ref)


@router.get("/transactions/{ref}/next", response_model=dict)
def next_states(ref: str) -> dict:
    txn = _load_or_404(ref)
    return {"state": txn.state, "allowed": tx.allowed_transitions(txn.state)}


@router.post("/transactions/{ref}/transition", response_model=Transaction)
def transition_transaction(
    ref: str,
    body: TransitionRequest,
    user: User = Depends(current_user),
) -> Transaction:
    """Move a transaction through the workflow — the IN-APP approval path.

    Approvals happen here, inside the product: the approver opens the item from
    their department queue / notification and acts. (The emailed magic-link
    remains only as a fallback for people without an account.)

    Permissions:
      - viewers cannot move work at all;
      - the authorisation gates ('approval' and 'paid') require an approver or
        admin — a reviewer can progress work but cannot self-authorise payment.
    Actor + department are taken from the SIGNED-IN USER, never from the request
    body, so the audit trail can't be spoofed by the client.
    """
    if user.role == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Viewers can't action items. Ask an admin for reviewer access.",
        )
    if body.to_state in _AUTHORISING_STATES and user.role not in ("approver", "admin"):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Only an approver can move an item to '{body.to_state}'. "
                "Your role is " + user.role + "."
            ),
        )

    txn = _load_or_404(ref)
    try:
        txn = tx.transition(
            txn, body.to_state,
            actor=user.name or user.email,
            department=user.department,
            note=body.note,
        )
    except tx.TransactionError as exc:
        # Illegal move / terminal state → 409 Conflict, not a 500.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Fan out the notification for the event we just appended. Never let a
    # notification failure break the state change that already persisted.
    try:
        nc.notify_transition(txn, txn.history[-1])
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Warning: notification fan-out failed for {ref}: {exc}")
    return txn


@router.post("/transactions/{ref}/view", response_model=Transaction)
def view_transaction(ref: str, body: ViewRequest) -> Transaction:
    txn = _load_or_404(ref)
    return tx.record_view(txn, department=body.department, actor=body.actor)


@router.post("/transactions/{ref}/note", response_model=Transaction)
def note_transaction(ref: str, body: NoteRequest) -> Transaction:
    if not body.note.strip():
        raise HTTPException(status_code=422, detail="note is required.")
    txn = _load_or_404(ref)
    return tx.add_note(txn, body.note.strip(), actor=body.actor, department=body.department)


# ─── notifications ──────────────────────────────────────────────────────────


@router.get("/notifications", response_model=dict)
def list_notifications(
    department: Department = Query(...),
    unread_only: bool = Query(default=False),
) -> dict:
    items: list[Notification] = nc.list_for(department, unread_only=unread_only)
    return {
        "department": department,
        "unread": nc.unread_count(department),
        "notifications": [n.model_dump() for n in items],
    }


@router.post("/notifications/{notif_id}/read", response_model=Notification)
def read_notification(notif_id: str) -> Notification:
    try:
        return nc.mark_read(notif_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/notifications/read-all", response_model=dict)
def read_all_notifications(department: Department = Query(...)) -> dict:
    return {"marked_read": nc.mark_all_read(department)}
