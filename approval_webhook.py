"""
DOCex approval webhook — an org-agnostic transport for routing sign-off
requests to (and receiving decisions from) an external workflow engine.

Design (per the human-in-the-loop integration pattern): DOCex never hard-wires
to one vendor. When ``APPROVAL_WEBHOOK_URL`` is set, DOCex POSTs a single,
normalized ``approval.requested`` event to it. Any automation platform can
consume that one shape — Microsoft Power Automate (our first target), Zapier,
n8n, a Slack/Teams workflow — route it to the right approver, and POST the
outcome back to ``/compliance/approve/callback`` authenticated with a shared
secret. The callback is normalized into the SAME internal sign-off path used by
the email magic-link, so every transport converges on one audit representation.

Everything here is INERT unless configured:
  - ``APPROVAL_WEBHOOK_URL``      — where to POST sign-off requests. Unset ⇒ no
    emit; the existing magic-link email flow is untouched.
  - ``APPROVAL_CALLBACK_SECRET``  — shared secret. Sent on outbound emits as the
    ``X-DOCex-Secret`` header, and REQUIRED (fail-closed) to accept callbacks.

Notes:
  - Outbound failures are swallowed (logged) — a down webhook must never break
    a sign-off request; the magic-link still works as a fallback.
  - Power Automate moved its HTTP-trigger URLs to
    ``*.environment.api.powerplatform.com`` (old logic.azure.com URLs retire
    Nov 30 2025) — that's just the value of APPROVAL_WEBHOOK_URL, no code change.
"""
from __future__ import annotations

import hmac
import json
import os
import urllib.request


def _callback_secret() -> str:
    return os.environ.get("APPROVAL_CALLBACK_SECRET", "").strip()


def emit_approval_request(event: dict, timeout: float = 8.0) -> bool:
    """POST a normalized approval.requested event to the configured webhook.

    Returns True if delivered (2xx), False if not configured or on any error.
    """
    url = os.environ.get("APPROVAL_WEBHOOK_URL", "").strip()
    if not url:
        return False
    payload = {"type": "approval.requested", **event}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    secret = _callback_secret()
    if secret:
        req.add_header("X-DOCex-Secret", secret)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001 — never let a bad webhook break sign-off
        print(f"[DOCex] approval webhook emit failed: {exc}")
        return False


def verify_callback_secret(provided: str) -> bool:
    """Constant-time check of an inbound callback secret. Fail-closed: if no
    secret is configured, all callbacks are rejected (so the endpoint can't be
    abused before the operator has set it up)."""
    expected = _callback_secret()
    if not expected:
        return False
    return hmac.compare_digest((provided or "").strip(), expected)
