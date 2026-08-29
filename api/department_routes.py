"""
DOCex department routes — an organisation defines its own departments.

Reading the list is open to any signed-in user (the UI needs labels everywhere).
Creating / renaming / deleting and re-routing workflow states is admin-only.

Endpoints:
  GET    /departments                 — list departments + state routing
  POST   /departments                 — create one (admin)
  PUT    /departments/{key}           — rename / reorder (admin)
  DELETE /departments/{key}           — delete, if it owns no workflow state (admin)
  PUT    /departments/routing/{state} — route a workflow state to a department (admin)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import departments as dept_mod  # noqa: E402
from models import DepartmentDef, User  # noqa: E402

from .auth_routes import current_user, require_admin  # noqa: E402

router = APIRouter(prefix="/departments", tags=["departments"])


class DepartmentCreate(BaseModel):
    name: str
    description: str = ""
    order: int = 100
    is_final_authority: bool = False
    key: Optional[str] = None       # optional explicit slug; derived from name otherwise


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None
    is_final_authority: Optional[bool] = None


class RoutingUpdate(BaseModel):
    department: Optional[str] = None   # None clears the owner for that state


@router.get("", response_model=dict)
def list_departments(_: User = Depends(current_user)) -> dict:
    reg = dept_mod.load()
    return {
        "departments": [d.model_dump() for d in reg.departments],
        "state_owners": reg.state_owners,
    }


@router.post("", response_model=DepartmentDef)
def create_department(body: DepartmentCreate, _: User = Depends(require_admin)) -> DepartmentDef:
    try:
        return dept_mod.add(
            body.name, description=body.description, order=body.order,
            is_final_authority=body.is_final_authority, key=body.key,
        )
    except dept_mod.DepartmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{key}", response_model=DepartmentDef)
def update_department(key: str, body: DepartmentUpdate,
                      _: User = Depends(require_admin)) -> DepartmentDef:
    try:
        return dept_mod.update(
            key, name=body.name, description=body.description,
            order=body.order, is_final_authority=body.is_final_authority,
        )
    except dept_mod.DepartmentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{key}", response_model=dict)
def delete_department(key: str, _: User = Depends(require_admin)) -> dict:
    try:
        dept_mod.remove(key)
    except dept_mod.DepartmentError as exc:
        # 409: it still owns a workflow state / is the last one standing.
        code = 404 if "Unknown department" in str(exc) else 409
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return {"status": "deleted", "key": key}


@router.put("/routing/{state}", response_model=dict)
def set_routing(state: str, body: RoutingUpdate, _: User = Depends(require_admin)) -> dict:
    try:
        reg = dept_mod.set_state_owner(state, body.department)
    except dept_mod.DepartmentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"state_owners": reg.state_owners}
