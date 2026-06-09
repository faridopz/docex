"""
DOCex connector framework — pull documents from external systems.

The goal: ingest documents from any system that holds a lot of them (ERPs,
DMS, drives) into the Knowledge Hub, where they become retrieval-searchable.
Every system has a different API, so we normalise them behind ONE small
interface. Adding a new ERP = one new DocumentConnector subclass, registered
in REGISTRY. Nothing else changes — the sync endpoint, dedupe, parsing, and
UI are all provider-agnostic.

To add a provider:
  1. Subclass DocumentConnector (id, label, is_configured, status_detail,
     list_documents, download).
  2. Read its own config from env vars.
  3. Append an instance to REGISTRY.

Built-in providers:
  - erpnext : ERPNext / Frappe (File doctype over REST). See erpnext_connector.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import erpnext_connector as _erpnext


class ConnectorError(RuntimeError):
    """Configuration or transport error talking to an external system."""


@dataclass
class DocumentRef:
    """A normalised handle to one document in an external system."""
    id: str                 # provider-unique id (used for dedupe: "<provider>:<id>")
    name: str               # filename / display name
    handle: str             # provider-specific download handle (e.g. a file_url)
    tags: list[str] = field(default_factory=list)


class DocumentConnector(ABC):
    """One external document source. Implement these five members."""

    id: str = ""            # short slug, e.g. "erpnext"
    label: str = ""         # display name, e.g. "ERPNext"

    @abstractmethod
    def is_configured(self) -> bool:
        """True when the env credentials for this provider are present."""

    @abstractmethod
    def status_detail(self) -> str:
        """A short, non-sensitive status line (e.g. the host) for the UI."""

    @abstractmethod
    def list_documents(self) -> list[DocumentRef]:
        """List the supported documents available to ingest."""

    @abstractmethod
    def download(self, ref: DocumentRef) -> bytes:
        """Fetch the raw bytes of one document."""


# ─── ERPNext / Frappe ───────────────────────────────────────────────────────


class ERPNextConnector(DocumentConnector):
    id = "erpnext"
    label = "ERPNext"

    def is_configured(self) -> bool:
        return _erpnext.is_configured()

    def status_detail(self) -> str:
        return _erpnext.base_host()

    def list_documents(self) -> list[DocumentRef]:
        try:
            files = _erpnext.list_files()
        except _erpnext.ERPNextError as exc:
            raise ConnectorError(str(exc)) from exc
        return [
            DocumentRef(
                id=str(f.get("name")),
                name=f.get("file_name") or str(f.get("name")),
                handle=f.get("file_url") or "",
                tags=_erpnext.tags_for(f),
            )
            for f in files
        ]

    def download(self, ref: DocumentRef) -> bytes:
        try:
            return _erpnext.download_file(ref.handle)
        except _erpnext.ERPNextError as exc:
            raise ConnectorError(str(exc)) from exc


# ─── Registry ───────────────────────────────────────────────────────────────
#
# Add new providers here. Order is the order they appear in the UI.

REGISTRY: list[DocumentConnector] = [
    ERPNextConnector(),
]


def list_connectors() -> list[DocumentConnector]:
    return list(REGISTRY)


def get_connector(provider_id: str) -> DocumentConnector | None:
    return next((c for c in REGISTRY if c.id == provider_id), None)
