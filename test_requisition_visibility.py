"""
A programme officer sees their own payment requests and their department's —
not every payment the organisation makes, and never someone else's bank
account number.

Found in the September 2026 experience audit: any signed-in user could call
GET /requisitions and list every payment in the organisation, open any of
them, and read the payee's full account number. At an NGO that includes
staff salary advances and consultant fees. The people who run the approval
chain (the departments that own a step, Finance, admins) still see
everything — they need to.

Unknown ids and hidden ids answer the same 404, so a guessed id can't be used
to learn that a payment exists.

Run: python test_requisition_visibility.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-visibility-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import attachments  # noqa: E402

attachments.set_backend(attachments.LocalDiskAttachmentBackend(Path(_TMP) / "files"))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402

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
    "departments": [
        {"key": "program", "name": "Programmes"},
        {"key": "hr", "name": "Human Resources"},
        {"key": "finance", "name": "Finance"},
        {"key": "ed", "name": "Executive Director", "is_final_authority": True},
    ],
    "workflow": {
        "max_amount": 100_000_000,
        "steps": [{"key": "finance", "label": "Finance review", "department": "finance"},
                  {"key": "ed", "label": "ED approval", "department": "ed"}],
    },
    "features": {"requisition_export": True, "requisition_attachments": True},
}

USERS = [
    ("amina@acme.org", "Amina", "program", "reviewer"),
    ("sam@acme.org", "Sam", "program", "reviewer"),
    ("hauwa@acme.org", "Hauwa", "hr", "reviewer"),
    ("femi@acme.org", "Femi", "finance", "approver"),
    ("ngozi@acme.org", "Dr Ngozi", "ed", "approver"),
    ("root@acme.org", "Root", "hr", "admin"),
]

ACCOUNT = "0123456789"


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    return TestClient(m.app, raise_server_exceptions=False)


def _h(c, email):
    tok = c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _raise(c, email, vendor):
    r = c.post("/requisitions", headers=_h(c, email),
               data={"vendor_name": vendor, "amount": "250000", "description": "x",
                     "vendor_account": ACCOUNT, "vendor_bank": "GTBank", "submit": "true"})
    assert r.status_code == 200, r.text
    return r.json()


def _refs(c, email):
    return {x["ref"] for x in c.get("/requisitions", headers=_h(c, email)).json()["requisitions"]}


def test_staff_see_their_own_and_their_departments() -> None:
    print("\nStaff: own requests and their department's, nobody else's")
    c = _client()
    amina = _raise(c, "amina@acme.org", "Hotel Maiduguri")
    sam = _raise(c, "sam@acme.org", "Kano Printers")
    hr = _raise(c, "hauwa@acme.org", "Salary advance — Hauwa")
    seen = _refs(c, "amina@acme.org")
    check("sees her own", amina["ref"] in seen, str(seen))
    check("sees a colleague's in Programmes", sam["ref"] in seen, str(seen))
    check("does not see HR's salary advance", hr["ref"] not in seen, str(seen))
    r = c.get(f"/requisitions/{hr['id']}", headers=_h(c, "amina@acme.org"))
    check("opening it by id: 404, same as an id that doesn't exist", r.status_code == 404, str(r.status_code))
    r = c.get(f"/requisitions/{hr['ref']}", headers=_h(c, "amina@acme.org"))
    check("opening it by reference: 404", r.status_code == 404, str(r.status_code))
    r = c.get(f"/requisitions/{hr['id']}/export.pdf", headers=_h(c, "amina@acme.org"))
    check("its PDF: 404", r.status_code == 404, str(r.status_code))
    r = c.post(f"/requisitions/{hr['id']}/comments", headers=_h(c, "amina@acme.org"), data={"text": "hi"})
    check("commenting on it: 404", r.status_code == 404, str(r.status_code))


def test_only_the_person_who_raised_it_can_edit_it() -> None:
    print("\nA returned request can only be changed and resent by the person who raised it")
    c = _client()
    sam = _raise(c, "sam@acme.org", "Musa Transport")
    r = c.post(f"/requisitions/{sam['id']}/decide", headers=_h(c, "femi@acme.org"),
               data={"decision": "returned", "notes": "attach the quote"})
    check("Finance returned it", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    r = c.put(f"/requisitions/{sam['id']}/draft", headers=_h(c, "amina@acme.org"),
              data={"vendor_account": "9999999999"})
    check("a colleague can't change the bank account", r.status_code in (400, 403, 404),
          f"{r.status_code} {r.text[:120]}")
    r = c.post(f"/requisitions/{sam['id']}/resubmit", headers=_h(c, "amina@acme.org"), data={"notes": "x"})
    check("a colleague can't resend it", r.status_code in (400, 403, 404), f"{r.status_code} {r.text[:120]}")
    r = c.put(f"/requisitions/{sam['id']}/draft", headers=_h(c, "sam@acme.org"),
              data={"description": "with quote"})
    check("the person who raised it can", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    import requisitions as rq
    check("account unchanged", rq.get_requisition("acme", sam["id"]).vendor_account == ACCOUNT)


def test_the_approval_chain_sees_everything() -> None:
    print("\nFinance, the ED (both own a step) and admins see every request")
    c = _client()
    everyone = _refs(c, "root@acme.org")
    check("admin sees all three+", len(everyone) >= 3, str(everyone))
    check("Finance sees all", _refs(c, "femi@acme.org") == everyone)
    check("ED sees all", _refs(c, "ngozi@acme.org") == everyone)


def test_account_numbers_are_masked_for_non_finance() -> None:
    print("\nAccount numbers: full for Finance and the person who raised it, masked for colleagues")
    c = _client()
    sam_req = next(x for x in c.get("/requisitions", headers=_h(c, "sam@acme.org")).json()["requisitions"]
                   if x["submitted_by"] == "sam@acme.org")
    as_sam = c.get(f"/requisitions/{sam_req['id']}", headers=_h(c, "sam@acme.org")).json()
    as_amina = c.get(f"/requisitions/{sam_req['id']}", headers=_h(c, "amina@acme.org")).json()
    as_femi = c.get(f"/requisitions/{sam_req['id']}", headers=_h(c, "femi@acme.org")).json()
    check("the submitter sees the number he typed", as_sam["vendor_account"] == ACCOUNT, as_sam["vendor_account"])
    check("Finance sees it in full", as_femi["vendor_account"] == ACCOUNT, as_femi["vendor_account"])
    check("a colleague sees only the last 4 digits",
          as_amina["vendor_account"] == "••••••6789", as_amina["vendor_account"])


def test_org_wide_views_are_for_the_chain() -> None:
    print("\nOrg-wide views (payments, audit, the period log) are not for programme staff")
    c = _client()
    H = _h(c, "amina@acme.org")
    for path in ("/payments", "/audit/summary", "/audit/findings",
                 "/requisitions/export/log.xlsx?start=2020-01-01&end=2030-01-01"):
        r = c.get(path, headers=H)
        check(f"{path.split('?')[0]}: 403 for staff", r.status_code == 403, f"{r.status_code} {r.text[:100]}")
    r = c.get("/payments", headers=_h(c, "femi@acme.org"))
    check("Finance still gets payments", r.status_code == 200, str(r.status_code))
    r = c.get("/audit/summary", headers=_h(c, "ngozi@acme.org"))
    check("the ED still gets the audit summary", r.status_code == 200, str(r.status_code))


def test_permissions_endpoint_tells_the_screen() -> None:
    print("\nThe screen is told whether this person sees the whole organisation")
    c = _client()
    p = c.get("/requisitions/document-permissions", headers=_h(c, "amina@acme.org")).json()
    check("staff: sees_everything false", p.get("sees_everything") is False, str(p))
    p = c.get("/requisitions/document-permissions", headers=_h(c, "ngozi@acme.org")).json()
    check("ED: sees_everything true", p.get("sees_everything") is True, str(p))


def test_rows_say_who_raised_it_and_who_has_it() -> None:
    print("\nEach row names the person who raised it and the department it is with")
    c = _client()
    rows = c.get("/requisitions", headers=_h(c, "femi@acme.org")).json()["requisitions"]
    amina = next(r for r in rows if r["submitted_by"] == "amina@acme.org" and r["status"] == "in_review")
    check("name, not just the address", amina["submitted_by_name"] == "Amina", str(amina.get("submitted_by_name")))
    check("with Finance, as a department key", amina["current_department"] == "finance",
          str(amina.get("current_department")))
    d = c.get(f"/requisitions/{amina['id']}", headers=_h(c, "femi@acme.org")).json()
    check("the detail view names her too", d.get("submitted_by_name") == "Amina")


if __name__ == "__main__":
    print("Who can see which payment")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    for email, name, dept, role in USERS:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    test_staff_see_their_own_and_their_departments()
    test_only_the_person_who_raised_it_can_edit_it()
    test_the_approval_chain_sees_everything()
    test_account_numbers_are_masked_for_non_finance()
    test_org_wide_views_are_for_the_chain()
    test_permissions_endpoint_tells_the_screen()
    test_rows_say_who_raised_it_and_who_has_it()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
