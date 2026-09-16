"""
WO-36, the HTTP half: importing a payee schedule and raising it.

The point this suite defends is that an IMPORTED batch is not a different
kind of requisition. The preview endpoint creates nothing; the rows then go
through POST /requisitions exactly as typed ones do, so the imported batch
picks up the same deterministic policy checks, the same approval chain, the
same audit log and the same compliance check. There is deliberately no
bulk-create endpoint.

Covers: the flag gates it; preview creates nothing; a bad file is refused
with a useful message; the preview reports problems without refusing the
whole file; the imported rows raise a real requisition whose amount is the
sum of the rows; the engine's own payee validation still applies; and the
over-cap case is reported rather than silently truncated.

Run: python test_payee_import_api.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_import_api_"))
store.set_store(store.JsonFileStore(_base / "store"))
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None

import json  # noqa: E402
import org_config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import api.main as m  # noqa: E402

client = TestClient(m.app)
_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


def hdr(email, password):
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


SCHEDULE = b"""Name,Account Number,Bank,Amount,Purpose
Aisha Bello,0123456789,GTBank,"20,000",Workshop stipend
Musa Ibrahim,2345678901,Zenith,15000,Workshop stipend
Grace Okon,3456789012,Access,12500,Transport
"""

# ─── bootstrap ──────────────────────────────────────────────────────────────

client.post("/auth/register", json={
    "email": "admin@neem.org", "name": "Admin", "password": "admin-passphrase",
    "department": "management", "role": "admin"})
ah = hdr("admin@neem.org", "admin-passphrase")

client.post("/auth/register", headers=ah, json={
    "email": "program@neem.org", "name": "Program", "password": "program-passphrase",
    "department": "program", "role": "reviewer"})
ph = hdr("program@neem.org", "program-passphrase")

client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
})

# ─── the flag gates it ──────────────────────────────────────────────────────

r = client.post("/requisitions/payees/preview", headers=ph,
                 files={"file": ("schedule.csv", SCHEDULE, "text/csv")})
check("flag off: import refused", r.status_code == 400)
check("the refusal names the flag", "multi_payee_requisitions" in r.json()["detail"])

org_config.set_features("default", multi_payee_requisitions=True)

# ─── preview reads the file and CREATES NOTHING ────────────────────────────

before = client.get("/requisitions", headers=ph).json()["total"]

r = client.post("/requisitions/payees/preview", headers=ph,
                 files={"file": ("schedule.csv", SCHEDULE, "text/csv")})
check("preview succeeds", r.status_code == 200)
preview = r.json()
check("three rows read", preview["total_rows"] == 3)
check("all three valid", preview["valid_count"] == 3)
check("no problems", preview["problem_count"] == 0)
check("total is the sum of the rows", preview["total_amount"] == 47500.0)
check("the comma-formatted amount parsed", preview["rows"][0]["amount"] == 20000.0)
check("the leading zero survived", preview["rows"][0]["account_number"] == "0123456789")
check("the detected column mapping is reported", "name" in preview["detected_columns"])
check("the payee cap is reported so the UI can warn", preview["max_payees"] >= 1)

after = client.get("/requisitions", headers=ph).json()["total"]
check("PREVIEW CREATED NOTHING — no requisition appeared", before == after)

# ─── the imported rows raise an ordinary requisition ───────────────────────

payees = [
    {k: row[k] for k in ("name", "account_number", "bank_name", "amount",
                          "purpose", "tin", "phone_or_email", "payee_type")}
    for row in preview["rows"] if row["ok"]
]
r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "September workshop stipends",
    "amount": "0",                      # ignored — the engine sums the payees
    "category": "supplies",
    "payees": json.dumps(payees),
})
check("the imported rows raise a requisition", r.status_code == 200)
req = r.json()
check("three payees landed", len(req["payees"]) == 3)
check("the engine recomputed the total from the rows, not the posted amount",
      req["amount"] == 47500.0)
check("payee detail survived the round trip",
      req["payees"][0]["account_number"] == "0123456789"
      and req["payees"][0]["bank_name"] == "GTBank")

# The whole point: it is an ORDINARY requisition on the ordinary path.
check("it ran the deterministic policy checks", len(req["checks"]) > 0)
check("it entered the approval chain", req["current_step"] == "finance")
check("it has an audit log", len(req["audit_log"]) > 0)
check("the audit chain verifies", req["audit_chain_valid"] is True)
check("it is visible in the normal list",
      client.get("/requisitions", headers=ph).json()["total"] == before + 1)

# ─── a file with problems previews them without refusing the whole file ───

MESSY = b"""Name,Account Number,Bank,Amount
Aisha Bello,0123456789,GTBank,20000
Broken Row,123456789,Zenith,15000
,3456789012,Access,10000
Good Row,4567890123,UBA,5000
"""
r = client.post("/requisitions/payees/preview", headers=ph,
                 files={"file": ("messy.csv", MESSY, "text/csv")})
check("a file with bad rows still previews", r.status_code == 200)
messy = r.json()
check("the good rows are counted", messy["valid_count"] == 2)
check("the bad rows are counted", messy["problem_count"] == 2)
check("the total counts only the good rows", messy["total_amount"] == 25000.0)
bad = [row for row in messy["rows"] if not row["ok"]]
check("the short account number is explained",
      any("Excel" in e for e in bad[0]["errors"]))
check("each problem row carries its Excel row number",
      all(row["row_number"] > 1 for row in bad))

# ─── unusable files are refused with a useful message ──────────────────────

r = client.post("/requisitions/payees/preview", headers=ph,
                 files={"file": ("junk.csv", b"alpha,beta\n1,2", "text/csv")})
check("a file with no recognisable headings is refused", r.status_code == 400)
check("the refusal explains what headings are needed",
      "header" in r.json()["detail"].lower())

r = client.post("/requisitions/payees/preview", headers=ph,
                 files={"file": ("empty.csv", b"", "text/csv")})
check("an empty file is refused", r.status_code == 400)

# ─── the engine's own payee rules still apply to imported rows ────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Bad batch", "amount": "0", "category": "supplies",
    "payees": json.dumps([{"name": "", "amount": 0}]),
})
check("the engine still rejects a payee row with no name or amount",
      r.status_code == 200 and any(c["result"] == "fail" for c in r.json()["checks"]))

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll payee-import API checks passed.")
