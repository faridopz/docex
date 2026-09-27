"""
ai_client.py — the one place an Anthropic client is created.

Every model call goes through here so that two things happen without each
engine remembering to do them:

  1. BEFORE the call, the organisation's daily AI caps are checked
     (observability.check_llm_allowed: calls per day and spend per day,
     set by DOCEX_LLM_DAILY_CALLS / DOCEX_LLM_DAILY_USD). Over a cap, the
     call is refused with LimitExceeded, which the API returns as a 429
     with a plain message. The per-minute burst guard is NOT applied per
     call: one batch legitimately makes dozens of calls in a minute.
  2. AFTER the call, its tokens are recorded against the organisation and
     an operation label (usage.record), so margin reviews and the caps read
     real numbers.

Both used to exist and neither was called: usage tables stayed empty, and
nothing limited what one client could spend.

The organisation is the instance's own (DOCEX_ORG) — one instance serves
one client. Recording never raises; the cap check does, by design.
"""
from __future__ import annotations

import os
from typing import Any

import anthropic


def _org() -> str:
    return (os.environ.get("DOCEX_ORG") or "default").strip() or "default"


def _record(operation: str, response: Any, model: str) -> None:
    try:
        import usage
        u = getattr(response, "usage", None)
        usage.record(
            _org(), operation, getattr(response, "model", None) or model or "unknown",
            input_tokens=getattr(u, "input_tokens", None),
            output_tokens=getattr(u, "output_tokens", None),
            cache_read_tokens=getattr(u, "cache_read_input_tokens", None),
            cache_creation_tokens=getattr(u, "cache_creation_input_tokens", None),
        )
    except Exception as exc:  # noqa: BLE001 — metering must never fail a call
        print(f"[ai_client] usage not recorded ({exc})")


class _MeteredMessages:
    def __init__(self, inner: Any, operation: str) -> None:
        self._inner = inner
        self._operation = operation

    def _call(self, fn, kwargs: dict):
        import observability
        observability.check_llm_allowed(_org(), operation=self._operation, burst=False)
        response = fn(**kwargs)
        _record(self._operation, response, kwargs.get("model", ""))
        return response

    def create(self, **kwargs):
        return self._call(self._inner.create, kwargs)

    def parse(self, **kwargs):
        return self._call(self._inner.parse, kwargs)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class MeteredClient:
    """Behaves like anthropic.Anthropic; messages.create/parse are metered."""

    def __init__(self, operation: str, **kwargs: Any) -> None:
        self._client = anthropic.Anthropic(**kwargs)
        self.messages = _MeteredMessages(self._client.messages, operation)

    def __getattr__(self, name: str):
        return getattr(self._client, name)


def client(operation: str, **kwargs: Any) -> MeteredClient:
    """A metered Anthropic client. `operation` is a short stable label
    ("compliance_check", "extraction", ...) so usage shows which part of the
    product is expensive, not just which client."""
    return MeteredClient(operation, **kwargs)
