"""
DOCex storage layer — org-scoped, backend-swappable persistence.

WHY THIS EXISTS
DOCex is becoming a product that many organisations run on (TA Connect, EVA,
Neem, and any mid-tier NGO with the same shape of finance function). Two
consequences drive this module:

  1. **Every record belongs to an organisation.** `org_id` is part of the storage
     key, not an afterthought — Org A must never be able to read Org B's
     agreements, payroll or payments. Retrofitting tenancy later is one of the
     most painful migrations there is, so we pay for it now, while it's cheap.

  2. **The backend must be swappable.** Today records are JSON files on local
     disk, which is EPHEMERAL on the current host (wiped on redeploy). The audit
     trail is the product's most valuable asset, so it will move to Postgres +
     object storage. Engines are written against the `Store` protocol, so that
     migration touches this file and nothing else.

Design notes:
  - Keys are validated (no path traversal) because collection/record ids can come
    from user input.
  - Reads never raise on a corrupt record: it's skipped with a warning, so one
    bad file can't take down a whole listing.
  - No LLM, no network. Pure persistence — trivially testable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator, Optional, Protocol

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class StoreError(ValueError):
    """Invalid key, or a backend failure the caller should surface as 4xx/5xx."""


def _validate(part: str, what: str) -> str:
    """Reject anything that could escape its directory or collide oddly."""
    if not part or not _SAFE_KEY.match(part) or ".." in part:
        raise StoreError(f"Invalid {what}: {part!r}")
    return part


class Store(Protocol):
    """The persistence contract every engine writes against.

    Implementations must scope every operation by org_id. `collection` is the
    record type ("agreements", "payroll_runs", ...); `record_id` is unique
    within (org, collection).
    """

    def put(self, org_id: str, collection: str, record_id: str, data: dict) -> dict: ...
    def get(self, org_id: str, collection: str, record_id: str) -> Optional[dict]: ...
    def list(self, org_id: str, collection: str) -> list[dict]: ...
    def delete(self, org_id: str, collection: str, record_id: str) -> bool: ...
    def collections(self, org_id: str) -> list[str]: ...


class JsonFileStore:
    """Local-disk JSON backend: {root}/{org_id}/{collection}/{record_id}.json

    Good enough for demos and single-node use. NOT durable on an ephemeral
    container filesystem — see the module docstring. Swap for PostgresStore
    without touching any engine.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)

    # ── paths ────────────────────────────────────────────────────────────────

    def _dir(self, org_id: str, collection: str) -> Path:
        return (
            self.root
            / _validate(org_id, "org id")
            / _validate(collection, "collection")
        )

    def _path(self, org_id: str, collection: str, record_id: str) -> Path:
        return self._dir(org_id, collection) / f"{_validate(record_id, 'record id')}.json"

    # ── operations ───────────────────────────────────────────────────────────

    def put(self, org_id: str, collection: str, record_id: str, data: dict) -> dict:
        path = self._path(org_id, collection, record_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Stamp the owning org on the record itself. Belt and braces: even if a
        # file is later moved or exported, it says who it belongs to.
        payload = {**data, "org_id": org_id}
        path.write_text(json.dumps(payload, indent=2, default=str))
        return payload

    def get(self, org_id: str, collection: str, record_id: str) -> Optional[dict]:
        path = self._path(org_id, collection, record_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception as exc:
            print(f"Warning: corrupt record {path.name}: {exc}")
            return None

    def list(self, org_id: str, collection: str) -> list[dict]:
        directory = self._dir(org_id, collection)
        if not directory.exists():
            return []
        out: list[dict] = []
        for path in sorted(directory.glob("*.json")):
            try:
                out.append(json.loads(path.read_text()))
            except Exception as exc:
                print(f"Warning: skipping corrupt record {path.name}: {exc}")
        return out

    def delete(self, org_id: str, collection: str, record_id: str) -> bool:
        path = self._path(org_id, collection, record_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def collections(self, org_id: str) -> list[str]:
        org_dir = self.root / _validate(org_id, "org id")
        if not org_dir.exists():
            return []
        return sorted(p.name for p in org_dir.iterdir() if p.is_dir())


# ─── module-level default store ─────────────────────────────────────────────
# Engines call get_store() rather than constructing one, so tests can redirect
# storage to a temp dir and production can later swap in Postgres centrally.

_DEFAULT_ROOT = Path(__file__).parent / "data"
_store: Optional[Store] = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = JsonFileStore(_DEFAULT_ROOT)
    return _store


def set_store(store: Store) -> None:
    """Install a different backend (tests, or PostgresStore in production)."""
    global _store
    _store = store


def is_configured() -> bool:
    """True once something has explicitly installed a backend. api/main.py
    checks this so a test that redirected storage before importing the app
    isn't silently pointed back at the real data directory."""
    return _store is not None


# ─── helpers engines share ──────────────────────────────────────────────────


def iter_records(org_id: str, collection: str) -> Iterator[dict]:
    yield from get_store().list(org_id, collection)


def require_org(org_id: Optional[str]) -> str:
    """Every engine call must name its organisation. Fail loudly rather than
    silently reading or writing someone else's data."""
    if not org_id or not str(org_id).strip():
        raise StoreError("org_id is required for every storage operation.")
    return _validate(str(org_id).strip(), "org id")
