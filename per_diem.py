"""
Per-diem entitlement — deterministic math for event / travel per-diem.

The finance workflow this automates (done by hand today): a participant attends
an event for N days. The org pays a daily per-diem, BUT when the org (or the
funder, e.g. TA Connect) already covers a component of that day — food at the
hotel, lodging, local transport — the participant is only entitled to the
UNCOVERED portion of the day's per-diem.

TA Connect's stated rule: "we pay 75% of the daily per-diem when food is
covered" — i.e. meals are ~25% of the day. This module generalises that: a
per-diem is split into weighted components (lodging / meals / incidentals);
each covered component is deducted from that day's entitlement. Food covered
=> pay 1 - 0.25 = 75%. Nothing is hardcoded — the component weights and the
advance fraction are policy inputs finance controls.

It also combines the per-diem entitlement with reimbursable RECEIPTS (transport,
printing, etc.) to produce a single number: what to actually pay this person.
Summing receipts is arithmetic; reconcile() in receipts.py already owns the
advance-retirement case — here we only add the *reimbursable* side.

Deterministic-first: this module is pure arithmetic. It never reads a document
and never guesses. The caller supplies structured day-coverage; reading the
schedule / receipts to PRODUCE that structure is the AI's job upstream.
Never raises: unrecognised inputs become flags, not exceptions — finance still
gets a usable number with the gap surfaced.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from models import RateCard, ReceiptItem, RuleResult


# The three standard per-diem components. Weights must sum to 1.0. "meals" is
# the one TA Connect covers when they feed participants at the hotel.
ComponentName = Literal["lodging", "meals", "incidentals"]

_TOLERANCE = 0.001  # float slack for weight-sum and money comparisons


def _flag(rid: str, desc: str, verdict: str, reasoning: str) -> RuleResult:
    return RuleResult(
        rule_id=rid,
        rule_description=desc,
        verdict=verdict,
        reasoning=reasoning,
        confidence="found",
    )


class PerDiemComponents(BaseModel):
    """How a single day's per-diem splits across components. Weights are
    fractions of the daily rate and should sum to 1.0. Defaults encode the
    common NGO split where meals are a quarter of the day — so 'food covered'
    lands exactly on TA Connect's 75% rule."""

    lodging: float = 0.50
    meals: float = 0.25
    incidentals: float = 0.25

    def weight(self, component: str) -> Optional[float]:
        return getattr(self, component, None) if component in self.model_fields else None

    def total(self) -> float:
        return self.lodging + self.meals + self.incidentals


class PerDiemPolicy(BaseModel):
    """The org's per-diem rule set. Finance controls all of this."""

    rate_per_day: float                          # full daily per-diem, e.g. 20000
    components: PerDiemComponents = Field(default_factory=PerDiemComponents)
    # Fraction of the *entitlement* paid up front as an advance. 1.0 = pay the
    # full entitlement; 0.75 would mean "advance 75% now, reconcile later".
    # Distinct from coverage — this is a cash-flow policy, not a deduction.
    advance_fraction: float = 1.0
    currency: str = "NGN"


class DayCoverage(BaseModel):
    """One day of the event and which per-diem components the org already
    covered that day. Empty `covered` => the participant is entitled to the
    full daily rate for that day."""

    label: str = "Day"
    covered: list[ComponentName] = []


class PerDiemDayLine(BaseModel):
    """Per-day breakdown — the audit trail for 'why this amount?'."""

    label: str
    full_rate: float
    covered: list[str] = []
    deducted_fraction: float          # sum of covered component weights
    payable_fraction: float           # 1 - deducted_fraction
    payable: float                    # full_rate * payable_fraction


class PerDiemResult(BaseModel):
    """Deterministic per-diem entitlement for one participant."""

    rate_per_day: float
    days: int
    full_entitlement: float           # rate * days, before any coverage
    coverage_deduction: float         # total deducted because org covered items
    entitlement: float                # full_entitlement - coverage_deduction
    advance_payable: float            # entitlement * advance_fraction
    currency: str = "NGN"
    day_lines: list[PerDiemDayLine] = []
    flags: list[RuleResult] = []
    summary: str = ""


