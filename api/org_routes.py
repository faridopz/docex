"""
DOCex org routes — what THIS client's instance has switched on.

One endpoint, and it exists to make the product model true in the interface
rather than only in the database.

The engine is shared by every client. What makes NEEM's system feel like NEEM's
and EVA's feel like EVA's is their profile: which product areas they bought
(`modules`) and which capabilities inside them are on (`features`). Both are set
in `profiles/<client>.json` and applied with org_config.

Without this endpoint the backend knew EVA had payroll and NEEM did not, but the
navigation showed both clients the same links — so a NEEM user could see a menu
item for something their organisation had never bought. That is the kind of
detail that quietly costs trust in a system people are using to move money.

  GET /org/config — { modules: [...], features: {...} }

Open to any signed-in user of the org: the UI needs it on first paint, and it
carries nothing sensitive — no policy numbers, no other org's data, no secrets.
Authorisation still happens on the routes that do the actual work; hiding a menu
item is a courtesy to the user, never a security boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

import org_config  # noqa: E402

from .context import Ctx, request_context, require_role  # noqa: E402

router = APIRouter(prefix="/org", tags=["org"])

# The complete, real set of module/feature names this instance understands —
# not every flag any org has ever set, but every one a route actually gates
# on. Kept here (rather than derived by scanning the codebase at runtime) so
# the settings screen has one place to look, and a new flag is a one-line
# addition, not a guess.
KNOWN_MODULES = list(org_config._ALL_MODULES)
KNOWN_FEATURES = [
    "attendance_payments", "withholding_tax", "bank_reconciliation",
    "vendor_register", "timesheets", "payroll", "advance_retirement",
    "accounting_export", "multi_payee_requisitions", "requisition_hold",
    "requisition_attachments",
]


class ClientConfig(BaseModel):
    """What the frontend needs to decide what this client can see."""
    modules: list[str] = Field(default_factory=list)
    features: dict[str, bool] = Field(default_factory=dict)


class ClientConfigIn(BaseModel):
    """Admin write: which modules and features this org has switched on."""
    modules: Optional[list[str]] = None
    features: Optional[dict[str, bool]] = None


@router.get("/config", response_model=ClientConfig)
async def get_client_config(ctx: Ctx = Depends(request_context)) -> ClientConfig:
    """Modules and feature flags for the caller's organisation.

    An org with no profile applied yet gets every module and no features —
    the same behaviour as before this endpoint existed, so nothing changes
    for an instance that hasn't been configured.
    """
    cfg = org_config.client_config(ctx.org_id)
    return ClientConfig(modules=cfg["modules"], features=cfg["features"])


@router.put("/config", response_model=ClientConfig)
async def set_client_config(
    body: ClientConfigIn, ctx: Ctx = Depends(request_context)
) -> ClientConfig:
    """Admin-only: turn modules/features on or off for THIS org, live.

    Until this existed, the org settings screen's module toggles wrote to a
    completely different, disconnected config (the legacy org_profile) that
    nothing here reads — so flipping a switch in settings visibly did
    nothing to the actual navigation. This is the endpoint that makes the
    switch real: it writes the same org_config record GET /org/config (and
    every route's feature gate) reads.
    """
    require_role(ctx, "admin")
    if body.modules is not None:
        org_config.set_modules(ctx.org_id, body.modules)
    if body.features is not None:
        org_config.set_features(ctx.org_id, **body.features)
    cfg = org_config.client_config(ctx.org_id)
    return ClientConfig(modules=cfg["modules"], features=cfg["features"])
