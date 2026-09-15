"""
End-to-end HTTP test: WO-24, named-person CC on requisitions.

The department-level CCRule from the previous session covered "copy
Management" but not NEEM's literal ask: "certain important people should
be CC'd" — a specific person, by name, regardless of which department
they happen to sit in (or whether they're in the CC'd department at all).

This required a real structural change, not just a new field: the
notification system had no concept of "addressed to one person" at all —
Notification.to_department was the only routing key. Added Notification.
to_user, taught notification_center.list_for/unread_count/mark_all_read to
also match it, and — the part that made it safe — wired real auth onto
GET/POST /notifications (api/transaction_routes.py), which previously took
`department` as a bare, unauthenticated query parameter. Without that fix,
"deliver personally-addressed notifications" would have meant "anyone can
read anyone's personal notifications by asking for their email" — a
regression disguised as a feature. viewer_email now always comes from the
bearer token.

Covers: a named person with NO relation to the CC'd department still gets
it; a department-only CC rule is unaffected (regression); a different
person in the same department as the named recipient does NOT see their
personal CC; the personal item surfaces regardless of which department
query the recipient uses (including the default); and it clears via the
recipient's own mark-all-read.

Run: python test_requisition_cc_named.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_cc_named_"))
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


# ─── bootstrap ──────────────────────────────────────────────────────────────

client.post("/auth/register", json={
    "email": "admin@neem.org", "name": "Admin", "password": "admin-passphrase",
    "department": "management", "role": "admin"})
ah = hdr("admin@neem.org", "admin-passphrase")

client.post("/auth/register", headers=ah, json={
    "email": "program@neem.org", "name": "Program", "password": "program-passphrase",
    "department": "program", "role": "reviewer"})
ph = hdr("program@neem.org", "program-passphrase")

# The Executive Director sits in "compliance" for auth/department-dashboard
# purposes — nothing to do with the CC rule that names her. This is the
# whole point: a named CC must not depend on the recipient's department.
client.post("/auth/register", headers=ah, json={
    # Role "approver" on purpose: she clears the role gate on decide(), so the
    # test below exercises decide()'s DEPARTMENT check specifically — proving
    # a personal CC grants no authority even for someone otherwise senior
    # enough to approve things, not just proving a viewer can't act (which
    # would be true of anyone and wouldn't isolate what CC does or doesn't do).
    "email": "ed@neem.org", "name": "ED", "password": "ed-passphrase",
    "department": "compliance", "role": "approver"})
eh = hdr("ed@neem.org", "ed-passphrase")

# A second person in the SAME department as the ED — used to prove a
# personal CC does not leak to everyone who shares that department.
client.post("/auth/register", headers=ah, json={
    "email": "other-compliance@neem.org", "name": "Other Compliance",
    "password": "other-passphrase", "department": "compliance", "role": "viewer"})
oh = hdr("other-compliance@neem.org", "other-passphrase")

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "management", "label": "Management", "department": "management"}],
    "cc_rules": [
        # Pure named-person rule: no department at all.
        {"min_amount": 2_000_000, "department": "", "label": "Executive Director",
         "emails": ["ed@neem.org"]},
        # Pure department rule — unchanged behaviour, regression check.
        {"min_amount": 500_000, "department": "management", "label": "Leadership",
         "emails": []},
    ],
})
check("workflow with a named-only CC rule saved", r.status_code == 200)
check("emails round-trip through the workflow API",
      r.json()["cc_rules"][0]["emails"] == ["ed@neem.org"])

# ─── below every threshold: nobody copied ───────────────────────────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Office Supplies Ltd", "amount": "100000", "category": "supplies",
})
check("small requisition raised", r.status_code == 200)
small_ref = r.json()["ref"]

ed_inbox = client.get("/notifications", headers=eh).json()["notifications"]
check("ED not copied below her threshold", not any(n["txn_ref"] == small_ref for n in ed_inbox))

# ─── crosses the department threshold only (500k) — not the ED's (2M) ──────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Regional Training Vendor", "amount": "800000", "category": "supplies",
})
check("mid-size requisition raised", r.status_code == 200)
mid_ref = r.json()["ref"]

mgmt_inbox = client.get("/notifications", headers=ah).json()["notifications"]
mgmt_cc = [n for n in mgmt_inbox if n["txn_ref"] == mid_ref and n["kind"] == "cc"]
check("management (department rule) copied at 800k", len(mgmt_cc) == 1)
check("that copy has no to_user — it's a department broadcast, not personal",
      mgmt_cc[0].get("to_user") in (None, ""))

ed_inbox = client.get("/notifications", headers=eh).json()["notifications"]
check("ED still not copied — 800k hasn't crossed her 2M threshold",
      not any(n["txn_ref"] == mid_ref for n in ed_inbox))

# ─── crosses the ED's named threshold (2M+) ─────────────────────────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Annual Conference Venue", "amount": "2500000", "category": "supplies",
})
check("large requisition raised", r.status_code == 200)
big_ref = r.json()["ref"]
big_id = r.json()["id"]

# The ED sees it in HER OWN department's feed (compliance) — the personal
# match works regardless of the query, including no department param at all
# (defaults to her own department).
ed_inbox_default = client.get("/notifications", headers=eh).json()["notifications"]
ed_cc = [n for n in ed_inbox_default if n["txn_ref"] == big_ref]
check("ED personally copied, found via her own (default) department feed", len(ed_cc) == 1)
check("her copy is kind='cc'", ed_cc[0]["kind"] == "cc" if ed_cc else False)
check("her copy is addressed to her personally (to_user)",
      bool(ed_cc) and ed_cc[0].get("to_user") == "ed@neem.org")

# Explicitly querying a DIFFERENT department still surfaces her personal item
# — a personal CC isn't confined to whichever department filter is active.
ed_inbox_other_dept = client.get("/notifications", headers=eh,
                                   params={"department": "program"}).json()["notifications"]
check("her personal copy also surfaces when she queries an unrelated department",
      any(n["txn_ref"] == big_ref for n in ed_inbox_other_dept))

# The colleague in the SAME department does NOT see it — this was never
# broadcast to "compliance", it was addressed to one person.
other_inbox = client.get("/notifications", headers=oh).json()["notifications"]
check("a colleague in the ED's own department does not see her personal CC",
      not any(n["txn_ref"] == big_ref for n in other_inbox))

# management is copied AGAIN too (the 500k rule also matches 2.5M — every
# matching rule fires, unchanged from before this feature).
mgmt_inbox = client.get("/notifications", headers=ah).json()["notifications"]
check("management also copied on the same large requisition (department rule still fires)",
      any(n["txn_ref"] == big_ref and n["kind"] == "cc" and not n.get("to_user")
          for n in mgmt_inbox))

# ─── being personally CC'd grants no approval authority, exactly like a
# department CC rule — decide() only ever checks the step's department ─────

r = client.post(f"/requisitions/{big_id}/decide", headers=eh,
                 data={"decision": "approved", "notes": "ED trying to approve from her CC"})
check("being personally CC'd does not grant approval authority", r.status_code == 400)

# ─── the personal notification clears via the ED's own mark-all-read,
# using her real department (not the CC rule's, which had none) ────────────

r = client.post("/notifications/read-all", headers=eh, params={"department": "compliance"})
check("mark-all-read (ED's own department) succeeds", r.status_code == 200)
ed_inbox_after = client.get("/notifications", headers=eh,
                             params={"unread_only": "true"}).json()["notifications"]
check("her personal CC is now read", not any(n["txn_ref"] == big_ref for n in ed_inbox_after))

# ─── auth is now required — the endpoint used to take a bare query param ───

r = client.get("/notifications")
check("GET /notifications now requires auth", r.status_code == 401)
r = client.post("/notifications/read-all")
check("POST /notifications/read-all now requires auth too", r.status_code == 401)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll named-person CC checks passed.")
