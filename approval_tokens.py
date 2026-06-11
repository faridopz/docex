"""
DOCex approval tokens — signed, expiring magic-links for verified sign-off.

A payment voucher's approvers don't log in (yet). To verify that a sign-off
really came from the right person, DOCex emails each approver a unique link
containing an HMAC-signed token bound to (check, stage, their email). Only
someone with access to that mailbox can open it — proving control of the
email account, the same pattern Bill.com / client-portal approvals use.

Tokens are:
  - signed (HMAC-SHA256 with a server secret — cannot be forged),
  - bound to one check + one stage + one approver email,
  - expiring (default 7 days),
  - effectively single-use (a stage can only be signed once; the route
    rejects a second sign-off for the same stage).

Secret resolution: APPROVAL_SECRET env var, else a persisted random secret
in {root}/.approval_secret so tokens survive restarts.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

_DEFAULT_TTL = 7 * 24 * 3600  # 7 days
_secret_cache: bytes | None = None


def _secret() -> bytes:
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    env = os.environ.get("APPROVAL_SECRET", "").strip()
    if env:
        _secret_cache = env.encode()
        return _secret_cache
    path = Path(__file__).parent / ".approval_secret"
    try:
        if path.exists():
            _secret_cache = path.read_bytes()
        else:
            _secret_cache = os.urandom(32)
            path.write_bytes(_secret_cache)
    except Exception:
        # Fall back to an ephemeral per-process secret if the file can't be
        # written. Tokens won't survive a restart, but the app still works.
        _secret_cache = _secret_cache or os.urandom(32)
    return _secret_cache


def _b64(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _unb64(data: bytes) -> bytes:
    return base64.urlsafe_b64decode(data + b"=" * (-len(data) % 4))


def make_token(
    check_id: str, stage: str, email: str, ttl_seconds: int = _DEFAULT_TTL
) -> str:
    payload = {
        "cid": check_id,
        "stage": stage,
        "email": email,
        "exp": int(time.time()) + ttl_seconds,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body, hashlib.sha256).digest())
    return f"{body.decode()}.{sig.decode()}"


def verify_token(token: str) -> dict:
    """Return the payload if valid; raise ValueError otherwise."""
    try:
        body_s, sig_s = token.split(".", 1)
        body = body_s.encode()
        sig = sig_s.encode()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Malformed approval link.") from exc
    expected = _b64(hmac.new(_secret(), body, hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise ValueError("This approval link is invalid.")
    try:
        payload = json.loads(_unb64(body))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Malformed approval link.") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("This approval link has expired.")
    return payload
