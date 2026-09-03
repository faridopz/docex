"""
Delegation of Authority — who must approve, at what amount.

WHY THIS EXISTS
EVA's process map routes every payment voucher "for approval in line with the
organisation's Delegation of Authority", ending at the Executive Director. Today
that matrix lives in people's heads and in a signed PDF nobody consults at the
moment of approval. The predictable results are a payment approved by someone
who lacked the authority, and an auditor asking who authorised something and
getting a shrug.

This makes the matrix data, and enforces it.

DETERMINISTIC-FIRST
Every decision here is arithmetic: compare an amount to a band, look up the
chain, check a position. No model call, ever. A finance system that asked an LLM
"is ₦4,200,000 above the threshold?" would be indefensible.

HOW IT DIFFERS FROM requisitions.RequisitionWorkflow
The existing workflow filters steps by `min_amount`, which expresses a
*monotonic* chain: bigger amounts pass through more steps, always the same ones
plus extras. That covers most orgs, including NEEM.

A DOA matrix is more general in two ways EVA actually needs:

  * **Bands select a chain**, rather than accumulating steps. A band can name a
    completely different set of approvers, not merely a longer one.
  * **Payment type scopes a band.** A ₦500,000 staff advance and a ₦500,000
    vendor invoice can require different approvers — EVA's advance policies
    (POL-FIN-300.01 to .04) are separate documents from their procurement
    policy for exactly this reason.

So this is an additional engine, not a replacement. Orgs whose rules are
monotonic keep using the workflow steps; orgs with a real DOA matrix switch on
the `doa_matrix` feature flag.

THE GAP IS THE DANGEROUS PART
`validate()` refuses a matrix with a gap between bands. A gap means some amount
resolves to no chain at all, which in practice means a payment that nobody can
approve and nobody can explain — the requisition simply sits. Overlaps are
rejected for the same reason in reverse: two chains for one amount is an
argument waiting to happen, in front of an auditor.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Optional

from pydantic import BaseModel, Field

import store

_CONFIG = "config"
_MATRIX_ID = "doa_matrix"

# Sentinel for "no upper bound". Using a number rather than None keeps the
# comparison logic in one shape and avoids a None-check at every boundary.
UNBOUNDED = float("inf")


class DOAError(ValueError):
    """An invalid matrix, or an amount no band covers. Callers map to 4xx."""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _org(org_id: Optional[str] = None) -> str:
    explicit = (org_id or "").strip()
    if explicit:
        return store.require_org(explicit)
    return store.require_org((os.environ.get("DOCEX_ORG") or "default").strip() or "default")


def _money(x: Optional[float]) -> float:
    return round(float(x or 0.0), 2)


# ─── model ──────────────────────────────────────────────────────────────────


class DOABand(BaseModel):
    """One authority band: an amount range, and who must sign inside it.

    Ranges are HALF-OPEN — `min_amount <= x < max_amount`. That makes a
    boundary unambiguous: with bands 0–100,000 and 100,000–1,000,000, exactly
    ₦100,000 falls in the second. Inclusive-both-ends would put it in both,
    and "which band is ₦100,000 in?" is precisely the question an auditor asks.
    """
    label: str = ""
    min_amount: float = 0.0
    max_amount: float = UNBOUNDED
    # Empty means the band applies to every payment type. A band naming types
    # is more specific and wins over a generic band covering the same amount.
    payment_types: list[str] = Field(default_factory=list)
    # Ordered department keys. Order is the approval sequence.
    approvers: list[str] = Field(default_factory=list)

    def covers_amount(self, amount: float) -> bool:
        return _money(amount) >= _money(self.min_amount) and (
            self.max_amount == UNBOUNDED or _money(amount) < _money(self.max_amount)
        )

    def covers_type(self, payment_type: str) -> bool:
        if not self.payment_types:
            return True
        return (payment_type or "").strip().lower() in {
            t.strip().lower() for t in self.payment_types
        }

    @property
    def is_specific(self) -> bool:
        return bool(self.payment_types)


class DOAMatrix(BaseModel):
    """An organisation's complete delegation of authority."""
    org_id: str = ""
    currency: str = "NGN"
    bands: list[DOABand] = Field(default_factory=list)
    # Appended to every chain if it isn't already the last approver. EVA's ED
    # authorises after the TLFA has processed payment, so this is not simply
    # "the highest band's approver" — it is a distinct, always-last step.
    final_authority: Optional[str] = None
    updated_at: Optional[str] = None


