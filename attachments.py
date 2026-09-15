"""
attachments.py — where the BYTES of a requisition's files actually live.

`requisitions.Attachment` (and `Requisition.attachments`) hold the METADATA
— filename, size, who uploaded it, an opaque `storage_key` — in the same
org-scoped store as everything else, so it travels with backups/exports
like the rest of the record. This module holds the bytes themselves, behind
a small pluggable backend, exactly the way store.py separates the Store
Protocol from JsonFileStore/PostgresStore:

  - LocalDiskAttachmentBackend — dev/test only. Files under a directory on
    local disk. Selected automatically when no Supabase config is present.
    NOT durable in production: Render's free-tier container disk is wiped
    on every redeploy (see CLAUDE.md). Every test in this codebase that
    touches attachments uses this backend, in a tempdir, and never talks to
    a network.

  - SupabaseStorageBackend — the production backend. DOCex already trusts
    Supabase for Postgres (DOCEX_DATABASE_URL); this is the same vendor's
    object storage, so onboarding a client adds no new vendor to explain or
    bill. Talks to the Storage REST API directly over httpx — the same
    library bank_verify.py already uses for Paystack — rather than pulling
    in a new SDK for two endpoints (upload, sign a download URL).

    Configured from SUPABASE_URL + DOCEX_SUPABASE_STORAGE_KEY. That second
    name is deliberately NOT "SUPABASE_SERVICE_ROLE_KEY" or anything
    DOCEX_DATABASE_URL-adjacent: it is a different credential serving a
    different purpose, in its own env var, so rotating one can never be
    confused with rotating the other.

    On using the service_role key here specifically, after
    check_supabase.py spends a whole file arguing against it: that
    argument is about the Postgres DATA API, which is reachable from the
    public internet over HTTPS by design — a leaked anon/service key there
    is a leaked database. Storage operations in this module run only from
    this server process, never from a browser, never logged, never
    returned to a client. That is the same trust boundary any other
    object-storage credential (an S3 access key, a GCS service account)
    already sits behind. A scoped, storage-only Supabase key would be
    strictly better if the project ever adds one; until then this is
    documented as a deliberate, bounded exception — not an oversight.

Nothing in this module executes or interprets uploaded content. Bytes go in,
bytes (or a signed URL to fetch them) come out. That is what makes an
arbitrary file type safe to accept without a virus scanner: it is never
opened by anything on this server, only stored and handed back.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Protocol

import httpx

# Generous for a scanned invoice or a phone photo of a receipt, small enough
# that one bad upload can't quietly fill a disk or a bucket.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


class AttachmentError(ValueError):
    """Refused: too large, storage unreachable, not found."""


class AttachmentBackend(Protocol):
    def put(
        self, org_id: str, req_id: str, attachment_id: str, filename: str,
        content: bytes, content_type: str,
    ) -> str:
        """Store the bytes. Returns an opaque storage_key — only this
        module's own backends ever interpret it."""
        ...

    def url(self, storage_key: str, *, expires_in: int = 3600) -> str:
        """A URL the browser can fetch the file from directly, valid for
        `expires_in` seconds. Never a permanent public URL. Returns "" if
        this backend has no such mechanism (LocalDiskAttachmentBackend) —
        callers fall back to streaming the bytes through the API instead."""
        ...

    def read(self, storage_key: str) -> bytes:
        """Fetch the stored bytes directly — for server-side use only (e.g.
        extracting text for a compliance check), never returned to a
        browser as-is. Every backend implements this directly rather than
        making callers round-trip through url(): LocalDiskAttachmentBackend
        has no URL mechanism at all, and a server-side caller has no reason
        to pay for a signed-URL round trip when it can read the bytes in
        one call."""
        ...


