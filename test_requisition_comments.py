"""
End-to-end HTTP test: WO-27, comments on requisitions.

NEEM's ask: "people should be able to view each request and documents
attached to each request and also make comments approve or decline or on
hold." The approve/decline/hold paths already exist (decide(), place_on_hold);
this is the remaining piece — a discussion thread separate from the
one-shot note attached to a single decision.

Deliberately unrestricted by role or status, matching the org-wide
visibility principle already established: anyone signed in can see a
requisition, so anyone signed in can comment on it, at any point in its
life — including after it's paid (an auditor asking a question later is
an entirely ordinary case). No feature flag: a comment thread moves no
money and grants no authority, the same class of always-on capability as
the audit log itself, not an org-specific process choice.

Run: python test_requisition_comments.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_comments_"))
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

client.post("/auth/register", headers=ah, json={
    "email": "finance@neem.org", "name": "Finance", "password": "finance-passphrase",
    "department": "finance", "role": "approver"})
fh = hdr("finance@neem.org", "finance-passphrase")

# A viewer with no stake in the requisition at all — proves comments are
# genuinely open, not restricted to the current step's department.
client.post("/auth/register", headers=ah, json={
    "email": "bystander@neem.org", "name": "Bystander", "password": "bystander-passphrase",
    "department": "compliance", "role": "viewer"})
bh = hdr("bystander@neem.org", "bystander-passphrase")

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
})
check("workflow saved", r.status_code == 200)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Print Shop", "amount": "50000", "category": "supplies",
})
check("requisition raised", r.status_code == 200)
req_id, req_ref = r.json()["id"], r.json()["ref"]
check("starts with no comments", r.json()["comments"] == [])

# ─── a blank comment is refused ─────────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/comments", headers=fh, data={"text": "   "})
check("a blank comment is refused", r.status_code == 400)

# ─── a viewer with no stake in it can still comment — genuinely open ───────

r = client.post(f"/requisitions/{req_id}/comments", headers=bh,
                 data={"text": "Is this the same vendor as last month's request?"})
check("an uninvolved viewer can comment", r.status_code == 200)
body = r.json()
check("comment recorded", len(body["comments"]) == 1)
check("author recorded", body["comments"][0]["author"] == "bystander@neem.org")
check("department recorded", body["comments"][0]["department"] == "compliance")
check("text intact", "same vendor" in body["comments"][0]["text"])
check("timestamped", bool(body["comments"][0]["at"]))

# ─── program (the submitter) is notified of the bystander's comment ───────

prog_inbox = client.get("/notifications", headers=ph).json()["notifications"]
check("submitter's department told about the comment",
      any(n["txn_ref"] == req_ref and n["kind"] == "mention" for n in prog_inbox))


def mention_count(headers) -> int:
    items = client.get("/notifications", headers=headers).json()["notifications"]
    return sum(1 for n in items if n["txn_ref"] == req_ref and n["kind"] == "mention")


# Finance was ALSO told about the bystander's comment (it's the current
# step) — that's the baseline before finance comments itself.
fin_mentions_before = mention_count(fh)
check("finance was told about someone else's comment", fin_mentions_before >= 1)

# ─── a second comment appends, doesn't replace ─────────────────────────────

r = client.post(f"/requisitions/{req_id}/comments", headers=fh,
                 data={"text": "Yes, same vendor — recurring stationery order."})
check("second comment posted", r.status_code == 200)
check("both comments present, in order", [c["text"] for c in r.json()["comments"]] == [
    "Is this the same vendor as last month's request?",
    "Yes, same vendor — recurring stationery order.",
])

# ─── the commenter's own department isn't notified of their own comment —
# the mention count for finance is unchanged after finance comments ────────

check("finance wasn't notified of its own comment",
      mention_count(fh) == fin_mentions_before)

# ─── commenting works after the requisition is decided too — not just
# while it's open ────────────────────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/decide", headers=fh,
                 data={"decision": "approved", "notes": "Recurring order, approved."})
check("approved", r.status_code == 200 and r.json()["status"] == "approved")

r = client.post(f"/requisitions/{req_id}/comments", headers=ah,
                 data={"text": "Confirmed with the vendor — price unchanged."})
check("a comment can be added after approval, not just while open", r.status_code == 200)
check("now three comments, thread never truncated", len(r.json()["comments"]) == 3)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition-comment checks passed.")
