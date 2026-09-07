"""
Withholding tax — one approved payment, two debits on the bank statement.

WHY THIS IS CORE, NOT A NEEM CUSTOMISATION
Every Nigerian organisation paying a vendor withholds tax at source and remits
it separately to the revenue authority. NEEM's cashbook shows it on nearly
every line, at 5% or 10%, remitted by RRR and coded 62010. EVA and TA Connect
face exactly the same obligation. It is the law, not a client preference.

THE FAILURE THIS PREVENTS
Reconciliation matches what DOCex says was paid against what left the bank. If
a ₦1,000,000 invoice is approved once and leaves the account as ₦950,000 to the
vendor plus ₦50,000 to the tax authority, then:

  * the vendor payment does not match on amount — DOCex expected ₦1,000,000
  * the tax remittance matches nothing at all, so it is reported as MONEY THAT
    LEFT THE ACCOUNT WITH NO APPROVED REQUEST

That is our most serious finding, fired at a statutory payment, on roughly half
the lines of a real Nigerian statement. The third time a finance officer sees a
red alert against a tax remittance they stop reading the alerts — which is how
a control designed to catch fraud ends up hiding it.

So the fix is not a filter that ignores tax lines. It is to model what actually
happened: an approved payment produces TWO disbursements, both expected, both
matched, and the audit trail shows the tax was withheld rather than lost.

RATES ARE CONFIGURATION, NOT CODE
DOCex ships NO withholding rates. Nigerian WHT rates differ by payment type and
by whether the payee is a company or an individual, and they change with
legislation — the Nigeria Tax Act reforms are recent enough that any rate
hard-coded here would be a confident, wrong deduction on somebody's invoice.
A wrong deduction is worse than none: it under-remits (a penalty) or
over-deducts from a vendor (a dispute and a refund).

So each organisation configures its own rules, ideally from the schedule their
auditor uses. Until they do, `enabled` is False and nothing is withheld.

DETERMINISTIC. Every figure here is arithmetic on a rate the client supplied.
No model is consulted.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

import store

_CONFIG = "config"
_POLICY_ID = "wht_policy"

PayeeType = Literal["company", "individual", "any"]


class WHTError(ValueError):
    """Invalid rule or policy — callers map this to HTTP 4xx."""


class WHTRule(BaseModel):
    """One line of an organisation's withholding schedule.

    `category` matches the spend category on a requisition. `payee_type` exists
    because Nigerian rates commonly differ between companies and individuals
    for the same service, and applying the company rate to an individual is a
    real over-deduction.
    """
    category: str
    rate_percent: float
    payee_type: PayeeType = "any"
    description: str = ""

    def matches(self, category: str, payee_type: str) -> bool:
        if (self.category or "").strip().lower() != (category or "").strip().lower():
            return False
        return self.payee_type == "any" or self.payee_type == payee_type


class WHTPolicy(BaseModel):
    """An organisation's withholding configuration.

    Off by default. An organisation that has not supplied its schedule gets no
    deductions at all, rather than a plausible guess applied to real invoices.
    """
    org_id: str = ""
    enabled: bool = False
    rules: list[WHTRule] = Field(default_factory=list)

    # Where the withheld tax goes, so the remittance is a real payee on the
    # ledger and matches a real line on the statement.
    authority_name: str = "Federal Inland Revenue Service"
    remittance_method: str = "RRR"        # Remita Retrieval Reference
    account_code: str = ""                # e.g. NEEM's 62010

    # Below this, withholding is not applied. Some organisations set a floor to
    # avoid remitting trivial amounts; 0 means withhold on everything.
    minimum_amount: float = 0.0

    updated_at: Optional[str] = None


class WHTResult(BaseModel):
    """What withholding does to one payment."""
    applies: bool = False
    gross: float = 0.0
    rate_percent: float = 0.0
    withheld: float = 0.0
    net_to_payee: float = 0.0
    category: str = ""
    payee_type: str = "any"
    rule_description: str = ""
    reason: str = ""          # why it did or did not apply — shown to a human


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _money(x: float) -> float:
    """Round to the kobo. Withholding is remitted to the authority, so the
    rounding has to be explicit rather than left to float display."""
    return round(float(x or 0.0) + 0.0, 2)


# ─── policy ─────────────────────────────────────────────────────────────────


def set_policy(org_id: str, policy: WHTPolicy) -> WHTPolicy:
    """Store an organisation's schedule.

    Validates before writing: a negative or absurd rate is a typo, and a typo
    in a tax rate becomes a wrong deduction on every invoice until somebody
    notices.
    """
    org = store.require_org(org_id)
    for rule in policy.rules:
        if not (rule.category or "").strip():
            raise WHTError("Every withholding rule needs a spend category.")
        if rule.rate_percent < 0 or rule.rate_percent > 100:
            raise WHTError(
                f"Rate for '{rule.category}' is {rule.rate_percent}% — that is "
                "not a withholding rate. Check the schedule.")
        if rule.rate_percent > 30:
            # Not refused: unusual rates exist. But it is worth a loud comment
            # in the record, because 50 instead of 5 is a plausible typo.
            rule.description = (rule.description or "") + \
                f" [UNUSUALLY HIGH — {rule.rate_percent}% — confirm with the schedule]"

    policy.org_id = org
    policy.updated_at = _now_iso()
    store.get_store().put(org, _CONFIG, _POLICY_ID, policy.model_dump())
    return policy


def get_policy(org_id: str) -> WHTPolicy:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _CONFIG, _POLICY_ID)
    return WHTPolicy.model_validate(raw) if raw else WHTPolicy(org_id=org)


# ─── the calculation ────────────────────────────────────────────────────────


def compute(
    org_id: str,
    *,
    gross: float,
    category: str,
    payee_type: str = "company",
    policy: Optional[WHTPolicy] = None,
) -> WHTResult:
    """How much to withhold from one payment, and why.

    Always returns a result rather than raising, and always says WHY — a
    finance officer looking at a payment with no deduction needs to know
    whether the category has no rule or whether withholding is switched off
    entirely. Those look identical on a payslip and are very different at
    audit.
    """
    p = policy or get_policy(org_id)
    gross = _money(gross)
    base = WHTResult(gross=gross, category=category, payee_type=payee_type,
                     net_to_payee=gross)

    if not p.enabled:
        base.reason = ("Withholding tax is not configured for this "
                       "organisation, so nothing was deducted.")
        return base
    if gross <= 0:
        base.reason = "No withholding on a zero or negative amount."
        return base
    if p.minimum_amount and gross < p.minimum_amount:
        base.reason = (f"Below the organisation's withholding floor of "
                       f"{p.minimum_amount:,.2f}.")
        return base

    # Most specific rule wins: one naming this payee type beats a catch-all,
    # because the specific rule is the one somebody deliberately wrote.
    matches = [r for r in p.rules if r.matches(category, payee_type)]
    if not matches:
        base.reason = (f"No withholding rule for category '{category}'"
                       f"{f' and {payee_type} payees' if payee_type != 'any' else ''}. "
                       "If tax should have been withheld, add the rule.")
        return base
    rule = sorted(matches, key=lambda r: r.payee_type == "any")[0]

    withheld = _money(gross * rule.rate_percent / 100.0)
    return WHTResult(
        applies=True, gross=gross, rate_percent=rule.rate_percent,
        withheld=withheld, net_to_payee=_money(gross - withheld),
        category=category, payee_type=payee_type,
        rule_description=rule.description,
        reason=(f"{rule.rate_percent}% withheld under the organisation's "
                f"schedule for '{category}'"
                f"{'' if rule.payee_type == 'any' else f' ({rule.payee_type} payee)'}."),
    )


# ─── recording the split ────────────────────────────────────────────────────


def record_split_payment(
    org_id: str,
    *,
    source_kind: str,
    source_id: str,
    source_ref: str,
    payee_name: str,
    gross: float,
    category: str,
    payee_type: str = "company",
    paid_at: str = "",
    paid_by: str = "",
    vendor_reference: str = "",
    tax_reference: str = "",
    payee_account: str = "",
    currency: str = "NGN",
) -> dict:
    """Record what actually left the bank: the net payment AND the remittance.

    This is the whole point of the module. Both are real disbursements, so
    reconciliation matches both, and neither appears as money nobody approved.
    The tax line names the authority as payee, because that is what the bank
    narration will say.

    Returns a summary including both disbursement ids, so a caller can show the
    pair on one screen.
    """
    import disbursements as _disb

    result = compute(org_id, gross=gross, category=category, payee_type=payee_type)
    when = paid_at or _now_iso()
    p = get_policy(org_id)

    vendor_payment = _disb.record(
        org_id, source_kind=source_kind, source_id=source_id,
        source_ref=source_ref, payee_name=payee_name,
        amount=result.net_to_payee, paid_at=when, paid_by=paid_by,
        bank_reference=vendor_reference, payee_account=payee_account,
        currency=currency, memo=category)

    tax_payment = None
    if result.applies and result.withheld > 0:
        tax_payment = _disb.record(
            org_id, source_kind=source_kind, source_id=source_id,
            # Same source_ref, so the pair is traceable to one approval — an
            # auditor asking "what authorised this remittance" gets the same
            # requisition the vendor payment came from.
            source_ref=source_ref,
            payee_name=p.authority_name,
            amount=result.withheld, paid_at=when, paid_by=paid_by,
            bank_reference=tax_reference, currency=currency,
            memo=(f"WHT {result.rate_percent}% on {source_ref} "
                  f"({payee_name})"))

    return {
        "gross": result.gross,
        "withheld": result.withheld,
        "net_to_payee": result.net_to_payee,
        "rate_percent": result.rate_percent,
        "reason": result.reason,
        "vendor_disbursement_id": vendor_payment.id,
        "tax_disbursement_id": tax_payment.id if tax_payment else "",
        "account_code": p.account_code,
        "remittance_method": p.remittance_method,
    }


# ─── reporting ──────────────────────────────────────────────────────────────


def liability(org_id: str, period: str) -> dict:
    """What was withheld in a period, and therefore owed to the authority.

    Finance needs this as its own number: withholding is money the
    organisation is holding on someone else's behalf, and under-remitting it
    carries a penalty. Reading it off a bank statement means trusting that
    every remittance was made; reading it from what was WITHHELD shows what
    should have gone out, which is the figure that matters.
    """
    import disbursements as _disb

    p = get_policy(org_id)
    items = _disb.list_disbursements(org_id, period=period)
    remittances = [d for d in items
                   if d.payee_name.strip().lower() == p.authority_name.strip().lower()]

    by_ref: dict[str, float] = {}
    for d in remittances:
        by_ref[d.source_ref] = _money(by_ref.get(d.source_ref, 0.0) + d.amount)

    return {
        "period": period,
        "authority": p.authority_name,
        "remittances": len(remittances),
        "total_withheld": _money(sum(d.amount for d in remittances)),
        "by_source": by_ref,
        "account_code": p.account_code,
        "method": p.remittance_method,
        "configured": p.enabled,
    }


def starter_rules_note() -> str:
    """Deliberately not a rate table.

    It would be easy to ship "5% on contracts, 10% on consultancy" and let
    clients accept the default. That is exactly how a wrong deduction reaches a
    real invoice — the default looks authoritative, nobody checks it, and the
    error surfaces as an under-remittance penalty months later.
    """
    return (
        "DOCex ships no withholding rates. Nigerian WHT differs by payment "
        "type and by whether the payee is a company or an individual, and the "
        "rates change with legislation. Ask the client's auditor or tax adviser "
        "for the schedule they currently apply, enter it once, and it governs "
        "every payment from then on. Until it is entered, nothing is withheld "
        "and every payment says so."
    )