def compute_per_diem(policy: PerDiemPolicy, days: list[DayCoverage]) -> PerDiemResult:
    """Compute a participant's per-diem entitlement, deducting any day-component
    the org already covered. Pure arithmetic; never raises."""

    flags: list[RuleResult] = []
    comp = policy.components

    # Guard: weights should sum to 1.0. If not, we still compute (using the
    # given weights) but flag it — silent mis-weighting is worse than a warning.
    wsum = comp.total()
    if abs(wsum - 1.0) > _TOLERANCE:
        flags.append(_flag(
            "PD-WEIGHTS",
            "Per-diem component weights should sum to 1.0",
            "flag",
            f"Component weights sum to {wsum:.3f}, not 1.0 "
            f"(lodging={comp.lodging}, meals={comp.meals}, incidentals={comp.incidentals}). "
            "Coverage deductions may be under/over-stated.",
        ))

    lines: list[PerDiemDayLine] = []
    total_deduction = 0.0
    rate = policy.rate_per_day

    for i, day in enumerate(days, start=1):
        deducted_fraction = 0.0
        applied: list[str] = []
        for component in day.covered:
            w = comp.weight(component)
            if w is None:
                flags.append(_flag(
                    "PD-UNKNOWN-COMPONENT",
                    "Covered item is not a known per-diem component",
                    "flag",
                    f"{day.label or f'Day {i}'}: '{component}' is not one of "
                    "lodging / meals / incidentals — no deduction applied for it.",
                ))
                continue
            deducted_fraction += w
            applied.append(component)

        # Clamp: covering more than the whole day never produces a negative day.
        if deducted_fraction > 1.0 + _TOLERANCE:
            flags.append(_flag(
                "PD-OVER-COVERED",
                "Covered components exceed the full daily per-diem",
                "flag",
                f"{day.label or f'Day {i}'}: covered weight {deducted_fraction:.3f} > 1.0; "
                "clamped to full coverage (₦0 payable for the day).",
            ))
            deducted_fraction = 1.0

        payable_fraction = max(0.0, 1.0 - deducted_fraction)
        payable = round(rate * payable_fraction, 2)
        total_deduction += round(rate * deducted_fraction, 2)
        lines.append(PerDiemDayLine(
            label=day.label or f"Day {i}",
            full_rate=rate,
            covered=applied,
            deducted_fraction=round(deducted_fraction, 4),
            payable_fraction=round(payable_fraction, 4),
            payable=payable,
        ))

    n = len(days)
    full = round(rate * n, 2)
    entitlement = round(sum(l.payable for l in lines), 2)
    coverage_deduction = round(full - entitlement, 2)
    advance = round(entitlement * policy.advance_fraction, 2)

    cur = policy.currency
    if n == 0:
        summary = "No event days supplied — per-diem entitlement is 0."
    else:
        covered_days = sum(1 for l in lines if l.deducted_fraction > 0)
        summary = (
            f"{n} day(s) at {cur} {rate:,.0f}/day = {cur} {full:,.0f} full; "
            f"{covered_days} day(s) had org-covered items "
            f"(−{cur} {coverage_deduction:,.0f}); entitlement {cur} {entitlement:,.0f}."
        )
        if policy.advance_fraction != 1.0:
            summary += f" Advance at {policy.advance_fraction:.0%} = {cur} {advance:,.0f}."

    return PerDiemResult(
        rate_per_day=rate,
        days=n,
        full_entitlement=full,
        coverage_deduction=coverage_deduction,
        entitlement=entitlement,
        advance_payable=advance,
        currency=cur,
        day_lines=lines,
        flags=flags,
        summary=summary,
    )


