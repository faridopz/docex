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

Persisted as ONE JSON document at {root}/departments.json — same file-based
pattern as org_profile.json. Never raises on a missing/corrupt file: it falls
back to the built-in defaults so the app always boots.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Optional

from models import DepartmentDef, DepartmentRegistry

_ROOT = Path(__file__).parent
_REGISTRY_PATH = _ROOT / "departments.json"

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


def load() -> DepartmentRegistry:
    """Load the registry, falling back to defaults if absent or unreadable."""
    if not _REGISTRY_PATH.exists():
        return default_registry()
    try:
        reg = DepartmentRegistry.model_validate_json(_REGISTRY_PATH.read_text())
    except Exception as exc:
        print(f"Warning: departments.json unreadable ({exc}); using defaults.")
        return default_registry()
    if not reg.departments:            # empty file → defaults, never an empty app
        return default_registry()
    if not reg.state_owners:
        reg.state_owners = dict(_DEFAULT_STATE_OWNERS)
    return reg


def save(reg: DepartmentRegistry) -> DepartmentRegistry:
    reg.updated_at = _now_iso()
    reg.departments.sort(key=lambda d: (d.order, d.name))
    _REGISTRY_PATH.write_text(reg.model_dump_json(indent=2))
    return reg


def list_departments() -> list[DepartmentDef]:
    return load().departments


def keys() -> list[str]:
    return [d.key for d in load().departments]


def exists(key: str) -> bool:
    return (key or "") in set(keys())


def get(key: str) -> Optional[DepartmentDef]:
    for d in load().departments:
        if d.key == key:
            return d
    return None


def label(key: str) -> str:
    """Display name for a key; falls back to the key itself so UI never breaks
    on a record referencing a department that was later renamed/removed."""
    d = get(key)
    return d.name if d else (key or "")


def require(key: str) -> str:
    """Validate a department key, raising DepartmentError if unknown."""
    if not exists(key):
        raise DepartmentError(
            f"Unknown department '{key}'. Known: {', '.join(keys()) or 'none'}."
        )
    return key


def add(name: str, description: str = "", order: int = 100,
        is_final_authority: bool = False, key: Optional[str] = None) -> DepartmentDef:
    reg = load()
    dept_key = slugify(key or name)
    if any(d.key == dept_key for d in reg.departments):
        raise DepartmentError(f"A department with key '{dept_key}' already exists.")
    dept = DepartmentDef(key=dept_key, name=name.strip() or dept_key,
                         description=description, order=order,
                         is_final_authority=is_final_authority)
    reg.departments.append(dept)
    save(reg)
    return dept


def update(key: str, *, name: Optional[str] = None, description: Optional[str] = None,
           order: Optional[int] = None, is_final_authority: Optional[bool] = None) -> DepartmentDef:
    """Update a department's display fields. The KEY is immutable on purpose —
    existing transactions/notifications reference it."""
    reg = load()
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
            save(reg)
            return d
    raise DepartmentError(f"Unknown department '{key}'.")


def remove(key: str) -> None:
    """Delete a department. Refuses if it still owns a workflow state — removing
    it would leave transactions with an unroutable owner."""
    reg = load()
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
    save(reg)


def state_owner(state: str) -> Optional[str]:
    """Which department owns a workflow state (None = unowned, e.g. 'returned')."""
    return load().state_owners.get(state)


def set_state_owner(state: str, department_key: Optional[str]) -> DepartmentRegistry:
    """Route a workflow state to a department (or clear it with None)."""
    reg = load()
    if department_key is None:
        reg.state_owners.pop(state, None)
    else:
        if not any(d.key == department_key for d in reg.departments):
            raise DepartmentError(f"Unknown department '{department_key}'.")
        reg.state_owners[state] = department_key
    return save(reg)
