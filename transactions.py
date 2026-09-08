"""
DOCex transaction backbone — the cross-department workflow spine.

Every work item (compliance check, payment run, voucher) gets ONE human
reference like "C24" and one status trail the whole org can see. This module
owns three deterministic concerns:

  1. Reference generation — a monotonic, per-prefix counter ("C24", "P7", ...),
     persisted so references never collide or reset across restarts.
  2. The state machine — the legal transitions between workflow states, and
     which department owns each state. Illegal moves raise, they don't corrupt.
  3. Persistence — records in the org-scoped store (store.py), so a transaction
     in flight and the reference counter both survive a redeploy. They used to
     be files beside the code, which the platform replaces on every deploy: the
     counter reset to zero and began reissuing references that already existed.

Design rules honoured here:
  - History is append-only; existing events are never mutated (audit-grade).
  - Nothing here calls an LLM. Workflow state is pure, testable logic.
  - Concurrency: the counter is bumped under a process lock AND the resulting
    reference is checked against existing records before it is used, because a
    duplicate lands on a payment voucher.

Notifications are emitted by callers (see api/transaction_routes.py) rather than
here, to keep this module free of side effects and trivially unit-testable.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import uuid
from pathlib import Path
from typing import Optional

import departments
import store
from models import (
    Department,
    Transaction,
    TransactionSummary,
    TxnEvent,
    TxnKind,
    TxnState,
)

_ROOT = Path(__file__).parent
_TXN_DIR = _ROOT / "transactions"          # legacy, read once at migration
_COUNTER_FILE = _TXN_DIR / ".counter"      # legacy
_TXNS = "transactions"                     # store collection
_COUNTER = "transaction_counter"           # store collection

# Human-reference prefix per kind. Compliance = "C" (matches the team's "C24").
_PREFIX: dict[str, str] = {
    "compliance_check": "C",
    "payment_run": "P",
    "voucher": "V",
    "travel_claim": "T",
    "payroll_run": "PR",
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


def _org(org_id: Optional[str] = None) -> str:
    explicit = (org_id or "").strip()
    if explicit:
        return store.require_org(explicit)
    return store.require_org((os.environ.get("DOCEX_ORG") or "default").strip()
                             or "default")


# ─── reference counter (monotonic, and checked) ─────────────────────────────


_ref_lock = threading.Lock()


def _next_number(org_id: Optional[str] = None) -> int:
    """Next sequence number for this org, from the durable counter.

    One shared counter keeps references unique across kinds; the prefix
    distinguishes them (C24 and P24 are different items).

    The old version locked a file with fcntl, which was correct on one machine
    and meaningless the moment the file itself stopped surviving a redeploy —
    the counter reset to zero and started handing out references that already
    existed. The counter is now a store record, so it persists.

    Concurrency: a process-level lock covers threads inside one instance, which
    is the deployment today. Two app instances could still interleave, so the
    caller re-checks uniqueness below rather than trusting the number. If DOCex
    ever runs more than one instance, this wants a real database sequence — it
    is written down here because that failure would otherwise appear as two
    payments sharing a voucher number.
    """
    org = _org(org_id)
    with _ref_lock:
        st = store.get_store()
        raw = st.get(org, _COUNTER, "transaction") or {"value": 0}
        nxt = int(raw.get("value", 0)) + 1
        st.put(org, _COUNTER, "transaction", {"value": nxt})
        return nxt


def next_ref(kind: TxnKind, org_id: Optional[str] = None) -> str:
    """Generate the next human reference for a kind, e.g. 'C24'.

    Verifies the reference is genuinely unused before returning it. A duplicate
    here is not cosmetic: this reference goes on the payment voucher, and two
    payments sharing one is the kind of thing an auditor finds.
    """
    prefix = _PREFIX.get(kind, "TX")
    org = _org(org_id)
    taken = {t.ref.lower() for t in _iter_all(org)}
    for _ in range(50):
        ref = f"{prefix}{_next_number(org)}"
        if ref.lower() not in taken:
            return ref
    raise TransactionError(
        "Could not allocate an unused transaction reference after 50 attempts. "
        "The counter is behind the records it should be ahead of — check the "
        "transaction_counter record for this org.")


# ─── persistence ────────────────────────────────────────────────────────────


def save(txn: Transaction, org_id: Optional[str] = None) -> Transaction:
    now = _now_iso()
    if not txn.created_at:
        txn.created_at = now
    txn.updated_at = now
    store.get_store().put(_org(org_id), _TXNS, txn.id, txn.model_dump())
    return txn


def load(txn_id: str, org_id: Optional[str] = None) -> Transaction:
    raw = store.get_store().get(_org(org_id), _TXNS, txn_id)
    if raw is None:
        raise TransactionError(f"Transaction '{txn_id}' not found.")
    return Transaction.model_validate(raw)


def load_by_ref(ref: str, org_id: Optional[str] = None) -> Transaction:
    """Look up a transaction by its human reference (C24). Linear scan — fine
    at the volumes DOCex handles; swap for an index if it ever isn't."""
    want = (ref or "").strip().lower()
    for txn in _iter_all(org_id):
        if txn.ref.lower() == want:
            return txn
    raise TransactionError(f"Transaction '{ref}' not found.")