def policy_from_rate_card(card: RateCard, role: Optional[str] = None) -> PerDiemPolicy:
    """Build a PerDiemPolicy from a TA-Connect-maintained rate card, picking the
    daily rate for the payee's role (falling back to the card default) and
    reading the component split + advance fraction the finance team configured.
    This is the bridge that makes the engine 100% data-driven — nothing about
    the rate or the 75% rule lives in code, it all comes from the saved card."""
    rate = card.default_rate_per_day
    if role:
        want = role.strip().lower()
        for line in card.roles:
            if line.role.strip().lower() == want:
                rate = line.amount_per_day
                break
    return PerDiemPolicy(
        rate_per_day=float(rate),
        components=PerDiemComponents(
            lodging=card.lodging_weight,
            meals=card.meals_weight,
            incidentals=card.incidentals_weight,
        ),
        advance_fraction=card.advance_fraction,
        currency=card.currency or "NGN",
    )


def uniform_days(num_days: int, covered: Optional[list[ComponentName]] = None,
                 label_prefix: str = "Day") -> list[DayCoverage]:
    """Convenience: build N identical days with the same coverage each day —
    the common case (org covers food every day of a residential workshop)."""
    covered = covered or []
    return [
        DayCoverage(label=f"{label_prefix} {i}", covered=list(covered))
        for i in range(1, max(0, num_days) + 1)
    ]


# ─── Combined participant payable ──────────────────────────────────────────
# What finance actually needs: one number per participant = per-diem
# entitlement + reimbursable receipts (transport, printing, etc.), with every
# component traceable. Reimbursables are receipts whose category is in
# `reimbursable_categories`; anything unreadable is surfaced as a flag, never
# silently dropped.

_DEFAULT_REIMBURSABLE = ("transport", "other")


class ParticipantPayable(BaseModel):
    """The bottom line for one participant, ready to become a voucher line."""

    participant_name: str
    event_name: str = ""
    per_diem: PerDiemResult
    reimbursable_total: float = 0.0
    reimbursable_count: int = 0
    unreadable_receipt_count: int = 0
    total_payable: float = 0.0
    currency: str = "NGN"
    flags: list[RuleResult] = []
    summary: str = ""


def build_participant_payable(
    participant_name: str,
    policy: PerDiemPolicy,
    days: list[DayCoverage],
    receipts: Optional[list[ReceiptItem]] = None,
    event_name: str = "",
    reimbursable_categories: tuple[str, ...] = _DEFAULT_REIMBURSABLE,
) -> ParticipantPayable:
    """Combine per-diem entitlement with reimbursable receipts into one payable.
    Pure arithmetic; never raises."""

    receipts = receipts or []
    pd = compute_per_diem(policy, days)
    flags: list[RuleResult] = list(pd.flags)

    reimb_total = 0.0
    reimb_count = 0
    unreadable = 0
    for r in receipts:
        cat = (r.category or "other").strip().lower()
        if cat not in reimbursable_categories:
            continue
        if r.amount is None:
            unreadable += 1
            flags.append(_flag(
                "PD-RECEIPT-UNREADABLE",
                "Reimbursable receipt has no readable amount",
                "flag",
                f"Receipt '{r.filename or cat}' ({cat}) has no amount — "
                "excluded from the total; confirm manually.",
            ))
            continue
        reimb_total += r.amount
        reimb_count += 1

    reimb_total = round(reimb_total, 2)
    total = round(pd.entitlement + reimb_total, 2)
    cur = policy.currency

    summary = (
        f"{participant_name}: per-diem {cur} {pd.entitlement:,.0f} "
        f"+ reimbursables {cur} {reimb_total:,.0f} ({reimb_count} receipt(s)) "
        f"= {cur} {total:,.0f} payable."
    )
    if unreadable:
        summary += f" ⚠ {unreadable} receipt(s) unreadable — review before paying."

    return ParticipantPayable(
        participant_name=participant_name,
        event_name=event_name,
        per_diem=pd,
        reimbursable_total=reimb_total,
        reimbursable_count=reimb_count,
        unreadable_receipt_count=unreadable,
        total_payable=total,
        currency=cur,
        flags=flags,
        summary=summary,
    )
