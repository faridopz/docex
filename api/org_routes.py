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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

import org_config  # noqa: E402

from .context import Ctx, request_context  # noqa: E402

router = APIRouter(prefix="/org", tags=["org"])


class ClientConfig(BaseModel):
    """What the frontend needs to decide what this client can see."""
    modules: list[str] = Field(default_factory=list)
    features: dict[str, bool] = Field(default_factory=dict)


@router.get("/config", response_model=ClientConfig)
async def get_client_config(ctx: Ctx = Depends(request_context)) -> ClientConfig:
    """Modules and feature flags for the caller's organisation.

    An org with no profile applied yet gets every module and no features —
    the same behaviour as before this endpoint existed, so nothing changes
    for an instance that hasn't been configured.
    """
    cfg = org_config.client_config(ctx.org_id)
    return ClientConfig(modules=cfg["modules"], features=cfg["features"])
