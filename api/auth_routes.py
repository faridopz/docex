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
  POST /auth/logout     — end every session this account holds
  GET  /auth/me         — the current user (requires token)
  POST /auth/password   — change your own password (requires the current one)
  GET  /auth/users      — list users (admin only)
  POST /auth/users/invite                  — create an account with a one-time
                                             password, returned once (admin)
  POST /auth/users/{id}/reset-password     — fresh one-time password (admin)
  POST /auth/users/{id}/deactivate         — end access, keep the record (admin)
  POST /auth/users/{id}/activate           — restore access (admin)
  PATCH /auth/users/{id}                   — name / department / role (admin)
  GET  /dashboard       — the caller's department dashboard (admin may pass ?department=)

Forced password change: an account created by an administrator carries
must_change_password. api/security.py blocks every route except /auth/me,
/auth/password and /auth/logout until it is cleared — enforced in the
middleware so it covers routes nobody has written yet.
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
    # The sign-in screen needs to know to send this person to the
    # change-password form rather than the dashboard. Duplicated out of `user`
    # deliberately so the client never has to reach into the nested object to
    # answer a question this important.
    must_change_password: bool = False


class InviteRequest(BaseModel):
    email: str
    name: str
    department: Department
    role: Role = "reviewer"


class InviteResponse(BaseModel):
    user: UserPublic
    temporary_password: str
    note: str = (
        "Give this password to the person directly. It is shown once, is not "
        "stored in readable form, and stops working as soon as they set their "
        "own. If it is lost, reset the account rather than looking it up.")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    department: Optional[Department] = None
    role: Optional[Role] = None


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
    except auth_mod.RateLimited as exc:
        # 429, not 401. The caller needs to know that waiting helps and more
        # guessing does not — and a monitoring system needs to tell a locked
        # account apart from a wrong password.
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    token = auth_mod.issue_token(user)
    auth_mod.record_login(user)
    return LoginResponse(token=token, user=auth_mod.public(user),
                         must_change_password=user.must_change_password)


@router.post("/auth/logout")
def logout(user: User = Depends(current_user)) -> dict:
    """End every session this account holds.

    Clearing the token in the browser is not a logout: a signed token that was
    captured still works until it expires. This records a cutoff so every token
    issued before now is refused — which also covers "I think someone has my
    password" without waiting for an administrator.
    """
    auth_mod.logout(user)
    return {"ok": True,
            "detail": "Signed out on every device."}


@router.get("/auth/me", response_model=UserPublic)
def me(user: User = Depends(current_user)) -> UserPublic:
    return auth_mod.public(user)


@router.get("/auth/users", response_model=dict)
def list_users(_: User = Depends(require_admin)) -> dict:
    return {"users": [u.model_dump() for u in auth_mod.list_public()]}


# ─── managing an organisation's people ──────────────────────────────────────
#
# `/auth/register` bootstraps the first admin and can also be used by an admin
# to create an account with a chosen password. These routes are what an
# administrator actually uses day to day: invite somebody, reset the one who
# forgot, and end access for the one who left.


@router.post("/auth/users/invite", response_model=InviteResponse)
def invite(body: InviteRequest, admin: User = Depends(require_admin)) -> InviteResponse:
    """Create an account with a one-time password, returned once.

    The administrator never chooses the password, which means they cannot
    reuse a house password across twenty accounts — the failure that turns one
    leaked credential into twenty.
    """
    try:
        user, temp = auth_mod.invite_user(
            body.email, body.name, body.department, body.role,
            invited_by=admin.email)
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return InviteResponse(user=auth_mod.public(user), temporary_password=temp)


@router.post("/auth/users/{user_id}/reset-password", response_model=InviteResponse)
def reset_user_password(user_id: str, admin: User = Depends(require_admin)) -> InviteResponse:
    """Issue a fresh one-time password. Ends every session that account holds.

    This is also the answer to "somebody is locked out after eight wrong
    attempts" — the reset clears the lockout, so the administrator does not
    have to wait fifteen minutes with a colleague standing over them.
    """
    try:
        user, temp = auth_mod.reset_password(user_id, reset_by=admin.email)
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InviteResponse(user=auth_mod.public(user), temporary_password=temp)


@router.post("/auth/users/{user_id}/deactivate", response_model=UserPublic)
def deactivate_user(user_id: str, admin: User = Depends(require_admin)) -> UserPublic:
    """End someone's access without deleting them.

    The record stays because the approval trail must still be able to say who
    authorised a payment last March. Sessions die immediately — an account
    disabled at 10am must not approve anything at 3pm.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own account. Ask another "
                   "administrator to do it.")
    try:
        return auth_mod.public(auth_mod.set_active(user_id, False, actor=admin.email))
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/users/{user_id}/activate", response_model=UserPublic)
def activate_user(user_id: str, admin: User = Depends(require_admin)) -> UserPublic:
    try:
        return auth_mod.public(auth_mod.set_active(user_id, True, actor=admin.email))
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/auth/users/{user_id}", response_model=UserPublic)
def update_user(user_id: str, body: UpdateUserRequest,
                admin: User = Depends(require_admin)) -> UserPublic:
    """Change a person's name, department or role.

    People move teams and get promoted. Without this the workaround is a second
    account, which silently splits one person's approval history in two.
    """
    try:
        return auth_mod.public(auth_mod.update_user(
            user_id, name=body.name, department=body.department,
            role=body.role, actor_id=admin.id))
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/password", response_model=dict)
def change_password(body: ChangePasswordRequest,
                    user: User = Depends(current_user)) -> dict:
    """Set your own password. Requires the current one, even on first use.

    Requiring the temporary password here is not friction for its own sake: it
    is what stops someone who walks past an unlocked laptop from taking the
    account permanently. Every other session is ended, so if the old password
    had leaked, the leak ends here too.
    """
    try:
        auth_mod.change_own_password(user, body.current_password, body.new_password)
    except auth_mod.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:                       # password strength
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Every session was just revoked, including the one that made this call, so
    # hand back a fresh token rather than making the user sign in again with a
    # password they set two seconds ago.
    return {"ok": True,
            "token": auth_mod.issue_token(user),
            "detail": "Password changed. You have been signed out everywhere else."}


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
