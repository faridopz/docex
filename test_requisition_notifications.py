"""
End-to-end HTTP test: requisitions now actually notify people.

Before this, the in-app notification feed only ever fired for the older
voucher/transaction flow — raising, routing, or paying a requisition told
nobody. This test drives the real FastAPI app and checks three things at
once: the department a requisition is parked on gets told it's their turn,
a department declining/returning it tells the submitter, and a higher-up
configured on a CC rule is copied the moment a qualifying requisition is
raised — without that CC ever granting them the ability to act on it.

Run: python test_requisition_notifications.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod
import notification_center as nc

_base = Path(tempfile.mkdtemp(prefix="docex_reqnotif_"))
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


# ─── bootstrap: admin (management), a submitter (program), an approver
# (finance) ────────────────────────────────────────────────────────────────

r = client.post("/auth/register", json={
    "email": "admin@neem.org", "name": "Admin", "password": "admin-passphrase",
    "department": "management", "role": "viewer"})
check("bootstrap admin registered", r.status_code == 200)
admin_tok = client.post("/auth/login", json={
    "email": "admin@neem.org", "password": "admin-passphrase"}).json()["token"]
ah = {"Authorization": f"Bearer {admin_tok}"}

client.post("/auth/register", headers=ah, json={
    "email": "program@neem.org", "name": "Program", "password": "program-passphrase",
    "department": "program", "role": "reviewer"})
prog_tok = client.post("/auth/login", json={
    "email": "program@neem.org", "password": "program-passphrase"}).json()["token"]
ph = {"Authorization": f"Bearer {prog_tok}"}

client.post("/auth/register", headers=ah, json={
    "email": "finance@neem.org", "name": "Finance", "password": "finance-passphrase",
    "department": "finance", "role": "approver"})
fin_tok = client.post("/auth/login", json={
    "email": "finance@neem.org", "password": "finance-passphrase"}).json()["token"]
fh = {"Authorization": f"Bearer {fin_tok}"}

# ─── workflow: one finance step, and a CC rule that copies management on
# anything at or above 2,000,000 — the "higher-ups copied on certain
# transactions" ask, expressed as data, not a special code path. ───────────

wf = {
    "steps": [
        {"key": "finance", "label": "Finance Review", "department": "finance",
         "can_override": True, "override_limit": 5_000_000},
    ],
    "allowed_categories": ["training"],
    "cc_rules": [
        {"min_amount": 2_000_000, "department": "management", "label": "Leadership"},
    ],
}
r = client.put("/requisitions/workflow", headers=ah, json=wf)
check("workflow (with a CC rule) saved", r.status_code == 200)
check("CC rule round-trips", r.json()["cc_rules"][0]["department"] == "management")

# ─── below the CC threshold: finance is told, management is NOT ───────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Local Print Shop", "amount": "150000",
    "category": "training", "project_code": "P-1",
})
check("small requisition raised", r.status_code == 200)
small_ref = r.json()["ref"]

fin_notifs = client.get("/notifications", headers=fh,
                        params={"department": "finance"}).json()["notifications"]
check("finance was told it's their turn (the base gap this closes)",
      any(n["txn_ref"] == small_ref and n["kind"] == "assigned" for n in fin_notifs))

mgmt_notifs = client.get("/notifications", headers=ah,
                         params={"department": "management"}).json()["notifications"]
check("management NOT copied — below the CC threshold",
      not any(n["txn_ref"] == small_ref for n in mgmt_notifs))

# ─── at/above the CC threshold: management is copied, on top of finance
# still being the one actually assigned to act ──────────────────────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Regional Training Vendor", "amount": "2500000",
    "category": "training", "project_code": "P-1",
})
check("large requisition raised", r.status_code == 200)
big_ref = r.json()["ref"]

mgmt_notifs = client.get("/notifications", headers=ah,
                         params={"department": "management"}).json()["notifications"]
big_cc = [n for n in mgmt_notifs if n["txn_ref"] == big_ref]
check("management copied on the large requisition", len(big_cc) == 1)
check("the CC notification is kind='cc', not 'assigned' — informed, not asked to act",
      big_cc[0]["kind"] == "cc" if big_cc else False)

fin_notifs = client.get("/notifications", headers=fh,
                        params={"department": "finance"}).json()["notifications"]
check("finance is still the one actually assigned",
      any(n["txn_ref"] == big_ref and n["kind"] == "assigned" for n in fin_notifs))

# Being CC'd grants no authority — management was never a workflow step, so
# it cannot decide this requisition regardless of being notified about it.
r = client.post(f"/requisitions/{r.json()['id']}/decide", headers=ah, data={
    "decision": "approved", "notes": "ok"})
check("being CC'd does not grant approval authority", r.status_code == 400)

# ─── decline notifies the submitter's own department ───────────────────────

in_review = client.get("/requisitions", headers=fh,
                       params={"status": "in_review"}).json()["requisitions"]
small_id = next(x["id"] for x in in_review if x["ref"] == small_ref)

client.post(f"/requisitions/{small_id}/decide", headers=fh,
           data={"decision": "returned", "notes": "Needs a quote attached."})
prog_notifs = client.get("/notifications", headers=ph,
                         params={"department": "program"}).json()["notifications"]
check("submitter's department told it was returned",
      any(n["txn_ref"] == small_ref and n["kind"] == "returned" for n in prog_notifs))

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition-notification checks passed.")
