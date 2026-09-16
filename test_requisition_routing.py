"""
WO-35: sending a requisition up and down the approval chain.

decide() has three outcomes and each moves a requisition exactly one way —
approve advances one step, return goes all the way back to the SUBMITTER,
decline ends it. Real chains need a fourth move: escalate this to the AED
now, or hand it back to Finance for another look without bouncing it to the
person who raised it and losing the reviews already done.

Covers:
- escalating forward, and the skipped stages being NAMED on the audit trail
  rather than quietly passed over
- sending it backward to an earlier stage, with the earlier approval still
  on the record (append-only — nothing is erased)
- a reason is mandatory, like a hold and like an override
- only the department currently holding it may move it
- a step that does not engage at this amount cannot be routed to, so no
  approval the policy never asked for can be invented
- routing to the current step, or to a step that does not exist, is refused
- it only works from IN_REVIEW
- the audit chain still verifies afterwards

Run: python test_requisition_routing.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_routing_"))
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


def hdr(email, password):
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


# ─── NEEM's real shape: finance → admin → aed, plus an ed step that only
# engages on large amounts ─────────────────────────────────────────────────

client.post("/auth/register", json={
    "email": "admin@neem.org", "name": "Admin", "password": "admin-passphrase",
    "department": "management", "role": "admin"})
ah = hdr("admin@neem.org", "admin-passphrase")

for email, dept in [("finance@neem.org", "finance"), ("office@neem.org", "compliance"),
                     ("program@neem.org", "program")]:
    client.post("/auth/register", headers=ah, json={
        "email": email, "name": email.split("@")[0], "password": "a-long-passphrase",
        "department": dept, "role": "reviewer"})
fh = hdr("finance@neem.org", "a-long-passphrase")
oh = hdr("office@neem.org", "a-long-passphrase")
ph = hdr("program@neem.org", "a-long-passphrase")

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [
        {"key": "finance", "label": "Finance / Audit review", "department": "finance"},
        {"key": "admin", "label": "Admin forwards to AED", "department": "compliance"},
        {"key": "aed", "label": "AED approval", "department": "management"},
        {"key": "ed", "label": "ED + AED joint approval", "department": "management",
         "min_amount": 7000001},
    ],
})
check("workflow saved", r.status_code == 200)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Sahad Stores", "amount": "500000", "category": "supplies",
})
req_id, req_ref = r.json()["id"], r.json()["ref"]
check("starts with finance", r.json()["current_step"] == "finance")

# ─── a reason is not optional ──────────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/route", headers=fh, data={"target_step": "aed"})
check("routing with no reason is refused", r.status_code == 400)
check("the refusal says a reason is needed", "reason" in r.json()["detail"].lower())

# ─── only the department holding it may move it ────────────────────────────

r = client.post(f"/requisitions/{req_id}/route", headers=oh, data={
    "target_step": "aed", "reason": "Trying to move someone else's step",
})
check("a different department cannot move it", r.status_code == 400)
check("the refusal names who actually holds it", "finance" in r.json()["detail"].lower())

# ─── a step that does not engage at this amount is refused ────────────────

r = client.post(f"/requisitions/{req_id}/route", headers=fh, data={
    "target_step": "ed", "reason": "Skip everyone, go straight to the ED",
})
check("cannot route to a step that does not engage at this amount", r.status_code == 400)
check("the refusal explains the threshold", "7,000,001" in r.json()["detail"]
      or "7000001" in r.json()["detail"])

# ─── escalating forward, skipping a stage ─────────────────────────────────

r = client.post(f"/requisitions/{req_id}/route", headers=fh, data={
    "target_step": "aed", "reason": "Vendor dispute — needs the AED's call today",
})
check("finance can escalate forward to the AED", r.status_code == 200)
body = r.json()
check("it is now with the AED", body["current_step"] == "aed")
routed = [e for e in body["audit_log"] if e["event"] == "rerouted"]
check("the routing is on the audit trail", len(routed) == 1)
check("it is logged as a DEVIATION, distinct from a normal advance",
      all(e["event"] != "routed" for e in body["audit_log"] if "Escalated" in (e["detail"] or "")))
check("the audit line says it was escalated", "Escalated" in routed[0]["detail"])
check("the SKIPPED stage is named, not quietly passed over",
      "Admin forwards to AED" in routed[0]["detail"])
check("the reason is on the trail", "Vendor dispute" in routed[0]["detail"])
check("the audit chain still verifies", body["audit_chain_valid"] is True)

# ─── sending it back down, without bouncing it to the submitter ───────────

r = client.post(f"/requisitions/{req_id}/route", headers=ah, data={
    "target_step": "finance", "reason": "Please re-check the FX rate used",
})
check("the AED can send it back to finance", r.status_code == 200)
back = r.json()
check("it is back with finance", back["current_step"] == "finance")
check("the status is still in_review — NOT returned to the submitter",
      back["status"] == "in_review")
check("the audit line says it was sent back",
      any("Sent back" in e["detail"] for e in back["audit_log"] if e["event"] == "rerouted"))

# Finance approves this time — and the earlier escalation is still on record.
r = client.post(f"/requisitions/{req_id}/decide", headers=fh, data={
    "decision": "approved", "notes": "FX rate confirmed",
})
check("finance can then approve normally", r.status_code == 200)
after = r.json()
check("approving from finance advances to the next stage", after["current_step"] == "admin")
check("both routing events survive — nothing was erased",
      sum(1 for e in after["audit_log"] if e["event"] == "rerouted") == 2)

# ─── refusals on nonsense targets ─────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/route", headers=oh, data={
    "target_step": "admin", "reason": "It is already here",
})
check("routing to the step it already sits at is refused", r.status_code == 400)

r = client.post(f"/requisitions/{req_id}/route", headers=oh, data={
    "target_step": "does-not-exist", "reason": "Nonsense target",
})
check("routing to a step that does not exist is refused", r.status_code == 400)

# ─── only from in_review ───────────────────────────────────────────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Draft Co", "amount": "1000", "category": "supplies", "submit": "false",
})
draft_id = r.json()["id"]
r = client.post(f"/requisitions/{draft_id}/route", headers=fh, data={
    "target_step": "aed", "reason": "Cannot route a draft",
})
check("a draft cannot be routed", r.status_code == 400)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition-routing checks passed.")
