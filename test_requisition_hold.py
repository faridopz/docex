"""
End-to-end HTTP test: WO-23, putting a requisition on hold.

NEEM's ask, verbatim: "if a payment is put on hold there should be a reason
why it's put on hold." This is deliberately NOT modelled as a fourth
decide() outcome alongside approve/decline/return — a hold isn't a verdict,
it doesn't leave the approver's queue, and releasing it must resume at the
exact step it paused on. Covers: the reason is mandatory, only the step's
own department may hold or release (same boundary decide() already
enforces), a held requisition cannot be decided out from under the hold,
the flag gates the whole capability, and the notification fired on hold
actually resolves to a working link (the ref-lookup fix in
requisitions.get_requisition()).

Run: python test_requisition_hold.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod
import org_config

_base = Path(tempfile.mkdtemp(prefix="docex_hold_"))
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


# ─── bootstrap: program raises, finance reviews, compliance is a second,
# uninvolved department used to prove the boundary check ───────────────────

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

client.post("/auth/register", headers=ah, json={
    "email": "finance@neem.org", "name": "Finance", "password": "finance-passphrase",
    "department": "finance", "role": "approver"})
fin_tok = client.post("/auth/login", json={
    "email": "finance@neem.org", "password": "finance-passphrase"}).json()["token"]
fh = {"Authorization": f"Bearer {fin_tok}"}

client.post("/auth/register", headers=ah, json={
    "email": "compliance@neem.org", "name": "Compliance", "password": "compliance-passphrase",
    "department": "compliance", "role": "approver"})
comp_tok = client.post("/auth/login", json={
    "email": "compliance@neem.org", "password": "compliance-passphrase"}).json()["token"]
ch = {"Authorization": f"Bearer {comp_tok}"}

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance Review", "department": "finance"}],
})
check("workflow saved", r.status_code == 200)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Regional Print Co", "amount": "80000", "category": "supplies",
})
check("requisition raised, parked with finance", r.status_code == 200)
req = r.json()
req_id, req_ref = req["id"], req["ref"]
check("landed in_review", req["status"] == "in_review")

# ─── flag off: hold refused with a message naming the flag ─────────────────

r = client.post(f"/requisitions/{req_id}/hold", headers=fh, data={"reason": "Waiting on a second quote."})
check("hold refused while the flag is off", r.status_code == 400)
check("refusal names the feature flag", "requisition_hold" in r.json()["detail"])

org_config.set_features("default", requisition_hold=True)

# ─── a blank reason is refused — this is the whole point of the feature ────

r = client.post(f"/requisitions/{req_id}/hold", headers=fh, data={"reason": "   "})
check("blank reason refused (422 — FastAPI's own required-field check)"
      if r.status_code == 422 else "blank reason refused (400 — engine's own check)",
      r.status_code in (400, 422))

# ─── wrong department cannot hold what it doesn't own ───────────────────────

r = client.post(f"/requisitions/{req_id}/hold", headers=ch, data={"reason": "Compliance trying to hold finance's item."})
check("a department the requisition isn't with cannot place a hold", r.status_code == 400)

# ─── the real case ──────────────────────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/hold", headers=fh,
                 data={"reason": "Waiting on a second quote from the vendor."})
check("finance holds its own item", r.status_code == 200)
held = r.json()
check("status is on_hold", held["status"] == "on_hold")
check("current_step untouched — resumes at the same place", held["current_step"] == "finance")
check("hold_reason recorded", held["hold_reason"] == "Waiting on a second quote from the vendor.")
check("held_by recorded", held["held_by"] == "finance@neem.org" or "finance" in (held["held_by"] or ""))
check("held_at recorded", bool(held["held_at"]))

# ─── a held requisition cannot be decided — decide() only accepts in_review
away_from_review = client.post(f"/requisitions/{req_id}/decide", headers=fh,
                                data={"decision": "approved", "notes": "ok"})
check("a held requisition cannot be approved out from under the hold",
      away_from_review.status_code == 400)

# ─── nor held again — place_on_hold also only accepts in_review ────────────

r = client.post(f"/requisitions/{req_id}/hold", headers=fh, data={"reason": "again"})
check("an already-held requisition cannot be held again", r.status_code == 400)

# ─── the submitter's department was told, with the reason, and the ref
# resolves to a real page (this is the get_requisition() ref-lookup fix) ────

prog_notifs = client.get("/notifications", headers=ph,
                          params={"department": "program"}).json()["notifications"]
held_notif = [n for n in prog_notifs if n["txn_ref"] == req_ref and n["kind"] == "held"]
check("submitter's department was notified, kind='held'", len(held_notif) == 1)
check("the notification body carries the actual reason",
      bool(held_notif) and "second quote" in held_notif[0]["body"])

r = client.get(f"/requisitions/{req_ref}", headers=fh)
check("GET by human ref resolves to the same requisition the notification points at",
      r.status_code == 200 and r.json()["id"] == req_id)

# ─── wrong department cannot release it either ──────────────────────────────

r = client.post(f"/requisitions/{req_id}/release-hold", headers=ch, data={})
check("a department the requisition isn't with cannot release the hold either", r.status_code == 400)

# ─── release resumes at the same step, clears the hold fields, and the
# finance queue hears about it again (arriving back = "your turn") ──────────

r = client.post(f"/requisitions/{req_id}/release-hold", headers=fh,
                 data={"notes": "Second quote received, matches the first."})
check("finance releases its own hold", r.status_code == 200)
released = r.json()
check("back to in_review", released["status"] == "in_review")
check("resumed at the SAME step, not re-routed from the top", released["current_step"] == "finance")
check("hold_reason cleared after release", released["hold_reason"] is None)
check("held_by cleared after release", released["held_by"] is None)

fin_notifs = client.get("/notifications", headers=fh,
                         params={"department": "finance"}).json()["notifications"]
resumed = [n for n in fin_notifs if n["txn_ref"] == req_ref and n["kind"] == "assigned"]
check("finance is told it's their turn again on release", len(resumed) >= 1)

# ─── now it can be approved normally — the hold left no scar on the chain ──

r = client.post(f"/requisitions/{req_id}/decide", headers=fh,
                 data={"decision": "approved", "notes": "Second quote checks out."})
check("approves cleanly after the hold is released", r.status_code == 200 and r.json()["status"] == "approved")

# ─── release-hold on something that was never held is refused ──────────────

r = client.post(f"/requisitions/{req_id}/release-hold", headers=fh, data={})
check("releasing a hold that doesn't exist is refused", r.status_code == 400)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition-hold checks passed.")
