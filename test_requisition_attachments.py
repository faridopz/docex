"""
End-to-end HTTP test: WO-22, real file attachments on requisitions.

NEEM's ask, verbatim: "attach as many files as possible" to a request —
the invoice itself, a signed memo, a beneficiary list — not just a ticked
`documents` label saying "invoice: yes". This is the remaining half of
that gap; `documents` (the policy checklist) is untouched.

Uses attachments.LocalDiskAttachmentBackend against a tempdir so the suite
never talks to a network — the same isolation principle as store.py's
JsonFileStore in every other test here. Covers: the flag gates the whole
capability end to end (off ⇒ upload refused, nothing written); an empty
file and an oversized file are both refused before anything is stored;
a valid upload round-trips filename/content_type/size/uploader through
GET; storage_key is never exposed in the JSON response (it's an internal
detail of attachments.py); the download endpoint streams back the exact
bytes and content-type for the local-disk backend, under a filename that
matches what was uploaded; the per-requisition cap refuses further
uploads once hit; and uploading is not restricted to a particular role
or status, matching the design note in requisition_routes.py that
attaching evidence moves no money and grants no authority.

Run: python test_requisition_attachments.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_attachments_"))
store.set_store(store.JsonFileStore(_base / "store"))
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None

import attachments  # noqa: E402
# Point the module at a throwaway directory before the app (and anything
# that might call get_backend() at import time) ever touches it — this is
# the same "install the test double before importing the app" ordering
# store.set_store() above already relies on.
_files = Path(tempfile.mkdtemp(prefix="docex_attachment_files_"))
attachments.set_backend(attachments.LocalDiskAttachmentBackend(_files))

import org_config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import api.main as m  # noqa: E402
import requisitions as rq  # noqa: E402

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

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
})
check("workflow saved", r.status_code == 200)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Sahad Stores", "amount": "60000", "category": "supplies",
})
check("requisition raised", r.status_code == 200)
req_id, req_ref = r.json()["id"], r.json()["ref"]
check("starts with no attachments", r.json()["attachments"] == [])

# ─── flag off: upload refused, nothing written ─────────────────────────────

r = client.post(f"/requisitions/{req_id}/attachments", headers=ph,
                 files={"file": ("invoice.pdf", b"%PDF-fake-bytes", "application/pdf")})
check("flag off: upload refused", r.status_code == 400)
check("refusal names the feature flag", "requisition_attachments" in r.json()["detail"])
check("nothing written to the local-disk backend while off",
      not any(_files.rglob("*")) or not any(p.is_file() for p in _files.rglob("*")))

org_config.set_features("default", requisition_attachments=True)

# ─── an empty file is refused ───────────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/attachments", headers=ph,
                 files={"file": ("empty.txt", b"", "text/plain")})
check("an empty file is refused", r.status_code == 400)

# ─── an oversized file is refused before it's stored ────────────────────────

oversized = b"x" * (attachments.MAX_ATTACHMENT_BYTES + 1)
r = client.post(f"/requisitions/{req_id}/attachments", headers=ph,
                 files={"file": ("huge.bin", oversized, "application/octet-stream")})
check("an oversized file is refused (413)", r.status_code == 413)

# ─── a valid upload round-trips through GET, storage_key never exposed ─────

content = b"%PDF-1.4 fake invoice contents"
r = client.post(f"/requisitions/{req_id}/attachments", headers=ph,
                 files={"file": ("invoice.pdf", content, "application/pdf")})
check("valid upload accepted", r.status_code == 200)
body = r.json()
check("one attachment recorded", len(body["attachments"]) == 1)
att = body["attachments"][0]
check("filename intact", att["filename"] == "invoice.pdf")
check("content_type intact", att["content_type"] == "application/pdf")
check("size intact", att["size"] == len(content))
check("uploader recorded", att["uploaded_by"] == "program@neem.org")
check("timestamped", bool(att["uploaded_at"]))
check("storage_key never exposed in the API response", "storage_key" not in att)

attachment_id = att["id"]

r2 = client.get(f"/requisitions/{req_id}", headers=ph)
check("attachment still present on a fresh GET", len(r2.json()["attachments"]) == 1)

# ─── engine record does carry storage_key (internal, not API-facing) ───────

stored = rq.get_requisition("default", req_id)
check("engine record has a real storage_key", bool(stored.attachments[0].storage_key))
check("bytes actually sit on local disk at that key",
      (_files / stored.attachments[0].storage_key).is_file())
check("bytes on disk match what was uploaded",
      (_files / stored.attachments[0].storage_key).read_bytes() == content)

# ─── download endpoint streams back the exact bytes ─────────────────────────

r = client.get(f"/requisitions/{req_id}/attachments/{attachment_id}", headers=ph)
check("download succeeds", r.status_code == 200)
check("downloaded bytes match the upload", r.content == content)
check("content-type preserved", r.headers.get("content-type", "").startswith("application/pdf"))
check("filename present in Content-Disposition",
      "invoice.pdf" in r.headers.get("content-disposition", ""))

# ─── a missing attachment id 404s ───────────────────────────────────────────

r = client.get(f"/requisitions/{req_id}/attachments/does-not-exist", headers=ph)
check("unknown attachment id 404s", r.status_code == 404)

# ─── uploading isn't role-gated — a plain reviewer (program, who raised
# the request) can attach; that's already exercised above. A second,
# uninvolved department can attach too — attaching evidence grants no
# authority, so it isn't restricted the way decide() is ─────────────────────

client.post("/auth/register", headers=ah, json={
    "email": "compliance@neem.org", "name": "Compliance", "password": "compliance-passphrase",
    "department": "compliance", "role": "viewer"})
ch = hdr("compliance@neem.org", "compliance-passphrase")

r = client.post(f"/requisitions/{req_id}/attachments", headers=ch,
                 files={"file": ("memo.txt", b"Approved by donor liaison.", "text/plain")})
check("an uninvolved viewer can also attach — no role gate", r.status_code == 200)
check("now two attachments", len(r.json()["attachments"]) == 2)

# ─── the per-requisition cap refuses further uploads once hit ──────────────
# Lowered for the test — 50 real uploads would just be slow, not more
# informative about the boundary itself.

rq.MAX_ATTACHMENTS_PER_REQUISITION = 2
r = client.post(f"/requisitions/{req_id}/attachments", headers=ph,
                 files={"file": ("one-too-many.txt", b"nope", "text/plain")})
check("the cap refuses a further upload once hit", r.status_code == 400)
check("refusal explains the cap", "attachment" in r.json()["detail"].lower())

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition-attachment checks passed.")
