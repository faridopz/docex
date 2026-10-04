"""
Payee bank-account checks for the payment request form.

  GET  /payee-check/banks    — one clean name per bank, for a dropdown
  POST /payee-check/account  — is this account in this name? (as it is typed)

The same check also runs on every request when it is submitted
(requisitions.run_policy_checks); these routes let the form catch a wrong
account while the submitter still has the invoice in front of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import org_config  # noqa: E402
import payee_verification as pv  # noqa: E402

from .context import Ctx, request_context  # noqa: E402

router = APIRouter(prefix="/payee-check", tags=["payee-check"])


class AccountIn(BaseModel):
    name: str
    account_number: str
    bank: str


@router.get("/banks")
async def banks(ctx: Ctx = Depends(request_context)) -> dict:
    # Gated like the check: an org without it keeps its free-text bank field.
    if not org_config.feature_enabled(ctx.org_id, "payee_account_check"):
        raise HTTPException(status_code=404, detail="Not Found")
    return {"banks": pv.bank_options()}


@router.post("/account")
async def check_account(body: AccountIn, ctx: Ctx = Depends(request_context)) -> dict:
    if not org_config.feature_enabled(ctx.org_id, "payee_account_check"):
        raise HTTPException(status_code=404, detail="Not Found")
    # Each lookup is paid for and returns a stranger's name for any account
    # number (30 Sep audit, M7). Plenty for real use; useless to a script.
    import os
    import rate_limit
    try:
        rate_limit.hit(ctx.org_id, "payee-check", ctx.user_id,
                       limit=int(os.environ.get("DOCEX_PAYEE_CHECKS_PER_HOUR", "40")),
                       window_seconds=3600)
    except rate_limit.RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return pv.check_account(ctx.org_id, name=body.name, account_number=body.account_number,
                            bank=body.bank)
