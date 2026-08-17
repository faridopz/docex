"""
DOCex in-app notification center — the cross-department, event-driven feed.

This is the read model behind the "Uber-style" live tracking: whenever a
transaction moves, the department that now needs to act gets a notification in
their inbox (compliance approves → finance is notified). It's deliberately
separate from notifications.py (which sends *email* on compliance checks): this
module is the in-product feed each department sees on their dashboard.

Pure + side-effect-light: it persists Notification records as JSON under
{root}/notifications/ and exposes create / list / mark-read, plus a single
`notify_transition` helper that maps a transaction event to the right recipient.
No LLM, no network — trivially testable.
"""
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Optional

from models import (
    Department,
    Notification,
    NotificationKind,
    Transaction,
    TxnEvent,
)

_ROOT = Path(__file__).parent
_NOTIF_DIR = _ROOT / "notifications"


def _now_iso() -> str:
    # Microsecond precision so the newest-first feed orders deterministically
    # even when several notifications land in the same second.
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def _ensure_dir() -> None:
    _NOTIF_DIR.mkdir(parents=True, exist_ok=True)


def _path(notif_id: str) -> Path:
    if not notif_id or "/" in notif_id or "\\" in notif_id or ".." in notif_id:
        raise ValueError(f"Invalid notification id: {notif_id!r}")
    return _NOTIF_DIR / f"{notif_id}.json"


def create(
    txn_ref: str,
    to_department: Department,
    kind: NotificationKind,
    title: str,
    body: str = "",
    actor: Optional[str] = None,
) -> Notification:
    _ensure_dir()
    notif = Notification(
        id=uuid.uuid4().hex,
        txn_ref=txn_ref,
        to_department=to_department,
        kind=kind,
        title=title,
        body=body,
        actor=actor,
        created_at=_now_iso(),
    )
    _path(notif.id).write_text(notif.model_dump_json(indent=2))
    return notif


def _iter_all() -> list[Notification]:
    _ensure_dir()
    out: list[Notification] = []
    for p in _NOTIF_DIR.glob("*.json"):
        try:
            out.append(Notification.model_validate_json(p.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupt notification {p.name}: {exc}")
    return out


def list_for(
    department: Department,
    unread_only: bool = False,
    limit: int = 100,
) -> list[Notification]:
    """Newest-first inbox for one department."""
    items = [n for n in _iter_all() if n.to_department == department]
    if unread_only:
        items = [n for n in items if not n.read]
    items.sort(key=lambda n: n.created_at or "", reverse=True)
    return items[: max(0, limit)]


def unread_count(department: Department) -> int:
    return sum(1 for n in _iter_all()
               if n.to_department == department and not n.read)


def mark_read(notif_id: str) -> Notification:
    path = _path(notif_id)
    if not path.exists():
        raise ValueError(f"Notification '{notif_id}' not found.")
    notif = Notification.model_validate_json(path.read_text())
    if not notif.read:
        notif.read = True
        path.write_text(notif.model_dump_json(indent=2))
    return notif


def mark_all_read(department: Department) -> int:
    """Mark every unread notification for a department read. Returns how many."""
    n = 0
    for notif in _iter_all():
        if notif.to_department == department and not notif.read:
            notif.read = True
            _path(notif.id).write_text(notif.model_dump_json(indent=2))
            n += 1
    return n


# ─── the event → recipient mapping ──────────────────────────────────────────

# Map the new state to (kind, headline) for the department taking ownership.
_ASSIGN_COPY: dict[str, tuple[NotificationKind, str]] = {
    "compliance_review": ("assigned", "New item for compliance review"),
    "finance_review": ("assigned", "Ready for finance review"),
    "approval": ("approved", "Awaiting approval"),
    "paid": ("paid", "Marked paid"),
    "intake": ("assigned", "New item at intake"),
    "submitted": ("assigned", "New submission"),
}


def notify_transition(txn: Transaction, event: TxnEvent) -> list[Notification]:
    """Emit the notification(s) for one transaction transition.

    Rule of thumb: the department that now OWNS the transaction is told to act.
    Returns for fixes notify whoever must fix it (the previous acting dept,
    when known). Returns the notifications created (possibly empty)."""
    out: list[Notification] = []
    ref = txn.ref

    if event.to_state == "returned":
        # Tell the department that had the ball before it was returned.
        target = event.department
        # If the returner IS a department, the fixer is usually 'program' who
        # assembled it; fall back to program when we can't infer.
        fixer: Optional[Department] = "program"
        out.append(create(
            ref, fixer, "returned",
            title=f"{ref} sent back for fixes",
            body=(event.note or "Returned for correction.")
                 + (f" (by {target})" if target else ""),
            actor=event.actor,
        ))
        return out

    owner = txn.owner_department
    if owner is None:
        return out
    kind, headline = _ASSIGN_COPY.get(txn.state, ("mention", "Update"))
    out.append(create(
        ref, owner, kind,
        title=f"{ref}: {headline}",
        body=f"{txn.title}" + (f" — {event.note}" if event.note else ""),
        actor=event.actor,
    ))
    return out
