"""
Bank accounts — because a donor-funded NGO does not have one.

NEEM runs roughly twenty. One per project, across three banks: B24 CARE/FCDO
and B9 Lafiya Sarari and B19 POCI and B2 Salary and B15 HQ Petty Cash, plus a
separate legal entity in Neem Institute Ltd. That is not unusual — it is how
donor money is ring-fenced, and most funders require it.

WHAT BREAKS WITHOUT THIS
Reconciliation matches payments against a statement. With one account per
organisation that is unambiguous. With twenty it is actively dangerous: a
₦380,000 payment from the CARE account and a ₦380,000 payment from the UNFPA
account are indistinguishable on amount and date, so uploading the CARE
statement would happily match the UNFPA payment and report both months as
clean. Two wrong answers, no warning.

So the account is part of the identity of a payment, not a label on it.

THE RULE THIS MODULE ENFORCES
If an organisation has more than one account, reconciliation must be told which
one — and refuses rather than picking. An engine that guesses which of twenty
accounts a statement belongs to will be wrong roughly nineteen times in twenty,
and the report it produces will look completely normal.

Organisations with a single account are unaffected: nothing to choose, nothing
to configure, no new step.

IDENTIFYING THE ACCOUNT FROM THE FILE
Bank statements carry the account number in their header — NEEM's cashbook
tabs do, and so does every GTBank and Zenith export we have seen. So the
importer reads it and says which account this is, rather than asking a person
to remember that 0459639450 is UNFPA. When it cannot tell, it asks.

Account numbers are stored, because matching a statement needs them, but they
are MASKED everywhere they are returned. A payment screen has no reason to show
a full account number, and the fewer places it appears the fewer places it can
leak.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Optional

from pydantic import BaseModel, Field

import store

_ACCOUNTS = "bank_accounts"


class BankAccountError(ValueError):
    """Invalid account or an ambiguous selection — callers map this to 4xx."""


class BankAccount(BaseModel):
    """One real bank account the organisation holds."""
    id: str
    org_id: str = ""

    # The client's own code for it. NEEM uses B24, B9, B19 — the same codes
    # that appear on their vouchers, so a person recognises it instantly.
    code: str = ""
    name: str = ""                      # "CARE / FCDO"
    bank_name: str = ""                 # "GTBank"
    account_number: str = ""            # stored; masked on the way out
    project_code: str = ""              # links payments to a grant
    purpose: str = "project"            # project / salary / petty_cash / admin
    currency: str = "NGN"

    # A separate legal entity's account. NEEM Institute Ltd is not NEEM
    # Foundation, and mixing their statements would be a real accounting error.
    entity: str = ""

    active: bool = True
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def masked(self) -> str:
        """Last four digits only. Enough to recognise, useless to misuse."""
        n = re.sub(r"\D", "", self.account_number or "")
        return f"••••{n[-4:]}" if len(n) >= 4 else "••••"

    @property
    def label(self) -> str:
        bits = [b for b in (self.code, self.name) if b]
        head = " · ".join(bits) or self.id
        return f"{head} ({self.bank_name} {self.masked})" if self.bank_name else head


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


# ─── register ───────────────────────────────────────────────────────────────


def add(org_id: str, *, code: str, name: str, account_number: str,
        bank_name: str = "", project_code: str = "", purpose: str = "project",
        currency: str = "NGN", entity: str = "", notes: str = "") -> BankAccount:
    """Register an account.

    Refuses a duplicate account number, because two records for one account
    means payments split across both and a reconciliation that can never
    balance — the kind of fault that takes a day to find and five seconds to
    prevent.
    """
    org = store.require_org(org_id)
    number = _digits(account_number)
    if not number:
        raise BankAccountError("An account needs its number — it is what "
                               "identifies a statement.")
    if len(number) != 10:
        raise BankAccountError(
            f"'{account_number}' is not a 10-digit Nigerian account number.")
    if not (name or code).strip():
        raise BankAccountError("An account needs a name or a code so a person "
                               "can tell it from the other nineteen.")

    existing = find_by_number(org, number)
    if existing is not None:
        raise BankAccountError(
            f"That account is already registered as {existing.label}. Edit it "
            "rather than adding a second record — two records for one account "
            "splits its payments and the reconciliation can never balance.")

    acct = BankAccount(
        id=uuid.uuid4().hex[:12], org_id=org, code=code.strip().upper(),
        name=name.strip(), bank_name=bank_name.strip(), account_number=number,
        project_code=project_code.strip(), purpose=purpose, currency=currency,
        entity=entity.strip(), notes=notes,
        created_at=_now_iso(), updated_at=_now_iso())
    return _save(org, acct)


def _save(org_id: str, acct: BankAccount) -> BankAccount:
    acct.updated_at = _now_iso()
    store.get_store().put(org_id, _ACCOUNTS, acct.id, acct.model_dump())
    return acct


def get(org_id: str, account_id: str) -> Optional[BankAccount]:
    raw = store.get_store().get(store.require_org(org_id), _ACCOUNTS, account_id)
    return BankAccount.model_validate(raw) if raw else None


def list_accounts(org_id: str, *, active_only: bool = True) -> list[BankAccount]:
    org = store.require_org(org_id)
    out: list[BankAccount] = []
    for raw in store.get_store().list(org, _ACCOUNTS):
        try:
            a = BankAccount.model_validate(raw)
        except Exception:
            continue
        if active_only and not a.active:
            continue
        out.append(a)
    return sorted(out, key=lambda a: (a.entity, a.code or a.name))


def find_by_number(org_id: str, account_number: str) -> Optional[BankAccount]:
    want = _digits(account_number)
    if not want:
        return None
    return next((a for a in list_accounts(org_id, active_only=False)
                 if _digits(a.account_number) == want), None)


def find_by_code(org_id: str, code: str) -> Optional[BankAccount]:
    want = (code or "").strip().upper()
    if not want:
        return None
    return next((a for a in list_accounts(org_id, active_only=False)
                 if a.code.upper() == want), None)


def deactivate(org_id: str, account_id: str, *, reason: str = "") -> BankAccount:
    """Close an account without deleting it.

    History has to survive: last year's reconciliations reference it, and a
    closed account with payments against it is still evidence.
    """
    acct = get(org_id, account_id)
    if acct is None:
        raise BankAccountError(f"Account '{account_id}' not found.")
    acct.active = False
    if reason:
        acct.notes = f"{acct.notes}\nClosed: {reason}".strip()
    return _save(store.require_org(org_id), acct)


# ─── the rule that prevents the dangerous case ──────────────────────────────


def resolve_for_reconciliation(org_id: str,
                               account_id: Optional[str] = None,
                               *, detected_number: str = "") -> Optional[BankAccount]:
    """Decide which account a reconciliation is for, or refuse.

    Three cases, in order:

      * an account was named — use it
      * the statement itself identified one — use that
      * the organisation has exactly one account — no ambiguity, use it

    Otherwise raise. This is the whole point of the module: with twenty
    accounts, guessing produces a report that looks perfectly normal and is
    about the wrong account. Refusing costs one click.

    Returns None when the organisation has registered no accounts at all —
    single-account behaviour, unchanged, so nobody is forced to configure
    something they do not have.
    """
    org = store.require_org(org_id)
    accounts = list_accounts(org)

    if account_id:
        acct = get(org, account_id)
        if acct is None:
            raise BankAccountError(f"Bank account '{account_id}' not found.")
        return acct

    if detected_number:
        found = find_by_number(org, detected_number)
        if found is not None:
            return found
        if accounts:
            raise BankAccountError(
                f"This statement is for account ending {detected_number[-4:]}, "
                "which is not registered. Add it first — reconciling it against "
                "another account's payments would produce a clean-looking "
                "report about the wrong money.")

    if not accounts:
        return None                      # no register: single-account behaviour
    if len(accounts) == 1:
        return accounts[0]

    raise BankAccountError(
        f"This organisation has {len(accounts)} bank accounts. Say which one "
        "this statement is for — payments of the same amount and date exist in "
        "several of them, so choosing wrongly produces a report that looks "
        "correct and is not. Accounts: "
        + "; ".join(a.label for a in accounts[:6])
        + ("…" if len(accounts) > 6 else ""))


# ─── reading the account number out of a statement ──────────────────────────

# Bank exports put it in the preamble above the header, in a handful of shapes:
#   "Account Number:  101662027"   "A/C No: 0459639450"   "Account: 3012345678"
_ACCOUNT_PATTERNS = (
    re.compile(r"acc(?:oun)?t\s*(?:number|no\.?|#)?\s*[:\-]?\s*(\d{10})", re.I),
    re.compile(r"a/?c\s*(?:no\.?|number)?\s*[:\-]?\s*(\d{10})", re.I),
    re.compile(r"\b(\d{10})\b"),
)


def detect_account_number(text: str, *, max_chars: int = 4000) -> str:
    """Find the account number in a statement's preamble.

    Looks only at the top of the file: a ten-digit number further down is far
    more likely to be a transaction reference or a phone number than the
    account this statement belongs to.

    Returns "" when nothing is found, which is a normal outcome — some exports
    genuinely omit it, and the caller then asks a person.
    """
    head = (text or "")[:max_chars]
    for pattern in _ACCOUNT_PATTERNS[:2]:
        m = pattern.search(head)
        if m:
            return m.group(1)
    # Last resort: a bare 10-digit number, but only in the first few lines,
    # where a transaction row is very unlikely to have reached yet.
    early = "\n".join(head.splitlines()[:8])
    m = _ACCOUNT_PATTERNS[2].search(early)
    return m.group(1) if m else ""


def identify(org_id: str, statement_text: str) -> dict:
    """What account does this statement belong to? Answer, or say you cannot."""
    number = detect_account_number(statement_text)
    if not number:
        return {"detected": False, "account_number": "",
                "message": ("No account number found in the statement header. "
                            "Choose the account manually.")}
    acct = find_by_number(org_id, number)
    if acct is None:
        return {"detected": True, "account_number": f"••••{number[-4:]}",
                "account_id": "", "registered": False,
                "message": (f"This statement is for an account ending "
                            f"{number[-4:]}, which is not registered yet.")}
    return {"detected": True, "account_number": acct.masked,
            "account_id": acct.id, "registered": True,
            "account_label": acct.label, "project_code": acct.project_code,
            "message": f"Recognised as {acct.label}."}


# ─── the view finance actually wants ────────────────────────────────────────


def portfolio(org_id: str, period: Optional[str] = None) -> dict:
    """Every account, with the month's activity and whether it is reconciled.

    Twenty accounts reconciled by hand is the cost this replaces, so the
    honest measure of the feature is whether somebody can see, on one screen,
    which of the twenty are done and which are not. That is the thing a
    spreadsheet cannot give them.
    """
    import bank_reconciliation as _rec
    import disbursements as _disb

    org = store.require_org(org_id)
    accounts = list_accounts(org)
    runs = _rec.list_runs(org, period=period) if period else _rec.list_runs(org)
    by_account: dict[str, list] = {}
    for r in runs:
        by_account.setdefault(getattr(r, "account_id", "") or "", []).append(r)

    payments = _disb.list_disbursements(org, period=period) if period else []
    paid_by_account: dict[str, list] = {}
    for d in payments:
        paid_by_account.setdefault(getattr(d, "account_id", "") or "", []).append(d)

    rows = []
    for a in accounts:
        mine = by_account.get(a.id, [])
        latest = mine[0] if mine else None
        spent = paid_by_account.get(a.id, [])
        rows.append({
            "account_id": a.id, "code": a.code, "name": a.name,
            "label": a.label, "bank_name": a.bank_name, "masked": a.masked,
            "project_code": a.project_code, "purpose": a.purpose,
            "entity": a.entity, "currency": a.currency,
            "payments": len(spent),
            "value": round(sum(d.amount for d in spent), 2),
            "reconciled": bool(latest and latest.reconciled),
            "closed": bool(latest and latest.locked),
            "last_run": latest.period if latest else "",
            "unresolved": latest.unresolved_high if latest else 0,
        })

    return {
        "period": period or "",
        "accounts": len(accounts),
        "entities": sorted({a.entity for a in accounts if a.entity}),
        "banks": sorted({a.bank_name for a in accounts if a.bank_name}),
        "reconciled": len([r for r in rows if r["reconciled"]]),
        "outstanding": len([r for r in rows if not r["closed"]]),
        "rows": rows,
    }
