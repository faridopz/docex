"""
Whose record is it? Vendors' bank details, field receipts, timesheets,
the old pipeline, advances, and the very first admin account.

Found in the 30 Sep 2026 security audit:
  * H1  the vendor register returned full bank account numbers to everyone;
  * H5  in the old transactions pipeline one Programmes approver could take a
        ₦5M item to "paid" alone, and a viewer could sign a note "The ED";
  * H6  a viewer uploaded a flagged ₦999,999 receipt and approved it himself;
  * H7  a viewer overwrote a colleague's timesheet hours, and any reviewer in
        any department could approve one (timesheets decide which donor pays
        whose salary);
  * H8  on an empty live instance, whoever registered first became admin;
  * M4  any department could read another's inbox by asking for it;
  * L3  anyone could learn whether a colleague had an overdue advance.

Each check names the failure it prevents. Run: python test_record_ownership.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-owner-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402

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
    "departments": [{"key": "program", "name": "Programmes"},
                    {"key": "finance", "name": "Finance"},
                    {"key": "ed", "name": "Executive Director"}],
    "workflow": {"max_amount": 10_000_000, "steps": [
        {"key": "budget", "label": "Budget holder", "requester_department": True},
        {"key": "finance", "label": "Finance review", "department": "finance"}]},
}

USERS = [("amina@acme.org", "Amina", "program", "viewer"),
         ("pm@acme.org", "PM", "program", "approver"),
         ("ngozi@acme.org", "Ngozi", "finance", "reviewer"),
         ("femi@acme.org", "Femi", "finance", "approver"),
         ("ed@acme.org", "ED", "ed", "approver"),
         ("root@acme.org", "Root", "ed", "admin")]


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)
    tokens: dict[str, dict] = {}

    def h(email: str) -> dict:
        if email not in tokens:
            r = c.post("/auth/login", json={"email": email, "password": PW})
            tokens[email] = {"Authorization": "Bearer " + r.json()["token"]}
        return tokens[email]
    return c, h


def test_vendor_bank_numbers_are_masked(c, h) -> None:
    print("\nH1: the vendor register shows full bank numbers only to Finance")
    import vendors as vd
    v = vd.create("acme", name="Kano Printers Ltd", created_by="root@acme.org")
    v.bank.account_number = "0987654321"
    vd._save("acme", v)
    r = c.get(f"/vendors/{v.id}", headers=h("amina@acme.org"))
    num = r.json().get("bank", {}).get("account_number", "") if r.status_code == 200 else ""
    check("a Programmes viewer sees ••••••4321, not the number", num == "••••••4321", f"{r.status_code} {num}")
    r = c.get("/vendors", headers=h("pm@acme.org"))
    nums = [x["bank"]["account_number"] for x in r.json().get("vendors", [])]
    check("…and the list is masked too", bool(nums) and all(n.startswith("••") for n in nums), str(nums))
    r = c.get(f"/vendors/{v.id}", headers=h("ngozi@acme.org"))
    check("Finance sees the full number to pay it", r.json()["bank"]["account_number"] == "0987654321")
    r = c.post(f"/vendors/{v.id}/verify", headers=h("pm@acme.org"), data={"account_number": "1111111111"})
    check("a Programmes approver cannot change a vendor's bank details", r.status_code == 403, str(r.status_code))


def test_legacy_pipeline_needs_the_right_department(c, h) -> None:
    print("\nH5: switched on, the old pipeline still follows departments and the session")
    import transactions as tx
    org_config.set_features("acme", legacy_intake=True)
    t = tx.create("payment_run", "Generator repair", amount=5_000_000, created_by="x")
    owner = tx._state_owner(t.state)
    outsider = "femi@acme.org" if owner != "finance" else "pm@acme.org"
    allowed = tx.allowed_transitions(t.state)
    r = c.post(f"/transactions/{t.ref}/transition", headers=h(outsider), json={"to_state": allowed[0]})
    check(f"an approver outside '{owner}' cannot move it on", r.status_code == 403,
          f"{r.status_code} {r.text[:100]}")
    r = c.post(f"/transactions/{t.ref}/note", headers=h("amina@acme.org"),
               json={"note": "approved", "actor": "The ED", "department": "ed"})
    last = (r.json().get("history") or [{}])[-1] if r.status_code == 200 else {}
    check("a note is signed by whoever wrote it, not who they claim to be",
          r.status_code == 200 and last.get("actor") != "The ED" and last.get("department") != "ed",
          str(last)[:160])
    r = c.get("/notifications?department=finance", headers=h("amina@acme.org"))
    check("M4: Finance's inbox is not readable by asking for it",
          r.json().get("department") == "program", str(r.json().get("department")))
    org_config.set_features("acme", legacy_intake=False)


def test_field_receipts_are_reviewed_by_finance_not_the_uploader(c, h) -> None:
    print("\nH6: a flagged receipt is reviewed by Finance, never by whoever uploaded it")
    import field_receipts as fr

    def plant(uploader: str):
        rec = fr.ReceiptLine(id=f"rcp-{uploader.split('@')[0]}", org_id="acme", uploaded_by=uploader,
                             amount_submitted=999_999, project_code="P-1",
                             status=fr.ReceiptStatus.FLAGGED)
        store.get_store().put("acme", fr._RECEIPTS, rec.id, rec.model_dump())
        return rec
    mine, fin = plant("amina@acme.org"), plant("ngozi@acme.org")
    r = c.post(f"/field-receipts/{mine.id}/resolve", headers=h("amina@acme.org"), data={"decision": "approved"})
    check("the uploader cannot approve their own flagged receipt", r.status_code == 403, str(r.status_code))
    r = c.post(f"/field-receipts/{fin.id}/resolve", headers=h("ngozi@acme.org"), data={"decision": "approved"})
    check("…not even when the uploader is in Finance", r.status_code == 403, str(r.status_code))
    r = c.post(f"/field-receipts/{mine.id}/resolve", headers=h("pm@acme.org"), data={"decision": "approved"})
    check("a Programmes approver cannot approve it either", r.status_code == 403, str(r.status_code))
    r = c.get(f"/field-receipts/{fin.id}", headers=h("amina@acme.org"))
    check("staff cannot open someone else's receipt", r.status_code == 404, str(r.status_code))
    r = c.put(f"/field-receipts/{fin.id}", headers=h("amina@acme.org"), data={"amount_submitted": "1"})
    check("…or change its amount", r.status_code == 404, str(r.status_code))
    r = c.get("/field-receipts", headers=h("amina@acme.org"))
    ids = [x["id"] for x in r.json().get("receipts", [])]
    check("staff see only their own receipts in the list", ids == [mine.id], str(ids))
    r = c.post(f"/field-receipts/{mine.id}/resolve", headers=h("ngozi@acme.org"), data={"decision": "approved"})
    check("someone else in Finance reviews it", r.status_code == 200, f"{r.status_code} {r.text[:120]}")


def test_timesheets_belong_to_their_owner(c, h) -> None:
    print("\nH7: a timesheet is its owner's; their department's approver signs it")
    import timesheets as ts
    org_config.set_features("acme", timesheets=True)
    sheet = ts.create_timesheet("acme", staff_id="amina@acme.org", period="2026-09", staff_name="Amina")
    entries = '[{"date": "2026-09-01", "hours": 8, "project_code": "P-1", "activity": "fieldwork"}]'
    r = c.put(f"/timesheets/{sheet.id}/entries", headers=h("pm@acme.org"), data={"entries": entries})
    check("her manager cannot rewrite her hours", r.status_code == 403, str(r.status_code))
    r = c.put(f"/timesheets/{sheet.id}/entries", headers=h("ed@acme.org"), data={"entries": entries})
    check("someone from another department cannot even find it", r.status_code == 404, str(r.status_code))
    r = c.post(f"/timesheets/{sheet.id}/submit", headers=h("pm@acme.org"))
    check("nobody else can sign and submit it for her", r.status_code == 403, str(r.status_code))
    r = c.get("/timesheets", headers=h("ed@acme.org"))
    check("another department's approver doesn't see it listed",
          sheet.id not in [x["id"] for x in r.json().get("timesheets", [])])
    r = c.put(f"/timesheets/{sheet.id}/entries", headers=h("amina@acme.org"), data={"entries": entries})
    check("she fills in her own", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    r = c.post(f"/timesheets/{sheet.id}/submit", headers=h("amina@acme.org"))
    check("…and submits it", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    r = c.post(f"/timesheets/{sheet.id}/approve", headers=h("ed@acme.org"))
    check("an approver from another department cannot approve it", r.status_code in (403, 404),
          str(r.status_code))
    r = c.post(f"/timesheets/{sheet.id}/approve", headers=h("pm@acme.org"))
    check("her own department's approver can", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    r = c.get(f"/timesheets/{sheet.id}", headers=h("ngozi@acme.org"))
    check("Finance can read it for payroll", r.status_code == 200, str(r.status_code))


def test_the_first_admin_cannot_be_claimed_in_production() -> None:
    print("\nH8: on a live instance, the first account isn't up for grabs")
    from fastapi import HTTPException
    from api import auth_routes
    saved = {k: os.environ.get(k) for k in ("DOCEX_ENV", "DOCEX_SETUP_TOKEN")}
    real = auth_routes.auth_mod.list_public
    auth_routes.auth_mod.list_public = lambda *a, **k: []     # an empty instance
    body = auth_routes.RegisterRequest(email="eve@evil.example", name="Eve",
                                       password="correct-horse-battery", department="finance")

    def attempt(code):
        try:
            auth_routes.register(body, None, code)
            return 200
        except HTTPException as exc:
            return exc.status_code
    try:
        os.environ["DOCEX_ENV"] = "production"
        os.environ.pop("DOCEX_SETUP_TOKEN", None)
        check("refused when no setup code is configured", attempt(None) == 403)
        check("…even if the stranger sends one", attempt("anything") == 403)
        os.environ["DOCEX_SETUP_TOKEN"] = "one-time-setup-code-123"
        check("a wrong setup code is refused", attempt("wrong") == 403)
        check("the right code gets through", attempt("one-time-setup-code-123") == 200)
    finally:
        auth_routes.auth_mod.list_public = real
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_advance_status_is_private(c, h) -> None:
    print("\nL3: whether a colleague has an overdue advance is Finance's business")
    org_config.set_features("acme", advance_retirement=True)
    seen = {}

    import advances as adv
    real = adv.payment_block

    def spy(org_id, *, staff_id="", project_code=""):
        seen["staff_id"], seen["project_code"] = staff_id, project_code
        return None
    adv.payment_block = spy
    try:
        c.get("/advances/block?staff_id=pm@acme.org", headers=h("amina@acme.org"))
        check("asking about a colleague answers about yourself instead",
              seen.get("staff_id") == "amina@acme.org", str(seen))
        c.get("/advances/block?staff_id=pm@acme.org", headers=h("ngozi@acme.org"))
        check("Finance can still check anyone before paying them", seen.get("staff_id") == "pm@acme.org",
              str(seen))
    finally:
        adv.payment_block = real


if __name__ == "__main__":
    print("Whose record is it?")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    org_config.set_features("acme", vendor_register=True)
    for email, name, dept, role in USERS:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    c, h = _client()
    test_vendor_bank_numbers_are_masked(c, h)
    test_legacy_pipeline_needs_the_right_department(c, h)
    test_field_receipts_are_reviewed_by_finance_not_the_uploader(c, h)
    test_timesheets_belong_to_their_owner(c, h)
    test_the_first_admin_cannot_be_claimed_in_production()
    test_advance_status_is_private(c, h)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