class DOADecision(BaseModel):
    """The resolved answer for one (amount, payment_type)."""
    amount: float
    payment_type: str = ""
    band_label: str = ""
    chain: list[str] = Field(default_factory=list)   # ordered department keys

    @property
    def first(self) -> Optional[str]:
        return self.chain[0] if self.chain else None

    @property
    def final(self) -> Optional[str]:
        return self.chain[-1] if self.chain else None


# ─── validation ─────────────────────────────────────────────────────────────


def validate(matrix: DOAMatrix, known_departments: Optional[set[str]] = None) -> list[str]:
    """Return a list of problems. Empty means the matrix is safe to install.

    Checks the failures that strand a payment rather than merely annoying
    someone: an amount no band covers, two bands claiming the same amount, a
    chain routed to a department that doesn't exist, and an empty chain.
    """
    problems: list[str] = []
    if not matrix.bands:
        problems.append("Matrix has no bands — every payment would be unapprovable.")
        return problems

    for i, b in enumerate(matrix.bands):
        name = b.label or f"band[{i}]"
        if _money(b.min_amount) < 0:
            problems.append(f"{name}: min_amount cannot be negative.")
        if b.max_amount != UNBOUNDED and _money(b.max_amount) <= _money(b.min_amount):
            problems.append(
                f"{name}: max_amount ({b.max_amount}) must exceed min_amount "
                f"({b.min_amount}) — the band covers nothing."
            )
        if not b.approvers:
            problems.append(f"{name}: no approvers — a payment here could never be approved.")
        if known_departments is not None:
            for dept in b.approvers:
                if dept not in known_departments:
                    problems.append(f"{name}: approver '{dept}' is not a department.")
        if len(set(b.approvers)) != len(b.approvers):
            problems.append(f"{name}: the same approver appears twice in the chain.")

    if known_departments is not None and matrix.final_authority:
        if matrix.final_authority not in known_departments:
            problems.append(
                f"final_authority '{matrix.final_authority}' is not a department."
            )

    # Coverage: within each payment-type scope, bands must tile [0, ∞) with no
    # gap and no overlap. Generic bands (no payment_types) are checked as their
    # own scope; a specific band is allowed to sit on top of a generic one.
    scopes: dict[str, list[DOABand]] = {}
    for b in matrix.bands:
        for key in (b.payment_types or ["*"]):
            scopes.setdefault(key.strip().lower(), []).append(b)

    for scope, bands in scopes.items():
        ordered = sorted(bands, key=lambda x: _money(x.min_amount))
        where = "all payment types" if scope == "*" else f"payment type '{scope}'"
        if _money(ordered[0].min_amount) > 0:
            problems.append(
                f"{where}: nothing covers amounts below "
                f"{_money(ordered[0].min_amount):,.2f} — those payments would stall."
            )
        for a, b in zip(ordered, ordered[1:]):
            a_max = a.max_amount
            if a_max == UNBOUNDED:
                problems.append(
                    f"{where}: '{a.label or 'a band'}' is unbounded but another band "
                    f"starts at {_money(b.min_amount):,.2f} — they overlap."
                )
                continue
            if _money(a_max) < _money(b.min_amount):
                problems.append(
                    f"{where}: gap between {_money(a_max):,.2f} and "
                    f"{_money(b.min_amount):,.2f} — an amount in that range has no "
                    f"approver and the requisition would sit forever."
                )
            elif _money(a_max) > _money(b.min_amount):
                problems.append(
                    f"{where}: '{a.label or 'a band'}' overlaps "
                    f"'{b.label or 'the next band'}' between "
                    f"{_money(b.min_amount):,.2f} and {_money(a_max):,.2f}."
                )
        if ordered[-1].max_amount != UNBOUNDED:
            problems.append(
                f"{where}: nothing covers amounts at or above "
                f"{_money(ordered[-1].max_amount):,.2f}. Give the top band no "
                f"upper bound, or the org's ceiling will silently block payments."
            )
    return problems


# ─── persistence ────────────────────────────────────────────────────────────


def set_matrix(org_id: str, matrix: DOAMatrix, *, check_departments: bool = True) -> DOAMatrix:
    """Install a matrix after validating it. Refuses to store a broken one —
    a half-valid DOA is worse than none, because it looks authoritative."""
    org = _org(org_id)
    known: Optional[set[str]] = None
    if check_departments:
        try:
            import departments
            known = {d.key for d in departments.list_departments(org)}
        except Exception:
            known = None
    problems = validate(matrix, known)
    if problems:
        raise DOAError("DOA matrix is invalid:\n  - " + "\n  - ".join(problems))
    matrix.org_id = org
    matrix.updated_at = _now_iso()
    store.get_store().put(org, _CONFIG, _MATRIX_ID, matrix.model_dump())
    return matrix


