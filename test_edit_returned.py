"""
A returned payment request can be corrected and sent again — and the audit
trail says exactly what changed, from what, to what.

Found in the live walkthrough on 28 Sep 2026: "Return for fixes" was a dead
end. The screen offered only "Resubmit", which sent the request back
unchanged, so "add the project code" or "the amount is wrong" could not be
acted on. The engine could already edit a returned request; nothing on the
screen called it. And the audit line it wrote said only which fields
changed ("amount"), not the figures, which is the first thing an auditor
asks when an amount moves between approvals.

Run: python test_edit_returned.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-editret-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_passed = _failed = 0
PW = "correct-horse-battery"


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


PROFILE = {
    "org_id": "acme", "currency": "NGN",
    "departments": [{"key": "program", "name": "Programmes"}, {"key": "finance", "name": "Finance"}],
    "workflow": {"max_amount": 10_000_000,
                 "steps": [{"key": "finance", "label": "Finance review", "department": "finance"}]},
}


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    return TestClient(m.app, raise_server_exceptions=False)


def _h(c, email):
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}


def test_correct_and_send_again() -> None:
    print("\nReturned → corrected → sent again, with a readable audit line")
    c = _client()
    S, F = _h(c, "amina@acme.org"), _h(c, "femi@acme.org")
    r = c.post("/requisitions", headers=S, data={"vendor_name": "Kano Printers", "amount": "120000",
                                                 "description": "Manuals", "submit": "true"}).json()
    c.post(f"/requisitions/{r['id']}/decide", headers=F, data={"decision": "returned", "notes": "Wrong amount, add the project"})
    r2 = c.put(f"/requisitions/{r['id']}/draft", headers=S,
               data={"amount": "95000", "project_code": "P-101"})
    check("edit accepted", r2.status_code == 200, f"{r2.status_code} {r2.text[:150]}")
    body = r2.json()
    check("amount changed", body["amount"] == 95000, str(body.get("amount")))
    check("still returned until it is sent", body["status"] == "returned", body["status"])
    line = next((e for e in reversed(body["audit_log"]) if e["event"] == "draft_edited"), None)
    detail = (line or {}).get("detail", "")
    check("audit says it was corrected after a return", "returned" in detail.lower(), detail)
    check("…and the figures, old → new", "120,000" in detail and "95,000" in detail, detail)
    check("…and the project code, from blank", "P-101" in detail, detail)
    r3 = c.post(f"/requisitions/{r['id']}/resubmit", headers=S, data={"notes": "Fixed amount and project"})
    check("sent again", r3.status_code == 200 and r3.json()["status"] == "in_review",
          f"{r3.status_code} {r3.text[:150]}")
    check("back at the first step", r3.json()["current_step"] == "finance", str(r3.json().get("current_step")))


def test_bank_account_change_is_recorded_without_printing_it() -> None:
    print("\nA changed bank account is recorded as changed; the digits aren't copied into the log")
    c = _client()
    S, F = _h(c, "amina@acme.org"), _h(c, "femi@acme.org")
    r = c.post("/requisitions", headers=S, data={"vendor_name": "Musa Transport", "amount": "50000",
                                                 "vendor_account": "0123456789", "submit": "true"}).json()
    c.post(f"/requisitions/{r['id']}/decide", headers=F, data={"decision": "returned", "notes": "account?"})
    body = c.put(f"/requisitions/{r['id']}/draft", headers=S, data={"vendor_account": "9876543210"}).json()
    detail = next(e for e in reversed(body["audit_log"]) if e["event"] == "draft_edited")["detail"]
    check("bank account named as changed", "account" in detail.lower(), detail)
    check("full numbers not written into the log", "9876543210" not in detail and "0123456789" not in detail, detail)
    check("last four shown so it can be traced", "3210" in detail, detail)


if __name__ == "__main__":
    print("Correcting a returned request")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    for email, name, dept, role in [("amina@acme.org", "Amina", "program", "reviewer"),
                                    ("femi@acme.org", "Femi", "finance", "approver")]:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    test_correct_and_send_again()
    test_bank_account_change_is_recorded_without_printing_it()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
