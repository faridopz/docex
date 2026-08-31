"""
Request context — who is calling, and which organisation they belong to.

Two facts every org-scoped endpoint needs:

  * the signed-in User (from the bearer token, via auth_routes.current_user)
  * the org_id to scope storage by

DOCex currently runs ONE organisation per instance (see CLAUDE.md, Phase 4:
multi-org tenancy is not built yet), so the org comes from the DOCEX_ORG
environment variable and defaults to "default". Centralising it here means
that when per-user org scoping lands, exactly one function changes rather
than every route file.

Usage in a route:

    from .context import Ctx, request_context

    @router.get("/things")
    async def list_things(ctx: Ctx = Depends(request_context)):
        return things.list_all(ctx.org_id)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException

from models import User
from .auth_routes import current_user


def default_org() -> str:
    """The organisation this instance serves."""
    return (os.environ.get("DOCEX_ORG") or "default").strip() or "default"


@dataclass(frozen=True)
class Ctx:
    """Resolved caller context passed to org-scoped endpoints."""
    user: User
    org_id: str

    @property
    def user_id(self) -> str:
        # Email is the stable human-readable actor in the audit log; an
        # auditor reading "amara@eva.org approved" needs no lookup table.
        return self.user.email

    @property
    def department(self) -> str:
        return self.user.department or ""

    @property
    def role(self) -> str:
        return self.user.role or "viewer"


def request_context(user: User = Depends(current_user)) -> Ctx:
    """FastAPI dependency: authenticate, then attach the org scope."""
    return Ctx(user=user, org_id=default_org())


def require_role(ctx: Ctx, *allowed: str) -> Ctx:
    """Guard an action behind one or more roles. Raises 403 otherwise."""
    if ctx.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"This action requires role: {', '.join(allowed)} (you are '{ctx.role}').",
        )
    return ctx
