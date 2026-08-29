"""
Grants & cash-flow engine — the "monthly compliance system".

The question this answers, every month, for any donor-funded NGO:

    For each signed agreement / project:
      how much cash was EXPECTED?
      how much did we REQUEST?
      how much ACTUALLY CAME?
      what's the variance, and how late is it?

That is arithmetic over four record types, so CODE owns all of it — no LLM
touches a figure here. (An LLM may later help read a signed agreement PDF to
*propose* the tranche schedule, but a human confirms it and code does the maths.)

Generic by design: nothing here is specific to one organisation. Any NGO with
donors, projects and tranche schedules — EVA, Neem, TA Connect — uses the same
engine with their own data, scoped by org_id (see store.py).

Money notes:
  - Amounts are rounded to 2dp at every boundary.
  - Currency is carried per agreement; we do NOT invent FX rates. A period
    mixing currencies is reported per-currency and flagged rather than summed
    into a meaningless total.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from pydantic import BaseModel, Field

import store

# Collections (record types) this engine owns.
_AGREEMENTS = "agreements"
_TRANCHES = "tranches"
_REQUESTS = "funding_requests"
_INFLOWS = "cash_inflows"


# ─── models ─────────────────────────────────────────────────────────────────


class Agreement(BaseModel):
    """A signed funding agreement with a donor."""
    id: str
    org_id: str = ""
    donor: str
    project_code: str                      # the org's own project/grant code
    title: str = ""
    value: float = 0.0                     # total agreement value
    currency: str = "NGN"
    signed_date: Optional[str] = None      # ISO date
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    document_ref: Optional[str] = None     # link/filename of the signed PDF
    status: str = "active"                 # active | closed | suspended
    created_at: Optional[str] = None


class Tranche(BaseModel):
    """One expected instalment under an agreement — the EXPECTED column."""
    id: str
    org_id: str = ""
    agreement_id: str
    label: str = ""                        # e.g. "Q1 disbursement"
    due_date: str                          # ISO date; drives the period + aging
    expected_amount: float = 0.0
    condition: str = ""                    # e.g. "on submission of Q4 report"


class FundingRequest(BaseModel):
    """What we actually asked the donor for — the REQUESTED column."""
    id: str
    org_id: str = ""
    agreement_id: str
    period: str                            # "YYYY-MM"
    requested_amount: float = 0.0
    submitted_date: Optional[str] = None
    status: str = "submitted"              # submitted | approved | rejected
    note: str = ""


class CashInflow(BaseModel):
    """Money that actually landed — the RECEIVED column. Ties to the bank."""
    id: str
    org_id: str = ""
    agreement_id: str
    received_date: str                     # ISO date
    amount: float = 0.0
    currency: str = "NGN"
    bank_ref: str = ""                     # statement/transfer reference
    allocated_project_code: str = ""       # coding at the point of receipt
    note: str = ""


class CashFlowRow(BaseModel):
    """One row of the monthly matrix — per (period × agreement)."""
    period: str
    agreement_id: str
    donor: str
    project_code: str
    currency: str
    expected: float = 0.0
    requested: float = 0.0
    received: float = 0.0                  # ONLY inflows in the agreement's currency
    # Inflows received in a DIFFERENT currency to the agreement. Deliberately
    # kept out of `received` — we do not invent FX rates, and a total that
    # silently mixes currencies is worse than no total. Surfaced with a flag so
    # finance converts and re-records it deliberately.
    received_other_currency: float = 0.0
    variance: float = 0.0                  # received - expected (negative = shortfall)
    pct_received: Optional[float] = None   # received / expected, None when expected == 0
    cumulative_expected: float = 0.0
    cumulative_received: float = 0.0
    cumulative_shortfall: float = 0.0      # >0 means still owed to date
    flags: list[str] = Field(default_factory=list)


class AgingRow(BaseModel):
    """A tranche that is due but not (fully) covered by receipts to date."""
    agreement_id: str
    donor: str
    project_code: str
    tranche_label: str
    due_date: str
    expected_amount: float
    covered_amount: float
    outstanding: float
    days_late: int
    currency: str = "NGN"


# ─── helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _money(x: float) -> float:
    return round(float(x or 0.0), 2)


def _period_of(iso_date: Optional[str]) -> Optional[str]:
    """'2026-08-14' -> '2026-08'. Returns None for unparseable input rather than
    raising — a bad date becomes a flag, never a crash."""
    if not iso_date:
        return None
    s = str(iso_date).strip()
    if len(s) >= 7 and s[4] == "-":
        return s[:7]
    return None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ─── write operations ───────────────────────────────────────────────────────


def add_agreement(org_id: str, **kwargs) -> Agreement:
    org = store.require_org(org_id)
    ag = Agreement(id=kwargs.pop("id", None) or _new_id("agr"), org_id=org,
                   created_at=_now_iso(), **kwargs)
    store.get_store().put(org, _AGREEMENTS, ag.id, ag.model_dump())
    return ag


def add_tranche(org_id: str, agreement_id: str, due_date: str,
                expected_amount: float, label: str = "", condition: str = "") -> Tranche:
    org = store.require_org(org_id)
    tr = Tranche(id=_new_id("trn"), org_id=org, agreement_id=agreement_id,
                 due_date=due_date, expected_amount=_money(expected_amount),
                 label=label, condition=condition)
    store.get_store().put(org, _TRANCHES, tr.id, tr.model_dump())
    return tr


def record_request(org_id: str, agreement_id: str, period: str,
                   requested_amount: float, submitted_date: Optional[str] = None,
                   note: str = "") -> FundingRequest:
    org = store.require_org(org_id)
    fr = FundingRequest(id=_new_id("req"), org_id=org, agreement_id=agreement_id,
                        period=period, requested_amount=_money(requested_amount),
                        submitted_date=submitted_date, note=note)
    store.get_store().put(org, _REQUESTS, fr.id, fr.model_dump())
    return fr


def record_inflow(org_id: str, agreement_id: str, received_date: str, amount: float,
                  currency: str = "NGN", bank_ref: str = "",
                  allocated_project_code: str = "", note: str = "") -> CashInflow:
    org = store.require_org(org_id)
    inf = CashInflow(id=_new_id("inf"), org_id=org, agreement_id=agreement_id,
                     received_date=received_date, amount=_money(amount),
                     currency=currency, bank_ref=bank_ref,
                     allocated_project_code=allocated_project_code, note=note)
    store.get_store().put(org, _INFLOWS, inf.id, inf.model_dump())
    return inf


# ─── read operations ────────────────────────────────────────────────────────


def list_agreements(org_id: str) -> list[Agreement]:
    org = store.require_org(org_id)
    return [Agreement.model_validate(r) for r in store.get_store().list(org, _AGREEMENTS)]


def _load_all(org: str) -> tuple[list[Agreement], list[Tranche], list[FundingRequest], list[CashInflow]]:
    s = store.get_store()
    ags = [Agreement.model_validate(r) for r in s.list(org, _AGREEMENTS)]
    trs = [Tranche.model_validate(r) for r in s.list(org, _TRANCHES)]
    reqs = [FundingRequest.model_validate(r) for r in s.list(org, _REQUESTS)]
    infs = [CashInflow.model_validate(r) for r in s.list(org, _INFLOWS)]
    return ags, trs, reqs, infs


# ─── the monthly matrix ─────────────────────────────────────────────────────


def monthly_matrix(org_id: str, period_from: Optional[str] = None,
                   period_to: Optional[str] = None,
                   project_code: Optional[str] = None) -> list[CashFlowRow]:
    """The monthly compliance table: expected vs requested vs actually received,
    per period per agreement, with variance and running shortfall.

    Periods are "YYYY-MM". Rows are emitted for any period in which an agreement
    has expected, requested or received activity, sorted by period then donor.
    Cumulative columns run across ALL periods up to and including the row's
    period (not just the filtered window), so a filtered view still tells the
    truth about what's owed to date.
    """
    org = store.require_org(org_id)
    ags, trs, reqs, infs = _load_all(org)
    by_id = {a.id: a for a in ags}

    # Bucket every input into (agreement_id, period).
    expected: dict[tuple[str, str], float] = {}
    requested: dict[tuple[str, str], float] = {}
    received: dict[tuple[str, str], float] = {}
    received_other: dict[tuple[str, str], float] = {}
    flags: dict[tuple[str, str], list[str]] = {}

    def _flag(key: tuple[str, str], msg: str) -> None:
        flags.setdefault(key, [])
        if msg not in flags[key]:
            flags[key].append(msg)

    for t in trs:
        p = _period_of(t.due_date)
        if p is None:
            continue
        key = (t.agreement_id, p)
        expected[key] = _money(expected.get(key, 0.0) + t.expected_amount)

    for r in reqs:
        p = (r.period or "").strip()[:7]
        if not p:
            continue
        key = (r.agreement_id, p)
        requested[key] = _money(requested.get(key, 0.0) + r.requested_amount)

    for i in infs:
        p = _period_of(i.received_date)
        if p is None:
            continue
        key = (i.agreement_id, p)
        ag = by_id.get(i.agreement_id)
        mismatched = bool(ag and i.currency and ag.currency and i.currency != ag.currency)
        if mismatched:
            # Never fold a foreign-currency receipt into the agreement-currency
            # total: the resulting number would be meaningless. Track it apart
            # and flag it for deliberate conversion.
            received_other[key] = _money(received_other.get(key, 0.0) + i.amount)
            _flag(key, f"{i.currency} {i.amount:,.2f} received against a "
                       f"{ag.currency} agreement — excluded from the total; convert and re-record")
        else:
            received[key] = _money(received.get(key, 0.0) + i.amount)
        if ag and i.allocated_project_code and i.allocated_project_code != ag.project_code:
            _flag(key, f"inflow coded to {i.allocated_project_code}, agreement is {ag.project_code}")

    # Include foreign-currency-only periods: a receipt we excluded from the
    # total still needs a visible row carrying its flag, or it would disappear.
    keys = set(expected) | set(requested) | set(received) | set(received_other)
    rows: list[CashFlowRow] = []

    # Cumulative running totals per agreement, computed over ALL periods in order.
    for agreement_id in {k[0] for k in keys}:
        ag = by_id.get(agreement_id)
        if ag is None:
            continue  # orphan record; skip rather than crash
        if project_code and ag.project_code != project_code:
            continue

        periods = sorted({k[1] for k in keys if k[0] == agreement_id})
        cum_exp = 0.0
        cum_rec = 0.0
        for p in periods:
            key = (agreement_id, p)
            exp = _money(expected.get(key, 0.0))
            req = _money(requested.get(key, 0.0))
            rec = _money(received.get(key, 0.0))
            cum_exp = _money(cum_exp + exp)
            cum_rec = _money(cum_rec + rec)

            # Apply the window AFTER cumulatives so they stay truthful.
            if period_from and p < period_from:
                continue
            if period_to and p > period_to:
                continue

            rows.append(CashFlowRow(
                period=p,
                agreement_id=agreement_id,
                donor=ag.donor,
                project_code=ag.project_code,
                currency=ag.currency,
                expected=exp,
                requested=req,
                received=rec,
                received_other_currency=_money(received_other.get(key, 0.0)),
                variance=_money(rec - exp),
                pct_received=(round(rec / exp * 100, 1) if exp else None),
                cumulative_expected=cum_exp,
                cumulative_received=cum_rec,
                cumulative_shortfall=_money(max(0.0, cum_exp - cum_rec)),
                flags=flags.get(key, []),
            ))

    rows.sort(key=lambda r: (r.period, r.donor, r.project_code))
    return rows


def aging(org_id: str, as_of: Optional[str] = None) -> list[AgingRow]:
    """Tranches that are due but not yet covered by receipts, oldest first.

    Coverage is applied cumulatively per agreement (receipts settle the oldest
    due tranche first) — the standard, defensible treatment when a donor's
    payment doesn't reference a specific tranche.
    """
    org = store.require_org(org_id)
    ags, trs, _reqs, infs = _load_all(org)
    by_id = {a.id: a for a in ags}
    today = (as_of or dt.date.today().isoformat())[:10]

    received_by_ag: dict[str, float] = {}
    for i in infs:
        if (i.received_date or "")[:10] <= today:
            received_by_ag[i.agreement_id] = _money(
                received_by_ag.get(i.agreement_id, 0.0) + i.amount
            )

    out: list[AgingRow] = []
    for agreement_id, agreement in by_id.items():
        due = sorted(
            [t for t in trs if t.agreement_id == agreement_id and (t.due_date or "")[:10] <= today],
            key=lambda t: t.due_date,
        )
        pot = received_by_ag.get(agreement_id, 0.0)
        for t in due:
            covered = _money(min(pot, t.expected_amount))
            pot = _money(max(0.0, pot - covered))
            outstanding = _money(t.expected_amount - covered)
            if outstanding <= 0:
                continue
            try:
                days = (dt.date.fromisoformat(today) - dt.date.fromisoformat(t.due_date[:10])).days
            except ValueError:
                days = 0
            out.append(AgingRow(
                agreement_id=agreement_id, donor=agreement.donor,
                project_code=agreement.project_code, tranche_label=t.label or "Tranche",
                due_date=t.due_date, expected_amount=t.expected_amount,
                covered_amount=covered, outstanding=outstanding,
                days_late=days, currency=agreement.currency,
            ))

    out.sort(key=lambda r: r.due_date)
    return out


def portfolio_summary(org_id: str, as_of: Optional[str] = None) -> dict:
    """Headline numbers for the dashboard: totals per currency + what's overdue."""
    rows = monthly_matrix(org_id)
    late = aging(org_id, as_of=as_of)
    by_currency: dict[str, dict[str, float]] = {}
    for r in rows:
        c = by_currency.setdefault(r.currency, {"expected": 0.0, "requested": 0.0, "received": 0.0})
        c["expected"] = _money(c["expected"] + r.expected)
        c["requested"] = _money(c["requested"] + r.requested)
        c["received"] = _money(c["received"] + r.received)
    for c in by_currency.values():
        c["variance"] = _money(c["received"] - c["expected"])
    return {
        "by_currency": by_currency,
        "overdue_count": len(late),
        "overdue_total": _money(sum(r.outstanding for r in late)),
        "agreements": len(list_agreements(org_id)),
    }
