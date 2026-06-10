"""
DOCex ↔ Odoo connector.

Odoo (the other common open-source ERP) exposes an external API over
XML-RPC. Every file in Odoo lives in the `ir.attachment` model — its
`datas` field holds the base64-encoded content, with `mimetype`,
`res_model` and `res_id` describing what the file is attached to.

This connector authenticates with an API key (works as the password in
Odoo 14+), lists supported document attachments, and downloads their bytes.
`xmlrpc.client` is in the Python standard library, so there's no new
dependency.

Configuration (env vars):
  ODOO_URL       e.g. https://sydani.odoo.com
  ODOO_DB        the database name
  ODOO_USERNAME  the login (email) of an API user
  ODOO_API_KEY   the user's API key (Settings > Account Security > API Keys)
"""
from __future__ import annotations

import base64
import os
import xmlrpc.client

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".docm", ".pptx", ".pptm")


class OdooError(RuntimeError):
    """Configuration or transport error talking to Odoo."""


def _config() -> tuple[str, str, str, str]:
    url = os.environ.get("ODOO_URL", "").strip().rstrip("/")
    db = os.environ.get("ODOO_DB", "").strip()
    user = os.environ.get("ODOO_USERNAME", "").strip()
    key = os.environ.get("ODOO_API_KEY", "").strip()
    return url, db, user, key


def is_configured() -> bool:
    url, db, user, key = _config()
    return bool(url and db and user and key)


def base_host() -> str:
    url, _, _, _ = _config()
    return url


# Cache the authenticated session so we don't re-authenticate on every file
# download. Keyed by config so it refreshes if the env changes.
_session: dict | None = None


def _connect() -> tuple[int, xmlrpc.client.ServerProxy, str, str]:
    global _session
    url, db, user, key = _config()
    if not (url and db and user and key):
        raise OdooError(
            "Odoo isn't configured. Set ODOO_URL, ODOO_DB, ODOO_USERNAME and "
            "ODOO_API_KEY in the backend .env."
        )
    if _session and _session.get("cfg") == (url, db, user):
        return _session["uid"], _session["models"], db, key

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, key, {})
    except Exception as exc:  # noqa: BLE001
        raise OdooError(f"Could not reach Odoo at {url}: {exc}") from exc
    if not uid:
        raise OdooError(
            "Odoo rejected the credentials. Check ODOO_DB, ODOO_USERNAME and "
            "ODOO_API_KEY."
        )
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    _session = {"cfg": (url, db, user), "uid": uid, "models": models}
    return uid, models, db, key


def _execute(model: str, method: str, args: list, kwargs: dict | None = None):
    uid, models, db, key = _connect()
    try:
        return models.execute_kw(db, uid, key, model, method, args, kwargs or {})
    except Exception as exc:  # noqa: BLE001
        raise OdooError(f"Odoo {model}.{method} failed: {exc}") from exc


def list_files(*, page_size: int = 200, max_files: int = 1000) -> list[dict]:
    """List supported document attachments from ir.attachment, newest first.

    Returns dicts with: id, name, mimetype, res_model, res_id. Filters to
    file attachments whose name ends in a supported extension via an OR
    domain so Odoo does the filtering server-side.
    """
    # Build an OR domain over the supported extensions (Polish notation).
    leaves = [("name", "=ilike", f"%{ext}") for ext in SUPPORTED_EXTENSIONS]
    domain: list = ["|"] * (len(leaves) - 1) + leaves
    # Only real binary attachments (skip URL attachments).
    domain = ["&", ("type", "=", "binary")] + domain

    out: list[dict] = []
    offset = 0
    while len(out) < max_files:
        recs = _execute(
            "ir.attachment",
            "search_read",
            [domain],
            {
                "fields": ["id", "name", "mimetype", "res_model", "res_id"],
                "limit": page_size,
                "offset": offset,
                "order": "id desc",
            },
        )
        if not recs:
            break
        out.extend(recs)
        if len(recs) < page_size:
            break
        offset += page_size
    return out[:max_files]


def download(attachment_id: str | int) -> bytes:
    """Download an attachment's bytes by id (base64-decoded from `datas`)."""
    recs = _execute(
        "ir.attachment",
        "read",
        [[int(attachment_id)]],
        {"fields": ["datas"]},
    )
    if not recs or not recs[0].get("datas"):
        raise OdooError(f"Attachment {attachment_id} has no downloadable content.")
    try:
        return base64.b64decode(recs[0]["datas"])
    except Exception as exc:  # noqa: BLE001
        raise OdooError(f"Could not decode attachment {attachment_id}: {exc}") from exc


def source_id(rec: dict) -> str:
    return str(rec.get("id"))


def tags_for(rec: dict) -> list[str]:
    tags = ["Odoo"]
    if rec.get("res_model"):
        tags.append(str(rec["res_model"]))
    return tags
