"""
Idempotency keys — a retry must never create a second payment.

The failure this prevents is mundane and expensive. A finance officer submits a
requisition; the connection drops before the response arrives; they press the
button again. Without a key, that is two requisitions for one invoice, and the
duplicate-invoice check will not catch it because both are equally new. Same
story on `pay`: a retried payment call would freeze a second transaction record
against an account that has already been debited.

The contract, which is the standard one:

  * The client generates a key for one logical write and reuses it on retries.
  * First call with a key: we record it as IN FLIGHT, run the work, then store
    the result against the key.
  * A repeat while the first is still running raises `IdempotencyConflict` —
    the caller is told to wait rather than being handed a half-finished write.
  * A repeat after completion returns the stored result. No work is re-run.

Keys are org-scoped like every other collection, so one organisation's key can
never resolve to another's record. They carry a timestamp so a future cleanup
job can drop old ones; nothing here expires them automatically, because a key
that quietly expires mid-retry would reintroduce exactly the bug it prevents.

Usage in a route:

    with idempotency.guard(org_id, "requisition.create", key) as slot:
        if slot.replayed:
            return slot.result
        req = rq.create_requisition(...)
        slot.store(_detail_out(req))
        return slot.result
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

import store

_KEYS = "idempotency_keys"

# How long an in-flight record may sit before we assume the request that made
# it died (process restart, container replaced) and let a retry take over.
# Generous: better to make a caller wait than to let two writes run at once.
_STALE_AFTER_SECONDS = 300

STATUS_IN_FLIGHT = "in_flight"
STATUS_DONE = "done"


class IdempotencyConflict(RuntimeError):
    """Same key is already being processed. The caller should retry shortly."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(iso: str) -> float:
    try:
        started = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return float("inf")
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds()


def _record_id(operation: str, key: str) -> str:
    """
    Namespace the key by operation so the same client key used for `create`
    and later for `pay` cannot collide. Hashed to keep it filename-safe,
    since the JSON store writes one file per record id.
    """
    digest = hashlib.sha256(f"{operation}:{key}".encode("utf-8")).hexdigest()
    return f"{operation}-{digest[:32]}"


@dataclass
class Slot:
    """The caller's handle on one idempotent operation."""

    org_id: str
    operation: str
    key: str
    record_id: str
    replayed: bool = False
    result: Any = None
    _stored: bool = field(default=False, repr=False)

    def store(self, result: Any) -> Any:
        """Record the outcome so a later retry with this key replays it."""
        self.result = result
        self._stored = True
        return result


@contextmanager
def guard(org_id: str, operation: str, key: Optional[str]) -> Iterator[Slot]:
    """
    Wrap a write in idempotency protection.

    With no key the guard is a no-op: `slot.replayed` is False and nothing is
    persisted. That keeps older clients working — they simply do not get the
    protection, which is exactly where they were before.

    On success the result passed to `slot.store()` is saved. If the wrapped
    block raises, the in-flight marker is removed so the caller can genuinely
    retry: a failed write should not permanently burn its key.
    """
    org = store.require_org(org_id)
    clean = (key or "").strip()

    if not clean:
        yield Slot(org_id=org, operation=operation, key="", record_id="")
        return

    rid = _record_id(operation, clean)
    db = store.get_store()
    existing = db.get(org, _KEYS, rid)

    if existing:
        status = existing.get("status")
        if status == STATUS_DONE:
            slot = Slot(
                org_id=org, operation=operation, key=clean, record_id=rid,
                replayed=True, result=existing.get("result"),
            )
            yield slot
            return
        # Still marked in flight. Either a genuine concurrent retry, or the
        # process that claimed it died. Only the latter may be taken over.
        if _age_seconds(existing.get("started_at", "")) < _STALE_AFTER_SECONDS:
            raise IdempotencyConflict(
                "This request is already being processed. Please wait a moment "
                "and check before submitting again."
            )

    db.put(org, _KEYS, rid, {
        "id": rid,
        "org_id": org,
        "operation": operation,
        "status": STATUS_IN_FLIGHT,
        "started_at": _now_iso(),
        "result": None,
    })

    slot = Slot(org_id=org, operation=operation, key=clean, record_id=rid)
    try:
        yield slot
    except Exception:
        # Release the key so the caller can retry the same logical write.
        db.delete(org, _KEYS, rid)
        raise

    if slot._stored:
        db.put(org, _KEYS, rid, {
            "id": rid,
            "org_id": org,
            "operation": operation,
            "status": STATUS_DONE,
            "started_at": _now_iso(),
            "completed_at": _now_iso(),
            "result": slot.result,
        })
    else:
        # The block finished without recording a result — treat it as a
        # non-event rather than locking the key against a real attempt later.
        db.delete(org, _KEYS, rid)


def forget(org_id: str, operation: str, key: str) -> bool:
    """Drop a stored key. Used by tests and by any manual replay."""
    return store.get_store().delete(
        store.require_org(org_id), _KEYS, _record_id(operation, key)
    )
