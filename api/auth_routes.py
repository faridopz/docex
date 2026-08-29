"""
DOCex auth + dashboard routes.

Login/registration and the per-department dashboard aggregation. RBAC is
enforced with small dependencies: `current_user` validates the bearer token;
`require_admin` gates user management.

Bootstrapping: the very first user created (when there are no users yet) is
forced to role=admin and may be created without a token — so a fresh install
can be set up. After that, only an admin can create users.

Endpoints:
  POST /auth/register   — create a user (first user = admin; then admin-only)
  POST /auth/login      — exchange email+password for a session token
  GET  /auth/me         — the current user (requires token)
  GET  /auth/users      — list users (admin only)
  GET  /dashboard       — the caller's department dashboard (admin may pass ?department=)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import auth as auth_mod  # noqa: E402
import notification_center as nc  # noqa: E402
import transactions as tx  # noqa: E402
from models import (  # noqa: E402
    DashboardSummary,
    Department,
    Role,
    User,
    UserPublic,
)

router = APIRouter(tags=["auth"])


# ─── auth dependencies ──────────────────────────────────────────────────────


def current_user(authorization: Optional[str] = Header(default=None)) -> User:
    """Resolve the caller from a `Authorization: Bearer <token>` header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return auth_mod.verify_token(token)
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required.")
    return user


# ─── request/response bodies ────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    department: Department
    role: Role = "reviewer"


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserPublic


# ─── routes ─────────────────────────────────────────────────────────────────


@router.get("/auth/status", response_model=dict)
def auth_status() -> dict:
    """Public: has this instance been set up yet?

    Deliberately unauthenticated and deliberately minimal — it reveals only
    whether an admin account exists, which the sign-in screen needs to know so
    a brand-new install can send the first person to /setup instead of a login
    form they can never pass. No user data is exposed.
    """
    return {"needs_setup": not auth_mod.list_public()}


@router.post("/auth/register", response_model=UserPublic)
def register(body: RegisterRequest, authorization: Optional[str] = Header(default=None)) -> UserPublic:
    first_user = not auth_mod.list_public()
    if first_user:
        role: Role = "admin"  # bootstrap: first account is the admin
    else:
        # Subsequent users require an admin token.
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Admin token required to add users.")
        try:
            caller = auth_mod.verify_token(authorization.split(" ", 1)[1].strip())
        except auth_mod.AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if caller.role != "admin":
            raise HTTPException(status_code=403, detail="Admin role required to add users.")
        role = body.role
    try:
        user = auth_mod.create_user(body.email, body.name, body.password, body.department, role)
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:  # weak password
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return auth_mod.public(user)


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    try:
        user = auth_mod.authenticate(body.email, body.password)
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return LoginResponse(token=auth_mod.issue_token(user), user=auth_mod.public(user))


@router.get("/auth/me", response_model=UserPublic)
def me(user: User = Depends(current_user)) -> UserPublic:
    return auth_mod.public(user)


@router.get("/auth/users", response_model=dict)
def list_users(_: User = Depends(require_admin)) -> dict:
    return {"users": [u.model_dump() for u in auth_mod.list_public()]}


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    user: User = Depends(current_user),
    department: Optional[Department] = Query(default=None),
) -> DashboardSummary:
    # Non-admins can only see their own department's dashboard.
    dept: Department = user.department
    if department is not None and department != user.department:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="You can only view your own department.")
        dept = department

    owned = tx.list_all(department=dept)
    counts: dict[str, int] = {}
    total_pending = 0.0
    for row in owned:
        counts[row.state] = counts.get(row.state, 0) + 1
        if row.state != "paid" and row.amount:
            total_pending += row.amount

    return DashboardSummary(
        department=dept,
        unread_notifications=nc.unread_count(dept),
        pending_on_me=len(owned),
        counts_by_state=counts,
        total_value_pending=round(total_pending, 2),
        recent=owned[:10],
    )
