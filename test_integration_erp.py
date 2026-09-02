"""End-to-end HTTP test of the ERP workflow through the real FastAPI app.
Run: python test_integration_erp.py"""
from __future__ import annotations

import tempfile
from pathlib import Path

# Redirect every store to temp dirs BEFORE the app handles requests.
import store
import auth as auth_mod
import notification_center as nc
import transactions as tx
import vouchers as vouchers_mod

_base = Path(tempfile.mkdtemp(prefix="docex_erp_"))
for sub in ("txn", "notif", "vouchers", "cards"):
    (_base / sub).mkdir()
store.set_store(store.JsonFileStore(_base / "store"))   # users + departments
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None
tx._TXN_DIR = _base / "txn"
tx._COUNTER_FILE = _base / "txn" / ".counter"
nc._NOTIF_DIR = _base / "notif"
vouchers_mod._VOUCHER_DIR = _base / "vouchers"

from fastapi.testclient import TestClient  # noqa: E402
import api.main as m  # noqa: E402
# Point the rate-card loaders (used by voucher route) at our temp card dir.
import api.voucher_routes as vr  # noqa: E402
vr._RATE_CARD_DIR = _base / "cards"

client = TestClient(m.app)
_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


# 1. Bootstrap admin (first user) + a finance user.
r = client.post("/auth/register", json={
    "email": "admin@taconnect-ng.org", "name": "Admin", "password": "adminpass",
    "department": "management", "role": "viewer"})
check("first register ok", r.status_code == 200)
check("first user forced to admin", r.json()["role"] == "admin")

admin_tok = client.post("/auth/login", json={
    "email": "admin@taconnect-ng.org", "password": "adminpass"}).json()["token"]
ah = {"Authorization": f"Bearer {admin_tok}"}

r = client.post("/auth/register", headers=ah, json={
    "email": "bola@taconnect-ng.org", "name": "Bola", "password": "financepass",
    "department": "finance", "role": "approver"})
check("admin can add finance user", r.status_code == 200)

# Non-admin cannot add users.
fin_tok = client.post("/auth/login", json={
    "email": "bola@taconnect-ng.org", "password": "financepass"}).json()["token"]
fh = {"Authorization": f"Bearer {fin_tok}"}
r = client.post("/auth/register", headers=fh, json={
    "email": "x@y.org", "name": "X", "password": "password", "department": "finance"})
check("non-admin blocked from adding users (403)", r.status_code == 403)

# Unauthenticated dashboard is rejected.
check("dashboard needs auth (401)", client.get("/dashboard").status_code == 401)

# 2. Build a voucher from participants (inline rate) and submit it.
r = client.post("/vouchers", json={
    "event_name": "Q3 Workshop", "created_by": "bola",
    "participants": [
        {"participant_name": "Aisha", "role": "Facilitator", "rate_per_day": 20000,
         "num_days": 3, "default_covered": ["meals"],
         "receipts": [{"filename": "taxi", "amount": 5000, "category": "transport"}]},
        {"participant_name": "Bello", "rate_per_day": 20000,
         "num_days": 2, "default_covered": ["meals"]},
    ]})
check("voucher built", r.status_code == 200)
v = r.json()
check("voucher total 45k+5k + 30k = 80k", abs(v["total"] - 80000) < 0.01)

r = client.post(f"/vouchers/{v['id']}/submit")
check("voucher submitted", r.status_code == 200)
ref = r.json()["txn_ref"]
check("got a V-reference", ref and ref.startswith("V"))

# 3. Compliance sees it (notification + owns the transaction).
r = client.get("/notifications", params={"department": "compliance"})
check("compliance notified of the new voucher", r.json()["unread"] >= 1)

r = client.get(f"/transactions/{ref}")
check("transaction is in compliance_review", r.json()["state"] == "compliance_review")

# Compliance views + passes to finance.
client.post(f"/transactions/{ref}/view", json={"department": "compliance"})
r = client.get(f"/transactions/{ref}")
check("viewed_by records compliance", "compliance" in r.json()["viewed_by"])

# Transitions are now the IN-APP approval path: authenticated + role-gated.
check("transition requires auth (401)",
      client.post(f"/transactions/{ref}/transition",
                  json={"to_state": "finance_review"}).status_code == 401)

r = client.post(f"/transactions/{ref}/transition", headers=ah,
                json={"to_state": "finance_review"})
check("moved to finance_review", r.json()["state"] == "finance_review")
check("actor recorded from signed-in user, not the body",
      r.json()["history"][-1]["actor"] == "Admin")

# Illegal jump is a 409 (admin passes the role gate, so we reach the state machine).
r = client.post(f"/transactions/{ref}/transition", headers=ah, json={"to_state": "paid"})
check("illegal transition rejected (409)", r.status_code == 409)

# 4. Finance dashboard reflects the pending item + its value.
r = client.get("/dashboard", headers=fh)
d = r.json()
check("finance dashboard department", d["department"] == "finance")
check("finance has 1 pending item", d["pending_on_me"] == 1)
check("finance pending value = 80k", abs(d["total_value_pending"] - 80000) < 0.01)
check("finance has unread notifications", d["unread_notifications"] >= 1)

# Non-admin cannot peek at another department's dashboard.
r = client.get("/dashboard", headers=fh, params={"department": "compliance"})
check("cross-department dashboard blocked for non-admin (403)", r.status_code == 403)

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All ERP integration checks passed.")