def get_matrix(org_id: str) -> Optional[DOAMatrix]:
    """The org's matrix, or None if they don't use one."""
    raw = store.get_store().get(_org(org_id), _CONFIG, _MATRIX_ID)
    if not raw:
        return None
    try:
        return DOAMatrix.model_validate(raw)
    except Exception as exc:
        raise DOAError(f"Stored DOA matrix is unreadable: {exc}") from exc


def is_active(org_id: str) -> bool:
    """True when this org both has the feature on and has a matrix installed."""
    try:
        import org_config
        if not org_config.feature_enabled(org_id, "doa_matrix"):
            return False
    except Exception:
        return False
    try:
        return get_matrix(org_id) is not None
    except DOAError:
        return False


# ─── resolution ─────────────────────────────────────────────────────────────


def resolve(org_id: str, amount: float, payment_type: str = "") -> DOADecision:
    """Who must approve this payment, in order.

    Raises DOAError when no band covers the amount. That is deliberate: the
    alternative is returning an empty chain, which downstream would read as
    "no approval needed" — the worst possible failure in a payments system.
    """
    matrix = get_matrix(org_id)
    if matrix is None:
        raise DOAError(f"No DOA matrix configured for '{org_id}'.")
    return resolve_with(matrix, amount, payment_type)


def resolve_with(matrix: DOAMatrix, amount: float, payment_type: str = "") -> DOADecision:
    """Pure resolution against a matrix — no storage. Used by tests and by
    anything previewing a matrix before installing it."""
    amt = _money(amount)
    candidates = [b for b in matrix.bands if b.covers_amount(amt) and b.covers_type(payment_type)]
    if not candidates:
        raise DOAError(
            f"No delegation of authority covers {matrix.currency} {amt:,.2f}"
            + (f" for payment type '{payment_type}'" if payment_type else "")
            + ". Configure a band for this amount before the payment can move."
        )
    # A band naming payment types is more specific than a catch-all covering the
    # same amount, so it wins. Ties break on the narrower range.
    candidates.sort(key=lambda b: (not b.is_specific, b.max_amount - b.min_amount))
    band = candidates[0]

    chain = list(band.approvers)
    if matrix.final_authority and (not chain or chain[-1] != matrix.final_authority):
        # Remove an earlier appearance so the final authority is last, once.
        chain = [d for d in chain if d != matrix.final_authority] + [matrix.final_authority]
    return DOADecision(
        amount=amt, payment_type=payment_type or "",
        band_label=band.label, chain=chain,
    )


# ─── enforcement ────────────────────────────────────────────────────────────


def next_approver(decision: DOADecision, approved_by: list[str]) -> Optional[str]:
    """The department whose turn it is, given who has already approved.

    Walks the chain in order and returns the first department not yet recorded.
    None means the chain is complete.
    """
    done = list(approved_by or [])
    for dept in decision.chain:
        if dept in done:
            done.remove(dept)   # consume one approval per chain position
            continue
        return dept
    return None


def can_approve(
    decision: DOADecision,
    department: str,
    approved_by: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """May this department approve right now? Returns (allowed, reason).

    Enforces ORDER, not just membership. A department later in the chain
    cannot approve before the ones ahead of it — skipping compliance and going
    straight to the ED is exactly the thing an auditor looks for.
    """
    dept = (department or "").strip()
    if not dept:
        return False, "No department supplied."
    if dept not in decision.chain:
        return False, (
            f"'{dept}' is not in the approval chain for this amount "
            f"({' → '.join(decision.chain)})."
        )
    expected = next_approver(decision, approved_by or [])
    if expected is None:
        return False, "This payment has already completed its approval chain."
    if dept != expected:
        return False, (
            f"Out of order: '{expected}' must approve before '{dept}'. "
            f"Chain: {' → '.join(decision.chain)}."
        )
    return True, ""


def describe(org_id: str) -> dict:
    """The matrix in a shape a UI or an auditor can read."""
    matrix = get_matrix(org_id)
    if matrix is None:
        return {"org_id": _org(org_id), "configured": False, "bands": []}
    return {
        "org_id": matrix.org_id,
        "configured": True,
        "currency": matrix.currency,
        "final_authority": matrix.final_authority,
        "updated_at": matrix.updated_at,
        "bands": [{
            "label": b.label,
            "min_amount": b.min_amount,
            "max_amount": None if b.max_amount == UNBOUNDED else b.max_amount,
            "payment_types": b.payment_types,
            "approvers": b.approvers,
        } for b in sorted(matrix.bands, key=lambda x: _money(x.min_amount))],
    }
