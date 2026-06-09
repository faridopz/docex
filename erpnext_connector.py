"""
DOCex ↔ ERPNext connector.

Sydani (and many NGOs) keep their knowledge base — proposals, inception
documents, implementation strategies, training material — as file
attachments inside ERPNext (built on the Frappe framework). The pain isn't
storage; it's findability: you have to open documents one by one to find
the relevant one.

This connector pulls those documents OUT of ERPNext into DOCex's Knowledge
Hub, where they become retrieval-searchable (see retrieval.py). We index a
copy and sync periodically rather than querying ERPNext live on every
search — search stays instant and keeps working even when the ERP is slow.

ERPNext / Frappe REST API used here:
  - Auth:  Authorization: token <api_key>:<api_secret>
  - List:  GET /api/resource/File?fields=[...]&filters=[...]&limit_page_length=N&limit_start=M
  - File:  the "File" doctype holds every attachment, with file_url,
           file_name, is_private, attached_to_doctype/attached_to_name.
  - Download: GET <base_url><file_url> with the same auth header.

Configuration (env vars):
  ERPNEXT_URL          e.g. https://erp.sydani.org   (no trailing slash needed)
  ERPNEXT_API_KEY      from ERPNext: User > API Access > Generate Keys
  ERPNEXT_API_SECRET
"""
from __future__ import annotations

import json
import os
from urllib.parse import quote, urljoin

import requests

# Document types the Knowledge Hub can parse. Everything else (images,
# spreadsheets, zips) is skipped during sync.
SUPPORTED_EXTENSIONS = (".pptx", ".pptm", ".pdf", ".docx", ".docm")

_TIMEOUT = 30.0


def _config() -> tuple[str, str, str]:
    base = os.environ.get("ERPNEXT_URL", "").strip().rstrip("/")
    key = os.environ.get("ERPNEXT_API_KEY", "").strip()
    secret = os.environ.get("ERPNEXT_API_SECRET", "").strip()
    return base, key, secret


def is_configured() -> bool:
    base, key, secret = _config()
    return bool(base and key and secret)


def base_host() -> str:
    """The host portion of the configured URL, for display (no secrets)."""
    base, _, _ = _config()
    return base


def _headers() -> dict[str, str]:
    _, key, secret = _config()
    return {"Authorization": f"token {key}:{secret}", "Accept": "application/json"}


class ERPNextError(RuntimeError):
    """Raised on configuration or transport errors talking to ERPNext."""


def _require_config() -> str:
    base, key, secret = _config()
    if not (base and key and secret):
        raise ERPNextError(
            "ERPNext isn't configured. Set ERPNEXT_URL, ERPNEXT_API_KEY and "
            "ERPNEXT_API_SECRET in the backend .env."
        )
    return base


def list_files(
    *,
    extra_filters: list | None = None,
    page_size: int = 100,
    max_files: int = 1000,
) -> list[dict]:
    """List File records from ERPNext, newest first, paginated.

    Returns dicts with: name, file_name, file_url, is_private,
    attached_to_doctype, attached_to_name, modified. Only files whose
    name ends in a supported extension are returned.

    `extra_filters` is passed straight through as Frappe filter syntax,
    e.g. [["attached_to_doctype", "=", "Project"]] to limit to project
    attachments, or [["folder", "=", "Home/Knowledge Base"]].
    """
    base = _require_config()
    fields = [
        "name",
        "file_name",
        "file_url",
        "is_private",
        "attached_to_doctype",
        "attached_to_name",
        "modified",
    ]
    out: list[dict] = []
    start = 0
    while len(out) < max_files:
        params = {
            "fields": json.dumps(fields),
            "limit_page_length": str(page_size),
            "limit_start": str(start),
            "order_by": "modified desc",
        }
        if extra_filters:
            params["filters"] = json.dumps(extra_filters)
        url = f"{base}/api/resource/File"
        try:
            resp = requests.get(
                url, headers=_headers(), params=params, timeout=_TIMEOUT
            )
        except requests.RequestException as exc:
            raise ERPNextError(f"Could not reach ERPNext at {base}: {exc}") from exc
        if resp.status_code in (401, 403):
            raise ERPNextError(
                "ERPNext rejected the API key/secret (401/403). Check the "
                "credentials and that the user has read access to File."
            )
        if not resp.ok:
            raise ERPNextError(
                f"ERPNext returned {resp.status_code}: {resp.text[:300]}"
            )
        batch = resp.json().get("data", [])
        if not batch:
            break
        for f in batch:
            fn = (f.get("file_name") or f.get("file_url") or "").lower()
            if fn.endswith(SUPPORTED_EXTENSIONS):
                out.append(f)
        if len(batch) < page_size:
            break
        start += page_size
    return out


def download_file(file_url: str) -> bytes:
    """Download a File's bytes by its file_url (e.g. '/files/x.pdf' or
    '/private/files/x.pdf'). Uses the same token auth so private files work."""
    base = _require_config()
    # file_url is server-relative; join onto the base. quote the path so
    # spaces/odd characters in filenames don't break the request.
    safe = quote(file_url, safe="/:%")
    url = urljoin(base + "/", safe.lstrip("/"))
    try:
        resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise ERPNextError(f"Could not download {file_url}: {exc}") from exc
    if not resp.ok:
        raise ERPNextError(
            f"Download of {file_url} failed ({resp.status_code})."
        )
    return resp.content


def source_ref_for(file_record: dict) -> str:
    """Stable dedupe key for an ERPNext file (its unique File.name)."""
    return f"erpnext:{file_record.get('name')}"


def tags_for(file_record: dict) -> list[str]:
    """Helpful tags derived from where the file is attached in ERPNext."""
    tags = ["ERPNext"]
    dt = file_record.get("attached_to_doctype")
    dn = file_record.get("attached_to_name")
    if dt:
        tags.append(str(dt))
    if dn:
        tags.append(str(dn))
    return tags
