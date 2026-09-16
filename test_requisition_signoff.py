"""
WO-33: emailed sign-off on requisitions — escalate, delegate, or send a
payment to someone who has no DOCex account.

The capability existed only on compliance checks, the separate parallel
system being consolidated away. This moves it onto the payment spine, and
the whole point of this suite is that moving it did NOT open a hole: an
emailed approval must be held to exactly the same rules as one made in-app.

Covers:
- a link can be requested for a step, and the request itself is audited
  BEFORE any email is attempted (the delegation is on the record even if
  SMTP is dead)
- the public verify endpoint returns enough to decide on — amount, payee,
  policy checks — not just a reference
- a valid link records a real approval, attributed to the email, and moves
  the requisition through the chain
- the token is bound to one org, one requisition, one step and one email:
  a tampered token is refused, an expired one is refused, and a compliance
  check's token cannot be used here
- a link for a step the requisition has already passed is refused (409),
  rather than silently approving the wrong step
- the self-approval rule still bites when the link is sent to the submitter
- an unknown/garbage token is refused

No SMTP and no network: send_raw_email returns False when SMTP_HOST is
unset, which is exactly the "copy the link by hand" path the route supports.

Run: python test_requisition_signoff.py
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_signoff_"))
store.set_store(store.JsonFileStore(_base / "store"))
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None

import approval_tokens  # noqa: E402
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


# ─── bootstrap: a two-step chain so "the step moved on" is testable ────────

client.post("/auth/register", json={
    "email": "admin@neem.org", "name": "Admin", "password": "admin-passphrase",
    "department": "management", "role": "admin"})
ah = hdr("admin@neem.org", "admin-passphrase")

client.post("/auth/register", headers=ah, json={
    "email": "program@neem.org", "name": "Program", "password": "program-passphrase",
    "department": "program", "role": "reviewer"})
ph = hdr("program@neem.org", "program-passphrase")

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [
        {"key": "finance", "label": "Finance review", "department": "finance"},
        {"key": "aed", "label": "AED approval", "department": "management"},
    ],
})
check("workflow saved with two steps", r.status_code == 200)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Sahad Stores", "amount": "450000", "category": "supplies",
    "description": "Office supplies for the Maiduguri office",
})
check("requisition raised", r.status_code == 200)
req_id, req_ref = r.json()["id"], r.json()["ref"]
check("it starts at the finance step", r.json()["current_step"] == "finance")

# ─── requesting a link ──────────────────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/request-signoff", headers=ph, json={
    "step": "finance", "approver_email": "External.Auditor@Example.com",
    "note": "Please review before Friday's run",
})
check("sign-off can be requested", r.status_code == 200)
body = r.json()
check("a link comes back even with no SMTP configured", bool(body.get("link")))
check("the link is the requisition approve path", "/approve/r/" in body["link"])
check("email is normalised to lowercase", body["approver_email"] == "external.auditor@example.com")
token = body["link"].rsplit("/", 1)[-1]

detail = client.get(f"/requisitions/{req_id}", headers=ph).json()
check("the delegation is on the audit trail",
      any(e["event"] == "signoff_requested" for e in detail["audit_log"]))
check("the audit line names who it was sent to",
      any("external.auditor@example.com" in (e["detail"] or "") for e in detail["audit_log"]))
check("requesting a link changes nothing about the requisition itself",
      detail["status"] == "in_review" and detail["current_step"] == "finance")

r = client.post(f"/requisitions/{req_id}/request-signoff", headers=ph, json={
    "step": "finance", "approver_email": "not-an-email",
})
check("a malformed approver email is refused", r.status_code == 422)

# ─── the public verify endpoint ─────────────────────────────────────────────

r = client.get(f"/requisitions/approve/verify/{token}")
check("verify works with NO authentication at all", r.status_code == 200)
v = r.json()
check("verify carries the amount", v["amount"] == 450000)
check("verify carries the payee", v["payee"] == "Sahad Stores")
check("verify carries amount in words", "Four Hundred Fifty Thousand" in v["amount_in_words"])
check("verify carries the purpose", "Maiduguri" in v["description"])
check("verify carries the policy checks to decide on", len(v["checks"]) > 0)
check("verify names the step", v["step"] == "finance")
check("verify says it is actionable", v["actionable"] is True)

r = client.get("/requisitions/approve/verify/utter-nonsense")
check("a garbage token is refused", r.status_code == 400)

tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
r = client.get(f"/requisitions/approve/verify/{tampered}")
check("a tampered signature is refused", r.status_code == 400)

expired = approval_tokens.make_token(
    req_id, "finance", "external.auditor@example.com", ttl_seconds=-1,
    org="default", kind="requisition")
r = client.get(f"/requisitions/approve/verify/{expired}")
check("an expired link is refused", r.status_code == 400)

# A compliance check's token is the same format and the same secret — it must
# still not work here, or the two systems leak into each other.
check_token = approval_tokens.make_token("some-check-id", "Review", "x@y.com")
r = client.get(f"/requisitions/approve/verify/{check_token}")
check("a compliance-check token cannot approve a requisition", r.status_code == 400)

# A token minted for a DIFFERENT org must not resolve this requisition.
other_org = approval_tokens.make_token(
    req_id, "finance", "x@y.com", org="some-other-org", kind="requisition")
r = client.get(f"/requisitions/approve/verify/{other_org}")
check("a token for another org cannot read this requisition", r.status_code == 404)

# ─── acting on the link ─────────────────────────────────────────────────────

r = client.post(f"/requisitions/approve/{token}", json={
    "action": "approve", "note": "Checked against the quotes.",
})
check("the emailed approval is recorded", r.status_code == 200)
check("it moved to the next step", r.json()["current_step"] == "aed")

detail = client.get(f"/requisitions/{req_id}", headers=ph).json()
approval = detail["approvals"][-1]
check("the approval is attributed to the approver's email",
      approval["actor"] == "external.auditor@example.com")
check("the approval is recorded against the finance step", approval["step"] == "finance")
check("the note survives", "Checked against the quotes" in approval["notes"])
check("the sign-off is marked as having come by email",
      "signed off by email" in approval["notes"])
check("it is signed like any other approval", bool(approval["signature"]))
check("the audit chain still verifies after an emailed approval",
      detail["audit_chain_valid"] is True)

# The same link again — the requisition has moved to the AED step, so the
# finance link must not act a second time.
r = client.post(f"/requisitions/approve/{token}", json={"action": "approve"})
check("the same link cannot be replayed once the step has moved on", r.status_code == 409)
check("the refusal says where it actually is now", "moved on" in r.json()["detail"].lower())

r = client.get(f"/requisitions/approve/verify/{token}")
check("verify now reports it is no longer actionable", r.json()["actionable"] is False)
check("verify reports it has moved", r.json()["already_moved"] is True)

# ─── the self-approval rule still applies to an emailed link ───────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Self Approval Ltd", "amount": "20000", "category": "supplies",
})
self_id = r.json()["id"]
r = client.post(f"/requisitions/{self_id}/request-signoff", headers=ph, json={
    "step": "finance", "approver_email": "program@neem.org",
})
self_token = r.json()["link"].rsplit("/", 1)[-1]
r = client.post(f"/requisitions/approve/{self_token}", json={"action": "approve"})
check("the submitter cannot approve their own requisition by email either",
      r.status_code == 400)

# ─── returning, not just approving ─────────────────────────────────────────

r = client.post(f"/requisitions/{self_id}/request-signoff", headers=ah, json={
    "step": "finance", "approver_email": "reviewer@partner.org",
})
ret_token = r.json()["link"].rsplit("/", 1)[-1]
r = client.post(f"/requisitions/approve/{ret_token}", json={
    "action": "return", "note": "Missing the third quote.",
})
check("an emailed approver can also send it back", r.status_code == 200)
check("returning sets the status to returned", r.json()["status"] == "returned")

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition sign-off checks passed.")