def _iter_all(org_id: Optional[str] = None) -> list[Transaction]:
    out: list[Transaction] = []
    for raw in store.get_store().list(_org(org_id), _TXNS):
        try:
            out.append(Transaction.model_validate(raw))
        except Exception as exc:  # skip corrupt records, don't crash the list
            print(f"Warning: skipping corrupt transaction "
                  f"{raw.get('id', '?')}: {exc}")
    return out


def migrate_legacy_transactions(org_id: Optional[str] = None) -> int:
    """One-time import from the pre-store {root}/transactions/ layout.

    Also carries the old file counter across, so references continue from where
    they left off instead of restarting at 1 and colliding with history.
    """
    if not _TXN_DIR.is_dir():
        return 0
    org = _org(org_id)
    st = store.get_store()
    if st.list(org, _TXNS):
        return 0
    imported = 0
    highest = 0
    for path in sorted(_TXN_DIR.glob("*.json")):
        try:
            txn = Transaction.model_validate_json(path.read_text())
        except Exception as exc:
            print(f"Warning: skipping legacy transaction {path.name}: {exc}")
            continue
        st.put(org, _TXNS, txn.id, txn.model_dump())
        imported += 1
        digits = "".join(c for c in txn.ref if c.isdigit())
        if digits.isdigit():
            highest = max(highest, int(digits))
    if _COUNTER_FILE.exists():
        try:
            raw = _COUNTER_FILE.read_text().strip()
            if raw.isdigit():
                highest = max(highest, int(raw))
        except Exception:
            pass
    if highest:
        st.put(org, _COUNTER, "transaction", {"value": highest})
    if imported:
        print(f"[transactions] Imported {imported} from the legacy directory "
              f"into org '{org}' (counter at {highest}).")
    return imported


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
    org_id: Optional[str] = None,
) -> Transaction:
    """Open a new transaction with a fresh reference and a 'created' event."""
    now = _now_iso()
    txn = Transaction(
        id=uuid.uuid4().hex,
        ref=next_ref(kind, org_id),
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
    return save(txn, org_id)


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
    org_id: Optional[str] = None,
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
    return save(txn, org_id)


def record_view(
    txn: Transaction,
    *,
    department: Optional[Department] = None,
    actor: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Transaction:
    """Record that a department/actor looked at this transaction. Idempotent per
    viewer — the 'viewed by compliance' signal, not a full history spam."""
    viewer = department or actor
    if viewer and viewer not in txn.viewed_by:
        txn.viewed_by.append(viewer)
        txn.history.append(TxnEvent(
            type="viewed", timestamp=_now_iso(), actor=actor, department=department,
        ))
        return save(txn, org_id)
    return txn


def add_note(
    txn: Transaction,
    note: str,
    *,
    actor: Optional[str] = None,
    department: Optional[Department] = None,
    org_id: Optional[str] = None,
) -> Transaction:
    txn.history.append(TxnEvent(
        type="noted", timestamp=_now_iso(), actor=actor,
        department=department, note=note,
    ))
    return save(txn, org_id)