def _safe_key_part(name: str) -> str:
    """A filename safe to use as (part of) a storage path — this is a path
    fragment, not a filesystem display name, so keep it boring: letters,
    digits, dot, dash, underscore. Everything else becomes '_' rather than
    being silently dropped, so two different unsafe names can't collide
    into the same key."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name.strip())
    return cleaned[:150] or "file"


class LocalDiskAttachmentBackend:
    """Dev/test only — see module docstring. Not durable in production."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or (Path(__file__).parent / "attachment_files")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        # storage_key is generated by this class (put(), below), never taken
        # verbatim from a client — but a defensive resolve+containment check
        # costs nothing and stops a future caller from being the first one
        # that DOES pass through something client-supplied.
        p = (self.root / storage_key).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise AttachmentError("Invalid storage key.")
        return p

    def put(self, org_id, req_id, attachment_id, filename, content, content_type) -> str:
        key = f"{org_id}/{req_id}/{attachment_id}-{_safe_key_part(filename)}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return key

    def read(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        if not path.is_file():
            raise AttachmentError("Stored file not found.")
        return path.read_bytes()

    def url(self, storage_key: str, *, expires_in: int = 3600) -> str:
        return ""


class SupabaseStorageBackend:
    """See module docstring for the full design rationale."""

    def __init__(self, base_url: str, service_key: str, bucket: str):
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.bucket = bucket

    def _headers(self, content_type: Optional[str] = None) -> dict:
        h = {"Authorization": f"Bearer {self.service_key}", "apikey": self.service_key}
        if content_type:
            h["Content-Type"] = content_type
        return h

    def put(self, org_id, req_id, attachment_id, filename, content, content_type) -> str:
        key = f"{org_id}/{req_id}/{attachment_id}-{_safe_key_part(filename)}"
        try:
            resp = httpx.post(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
                headers=self._headers(content_type or "application/octet-stream"),
                content=content,
                timeout=60,
            )
        except httpx.HTTPError as exc:
            raise AttachmentError(f"Could not reach storage: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise AttachmentError(
                f"Storage upload failed ({resp.status_code}): {resp.text[:300]}"
            )
        return key

    def url(self, storage_key: str, *, expires_in: int = 3600) -> str:
        try:
            resp = httpx.post(
                f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{storage_key}",
                headers=self._headers("application/json"),
                json={"expiresIn": expires_in},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise AttachmentError(f"Could not reach storage: {exc}") from exc
        if resp.status_code != 200:
            raise AttachmentError(
                f"Could not sign a download URL ({resp.status_code}): {resp.text[:300]}"
            )
        signed = (resp.json() or {}).get("signedURL", "")
        if not signed:
            raise AttachmentError("Storage did not return a signed URL.")
        # Supabase returns a path like "/object/sign/<bucket>/<key>?token=...";
        # the caller needs the full URL.
        return f"{self.base_url}/storage/v1{signed}"

    def read(self, storage_key: str) -> bytes:
        # A direct authenticated GET, not a signed-URL round trip — this
        # only ever runs server-side (see the Protocol docstring), so there
        # is nothing to gain from minting a temporary URL first.
        try:
            resp = httpx.get(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{storage_key}",
                headers=self._headers(), timeout=60,
            )
        except httpx.HTTPError as exc:
            raise AttachmentError(f"Could not reach storage: {exc}") from exc
        if resp.status_code != 200:
            raise AttachmentError(
                f"Could not fetch stored file ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.content


_backend: Optional[AttachmentBackend] = None


def get_backend() -> AttachmentBackend:
    global _backend
    if _backend is None:
        _backend = _from_env()
    return _backend


def set_backend(backend: AttachmentBackend) -> None:
    """Install a different backend — tests, or explicit wiring at boot."""
    global _backend
    _backend = backend


def is_configured() -> bool:
    return _backend is not None


def _from_env() -> AttachmentBackend:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("DOCEX_SUPABASE_STORAGE_KEY", "").strip()
    bucket = os.environ.get("DOCEX_SUPABASE_STORAGE_BUCKET", "requisition-attachments").strip()
    if url and key:
        return SupabaseStorageBackend(url, key, bucket or "requisition-attachments")
    print("[attachments] SUPABASE_URL / DOCEX_SUPABASE_STORAGE_KEY not set — using "
          "local disk. NOT durable in production (CLAUDE.md: local disk is wiped on "
          "every redeploy). Set both to switch to Supabase Storage before go-live.")
    return LocalDiskAttachmentBackend()
