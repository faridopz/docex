"""
DOCex departments registry — each organisation defines its own departments.

Why this exists: departments used to be a hard-coded set of four
(compliance/finance/program/management). Real orgs differ — EVA runs
Program / Compliance / Finance / TLFA / ED, with the ED holding final
authorisation. This module makes the list data, not code, while keeping every
existing record valid (the defaults reproduce the old four exactly).

It owns two things:
  1. The department list (key + display name + order).
  2. The state -> owning-department map, so an org routes its own workflow
     (who the ball sits with at each stage of the transaction state machine).

Persisted as ONE record in the org-scoped store (collection "config", record
"departments"), so each organisation carries its own registry and it survives a
redeploy when DOCEX_DB is set. Never raises on a missing/corrupt record: it
falls back to the built-in defaults so the app always boots.

Every public function takes an optional org_id; omitted means the instance
default (DOCEX_ORG). Existing single-org callers therefore need no change.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from typing import Optional

import store
from models import DepartmentDef, DepartmentRegistry

_CONFIG = "config"                     # store collection
_REGISTRY_ID = "departments"           # record id within it


def _org(org_id: Optional[str] = None) -> str:
    explicit = (org_id or "").strip()
    if explicit:
        return store.require_org(explicit)
    return store.require_org((os.environ.get("DOCEX_ORG") or "default").strip() or "default")

# The original four — kept as the seed so existing installs behave identically.
_DEFAULT_DEPARTMENTS: list[DepartmentDef] = [
    DepartmentDef(key="program", name="Program / M&E",
                  description="Initiates requests and assembles documentation", order=10),
    DepartmentDef(key="compliance", name="Compliance",
                  description="Checks payments against policy and donor rules", order=20),
    DepartmentDef(key="finance", name="Finance",
                  description="Verifies accuracy, budget and processes payment", order=30),
    DepartmentDef(key="management", name="Management",
                  description="Final approval and authorisation", order=40,
                  is_final_authority=True),
]

# Default workflow ownership — mirrors the previous hard-coded _STATE_OWNER.
_DEFAULT_STATE_OWNERS: dict[str, str] = {
    "submitted": "program",
    "intake": "program",
    "compliance_review": "compliance",
    "finance_review": "finance",
    "approval": "management",
    "paid": "finance",
    # "returned" deliberately has NO owner — the return event names who must fix it.
}


class DepartmentError(ValueError):
    """Invalid key / unknown department / attempt to delete one still in use."""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    """Turn a display name into a stable key: 'Finance & Admin' -> 'finance-admin'."""
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    if not s:
        raise DepartmentError("Department name must contain at least one letter or number.")
    return s


def default_registry() -> DepartmentRegistry:
    return DepartmentRegistry(
        departments=list(_DEFAULT_DEPARTMENTS),
        state_owners=dict(_DEFAULT_STATE_OWNERS),
        updated_at=_now_iso(),
    )


def migrate_legacy_registry(org_id: Optional[str] = None) -> bool:
    """One-time import of the pre-store {root}/departments.json file. Only
    runs when the org has no registry in the store yet. Returns True if
    something was imported."""
    from pathlib import Path
    legacy = Path(__file__).parent / "departments.json"
    if not legacy.exists():
        return False
    org = _org(org_id)
    if store.get_store().get(org, _CONFIG, _REGISTRY_ID) is not None:
        return False
    try:
        reg = DepartmentRegistry.model_validate_json(legacy.read_text())
    except Exception as exc:
        print(f"Warning: legacy departments.json unreadable ({exc}); not imported.")
        return False
    if not reg.departments:
        return False
    save(reg, org)
    print(f"[departments] Imported legacy departments.json into org '{org}'.")
    return True


def load(org_id: Optional[str] = None) -> DepartmentRegistry:
    """Load the registry, falling back to defaults if absent or unreadable."""
    raw = store.get_store().get(_org(org_id), _CONFIG, _REGISTRY_ID)
    if raw is None:
        return default_registry()
    try:
        reg = DepartmentRegistry.model_validate(raw)
    except Exception as exc:
        print(f"Warning: departments registry unreadable ({exc}); using defaults.")
        return default_registry()
    if not reg.departments:            # empty record → defaults, never an empty app
        return default_registry()
    if not reg.state_owners:
        reg.state_owners = dict(_DEFAULT_STATE_OWNERS)
    return reg


def save(reg: DepartmentRegistry, org_id: Optional[str] = None) -> DepartmentRegistry:
    reg.updated_at = _now_iso()
    reg.departments.sort(key=lambda d: (d.order, d.name))
    store.get_store().put(_org(org_id), _CONFIG, _REGISTRY_ID, reg.model_dump())
    return reg


def list_departments(org_id: Optional[str] = None) -> list[DepartmentDef]:
    return load(org_id).departments


def keys(org_id: Optional[str] = None) -> list[str]:
    return [d.key for d in load(org_id).departments]


def exists(key: str, org_id: Optional[str] = None) -> bool:
    return (key or "") in set(keys(org_id))


def get(key: str, org_id: Optional[str] = None) -> Optional[DepartmentDef]:
    for d in load(org_id).departments:
        if d.key == key:
            return d
    return None


def label(key: str, org_id: Optional[str] = None) -> str:
    """Display name for a key; falls back to the key itself so UI never breaks
    on a record referencing a department that was later renamed/removed."""
    d = get(key, org_id)
    return d.name if d else (key or "")


def require(key: str, org_id: Optional[str] = None) -> str:
    """Validate a department key, raising DepartmentError if unknown."""
    if not exists(key, org_id):
        raise DepartmentError(
            f"Unknown department '{key}'. Known: {', '.join(keys(org_id)) or 'none'}."
        )
    return key


def add(name: str, description: str = "", order: int = 100,
        is_final_authority: bool = False, key: Optional[str] = None,
        org_id: Optional[str] = None) -> DepartmentDef:
    reg = load(org_id)
    dept_key = slugify(key or name)
    if any(d.key == dept_key for d in reg.departments):
        raise DepartmentError(f"A department with key '{dept_key}' already exists.")
    dept = DepartmentDef(key=dept_key, name=name.strip() or dept_key,
                         description=description, order=order,
                         is_final_authority=is_final_authority)
    reg.departments.append(dept)
    save(reg, org_id)
    return dept


def update(key: str, *, name: Optional[str] = None, description: Optional[str] = None,
           order: Optional[int] = None, is_final_authority: Optional[bool] = None,
           org_id: Optional[str] = None) -> DepartmentDef:
    """Update a department's display fields. The KEY is immutable on purpose —
    existing transactions/notifications reference it."""
    reg = load(org_id)
    for d in reg.departments:
        if d.key == key:
            if name is not None:
                d.name = name.strip() or d.name
            if description is not None:
                d.description = description
            if order is not None:
                d.order = order
            if is_final_authority is not None:
                d.is_final_authority = is_final_authority
            save(reg, org_id)
            return d
    raise DepartmentError(f"Unknown department '{key}'.")


def remove(key: str, org_id: Optional[str] = None) -> None:
    """Delete a department. Refuses if it still owns a workflow state — removing
    it would leave transactions with an unroutable owner."""
    reg = load(org_id)
    if key in set(reg.state_owners.values()):
        owned = [s for s, d in reg.state_owners.items() if d == key]
        raise DepartmentError(
            f"'{key}' still owns workflow state(s): {', '.join(owned)}. "
            "Reassign those states before deleting it."
        )
    remaining = [d for d in reg.departments if d.key != key]
    if len(remaining) == len(reg.departments):
        raise DepartmentError(f"Unknown department '{key}'.")
    if not remaining:
        raise DepartmentError("An organisation must keep at least one department.")
    reg.departments = remaining
    save(reg, org_id)


def state_owner(state: str, org_id: Optional[str] = None) -> Optional[str]:
    """Which department owns a workflow state (None = unowned, e.g. 'returned')."""
    return load(org_id).state_owners.get(state)


def set_state_owner(state: str, department_key: Optional[str],
                    org_id: Optional[str] = None) -> DepartmentRegistry:
    """Route a workflow state to a department (or clear it with None)."""
    reg = load(org_id)
    if department_key is None:
        reg.state_owners.pop(state, None)
    else:
        if not any(d.key == department_key for d in reg.departments):
            raise DepartmentError(f"Unknown department '{department_key}'.")
        reg.state_owners[state] = department_key
    return save(reg, org_id)


def replace_all(departments: list[DepartmentDef], state_owners: dict[str, str],
                org_id: Optional[str] = None) -> DepartmentRegistry:
    """Install a complete registry in one write — used by org_config when a
    client profile is applied. Validates that every state owner names a
    department that exists, so a profile typo fails here, not as a stuck
    requisition three weeks later."""
    if not departments:
        raise DepartmentError("An organisation must have at least one department.")
    known = {d.key for d in departments}
    bad = {s: d for s, d in state_owners.items() if d not in known}
    if bad:
        raise DepartmentError(
            "State owners reference unknown departments: "
            + ", ".join(f"{s} → '{d}'" for s, d in bad.items())
        )
    reg = DepartmentRegistry(departments=list(departments),
                             state_owners=dict(state_owners),
                             updated_at=_now_iso())
    return save(reg, org_id)
