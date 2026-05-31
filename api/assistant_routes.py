"""
DOCex Assistant routes.

  POST /assistant/summarize
      Body: { context_kind: str, context_id: str?, payload: dict }
      Returns: AssistantBrief

Stateless — the Assistant doesn't persist briefings. Each result page
calls it on mount; the result is cached in browser state. Re-runs are
cheap (~$0.002 per call). When we want persistence later (e.g. "show me
the briefing from last week's run") we can save AssistantBrief alongside
the result it describes, indexed by context_id.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from assistant import summarize  # noqa: E402
from models import AssistantBrief  # noqa: E402

router = APIRouter(prefix="/assistant", tags=["assistant"])


class SummarizeRequest(BaseModel):
    context_kind: str
    payload: dict[str, Any]
    context_id: Optional[str] = None


@router.post("/summarize", response_model=AssistantBrief)
def summarize_endpoint(body: SummarizeRequest) -> AssistantBrief:
    if not body.payload:
        raise HTTPException(
            status_code=422,
            detail="payload is required — pass the result dict you want briefed",
        )
    return summarize(
        context_kind=body.context_kind,
        payload=body.payload,
        context_id=body.context_id,
    )
