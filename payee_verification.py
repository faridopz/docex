"""
payee_verification.py — is this account really in this person's name?

Every payee on a payment request — the one vendor, or each of a hundred
workshop participants — is looked up with the bank and the name the bank
holds is compared with the name on the request. The result is ONE policy
check on the request, so it sits with the others: no extra step, no separate
upload, nothing for the submitter to remember.

Why it matters: the most common accounts-payable fraud is a real vendor, a
real invoice and a substituted account number. Every other check passes.
The bank's own name for the account is the evidence against it.

DETERMINISTIC. The lookup returns a name; the comparison is the same scored
name match bank_verify.py already uses (typo-tolerant, prefix-attack
resistant). No model is involved.

PROVIDER. `_resolve(account_number, bank_code) -> (name | None, error | None)`
is the only place a bank is contacted. In Nigeria that is Paystack's account
resolution, which is free. Elsewhere, or before a key is configured, it is
None and the check says plainly that checking is not set up — a warning,
never a block, so an organisation without a provider is never stopped.

CACHE. A successful lookup is kept, per organisation, for 30 days: a vendor
paid monthly is looked up once a month, not on every request.

Account numbers are never shown in full in any message.
"""
from __future__ import annotations

import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import store

_CACHE = "payee_account_checks"
_CACHE_DAYS = 30
_WORKERS = 8
_MAX_LISTED = 5          # problem rows named in the message before "and N more"


def _paystack_resolve(account_number: str, bank_code: str):
    import bank_verify
    return bank_verify.resolve_account(account_number, bank_code)


# None = no provider configured. Replaced in tests with a stand-in.
_resolve: Optional[Callable] = (
    _paystack_resolve if (os.environ.get("PAYSTACK_SECRET_KEY") or "").strip() else None
)


# ─── banks ───────────────────────────────────────────────────────────────────


def _codes() -> dict[str, str]:
    import bank_verify
    return bank_verify.BANK_CODES


def bank_code(name: str) -> Optional[str]:
    """'GTB', 'gtbank', 'Guaranty Trust Bank' → '058'. None if unrecognised."""
    cleaned = " ".join((name or "").lower().split())
    if not cleaned:
        return None
    if cleaned.isdigit():
        return cleaned
    code = _codes().get(cleaned)
    if code:
        return code
    # The list's own names, e.g. "Guaranty Trust Bank (GTBank)", must resolve
    # when chosen — so a name picked from the dropdown is never "unrecognised".
    return next((o["code"] for o in bank_options() if o["name"].lower() == cleaned), None)


def bank_options() -> list[dict]:
    """One clean entry per bank for a dropdown — the longest alias, title-cased.

    A dropdown instead of free text is what makes "GTB" and "Guaranty Trust
    Bank" the same bank, which a lookup (and a bulk-upload file) needs.
    """
    by_code: dict[str, str] = {}
    for alias, code in _codes().items():
        if len(alias) > len(by_code.get(code, "")):
            by_code[code] = alias
    special = {"058": "Guaranty Trust Bank (GTBank)", "033": "United Bank for Africa (UBA)",
               "214": "First City Monument Bank (FCMB)", "011": "First Bank of Nigeria"}
    out = [{"code": code, "name": special.get(code) or " ".join(w.capitalize() for w in alias.split())}
           for code, alias in by_code.items()]
    return sorted(out, key=lambda o: o["name"])


# ─── one account ─────────────────────────────────────────────────────────────


def _mask(account: str) -> str:
    digits = "".join(ch for ch in account or "" if ch.isdigit())
    return f"••••{digits[-4:]}" if len(digits) >= 4 else "••••"


def _cached(org: str, code: str, account: str) -> Optional[str]:
    raw = store.get_store().get(org, _CACHE, f"{code}-{account}")
    if not raw:
        return None
    try:
        when = dt.datetime.fromisoformat(raw.get("checked_at", ""))
    except ValueError:
        return None
    if dt.datetime.now(dt.timezone.utc) - when > dt.timedelta(days=_CACHE_DAYS):
        return None
    return raw.get("name") or None


