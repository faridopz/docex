"""
WO-48 — every payee's bank account is checked against the name the bank
holds, inside the payment request, with no extra step.

The standalone Bank Verify tool checked uploaded schedules; the people and
vendors typed into a payment request were never checked at all. The most
common accounts-payable fraud — a real vendor, a real invoice, a substituted
account number — walked straight past it.

The bank lookup is a provider behind one function. These tests stand in for
it, so they run with no key and no network, and prove the behaviour, not
Paystack.

Run: python test_payee_verification.py
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-payeecheck-")
os.environ["DOCEX_ORG"] = "pv"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import payee_verification as pv  # noqa: E402
import requisitions as rq  # noqa: E402

_passed = _failed = 0

# What "the bank" says each account is called.
BANK = {
    ("058", "0123456789"): "ACME SUPPLIES LIMITED",
    ("057", "0987654321"): "AISHA MUSA BELLO",
    ("058", "0111111111"): "JOHN OKAFOR",          # the substituted account
}
CALLS: list = []


def fake_resolve(account_number: str, bank_code: str):
    CALLS.append((bank_code, account_number))
    time.sleep(0.02)
    name = BANK.get((bank_code, account_number))
    return (name, None) if name else (None, "Could not resolve account name")


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _pc(req):
    return next((c for c in req.checks if c.code == "PAYEE_ACCOUNT_VERIFIED"), None)


def _vendor(org, name, acct, bank, amount=1000.0):
    return rq.create_requisition(org, submitted_by="u@t", department="program", vendor_name=name,
                                 amount=amount, vendor_account=acct, vendor_bank_name=bank)


def test_the_right_account_passes() -> None:
    print("\nName on the request matches the bank's name for that account")
    req = _vendor("pv", "Acme Supplies Ltd", "0123456789", "GTBank")
    c = _pc(req)
    check("checked", c is not None)
    check("passes", c and c.result == rq.CheckResult.PASS, str(c))


def test_a_substituted_account_is_flagged_by_name() -> None:
    print("\nReal vendor, someone else's account: the check names who actually gets paid")
    req = _vendor("pv", "Acme Supplies Ltd", "0111111111", "GTBank")
    c = _pc(req)
    check("flagged", c and c.result == rq.CheckResult.WARNING, str(c))
    check("says whose account it really is", c and "JOHN OKAFOR" in c.message, c.message if c else "")
    check("never shows the full account number", c and "0111111111" not in c.message, c.message if c else "")


def test_the_org_can_make_a_mismatch_block_payment() -> None:
    print("\nOrgs that want it can make a mismatch a blocking check")
    org_config.set_features("strict", payee_account_check=True, payee_check_blocks=True,
                            multi_payee_requisitions=True)
    req = _vendor("strict", "Acme Supplies Ltd", "0111111111", "GTBank")
    check("blocks (needs an override with a reason)", _pc(req).result == rq.CheckResult.FAIL, str(_pc(req)))


def test_a_batch_is_checked_person_by_person_and_quickly() -> None:
    print("\nA 60-person batch is checked in parallel and names only the problem rows")
    payees = [rq.Payee(name="Aisha Musa Bello", account_number="0987654321", bank_name="Zenith Bank",
                       amount=10.0) for _ in range(59)]
    payees.append(rq.Payee(name="Chinedu Eze", account_number="0111111111", bank_name="GTB", amount=10.0))
    CALLS.clear()
    t0 = time.time()
    req = rq.create_requisition("pv", submitted_by="u@t", department="program",
                                vendor_name="Workshop", amount=600.0, payees=payees)
    took = time.time() - t0
    c = _pc(req)
    check("flagged", c and c.result == rq.CheckResult.WARNING, str(c))
    check("names the one wrong row", c and "Chinedu Eze" in c.message and "Aisha" not in c.message,
          c.message if c else "")
    check("no account looked up twice (and none already known looked up at all)",
          len(CALLS) == len(set(CALLS)) and len(CALLS) <= 2, str(CALLS))
    check(f"fast (took {took:.2f}s)", took < 3.0)


def test_a_known_account_is_not_looked_up_twice() -> None:
    print("\nAn account checked recently is not looked up again")
    CALLS.clear()
    _vendor("pv", "Acme Supplies Ltd", "0123456789", "GTBank", amount=2000.0)
    check("served from the org's own recent checks", CALLS == [], str(CALLS))


def test_an_unknown_bank_is_said_plainly() -> None:
    print("\nA bank name nobody recognises is a warning that says so")
    req = _vendor("pv", "Acme Supplies Ltd", "0123456789", "Bank of Atlantis")
    c = _pc(req)
    check("warning", c and c.result == rq.CheckResult.WARNING)
    check("says the bank wasn't recognised", c and "recognis" in c.message.lower(), c.message if c else "")


def test_no_provider_means_a_single_clear_warning() -> None:
    print("\nNo verification service configured: one warning, not a wall of errors")
    saved = pv._resolve
    pv._resolve = None
    try:
        # An account never looked up before (a known one is served from the
        # org's recent checks, which is the point of keeping them).
        req = _vendor("pv", "New Vendor Ltd", "0222222222", "GTBank", amount=3000.0)
        c = _pc(req)
        check("warning", c and c.result == rq.CheckResult.WARNING, str(c))
        check("says checking isn't set up", c and "not set up" in c.message.lower(), c.message if c else "")
    finally:
        pv._resolve = saved


def test_flag_off_means_no_check_and_no_calls() -> None:
    print("\nFlag off: nothing is checked, nothing is called")
    CALLS.clear()
    req = _vendor("off", "Acme Supplies Ltd", "0123456789", "GTBank")
    check("no payee check", _pc(req) is None)
    check("no lookups", CALLS == [])


def test_bank_names_become_bank_codes() -> None:
    print("\nThe bank list offers one clean name per bank")
    opts = pv.bank_options()
    names = [o["name"] for o in opts]
    check("GTBank offered once", sum(1 for n in names if "Guaranty" in n or "GTB" in n) == 1, str(names[:8]))
    check("every option has a code", all(o["code"] for o in opts))
    check("'GTB', 'gtbank', 'Guaranty Trust Bank' are one bank",
          pv.bank_code("GTB") == pv.bank_code("gtbank") == pv.bank_code("Guaranty Trust Bank") == "058")
    wrong = [o for o in opts if pv.bank_code(o["name"]) != o["code"]]
    check("every name in the list is recognised when chosen", not wrong, str(wrong))


def test_the_form_can_check_an_account_as_it_is_typed() -> None:
    print("\nHTTP: the bank list, and a single-account check for the form")
    from fastapi.testclient import TestClient
    import api.main as m

    c = TestClient(m.app, raise_server_exceptions=False)
    PW = "correct-horse-battery"
    A.create_user("u@t", "User", PW, "program", "reviewer", org_id="pv")
    tok = c.post("/auth/login", json={"email": "u@t", "password": PW}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    r = c.get("/payee-check/banks", headers=H)
    check("bank list served", r.status_code == 200 and len(r.json()["banks"]) > 10, f"{r.status_code}")
    r = c.post("/payee-check/account", headers=H,
               json={"name": "Acme Supplies Ltd", "account_number": "0111111111", "bank": "GTBank"})
    check("mismatch reported with the bank's name",
          r.status_code == 200 and r.json()["status"] == "mismatch" and r.json()["bank_name_on_record"] == "JOHN OKAFOR",
          r.text[:200])
    org_config.set_features("pv", payee_account_check=False)
    try:
        r = c.get("/payee-check/banks", headers=H)
        check("check switched off: no bank list, the form is unchanged", r.status_code == 404, str(r.status_code))
    finally:
        org_config.set_features("pv", payee_account_check=True)


if __name__ == "__main__":
    print("WO-48 — payee bank accounts checked inside the request")
    pv._resolve = fake_resolve
    for org in ("pv", "off"):
        org_config.set_features(org, multi_payee_requisitions=True)
    org_config.set_features("pv", payee_account_check=True)
    test_the_right_account_passes()
    test_a_substituted_account_is_flagged_by_name()
    test_the_org_can_make_a_mismatch_block_payment()
    test_a_batch_is_checked_person_by_person_and_quickly()
    test_a_known_account_is_not_looked_up_twice()
    test_an_unknown_bank_is_said_plainly()
    test_no_provider_means_a_single_clear_warning()
    test_flag_off_means_no_check_and_no_calls()
    test_bank_names_become_bank_codes()
    test_the_form_can_check_an_account_as_it_is_typed()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
