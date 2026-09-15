"""
End-to-end HTTP test: the multi-payee requisition FORM, not just the engine.

test_requisitions.py already proves rq.create_requisition() and
disbursements.py handle a payee list correctly at the Python level. This
file proves the thing a browser actually sends arrives intact: the frontend
posts payees as a JSON string in a multipart form field (there is no clean
way to post nested objects any other way through FastAPI's Form()), and two
real gaps lived exactly at that boundary until this feature was built —
the route never accepted a `payees` field at all, and even after the engine
supported it, the API never serialised `payees` back out in the response.

Also covers a gap the code review for this feature caught: update_draft()
must enforce the same feature-flag and max_payees checks create_requisition()
does. Without that, a draft raised single-vendor could be edited into an
unlimited batch on an org that never turned multi-payee requisitions on.

Run: python test_requisition_payee_api.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import store
import auth as auth_mod
import org_config

_base = Path(tempfile.mkdtemp(prefix="docex_payee_api_"))
store.set_store(store.JsonFileStore(_base / "store"))
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None

from fastapi.testclient import TestClient  # noqa: E402
import api.main as m  # noqa: E402

client = TestClient(m.app)
_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


# ─── bootstrap ──────────────────────────────────────────────────────────────

client.post("/auth/register", json={
    "email": "admin@neem.org", "name": "Admin", "password": "admin-passphrase",
    "department": "management", "role": "viewer"})
admin_tok = client.post("/auth/login", json={
    "email": "admin@neem.org", "password": "admin-passphrase"}).json()["token"]
ah = {"Authorization": f"Bearer {admin_tok}"}

client.post("/auth/register", headers=ah, json={
    "email": "program@neem.org", "name": "Program", "password": "program-passphrase",
    "department": "program", "role": "reviewer"})
prog_tok = client.post("/auth/login", json={
    "email": "program@neem.org", "password": "program-passphrase"}).json()["token"]
ph = {"Authorization": f"Bearer {prog_tok}"}

# A small cap (3) so the test can trip it without typing 101 payee rows.
r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
    "max_payees": 3,
})
check("workflow with max_payees=3 saved", r.status_code == 200 and r.json()["max_payees"] == 3)

payees = [
    {"name": "Aisha Bello", "account_number": "0011234567", "bank_name": "GTBank",
     "amount": 20000, "purpose": "Facilitator stipend", "phone_or_email": "aisha@x.org",
     "payee_type": "staff"},
    {"name": "Chidi Okafor", "account_number": "0021234567", "bank_name": "Access Bank",
     "amount": 15000, "purpose": "Participant stipend", "tin": "TIN-002",
     "payee_type": "beneficiary"},
]

# ─── flag off: the form field is refused exactly like the engine refuses it ─

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "August workshop stipends", "amount": "0",
    "category": "", "payees": json.dumps(payees),
})
check("payees refused with a clear message while the flag is off", r.status_code == 400)
check("refusal names the feature flag",
      "multi_payee_requisitions" in r.json()["detail"])

org_config.set_features("default", multi_payee_requisitions=True)

# ─── malformed payloads are 400s, not silently-empty requisitions ──────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Bad JSON test", "amount": "0", "payees": "{not json",
})
check("malformed payees JSON is a 400", r.status_code == 400)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Not a list test", "amount": "0", "payees": json.dumps({"a": 1}),
})
check("a JSON object (not array) for payees is a 400", r.status_code == 400)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Bad row test", "amount": "0", "payees": json.dumps(["not an object"]),
})
check("a non-object row is a 400", r.status_code == 400)

# ─── the real case: two payees, posted the way the browser posts them ──────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "August workshop stipends", "amount": "999999",  # ignored — must be overridden
    "category": "", "project_code": "P-1", "payees": json.dumps(payees),
})
check("multi-payee requisition raised", r.status_code == 200)
body = r.json()
check("amount is the sum of the payees, NOT the bogus amount field sent",
      abs(body["amount"] - 35000) < 0.01)
check("both payees round-tripped through the API", len(body["payees"]) == 2)
check("a payee's bank details survive the JSON→Form→JSON round trip",
      body["payees"][0]["account_number"] == "0011234567"
      and body["payees"][0]["bank_name"] == "GTBank"
      and body["payees"][0]["payee_type"] == "staff")
check("a payee field that was never set (tin) comes back as its default, not missing",
      body["payees"][0]["tin"] == "")
req_id = body["id"]

# GET the same requisition back — this is the exact code path
# (_detail_out → _payee_out) that used to silently drop payees.
r = client.get(f"/requisitions/{req_id}", headers=ph)
check("payees also present on GET, not just the create response",
      len(r.json()["payees"]) == 2)

# ─── over the cap: refused with the actual numbers, not a generic error ────

over_cap = payees + [
    {"name": "Third", "amount": 1000}, {"name": "Fourth", "amount": 1000},
]
r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Too many payees", "amount": "0", "payees": json.dumps(over_cap),
})
check("over max_payees is refused (400)", r.status_code == 400)
check("refusal states this org's actual cap", "3" in r.json()["detail"])

# ─── draft path: same enforcement, not a side door ─────────────────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Draft, starts single-vendor", "amount": "50000", "submit": "false",
})
check("single-vendor draft saved", r.status_code == 200)
draft_id = r.json()["id"]

r = client.put(f"/requisitions/{draft_id}/draft", headers=ph, data={
    "payees": json.dumps(payees),
})
check("draft converted into a batch on edit", r.status_code == 200)
check("draft's amount recomputed from the new payee list",
      abs(r.json()["amount"] - 35000) < 0.01)

r = client.put(f"/requisitions/{draft_id}/draft", headers=ph, data={
    "payees": json.dumps(over_cap),
})
check("editing a draft past max_payees is refused too, not just create", r.status_code == 400)

r = client.put(f"/requisitions/{draft_id}/draft", headers=ph, data={"payees": "[]"})
check("a draft can be edited back to zero payees (single-vendor again)", r.status_code == 200)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition payee-API checks passed.")
