"""
Only the people who handle money may record that a payment left the bank.

Found recording the demo walkthrough (29 Sep 2026): the pay route allowed any
approver or admin. With the budget-holder step, every department now has an
approver, so a Programme Manager could open an approved request and mark it
paid, freezing the transaction record with a bank reference they cannot know.
The screen also showed "Mark as paid" to a Finance officer whose role the
server then refused. The rule is now the one the payee schedule already
uses: the organisation's finance department(s), with approver authority, or
an admin, and the screen shows the button only to them.

Run: python test_who_can_pay.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-whopays-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

PW = "correct-horse-battery"
_passed = _failed = 0


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
    "workflow": {"max_amount": 10_000_000, "steps": [
        {"key": "budget", "label": "Budget holder", "requester_department": True},
        {"key": "finance", "label": "Finance review", "department": "finance"}]},
}


def test_only_money_handlers_record_payment() -> None:
    print("\nAn approved request: who may mark it paid")
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}

    r = rq.create_requisition("acme", submitted_by="amina@acme.org", department="program",
                              vendor_name="Kano Printers", amount=50_000)
    rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="pm@acme.org", department="program")
    rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="femi@acme.org", department="finance")
    for email, who, ok in [("pm@acme.org", "the Programme Manager (an approver, not Finance)", False),
                           ("ngozi@acme.org", "a Finance officer without approver authority", False)]:
        res = c.post(f"/requisitions/{r.id}/pay", headers=h(email), data={"bank_reference": "FT1"})
        check(f"{who}: refused", res.status_code == 403, f"{res.status_code} {res.text[:120]}")
    perms = c.get("/requisitions/document-permissions", headers=h("pm@acme.org")).json()
    check("the screen is told not to offer it to the Programme Manager", perms.get("can_pay") is False, str(perms))
    perms = c.get("/requisitions/document-permissions", headers=h("femi@acme.org")).json()
    check("…and to offer it to the Finance approver", perms.get("can_pay") is True, str(perms))
    res = c.post(f"/requisitions/{r.id}/pay", headers=h("femi@acme.org"), data={"bank_reference": "FT1"})
    check("the Finance approver records it", res.status_code == 200, f"{res.status_code} {res.text[:160]}")


if __name__ == "__main__":
    print("Recording a payment is Finance's job")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    for email, name, dept, role in [("amina@acme.org", "Amina", "program", "reviewer"),
                                    ("pm@acme.org", "PM", "program", "approver"),
                                    ("ngozi@acme.org", "Ngozi", "finance", "reviewer"),
                                    ("femi@acme.org", "Femi", "finance", "approver")]:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    test_only_money_handlers_record_payment()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
