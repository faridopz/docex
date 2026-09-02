"""Tests for custom departments + in-app approval permissions.
Run: python test_departments.py"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod
import departments as dept_mod  # noqa: F401  (exercised via the API)
import notification_center as nc
import transactions as tx

# Redirect every store to temp locations BEFORE the app is exercised.
_base = Path(tempfile.mkdtemp(prefix="docex_dept_"))
for sub in ("txn", "notif"):
    (_base / sub).mkdir()
store.set_store(store.JsonFileStore(_base / "store"))   # users + departments
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None
tx._TXN_DIR = _base / "txn"
tx._COUNTER_FILE = _base / "txn" / ".counter"
nc._NOTIF_DIR = _base / "notif"

from fastapi.testclient import TestClient  # noqa: E402
import api.main as m  # noqa: E402

client = TestClient(m.app)
_fail = 0


def check(name, cond, extra=""):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}{(' — ' + extra) if extra and not cond else ''}")
    if not cond:
        _fail += 1


def expect_err(name, fn, exc=dept_mod.DepartmentError):
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected an error, none raised")
        _fail += 1
    except exc:
        print(f"PASS  {name}: raised as expected")


# ── registry defaults preserve the original four (backward compatible) ──
check("defaults seed the original four",
      dept_mod.keys() == ["program", "compliance", "finance", "management"])
check("default routing unchanged", dept_mod.state_owner("approval") == "management")
check("state machine reads the registry", tx._state_owner("compliance_review") == "compliance")

# ── an org can add its OWN departments (EVA-style) ──
dept_mod.add("Team Lead Finance & Admin", description="TLFA", order=35)
ed = dept_mod.add("Executive Director", order=50, is_final_authority=True)
check("custom key slugified", ed.key == "executive-director")
check("custom departments listed", "team-lead-finance-admin" in dept_mod.keys())
check("label resolves", dept_mod.label("executive-director") == "Executive Director")
expect_err("duplicate department rejected", lambda: dept_mod.add("Finance"))

# ── workflow can be re-routed to a custom department ──
dept_mod.set_state_owner("approval", "executive-director")
check("approval now routes to the ED", dept_mod.state_owner("approval") == "executive-director")
check("state machine picks up the new owner", tx._state_owner("approval") == "executive-director")

# A department owning a state can't be deleted out from under it.
expect_err("cannot delete a department that owns a state",
           lambda: dept_mod.remove("executive-director"))
dept_mod.remove("team-lead-finance-admin")
check("unused department deletes cleanly", "team-lead-finance-admin" not in dept_mod.keys())

# ── users can't be created in a department that doesn't exist ──
expect_err("unknown department rejected on user create",
           lambda: auth_mod.create_user("x@y.org", "X", "password", "not-a-dept"),
           exc=auth_mod.AuthError)

# ── in-app approval permissions ──
admin = client.post("/auth/register", json={
    "email": "admin@eva.org", "name": "Admin", "password": "adminpass",
    "department": "finance"}).json()
ah = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'admin@eva.org', 'password': 'adminpass'}).json()['token']}"}

client.post("/auth/register", headers=ah, json={
    "email": "viewer@eva.org", "name": "Viewer", "password": "viewpass",
    "department": "finance", "role": "viewer"})
client.post("/auth/register", headers=ah, json={
    "email": "rev@eva.org", "name": "Rev", "password": "revpass",
    "department": "compliance", "role": "reviewer"})
vh = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'viewer@eva.org', 'password': 'viewpass'}).json()['token']}"}
rh = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'rev@eva.org', 'password': 'revpass'}).json()['token']}"}

txn = tx.create("voucher", "Test voucher", amount=1000)
ref = txn.ref

check("viewer cannot action items (403)",
      client.post(f"/transactions/{ref}/transition", headers=vh,
                  json={"to_state": "compliance_review"}).status_code == 403)
check("reviewer CAN progress work",
      client.post(f"/transactions/{ref}/transition", headers=rh,
                  json={"to_state": "compliance_review"}).status_code == 200)
check("reviewer CANNOT authorise (approval gate, 403)",
      client.post(f"/transactions/{ref}/transition", headers=rh,
                  json={"to_state": "approval"}).status_code == 403)
r = client.post(f"/transactions/{ref}/transition", headers=ah, json={"to_state": "approval"})
check("admin/approver CAN authorise", r.status_code == 200, f"status={r.status_code}")
check("item now owned by the ED (custom routing end-to-end)",
      r.json()["owner_department"] == "executive-director")

# ── departments API ──
check("GET /departments needs auth", client.get("/departments").status_code == 401)
body = client.get("/departments", headers=ah).json()
check("API lists departments + routing",
      any(d["key"] == "executive-director" for d in body["departments"])
      and body["state_owners"]["approval"] == "executive-director")
check("non-admin cannot create a department",
      client.post("/departments", headers=rh, json={"name": "Nope"}).status_code == 403)
check("admin can create a department",
      client.post("/departments", headers=ah, json={"name": "Procurement"}).status_code == 200)

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All department + approval-permission checks passed.")
