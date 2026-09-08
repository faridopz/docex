"""
Default-deny authentication for the whole API.

WHY THIS EXISTS
Roughly ninety routes had no authentication. The newer work (requisitions,
departments, field receipts, org config) gates every endpoint with
`Depends(current_user)`; the older demo-era routers never did. That left client
rulebooks, saved compliance checks, transactions and vouchers readable by
anyone with the URL, and left endpoints that spend real money — Claude calls,
Paystack lookups — open to anyone who wanted to spend it.

WHY A MIDDLEWARE RATHER THAN NINETY DECORATORS
Adding `Depends(current_user)` to every route would work exactly once. The next
route someone adds would be public again, silently, and nobody would notice
until it mattered. Default-deny inverts that: a new route is protected the
moment it exists, and making something public is a deliberate edit to the
allowlist below — visible in review, and covered by test_auth_coverage.py.

The allowlist is small on purpose. Every entry is a path that must work for
someone who is not signed in, with a note saying why.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, Optional

# ─── the allowlist ──────────────────────────────────────────────────────────

# Exact paths, no parameters.
PUBLIC_EXACT: frozenset[str] = frozenset({
    "/health",              # liveness probe — must answer before anyone logs in
    "/auth/status",         # tells the UI whether first-run setup is needed
    "/auth/login",          # obviously
    "/auth/register",       # first user bootstraps the instance; afterwards the
                            # route itself requires an admin caller
    "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect",
})

# Patterns for links we deliberately hand to people who have no account.
# Each carries an unguessable token that IS the credential, so the URL is the
# authorisation — which is why these and only these are matched loosely.
PUBLIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Public self-check-in: attendees enter their own name at an event.
    re.compile(r"^/agents/attendance-payment/collections/public/[^/]+(/attendees)?$"),
    # Emailed approval magic-links, and the callback that completes them.
    re.compile(r"^/compliance/approve/verify/[^/]+$"),
    re.compile(r"^/compliance/approve/[^/]+$"),
    re.compile(r"^/compliance/approval-callback$"),
)


def is_public(path: str) -> bool:
    """True if this path is deliberately reachable without a session."""
    if path in PUBLIC_EXACT:
        return True
    return any(p.match(path) for p in PUBLIC_PATTERNS)


# ─── the forced password change ─────────────────────────────────────────────
#
# An administrator inviting twenty colleagues has to choose each starting
# password, so for a short while the administrator knows every user's password.
# That is only tolerable if the password expires the first time it is used.
#
# Enforced HERE, in the default-deny middleware, for the same reason the
# authentication check lives here: a rule applied route by route protects the
# routes somebody remembered. This one covers every route that exists and every
# route anyone adds later. While a change is pending the session can reach only
# the handful of paths below — enough to see who you are, set a new password,
# and sign out. Nothing that reads a payment, and nothing that approves one.

PASSWORD_CHANGE_ALLOWED: frozenset[str] = frozenset({
    "/auth/me",
    "/auth/password",
    "/auth/logout",
})


# ─── middleware ─────────────────────────────────────────────────────────────


class AuthMiddleware:
    """Pure-ASGI bearer-token gate.

    Deliberately raw ASGI rather than Starlette's BaseHTTPMiddleware: that class
    buffers the whole response and deadlocks with GZipMiddleware on anything
    large enough to compress — a bug this codebase has already been bitten by
    (see _RequestIDMiddleware in api/main.py).

    Routes keep their own `Depends(current_user)` and role checks. This is a
    floor, not a replacement: it guarantees a caller is authenticated, while the
    route still decides what that particular user may do.
    """

    def __init__(self, app, allowed_origins: Iterable[str] = ()):
        self.app = app
        self._origins = set(allowed_origins)

    # CORS runs inside this middleware, so a 401 generated here would otherwise
    # carry no CORS headers — the browser would surface an opaque network error
    # instead of the 401, and the frontend could never cleanly sign the user
    # out. Reflecting the origin on the rejection keeps that path working.
    def _cors_headers(self, scope) -> list[tuple[bytes, bytes]]:
        origin = ""
        for k, v in scope.get("headers") or []:
            if k == b"origin":
                origin = v.decode("latin-1")
                break
        if origin and origin in self._origins:
            return [
                (b"access-control-allow-origin", origin.encode("latin-1")),
                (b"access-control-allow-credentials", b"true"),
                (b"vary", b"Origin"),
            ]
        return []

    async def _reject(self, scope, send, detail: str, status: int = 401,
                      extra: Optional[dict] = None) -> None:
        body = json.dumps({"detail": detail, **(extra or {})}).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            *self._cors_headers(scope),
        ]
        if status == 401:
            headers.insert(2, (b"www-authenticate", b"Bearer"))
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # CORS preflight carries no Authorization header by design.
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if is_public(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        token = ""
        for k, v in scope.get("headers") or []:
            if k == b"authorization":
                raw = v.decode("latin-1")
                if raw.lower().startswith("bearer "):
                    token = raw[7:].strip()
                break

        if not token:
            await self._reject(scope, send, "Not authenticated.")
            return

        try:
            import auth
            user = auth.verify_token(token)
        except Exception as exc:
            # auth.AuthError carries a message safe to show ("Session expired —
            # please sign in again"). Anything else is reported generically.
            import auth as _auth
            detail = str(exc) if isinstance(exc, _auth.AuthError) else "Invalid session."
            await self._reject(scope, send, detail)
            return

        # A one-time password gets you exactly far enough to replace it.
        # 403 with a machine-readable flag, not 401: the session is valid, so
        # the frontend must redirect to the change-password screen rather than
        # sign the user out and lose the credential they just used.
        if getattr(user, "must_change_password", False) \
                and scope.get("path", "") not in PASSWORD_CHANGE_ALLOWED:
            await self._reject(
                scope, send,
                "Set a new password before using DOCex. The password you were "
                "given works once.",
                status=403,
                extra={"must_change_password": True},
            )
            return

        await self.app(scope, receive, send)
