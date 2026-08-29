"""
DOCex transaction backbone — the cross-department workflow spine.

Every work item (compliance check, payment run, voucher) gets ONE human
reference like "C24" and one status trail the whole org can see. This module
owns three deterministic concerns:

  1. Reference generation — a monotonic, per-prefix counter ("C24", "P7", ...),
     persisted so references never collide or reset across restarts.
  2. The state machine — the legal transitions between workflow states, and
     which department owns each state. Illegal moves raise, they don't corrupt.
  3. Persistence — JSON files under {root}/transactions/, mirroring the existing
     rulebook / check / run pattern.

Design rules honoured here:
  - History is append-only; existing events are never mutated (audit-grade).
  - Nothing here calls an LLM. Workflow state is pure, testable logic.
  - Concurrency: the reference counter is bumped under an OS file lock so two
    near-simultaneous creates can't hand out the same number.

Notifications are emitted by callers (see api/transaction_routes.py) rather than
here, to keep this module free of side effects and trivially unit-testable.
"""
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Optional

# fcntl is POSIX-only (the Render/Linux target). Guarded so imports never fail
# on a dev machine without it; the lock simply becomes a no-op there.
try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore

import departments
from models import (
    Department,
    Transaction,
    TransactionSummary,
    TxnEvent,
    TxnKind,
    TxnState,
)

_ROOT = Path(__file__).parent
_TXN_DIR = _ROOT / "transactions"
_COUNTER_FILE = _TXN_DIR / ".counter"

# Human-reference prefix per kind. Compliance = "C" (matches the team's "C24").
_PREFIX: dict[str, str] = {
    "compliance_check": "C",
    "payment_run": "P",
    "voucher": "V",
    "travel_claim": "T",
}

# Legal state transitions. Any move not listed is rejected. `returned` is the
# "send back for fixes" side-state reachable from the review stages, and can
# itself route back into the pipeline.
_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"intake", "compliance_review", "returned"},
    "intake": {"compliance_review", "returned"},
    "compliance_review": {"finance_review", "approval", "returned"},
    "finance_review": {"approval", "compliance_review", "returned"},
    "approval": {"paid", "finance_review", "returned"},
    "paid": set(),  # terminal
    "returned": {"submitted", "intake", "compliance_review", "finance_review"},
}

# Which department owns each state (the ball is with them). This is now DATA,
# not code: it comes from the org's departments registry so each organisation
# routes its own workflow (EVA sends `approval` to "ed"; the default install
# sends it to "management"). `returned` has no fixed owner — the return event
# names who must fix it. _state_owner() never raises: an unmapped state simply
# has no owner, which the UI renders as "Unassigned".


def _state_owner(state: str) -> Optional[Department]:
    try:
        return departments.state_owner(state)
    except Exception:  # pragma: no cover - registry unreadable; stay functional
        return None


class TransactionError(ValueError):
    """Raised for illegal transitions or bad ids — callers map to HTTP 4xx."""


# ─── time / io helpers ──────────────────────────────────────────────────────


def _now_iso() -> str:
    # Microsecond precision keeps event ordering + newest-first listing
    # deterministic when several updates happen within the same second.
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def _ensure_dir() -> None:
    _TXN_DIR.mkdir(parents=True, exist_ok=True)


def _txn_path(txn_id: str) -> Path:
    # Guard against path traversal — ids are uuids, but never trust input.
    if not txn_id or "/" in txn_id or "\\" in txn_id or ".." in txn_id:
        raise TransactionError(f"Invalid transaction id: {txn_id!r}")
    return _TXN_DIR / f"{txn_id}.json"


# ─── reference counter (locked, monotonic) ──────────────────────────────────


def _next_number() -> int:
    """Return the next global sequence number, incrementing the persisted
    counter atomically. One shared counter keeps references unique across
    kinds; the prefix distinguishes them (C24 vs P24 are different items)."""
    _ensure_dir()
    # Open for read+write, create if missing.
    with open(_COUNTER_FILE, "a+") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            raw = fh.read().strip()
            current = int(raw) if raw.isdigit() else 0
            nxt = current + 1
            fh.seek(0)
            fh.truncate()
            fh.write(str(nxt))
            fh.flush()
            return nxt
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def next_ref(kind: TxnKind) -> str:
    """Generate the next human reference for a kind, e.g. 'C24'."""
    prefix = _PREFIX.get(kind, "TX")
    return f"{prefix}{_next_number()}"


# ─── persistence ────────────────────────────────────────────────────────────


def save(txn: Transaction) -> Transaction:
    _ensure_dir()
    now = _now_iso()
    if not txn.created_at:
        txn.created_at = now
    txn.updated_at = now
    _txn_path(txn.id).write_text(txn.model_dump_json(indent=2))
    return txn


def load(txn_id: str) -> Transaction:
    path = _txn_path(txn_id)
    if not path.exists():
        raise TransactionError(f"Transaction '{txn_id}' not found.")
    return Transaction.model_validate_json(path.read_text())


