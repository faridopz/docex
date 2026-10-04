"""
Expense claims: staff claim back what they spent.

What this prevents:
  * a claim paid without a receipt for each thing claimed;
  * a claimant typing a total that doesn't match their items;
  * a claim that bypasses the approval chain other payments go through;
  * an advance settled twice, or someone settling a colleague's advance;
  * paying the whole claim when an advance already covered part of it
    (the advance would be paid out twice);
  * an advance left "outstanding" after its spending was approved — which
    blocks the person's next payment for no reason;
  * a claim the advance fully covered sitting in Finance's "to pay" list.

Run: python test_expense_claims.py
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-claims-")
os.environ["DOCEX_ORG"] = "acme"
os.environ["DOCEX_ATTACHMENTS_DIR"] = str(Path(_TMP) / "att")
os.environ.pop("SUPABASE_URL", None)

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import advances  # noqa: E402
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

ITEMS = [{"description": "Taxi to Zaria clinic", "unit_cost": 6000, "date": "2026-09-14", "budget_line": "L1"},
         {"description": "Lunch for 4 volunteers", "unit_cost": 8000, "date": "2026-09-14"},
         {"description": "Printing referral forms", "unit_cost": 11000, "date": "2026-09-15"}]


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}
    return c, h


def _claim(c, h, items=ITEMS, *, advance_id="", who="amina@acme.org", amount="999999"):
    r = c.post("/requisitions", headers=h(who), data={
        "kind": "expense_claim", "vendor_name": "Someone Else", "amount": amount,
        "project_code": "TB-26", "description": "Field visit, Zaria", "budget_lines": json.dumps(items),
        "vendor_account": "0123456789", "vendor_bank_name": "GTBank",
        "advance_id": advance_id, "submit": "false"})
    assert r.status_code == 200, r.text
    return r.json()


def _receipt(c, h, rid, n, who="amina@acme.org"):
    return c.post(f"/requisitions/{rid}/attachments", headers=h(who), data={"document_type": f"item-{n}"},
                  files={"file": (f"receipt{n}.pdf", b"%PDF-1.4 receipt", "application/pdf")})


def _codes(rid, code):
    return [x for x in rq.get_requisition("acme", rid).checks if x.code == code]


def _approve_all(rid):
    rq.decide("acme", rid, decision=rq.Decision.APPROVED, actor="pm@acme.org", department="program")
    return rq.decide("acme", rid, decision=rq.Decision.APPROVED, actor="femi@acme.org", department="finance")


def test_a_claim_is_its_items(c, h) -> None:
    print("\nA claim is its items, and the payee is the claimant")
    body = _claim(c, h)
    check("the total is the items, not what the form said (₦25,000, not ₦999,999)",
          body["amount"] == 25_000 and body["claim_total"] == 25_000, str(body["amount"]))
    check("the payee is the claimant, by their account name", body["vendor_name"] == "Amina Bello", body["vendor_name"])
    check("it is recorded as an expense claim", body["kind"] == "expense_claim")
    r = c.post(f"/requisitions/{body['id']}/submit", headers=h("amina@acme.org"))
    rec = _codes(body["id"], "ITEM_RECEIPTS")
    check("sent without receipts: the check fails and names the items",
          rec and rec[0].result == rq.CheckResult.FAIL and "1, 2, 3" in rec[0].message,
          f"{r.status_code} {[x.message for x in rec]}")
    return body


def test_each_item_needs_its_receipt(c, h) -> None:
    print("\nOne receipt per item")
    body = _claim(c, h)
    for n in (1, 2):
        check(f"receipt {n} attaches", _receipt(c, h, body["id"], n).status_code == 200)
    r = c.post(f"/requisitions/{body['id']}/submit", headers=h("amina@acme.org"))
    rec = _codes(body["id"], "ITEM_RECEIPTS")[0]
    check("two of three receipts still fails, naming item 3",
          rec.result == rq.CheckResult.FAIL and "item 3" in rec.message, rec.message)
    rq.decide("acme", body["id"], decision=rq.Decision.RETURNED, actor="pm@acme.org", department="program",
              notes="Receipt for printing missing")
    _receipt(c, h, body["id"], 3)
    r = c.post(f"/requisitions/{body['id']}/resubmit", headers=h("amina@acme.org"), data={"notes": "added"})
    rec = _codes(body["id"], "ITEM_RECEIPTS")[0]
    check("with all three it passes", rec.result == rq.CheckResult.PASS, f"{r.status_code} {rec.message}")
    after = _approve_all(body["id"])
    check("it goes through the same approval chain as any payment", after.status == rq.ReqStatus.APPROVED,
          after.status.value)
    t = rq.mark_paid("acme", body["id"], actor="femi@acme.org", bank_reference="FT-REIMB")
    check("Finance reimburses it like any payment", t.amount == 25_000 and t.vendor_name == "Amina Bello")


def test_a_claim_against_an_advance(c, h) -> None:
    print("\nSettling an advance: only the difference is paid")
    adv = advances.issue("acme", staff_id="amina@acme.org", amount=20_000, purpose="Zaria trip",
                         project_code="TB-26")
    body = _claim(c, h, advance_id=adv.id)
    check("₦25,000 spent against a ₦20,000 advance: ₦5,000 to pay", body["amount"] == 5_000
          and body["claim_total"] == 25_000, str(body))
    for n in (1, 2, 3):
        _receipt(c, h, body["id"], n)
    c.post(f"/requisitions/{body['id']}/submit", headers=h("amina@acme.org"))
    ac = _codes(body["id"], "CLAIM_ADVANCE")[0]
    check("the check says what happens to the advance", ac.result == rq.CheckResult.PASS
          and "5,000.00 to reimburse" in ac.message, ac.message)
    second = _claim(c, h, advance_id=adv.id)
    for n in (1, 2, 3):
        _receipt(c, h, second["id"], n)
    c.post(f"/requisitions/{second['id']}/submit", headers=h("amina@acme.org"))
    check("a second claim on the same advance fails",
          _codes(second["id"], "CLAIM_ADVANCE")[0].result == rq.CheckResult.FAIL)
    rq.decide("acme", second["id"], decision=rq.Decision.DECLINED, actor="pm@acme.org", department="program", notes="dup")
    _approve_all(body["id"])
    a = advances.get("acme", adv.id)
    check("final approval retires the advance with the approved spend", not a.open and a.spent == 25_000
          and a.direction == "reimburse", f"{a.status} {a.spent} {a.direction}")
    req = rq.get_requisition("acme", body["id"])
    check("…and the claim waits for the ₦5,000 to be paid", req.status == rq.ReqStatus.APPROVED)
    check("the retirement is on the claim's audit trail", any(e.event == "advance_retired" for e in req.audit_log))


def test_an_advance_that_covered_everything(c, h) -> None:
    print("\nSpent less than the advance: nothing to pay, the balance is owed back")
    adv = advances.issue("acme", staff_id="amina@acme.org", amount=40_000, purpose="Kano trip")
    body = _claim(c, h, advance_id=adv.id)
    check("nothing to pay", body["amount"] == 0, str(body["amount"]))
    for n in (1, 2, 3):
        _receipt(c, h, body["id"], n)
    r = c.post(f"/requisitions/{body['id']}/submit", headers=h("amina@acme.org"))
    check("a claim that pays nothing can still be sent", r.status_code == 200, r.text[:160])
    check("the check says ₦15,000 is to be returned",
          "15,000.00 to be returned" in _codes(body["id"], "CLAIM_ADVANCE")[0].message)
    after = _approve_all(body["id"])
    check("approved, it closes as settled — never in Finance's to-pay list",
          after.status == rq.ReqStatus.SETTLED, after.status.value)
    a = advances.get("acme", adv.id)
    check("the advance is retired, with ₦15,000 to recover", not a.open and a.direction == "recover"
          and a.balance == 15_000, f"{a.direction} {a.balance}")
    try:
        rq.mark_paid("acme", body["id"], actor="femi@acme.org")
        check("a settled claim can't be marked paid", False)
    except rq.RequisitionError:
        check("a settled claim can't be marked paid", True)


def test_someone_elses_advance(c, h) -> None:
    print("\nYou can only settle your own advance")
    adv = advances.issue("acme", staff_id="pm@acme.org", amount=10_000, purpose="x")
    body = _claim(c, h, advance_id=adv.id)
    c.post(f"/requisitions/{body['id']}/submit", headers=h("amina@acme.org"))
    check("a claim naming a colleague's advance fails",
          _codes(body["id"], "CLAIM_ADVANCE")[0].result == rq.CheckResult.FAIL)


def test_switched_off(c, h) -> None:
    print("\nAn organisation without expense claims")
    org_config.set_features("acme", expense_claims=False)
    r = c.post("/requisitions", headers=h("amina@acme.org"), data={
        "kind": "expense_claim", "vendor_name": "x", "amount": "1", "budget_lines": json.dumps(ITEMS)})
    check("can't raise one", r.status_code == 400 and "not switched on" in r.text, r.text[:120])
    org_config.set_features("acme", expense_claims=True)


if __name__ == "__main__":
    print("Expense claims")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    org_config.set_features("acme", expense_claims=True, requisition_attachments=True, advance_retirement=True)
    for email, name, dept, role in [("amina@acme.org", "Amina Bello", "program", "viewer"),
                                    ("pm@acme.org", "PM", "program", "approver"),
                                    ("femi@acme.org", "Femi", "finance", "approver")]:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    c, h = _client()
    test_a_claim_is_its_items(c, h)
    test_each_item_needs_its_receipt(c, h)
    test_a_claim_against_an_advance(c, h)
    test_an_advance_that_covered_everything(c, h)
    test_someone_elses_advance(c, h)
    test_switched_off(c, h)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
