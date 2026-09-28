"""
A "budget holder" step: the request goes first to the head of the
department that raised it — whichever department that is.

Research (28 Sep 2026: ActionAid, HIAS, Twaweza, MCLD, Humentum) found the
same first approval almost everywhere: the budget holder confirms the need
is real and the goods or services were delivered, BEFORE Finance checks
compliance. DOCex could only route a step to one fixed department, so an
organisation had to either send every request to one department's manager
or skip the check. `requester_department: true` on a step routes it to the
raiser's own department, request by request.

Run: python test_budget_holder_step.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-budgetholder-")
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
    "departments": [{"key": "program", "name": "Programmes"}, {"key": "hr", "name": "HR"},
                    {"key": "finance", "name": "Finance"}],
    "workflow": {"max_amount": 10_000_000, "steps": [
        {"key": "budget", "label": "Budget holder approval", "requester_department": True},
        {"key": "finance", "label": "Finance review", "department": "finance"},
    ]},
}

USERS = [
    ("amina@acme.org", "Amina", "program", "reviewer"),
    ("pm@acme.org", "Programme Manager", "program", "approver"),
    ("sam@acme.org", "Sam", "program", "reviewer"),
    ("hauwa@acme.org", "Hauwa", "hr", "reviewer"),
    ("hrhead@acme.org", "HR Head", "hr", "approver"),
    ("femi@acme.org", "Femi", "finance", "approver"),
]


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    return TestClient(m.app, raise_server_exceptions=False)


def _h(c, email):
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}


def _pending(c, email):
    return {r["ref"] for r in c.get("/requisitions/pending", headers=_h(c, email)).json()["requisitions"]}


def test_profile_with_a_budget_holder_step_is_valid() -> None:
    print("\nA step with requester_department needs no fixed department")
    rep = org_config.validate_profile(copy.deepcopy(PROFILE))
    check("profile valid", rep.ok, "; ".join(rep.errors))


def test_programme_request_goes_to_the_programme_manager() -> None:
    print("\nProgrammes raises → Programmes' approver has it first, not Finance, not HR")
    c = _client()
    r = c.post("/requisitions", headers=_h(c, "amina@acme.org"),
               data={"vendor_name": "Kano Printers", "amount": "80000", "submit": "true"}).json()
    check("with Programmes", r.get("current_department") == "program", str(r.get("current_department")))
    check("in the programme manager's queue", r["ref"] in _pending(c, "pm@acme.org"))
    check("not in Finance's queue yet", r["ref"] not in _pending(c, "femi@acme.org"))
    check("not in HR's queue", r["ref"] not in _pending(c, "hrhead@acme.org"))
    d = c.post(f"/requisitions/{r['id']}/decide", headers=_h(c, "femi@acme.org"), data={"decision": "approved"})
    check("Finance can't jump the budget holder", d.status_code in (400, 403), f"{d.status_code} {d.text[:120]}")
    d = c.post(f"/requisitions/{r['id']}/decide", headers=_h(c, "hrhead@acme.org"), data={"decision": "approved"})
    check("another department's head can't approve it", d.status_code in (400, 403), f"{d.status_code} {d.text[:120]}")
    d = c.post(f"/requisitions/{r['id']}/decide", headers=_h(c, "sam@acme.org"), data={"decision": "approved"})
    check("a fellow programme officer can't approve it", d.status_code == 403, f"{d.status_code} {d.text[:120]}")
    d = c.post(f"/requisitions/{r['id']}/decide", headers=_h(c, "pm@acme.org"),
               data={"decision": "approved", "notes": "Needed for the Kano training"})
    check("programme manager approves", d.status_code == 200, f"{d.status_code} {d.text[:160]}")
    check("now with Finance", d.json().get("current_department") == "finance", str(d.json().get("current_department")))
    check("and in Finance's queue", r["ref"] in _pending(c, "femi@acme.org"))


def test_hr_request_goes_to_the_hr_head() -> None:
    print("\nThe same step, raised from HR → HR's head")
    c = _client()
    r = c.post("/requisitions", headers=_h(c, "hauwa@acme.org"),
               data={"vendor_name": "Training venue", "amount": "60000", "submit": "true"}).json()
    check("with HR", r.get("current_department") == "hr", str(r.get("current_department")))
    check("in HR head's queue", r["ref"] in _pending(c, "hrhead@acme.org"))
    check("not in the programme manager's", r["ref"] not in _pending(c, "pm@acme.org"))


def test_a_budget_holder_cannot_approve_their_own_request() -> None:
    print("\nThe programme manager's own request still needs someone else")
    c = _client()
    r = c.post("/requisitions", headers=_h(c, "pm@acme.org"),
               data={"vendor_name": "Fuel", "amount": "20000", "submit": "true"}).json()
    d = c.post(f"/requisitions/{r['id']}/decide", headers=_h(c, "pm@acme.org"), data={"decision": "approved"})
    check("refused", d.status_code in (400, 403), f"{d.status_code} {d.text[:120]}")


def test_budget_holders_do_not_see_every_payment() -> None:
    print("\nA budget-holder step doesn't make every department part of the org-wide chain")
    c = _client()
    refs = {x["ref"] for x in c.get("/requisitions", headers=_h(c, "hrhead@acme.org")).json()["requisitions"]}
    everyone = {x["ref"] for x in c.get("/requisitions", headers=_h(c, "femi@acme.org")).json()["requisitions"]}
    check("HR head sees HR's requests only", refs and refs < everyone, f"{refs} vs {everyone}")


if __name__ == "__main__":
    print("Budget-holder step: the raiser's own department approves first")
    test_profile_with_a_budget_holder_step_is_valid()
    org_config.apply_profile(copy.deepcopy(PROFILE))
    for email, name, dept, role in USERS:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    test_programme_request_goes_to_the_programme_manager()
    test_hr_request_goes_to_the_hr_head()
    test_a_budget_holder_cannot_approve_their_own_request()
    test_budget_holders_do_not_see_every_payment()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
