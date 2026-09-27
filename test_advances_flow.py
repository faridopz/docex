"""
Paying an advance starts its retirement clock — nobody re-types it.

The advance engine (ageing, blocking the next payment, salary recovery) was
built and tested, but nothing fed it: paying an advance request never created
an advance. Unless finance re-entered every advance by hand, the clock never
started and the whole ladder sat idle.

Which categories are advances, and which run the clock from the end of a trip,
are each organisation's own settings (NEEM: "advance" from payment, "dsa" from
the end of the trip — their slide 10). Nothing here is one client's process.

Run: python test_advances_flow.py
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-advflow-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import advances as adv  # noqa: E402
import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_passed = _failed = 0
ORG = "acme"
PW = "correct-horse-battery"


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _setup():
    org_config.set_features(ORG, advance_retirement=True)
    adv.set_policy(ORG, adv.AdvancePolicy(
        enabled=True, retirement_days=7, working_days=5, use_working_days=True,
        open_for_categories=["advance", "dsa"], activity_end_categories=["dsa"]))
    wf = rq.get_workflow(ORG)
    wf.allowed_categories = ["advance", "dsa", "fuel"]
    rq.set_workflow(ORG, wf)
    A.create_user("amina@acme.org", "Amina Bello", PW, "program", "reviewer", org_id=ORG)
    A.create_user("femi@acme.org", "Femi Finance", PW, "finance", "approver", org_id=ORG)
    A.create_user("tunde@acme.org", "Tunde Ops", PW, "program", "reviewer", org_id=ORG)


def _paid(category, raiser="amina@acme.org", amount=50000.0, activity_end=""):
    r = rq.create_requisition(ORG, submitted_by=raiser, department="program",
                              vendor_name="Amina Bello", amount=amount, category=category,
                              project_code="P1", activity_end=activity_end)
    raw = store.get_store().get(ORG, "requisitions", r.id)
    raw["status"] = "approved"
    store.get_store().put(ORG, "requisitions", r.id, raw)
    rq.mark_paid(ORG, r.id, actor="femi@acme.org")
    return rq.get_requisition(ORG, r.id)


def _opened_for(req):
    return [a for a in adv.list_advances(ORG) if a.source_ref == req.ref]


def test_paying_an_advance_opens_it() -> None:
    print("\nAn 'advance' request, paid: its advance exists, with a clock, for the person who raised it")
    req = _paid("advance")
    opened = _opened_for(req)
    check("one advance opened", len(opened) == 1, str(len(opened)))
    a = opened[0] if opened else None
    check("for the person who raised it, by name", a and a.staff_id == "amina@acme.org"
          and a.staff_name == "Amina Bello", str(a and (a.staff_id, a.staff_name)))
    check("for the amount paid", a and a.amount == 50000.0)
    check("due 5 working days from today",
          a and a.due_at == adv.add_working_days(dt.date.today(), 5).isoformat(), a and a.due_at)
    check("the request's own trail says so",
          any(e.event == "advance_opened" and a.ref in e.detail for e in req.audit_log), "")
    check("and the trail still verifies", rq.verify_audit_chain(req))


def test_dsa_counts_from_the_end_of_the_trip() -> None:
    print("\nDSA: the clock starts when the trip ends, not when it's paid")
    end = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    req = _paid("dsa", activity_end=end)
    a = _opened_for(req)[0]
    check("due 5 working days after the trip",
          a.due_at == adv.add_working_days(dt.date.fromisoformat(end), 5).isoformat(), a.due_at)


def test_dsa_without_a_trip_end_is_warned_before_approval() -> None:
    print("\nDSA with no trip end date: a warning while it can still be fixed")
    r = rq.create_requisition(ORG, submitted_by="amina@acme.org", department="program",
                              vendor_name="Amina Bello", amount=1000.0, category="dsa")
    c = next((c for c in r.checks if c.code == "TRIP_END_DATE"), None)
    check("warned", c is not None and c.result == rq.CheckResult.WARNING, str(c))
    r2 = rq.create_requisition(ORG, submitted_by="amina@acme.org", department="program",
                               vendor_name="Amina Bello", amount=1000.0, category="fuel")
    check("not on other categories", not any(c.code == "TRIP_END_DATE" for c in r2.checks))


def test_other_categories_open_nothing() -> None:
    print("\nFuel is not an advance")
    req = _paid("fuel", amount=2000.0)
    check("nothing opened", _opened_for(req) == [])


def test_flag_off_opens_nothing() -> None:
    print("\nAdvance retirement off: paying opens nothing")
    org_config.set_features(ORG, advance_retirement=False)
    try:
        req = _paid("advance", amount=3000.0)
        check("nothing opened", _opened_for(req) == [])
    finally:
        org_config.set_features(ORG, advance_retirement=True)


def test_an_overdue_advance_blocks_the_next_request() -> None:
    print("\nOnce it's overdue, the same person's next request is blocked")
    req = _paid("advance", raiser="tunde@acme.org", amount=7000.0)
    a = _opened_for(req)[0]
    raw = store.get_store().get(ORG, adv._ADVANCES, a.id)
    raw["due_at"] = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    store.get_store().put(ORG, adv._ADVANCES, a.id, raw)
    nxt = rq.create_requisition(ORG, submitted_by="tunde@acme.org", department="program",
                                vendor_name="Hotel", amount=100.0, category="fuel")
    c = next((c for c in nxt.checks if c.code == "ADVANCE_OUTSTANDING"), None)
    check("blocked, naming the advance", c is not None and c.result == rq.CheckResult.FAIL
          and a.ref in (c.actual_value or "") + c.message, str(c))


def test_http_staff_see_their_own_finance_sees_all() -> None:
    print("\nHTTP: staff see only their own advances and cannot settle them; finance can")
    from fastapi.testclient import TestClient
    import api.main as m

    c = TestClient(m.app, raise_server_exceptions=False)

    def login(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}

    amina, femi = login("amina@acme.org"), login("femi@acme.org")
    mine = c.get("/advances", headers=amina).json()["advances"]
    check("staff list is only their own", mine and all(a["staff_id"] == "amina@acme.org" for a in mine),
          str({a["staff_id"] for a in mine}))
    ag = c.get("/advances/aging", headers=amina).json()
    check("staff overdue list is only their own", all(r["staff_id"] == "amina@acme.org" for r in ag["rows"]),
          str({r["staff_id"] for r in ag["rows"]}))
    everyone = c.get("/advances", headers=femi).json()["advances"]
    check("finance sees everyone's", {a["staff_id"] for a in everyone} >= {"amina@acme.org", "tunde@acme.org"})

    target = mine[0]["id"]
    r = c.post(f"/advances/{target}/retire", headers=amina, data={"spent": "50000"})
    check("staff cannot mark their own advance retired", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
    r = c.post(f"/advances/{target}/retire", headers=femi, data={"spent": "45000"})
    check("finance can", r.status_code == 200 and r.json()["status"] != "outstanding",
          f"{r.status_code} {r.text[:160]}")
    own = adv.issue(ORG, staff_id="femi@acme.org", staff_name="Femi Finance", amount=7000.0,
                    purpose="field trip")
    r = c.post(f"/advances/{own.id}/retire", headers=femi, data={"spent": "7000"})
    check("but not their own", r.status_code == 403, f"{r.status_code} {r.text[:120]}")


if __name__ == "__main__":
    print("Advances open themselves when paid")
    _setup()
    test_paying_an_advance_opens_it()
    test_dsa_counts_from_the_end_of_the_trip()
    test_dsa_without_a_trip_end_is_warned_before_approval()
    test_other_categories_open_nothing()
    test_flag_off_opens_nothing()
    test_an_overdue_advance_blocks_the_next_request()
    test_http_staff_see_their_own_finance_sees_all()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
