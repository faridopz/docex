"""
Error reporting and cost limits — the two things that stop a bad day
becoming a bad month.

SENTRY
Optional and off unless SENTRY_DSN is set, so nothing changes for a developer
who has not configured it. When it IS set, `send_default_pii=False` is not
negotiable: crash reports from this system would otherwise carry vendor names,
amounts and staff names to a third party, and the product's whole claim is that
client financial data stays where it belongs.

SPEND LIMITS
Model calls are the only unbounded cost in the system. `max_tokens` caps a
single request; nothing caps the NUMBER of requests, so before this module an
authenticated user could loop a compliance check and run up a bill with no
ceiling. usage.py records spend — recording is not limiting.

Two independent guards, because they fail differently:

  RATE LIMIT   — a burst. Someone (or a broken retry loop) firing repeatedly.
                 Short window, resets quickly.
  DAILY QUOTA  — sustained volume. A client whose usage quietly doubles, or an
                 automation left running over a weekend.

Both fail CLOSED with a message naming the limit and when it resets. In a
finance system a refused request is a nuisance; an unbounded bill is not.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from collections import deque
from typing import Optional

# ─── Sentry ─────────────────────────────────────────────────────────────────

_sentry_ready = False


def init_sentry() -> bool:
    """Wire up error reporting if a DSN is configured. Safe to call twice."""
    global _sentry_ready
    if _sentry_ready:
        return True
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        print("[observability] SENTRY_DSN is set but sentry-sdk is not installed "
              "— run: pip install sentry-sdk", flush=True)
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("DOCEX_ENV", "production"),
        release=os.environ.get("DOCEX_RELEASE") or None,
        # 10% of requests traced. Enough to spot a slow endpoint without
        # paying to trace every health check.
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
        # NEVER send personal data. This system holds vendor names, amounts,
        # staff names and payment references; none of it belongs in a crash
        # report on someone else's infrastructure.
        send_default_pii=False,
        before_send=_scrub,
    )
    sentry_sdk.set_tag("org", os.environ.get("DOCEX_ORG", "default"))
    _sentry_ready = True
    print("[observability] Sentry active", flush=True)
    return True


# Header and field names that must never leave this system, even inside an
# error report.
_SECRET_HINTS = (
    "authorization", "cookie", "token", "secret", "password", "apikey",
    "signing", "dsn", "session", "credential", "bearer",
)


def _is_secret(name: str) -> bool:
    """Would this field name hold a credential?

    Dashes and underscores are stripped before matching, because the same
    thing arrives as `api_key`, `apiKey` and `X-Api-Key` depending on where it
    came from — and a hint list that only catches two of the three leaks the
    key in the third. A test caught exactly that.
    """
    flat = name.lower().replace("-", "").replace("_", "")
    return any(hint.replace("_", "") in flat for hint in _SECRET_HINTS)


def _scrub(event, hint):  # pragma: no cover - exercised only with a live DSN
    """Strip credentials from an event before it leaves the process."""
    try:
        req = event.get("request") or {}
        headers = req.get("headers")
        if isinstance(headers, dict):
            for key in list(headers):
                if _is_secret(key):
                    headers[key] = "[redacted]"
        # Query strings and bodies can carry a token someone put in a URL.
        req.pop("query_string", None)
        req.pop("data", None)
        for var in (event.get("extra") or {}):
            if _is_secret(var):
                event["extra"][var] = "[redacted]"
    except Exception:
        # A scrubber that raises would drop the error entirely, which is worse
        # than a slightly noisy report.
        pass
    return event


def capture(exc: BaseException, **context) -> None:
    """Report an exception with context, if Sentry is configured."""
    if not _sentry_ready:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                if not _is_secret(key):
                    scope.set_extra(key, value)
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


# ─── spend limits ───────────────────────────────────────────────────────────


class LimitExceeded(RuntimeError):
    """A rate limit or quota was hit. Callers map this to HTTP 429."""


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# Defaults sized for a finance team, not an API service. A busy month at ~200
# requisitions is well inside these; a runaway loop is not.
def rate_limit_per_minute() -> int:
    return _int_env("DOCEX_LLM_RATE_PER_MIN", 20)


def daily_call_cap() -> int:
    return _int_env("DOCEX_LLM_DAILY_CALLS", 500)


def daily_cost_cap_usd() -> float:
    return _float_env("DOCEX_LLM_DAILY_USD", 25.0)


_lock = threading.Lock()
_recent: dict[str, deque] = {}          # org -> timestamps, for the burst guard


def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def check_llm_allowed(org_id: Optional[str], *, operation: str = "llm") -> None:
    """Raise LimitExceeded if this org has hit a limit. Call BEFORE the model.

    Deliberately fails closed. The alternative — logging a warning and calling
    anyway — is how an unbounded bill happens while the logs say everything is
    fine.
    """
    org = (org_id or "default").strip() or "default"

    # 1. Burst. A broken retry loop shows up here within seconds.
    per_min = rate_limit_per_minute()
    if per_min > 0:
        now = time.monotonic()
        with _lock:
            window = _recent.setdefault(org, deque())
            while window and now - window[0] > 60.0:
                window.popleft()
            if len(window) >= per_min:
                wait = int(61 - (now - window[0]))
                raise LimitExceeded(
                    f"Too many AI requests — {per_min} per minute is the limit. "
                    f"Try again in about {max(wait, 1)}s.")
            window.append(now)

    # 2. Sustained volume and spend, from what usage.py already records.
    try:
        import usage
        today = usage.summary(org, None)
        rows = [r for r in usage.daily(org) if r["day"] == _today()]
        calls = int(rows[0]["calls"]) if rows else 0
        cost = float(rows[0]["cost_usd"]) if rows else 0.0
    except Exception:
        # If metering is unavailable we still have the burst guard. Blocking
        # every request because a usage row could not be read would take the
        # product down to protect a budget.
        return

    cap_calls = daily_call_cap()
    if cap_calls > 0 and calls >= cap_calls:
        raise LimitExceeded(
            f"Daily AI limit reached ({cap_calls} requests). It resets at midnight UTC. "
            "Contact your administrator if you need it raised.")

    cap_usd = daily_cost_cap_usd()
    if cap_usd > 0 and cost >= cap_usd:
        raise LimitExceeded(
            f"Daily AI spend limit reached (${cap_usd:.2f}). It resets at midnight UTC. "
            "Contact your administrator if you need it raised.")


# ─── kill switch ────────────────────────────────────────────────────────────


def feature_killed(name: str) -> bool:
    """True when a feature has been switched off by environment variable.

    Lets you disable something expensive or misbehaving without a deploy:

        DOCEX_KILL_LLM=1        every model call refuses
        DOCEX_KILL_UPLOADS=1    uploads refuse
        DOCEX_KILL_ALL=1        the whole application refuses

    Deliberately environment-driven rather than a database flag: if the
    database is the thing that is broken, a database-backed kill switch is
    exactly the switch you cannot reach.
    """
    if os.environ.get("DOCEX_KILL_ALL", "").strip() in ("1", "true", "yes"):
        return True
    key = f"DOCEX_KILL_{name.upper()}"
    return os.environ.get(key, "").strip() in ("1", "true", "yes")


def require_enabled(name: str, label: str = "") -> None:
    """Raise if a feature has been killed."""
    if feature_killed(name):
        raise LimitExceeded(
            f"{label or name.replace('_', ' ').title()} is temporarily disabled. "
            "This is deliberate — please try again later or contact support.")
