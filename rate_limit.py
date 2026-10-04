"""
A small, durable rate limit for actions that cost money or reveal personal data.

Stored in the org's own store (not memory), so a restart can't reset it and
two server instances count together. Fixed windows are enough here: the aim
is to stop a script running through thousands of bank-account lookups, not
to shape normal traffic.
"""
from __future__ import annotations

import hashlib
import time

import store

_COLLECTION = "rate_limits"


class RateLimited(Exception):
    pass


def hit(org_id: str, action: str, who: str, *, limit: int, window_seconds: int) -> int:
    """Count one use; raise RateLimited once `limit` is exceeded in the window.
    Returns how many uses remain."""
    window = int(time.time() // window_seconds)
    key = hashlib.sha256(f"{action}|{(who or '').lower()}|{window}".encode()).hexdigest()[:32]
    s = store.get_store()
    org = store.require_org(org_id)
    raw = s.get(org, _COLLECTION, key) or {}
    count = int(raw.get("count", 0))
    if count >= limit:
        minutes = max(1, int(((window + 1) * window_seconds - time.time()) // 60) + 1)
        raise RateLimited(f"You've reached the limit for this check. Try again in about {minutes} minutes.")
    s.put(org, _COLLECTION, key, {"count": count + 1, "action": action, "window": window})
    return limit - count - 1
