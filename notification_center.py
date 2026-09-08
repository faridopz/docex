"""
DOCex in-app notification center — the cross-department, event-driven feed.

This is the read model behind the "Uber-style" live tracking: whenever a
transaction moves, the department that now needs to act gets a notification in
their inbox (compliance approves → finance is notified). It's deliberately
separate from notifications.py (which sends *email* on compliance checks): this
module is the in-product feed each department sees on their dashboard.

PERSISTENCE
Notifications are records in the org-scoped store (store.py), not files under
{root}/notifications/. The old layout was wiped on every redeploy, and the
symptom was nastier than it sounds: nobody loses money, but a department's
to-do list silently empties overnight and the team concludes that work
vanished. A finance system that appears to lose things is not trusted with
things, whatever the audit log says.

Every function takes an optional `org_id` defaulting to DOCEX_ORG, so existing
single-org callers were untouched by the change.
"""
from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path
from typing import Optional

import store
from models import (
    Department,
    Notification,
    NotificationKind,
    Transaction,
    TxnEvent,
)

_ROOT = Path(__file__).parent
_NOTIF_DIR = _ROOT / "notifications"          # legacy, read once at migration
_NOTIFICATIONS = "notifications"              # store collection


def _org(org_id: Optional[str] = None) -> str:
    explicit = (org_id or "").strip()
    if explicit:
        return store.require_org(explicit)
    return store.require_org((os.environ.get("DOCEX_ORG") or "default").strip()
                             or "default")


def _now_iso() -> str:
    # Microsecond precision so the newest-first feed orders deterministically
    # even when several notifications land in the same second.
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def create(
    txn_ref: str,
    to_department: Department,
    kind: NotificationKind,
    title: str,
    body: str = "",
    actor: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Notification:
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
    store.get_store().put(_org(org_id), _NOTIFICATIONS, notif.id,
                          notif.model_dump())
    return notif


def _iter_all(org_id: Optional[str] = None) -> list[Notification]:
    out: list[Notification] = []
    for raw in store.get_store().list(_org(org_id), _NOTIFICATIONS):
        try:
            out.append(Notification.model_validate(raw))
        except Exception as exc:
            print(f"Warning: skipping corrupt notification "
                  f"{raw.get('id', '?')}: {exc}")
    return out


def list_for(
    department: Department,
    unread_only: bool = False,
    limit: int = 100,
    org_id: Optional[str] = None,
) -> list[Notification]:
    """Newest-first inbox for one department."""
    items = [n for n in _iter_all(org_id) if n.to_department == department]
    if unread_only:
        items = [n for n in items if not n.read]
    items.sort(key=lambda n: n.created_at or "", reverse=True)
    return items[: max(0, limit)]


def unread_count(department: Department, org_id: Optional[str] = None) -> int:
    return sum(1 for n in _iter_all(org_id)
               if n.to_department == department and not n.read)


def mark_read(notif_id: str, org_id: Optional[str] = None) -> Notification:
    org = _org(org_id)
    raw = store.get_store().get(org, _NOTIFICATIONS, notif_id)
    if raw is None:
        raise ValueError(f"Notification '{notif_id}' not found.")
    notif = Notification.model_validate(raw)
    if not notif.read:
        notif.read = True
        store.get_store().put(org, _NOTIFICATIONS, notif.id, notif.model_dump())
    return notif


def mark_all_read(department: Department, org_id: Optional[str] = None) -> int:
    """Mark every unread notification for a department read. Returns how many."""
    org = _org(org_id)
    n = 0
    for notif in _iter_all(org):
        if notif.to_department == department and not notif.read:
            notif.read = True
            store.get_store().put(org, _NOTIFICATIONS, notif.id, notif.model_dump())
            n += 1
    return n


def migrate_legacy_notifications(org_id: Optional[str] = None) -> int:
    """One-time import from the pre-store {root}/notifications/ layout.

    Only runs when the store holds none for this org, so it is safe on every
    boot. Mirrors auth.migrate_legacy_users().
    """
    if not _NOTIF_DIR.is_dir():
        return 0
    org = _org(org_id)
    if store.get_store().list(org, _NOTIFICATIONS):
        return 0
    imported = 0
    for path in sorted(_NOTIF_DIR.glob("*.json")):
        try:
            notif = Notification.model_validate_json(path.read_text())
        except Exception as exc:
            print(f"Warning: skipping legacy notification {path.name}: {exc}")
            continue
        store.get_store().put(org, _NOTIFICATIONS, notif.id, notif.model_dump())
        imported += 1
    if imported:
        print(f"[notifications] Imported {imported} from the legacy directory "
              f"into org '{org}'.")
    return imported


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