def check_account(org_id: str, *, name: str, account_number: str, bank: str) -> dict:
    """Look one account up and compare names.

    status: verified | warning | mismatch | unverifiable | unknown_bank | not_configured
    """
    org = store.require_org(org_id)
    account = "".join(ch for ch in account_number or "" if ch.isdigit())
    code = bank_code(bank)
    base = {"account": _mask(account), "bank": bank, "name": name,
            "bank_name_on_record": None, "score": None}
    if not code:
        return {**base, "status": "unknown_bank",
                "message": f"The bank '{bank or '(blank)'}' wasn't recognised — choose it from the list."}
    if len(account) != 10:
        return {**base, "status": "unverifiable",
                "message": f"{_mask(account)} is not a 10-digit account number."}

    on_record = _cached(org, code, account)
    if on_record is None:
        if _resolve is None:
            return {**base, "status": "not_configured",
                    "message": "Bank account checking is not set up for this organisation."}
        on_record, error = _resolve(account, code)
        if not on_record:
            return {**base, "status": "unverifiable",
                    "message": f"The bank could not confirm {_mask(account)} at {bank}: {error or 'no name returned'}."}
        store.get_store().put(org, _CACHE, f"{code}-{account}", {
            "name": on_record, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()})

    import bank_verify
    score = bank_verify._name_match_score(name or "", on_record)
    verdict = bank_verify._classify_match(score)
    return {**base, "status": verdict, "bank_name_on_record": on_record, "score": score,
            "message": ("" if verdict == "verified" else
                        f"{_mask(account)} at {bank} is in the name of {on_record}, not '{name}'.")}


# ─── a whole requisition ─────────────────────────────────────────────────────


def check_requisition(org_id: str, req) -> Optional[object]:
    """The PAYEE_ACCOUNT_VERIFIED policy check for a requisition, or None.

    None when there is nothing to check (no account given) — a check that
    says "nothing checked" on every cash advance is noise.
    """
    import org_config
    import requisitions as rq

    org = store.require_org(org_id)
    if not org_config.feature_enabled(org, "payee_account_check"):
        return None

    rows = ([(p.name, p.account_number, p.bank_name) for p in req.payees]
            if req.payees else
            [(req.vendor_name, req.vendor_account, req.vendor_bank_name)])
    rows = [r for r in rows if (r[1] or "").strip()]
    if not rows:
        return None

    # Each distinct account once, in parallel: a 100-person batch is mostly
    # the same handful of lookups repeated, and each lookup is a network call.
    distinct: dict[tuple, dict] = {}
    keys = []
    for name, acct, bank in rows:
        k = (bank_code(bank) or bank, "".join(ch for ch in acct if ch.isdigit()))
        keys.append(k)
        distinct.setdefault(k, {"name": name, "acct": acct, "bank": bank})
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {k: pool.submit(check_account, org, name=v["name"], account_number=v["acct"], bank=v["bank"])
                   for k, v in distinct.items()}
        looked_up = {k: f.result() for k, f in futures.items()}

    results = []
    for (name, acct, bank), k in zip(rows, keys):
        r = dict(looked_up[k])
        if r.get("bank_name_on_record") and r["status"] in ("verified", "warning", "mismatch"):
            # Same account, different name on this row: score THIS row's name.
            import bank_verify
            score = bank_verify._name_match_score(name or "", r["bank_name_on_record"])
            r["status"] = bank_verify._classify_match(score)
            r["name"] = name
            r["message"] = ("" if r["status"] == "verified" else
                            f"{r['account']} at {bank} is in the name of {r['bank_name_on_record']}, not '{name}'.")
        results.append(r)

    if all(r["status"] == "not_configured" for r in results):
        return rq.PolicyCheck(
            code="PAYEE_ACCOUNT_VERIFIED", name="Bank account in the payee's name",
            result=rq.CheckResult.WARNING, policy_value="bank's name matches the payee",
            actual_value="not checked",
            message="Bank account checking is not set up for this organisation, so no account was checked.")

    problems = [r for r in results if r["status"] != "verified"]
    blocks = org_config.feature_enabled(org, "payee_check_blocks")
    mismatch = any(r["status"] == "mismatch" for r in problems)
    if not problems:
        result = rq.CheckResult.PASS
        message = (f"All {len(results)} payees' accounts are in their own names."
                   if len(results) > 1 else "The account is in the payee's name.")
    else:
        result = rq.CheckResult.FAIL if (blocks and mismatch) else rq.CheckResult.WARNING
        listed = "; ".join(f"{r['name']}: {r['message']}" if len(results) > 1 else r["message"]
                           for r in problems[:_MAX_LISTED])
        more = len(problems) - _MAX_LISTED
        message = (f"{len(problems)} of {len(results)} to check. " if len(results) > 1 else "") + listed \
            + (f" …and {more} more." if more > 0 else "")
    return rq.PolicyCheck(
        code="PAYEE_ACCOUNT_VERIFIED", name="Bank account in the payee's name",
        result=result, policy_value="bank's name matches the payee",
        actual_value=f"{len(results) - len(problems)} of {len(results)} confirmed",
        message=message)