def load_by_ref(ref: str) -> Transaction:
    """Look up a transaction by its human reference (C24). Linear scan — fine
    at the volumes DOCex handles; swap for an index if it ever isn't."""
    want = (ref or "").strip().lower()
    for txn in _iter_all():
        if txn.ref.lower() == want:
            return txn
    raise TransactionError(f"Transaction '{ref}' not found.")


def _iter_all() -> list[Transaction]:
    _ensure_dir()
    out: list[Transaction] = []
    for path in _TXN_DIR.glob("*.json"):
        try:
            out.append(Transaction.model_validate_json(path.read_text()))
        except Exception as exc:  # skip corrupt records, don't crash the list
            print(f"Warning: skipping corrupt transaction {path.name}: {exc}")
    return out


def list_all(
    department: Optional[Department] = None,
    state: Optional[TxnState] = None,
) -> list[TransactionSummary]:
    """List transactions as lightweight summaries, newest first, with optional
    department / state filters (the dashboard's 'pending on me' view)."""
    txns = _iter_all()
    txns.sort(key=lambda t: t.updated_at or t.created_at or "", reverse=True)
    rows: list[TransactionSummary] = []
    for t in txns:
        if department is not None and t.owner_department != department:
            continue
        if state is not None and t.state != state:
            continue
        rows.append(TransactionSummary(
            ref=t.ref, kind=t.kind, title=t.title, state=t.state,
            owner_department=t.owner_department, amount=t.amount,
            currency=t.currency, updated_at=t.updated_at,
        ))
    return rows


# ─── lifecycle operations ───────────────────────────────────────────────────


def create(
    kind: TxnKind,
    title: str,
    *,
    source_kind: Optional[TxnKind] = None,
    source_id: Optional[str] = None,
    amount: Optional[float] = None,
    currency: str = "NGN",
    created_by: Optional[str] = None,
    initial_state: TxnState = "submitted",
) -> Transaction:
    """Open a new transaction with a fresh reference and a 'created' event."""
    now = _now_iso()
    txn = Transaction(
        id=uuid.uuid4().hex,
        ref=next_ref(kind),
        kind=kind,
        title=title.strip() or "Untitled",
        state=initial_state,
        owner_department=_state_owner(initial_state),
        source_kind=source_kind,
        source_id=source_id,
        amount=amount,
        currency=currency or "NGN",
        created_by=created_by,
        created_at=now,
        updated_at=now,
        history=[TxnEvent(type="created", timestamp=now, actor=created_by,
                          department=_state_owner(initial_state),
                          to_state=initial_state)],
    )
    if source_id:
        txn.history.append(TxnEvent(type="linked", timestamp=now, actor=created_by,
                                    note=f"Linked to {source_kind or 'source'} {source_id}"))
    return save(txn)


def can_transition(current: TxnState, target: TxnState) -> bool:
    return target in _TRANSITIONS.get(current, set())


def allowed_transitions(current: TxnState) -> list[TxnState]:
    return sorted(_TRANSITIONS.get(current, set()))


def transition(
    txn: Transaction,
    to_state: TxnState,
    *,
    actor: Optional[str] = None,
    department: Optional[Department] = None,
    note: Optional[str] = None,
) -> Transaction:
    """Move a transaction to a new state, enforcing the state machine. Appends
    an event, updates the owning department, and persists. Raises
    TransactionError on an illegal move — the caller decides the HTTP response."""
    current = txn.state
    if to_state == current:
        raise TransactionError(f"{txn.ref} is already in state '{current}'.")
    if not can_transition(current, to_state):
        raise TransactionError(
            f"Illegal transition for {txn.ref}: '{current}' → '{to_state}'. "
            f"Allowed: {allowed_transitions(current) or 'none (terminal)'}."
        )
    now = _now_iso()
    event_type = (
        "returned" if to_state == "returned"
        else "paid" if to_state == "paid"
        else "approved" if to_state == "approval"
        else "state_changed"
    )
    txn.history.append(TxnEvent(
        type=event_type, timestamp=now, actor=actor,
        department=department, from_state=current, to_state=to_state, note=note,
    ))
    txn.state = to_state
    txn.owner_department = _state_owner(to_state)
    return save(txn)


def record_view(
    txn: Transaction,
    *,
    department: Optional[Department] = None,
    actor: Optional[str] = None,
) -> Transaction:
    """Record that a department/actor looked at this transaction. Idempotent per
    viewer — the 'viewed by compliance' signal, not a full history spam."""
    viewer = department or actor
    if viewer and viewer not in txn.viewed_by:
        txn.viewed_by.append(viewer)
        txn.history.append(TxnEvent(
            type="viewed", timestamp=_now_iso(), actor=actor, department=department,
        ))
        return save(txn)
    return txn


def add_note(
    txn: Transaction,
    note: str,
    *,
    actor: Optional[str] = None,
    department: Optional[Department] = None,
) -> Transaction:
    txn.history.append(TxnEvent(
        type="noted", timestamp=_now_iso(), actor=actor,
        department=department, note=note,
    ))
    return save(txn)
