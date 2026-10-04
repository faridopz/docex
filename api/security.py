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
import os
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
    # The same, for requisitions — an approver who is travelling, an auditor,
    # or a board member with no DOCex account. The token is HMAC-signed,
    # expires, and is bound to one org + one requisition + one step + one
    # email address, so it authorises exactly one decision and nothing else.
    #
    # Note the shapes: these have TWO and THREE segments after /requisitions,
    # where the authenticated detail route is /requisitions/{id} with one. A
    # token can therefore never be read as a requisition id, and none of the
    # authenticated /requisitions/{id}/… routes can be reached through here.
    re.compile(r"^/requisitions/approve/verify/[^/]+$"),
    re.compile(r"^/requisitions/approve/[^/]+$"),
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


# ─── the overdue second factor ──────────────────────────────────────────────
#
# An organisation that switches on two-factor for its approvers is buying one
# specific promise: a leaked password alone can no longer release money. The
# grace period exists so a payment run is not missed the day the rule lands;
# it is not a suggestion. Once it has passed, an unenrolled approver's session
# can reach only what it takes to enrol — and sign out. Same mechanism as the
# forced password change, enforced in the same place, for the same reason.

MFA_SETUP_ALLOWED: frozenset[str] = frozenset({
    "/auth/me",
    "/auth/logout",
    "/auth/mfa",
    "/auth/mfa/begin",
    "/auth/mfa/confirm",
    "/auth/password",
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

        # The grace period for a required second factor has run out. The
        # session is still valid — the person proved their password — so this
        # is a 403 with a flag, and the frontend sends them to the setup
        # screen rather than signing them out. Viewers, and anyone still
        # inside their grace period, never reach the enrolment lookup.
        if scope.get("path", "") not in MFA_SETUP_ALLOWED:
            try:
                import mfa
                overdue = mfa.is_overdue(
                    user.id, user.role, getattr(user, "created_at", None),
                    getattr(user, "org_id", None))
            except Exception:
                # A broken policy record must not lock the whole organisation
                # out of a finance system. Log-worthy, but fail open here:
                # the password check above has already run.
                overdue = False
            if overdue:
                await self._reject(
                    scope, send,
                    "Two-factor authentication is required for your role and "
                    "the setup period has ended. Set it up to continue.",
                    status=403,
                    extra={"mfa_setup_required": True},
                )
                return

        # Modules the organisation hasn't switched on are refused here, not
        # just hidden in the menu: screening and knowledge spend model credit
        # on every call, and a direct API call used to bypass the nav.
        module = module_for_path(scope.get("path", ""))
        if module and not _module_enabled(module):
            await self._reject(
                scope, send,
                f"{module.capitalize()} isn't part of your organisation's DOCex plan. "
                "Contact founder@docex.app to add it.",
                status=403,
                extra={"module_not_enabled": module},
            )
            return

        # Who may use this part of the system at all. Routes still apply
        # their own finer rules; this is the floor for whole areas — payroll,
        # bank data, reconciliation, the older payment pipelines — so that a
        # route written without a role check can't hand money data to any
        # signed-in member of staff. (Found in the 30 Sep 2026 audit: about 110
        # older routes checked only that someone was signed in.)
        refusal = access_refusal(scope.get("method", "GET"), scope.get("path", ""), user)
        if refusal:
            status, detail = refusal
            await self._reject(scope, send, detail, status=status)
            return

        await self.app(scope, receive, send)


# ─── access by area ─────────────────────────────────────────────────────────
#
# (methods, path pattern, who). First match wins. "*" means every method.
#   money          — an admin, or anyone in the org's finance department(s)
#   money_approver — an admin, or an approver in the finance department(s)
#   chain          — money, plus departments that own an approval step
#   admin          — administrators only
#   feature:<flag> — only when the organisation has switched that feature on
_READ = frozenset({"GET", "HEAD"})
_ANY = frozenset({"*"})
_ACCESS_RULES: tuple[tuple[frozenset, re.Pattern[str], str], ...] = (
    # Salaries, bank accounts, statements, ledgers: Finance's material.
    (_ANY, re.compile(r"^/payroll(/.*)?$"), "money"),
    (_ANY, re.compile(r"^/accounting(/.*)?$"), "money"),
    (_ANY, re.compile(r"^/reconciliation(/.*)?$"), "money"),
    (_READ, re.compile(r"^/treasury/wht/(policy|preview)$"), "signed_in"),
    (frozenset({"POST"}), re.compile(r"^/treasury/wht/preview$"), "signed_in"),
    (_ANY, re.compile(r"^/treasury(/.*)?$"), "money"),
    (_ANY, re.compile(r"^/verify(/.*)?$"), "money"),
    (_ANY, re.compile(r"^/per-diem(/.*)?$"), "money"),
    (_ANY, re.compile(r"^/agents/attendance-payment(/.*)?$"), "money"),
    # Rate cards set what people are paid: anyone may read, admins change.
    (_READ, re.compile(r"^/rate-cards(/.*)?$"), "signed_in"),
    (_ANY, re.compile(r"^/rate-cards(/.*)?$"), "admin"),
    # Vendor bank details and blocking: Finance.
    (_ANY, re.compile(r"^/vendors/[^/]+/(verify|block|unblock)$"), "money"),
    # The policy-document (compliance) area.
    (_ANY, re.compile(r"^/compliance/(org-profile|rulebooks|policy)(/.*)?$"), "admin_write"),
    (frozenset({"DELETE"}), re.compile(r"^/compliance(/.*)?$"), "admin"),
    (_ANY, re.compile(r"^/compliance/checks/[^/]+/(approve|unapprove|mark-paid|request-signoff)$"), "money_approver"),
    (_READ, re.compile(r"^/compliance(/.*)?$"), "chain"),
    (_ANY, re.compile(r"^/compliance(/.*)?$"), "money"),
    # The older intake pipeline, replaced by payment requests. Only for an
    # organisation that has deliberately switched it (or the attendance
    # vouchers that feed it) back on. Vouchers are payables: Finance's.
    (_ANY, re.compile(r"^/vouchers(/.*)?$"), "feature:attendance_payments+money"),
    (_ANY, re.compile(r"^/transactions(/.*)?$"), "feature:legacy_intake|attendance_payments"),
    # Knowledge decks: anyone with the module may ask; admins curate.
    (frozenset({"DELETE", "PATCH"}), re.compile(r"^/knowledge/decks/[^/]+$"), "admin"),
    (frozenset({"POST"}), re.compile(r"^/knowledge/decks$"), "admin"),
    (_ANY, re.compile(r"^/diagnostics(/.*)?$"), "admin"),
)


def _rule_for(method: str, path: str) -> Optional[str]:
    for methods, pattern, who in _ACCESS_RULES:
        if ("*" in methods or method in methods) and pattern.match(path):
            return who
    return None


def _money_departments(org: str) -> set[str]:
    try:
        import payment_voucher
        return set(payment_voucher.schedule_departments(org))
    except Exception:
        return {"finance"}


def _chain_departments(org: str) -> set[str]:
    out = _money_departments(org)
    try:
        import requisitions
        wf = requisitions.get_workflow(org)
        out |= {s.department.lower() for s in wf.steps if s.department}
        out |= {(r.department or "").lower() for r in wf.cc_rules if getattr(r, "department", "")}
    except Exception:
        pass
    return out


def access_refusal(method: str, path: str, user) -> Optional[tuple[int, str]]:
    """(status, message) if this user may not use this area; None if they may."""
    who = _rule_for(method.upper(), path)
    if who is None or who == "signed_in":
        return None
    org = (getattr(user, "org_id", None) or os.environ.get("DOCEX_ORG") or "default").strip() or "default"
    role = getattr(user, "role", "") or ""
    dept = (getattr(user, "department", "") or "").lower()
    if who.startswith("feature:"):
        # A switched-off area is absent for everyone, administrators included:
        # "off" must mean off, not "off unless you're an admin".
        spec, _, then = who.split(":", 1)[1].partition("+")
        try:
            import org_config
            on = any(org_config.feature_enabled(org, f) for f in spec.split("|") if f)
        except Exception:
            on = False
        if not on:
            return 404, "Not Found"
        if not then:
            return None
        who = then
    if role == "admin":
        return None
    if who == "admin_write":
        return None if method.upper() in _READ and dept in _chain_departments(org) else \
            (403, "Only an administrator can change this.")
    if who == "admin":
        return 403, "Only an administrator can do this."
    if who == "money":
        return None if dept in _money_departments(org) else \
            (403, "This is Finance's area. Ask Finance or an administrator.")
    if who == "money_approver":
        return None if (dept in _money_departments(org) and role == "approver") else \
            (403, "Only a Finance approver or an administrator can do this.")
    if who == "chain":
        return None if dept in _chain_departments(org) else \
            (403, "Only the people who approve payments can see this.")
    return 403, "Not allowed."


# ─── module entitlements ────────────────────────────────────────────────────

# Path prefix → the product module it belongs to. Everything not listed is
# part of the core (compliance and finance) and always available.
_MODULE_PATHS: tuple[tuple[str, str], ...] = (
    ("/extract", "screening"),
    ("/draft-followups", "screening"),
    ("/knowledge", "knowledge"),
)


def module_for_path(path: str) -> str | None:
    for prefix, module in _MODULE_PATHS:
        if path == prefix or path.startswith(prefix + "/"):
            return module
    return None


def _module_enabled(module: str) -> bool:
    try:
        import org_config
        org = (os.environ.get("DOCEX_ORG") or "default").strip() or "default"
        return module in org_config.client_config(org)["modules"]
    except Exception:
        # A broken config record must not lock an organisation out; the
        # nav still hides what isn't bought.
        return True


# ─── request size ───────────────────────────────────────────────────────────
#
# Found in the 30 Sep audit (M5): no request had a size limit, and several
# upload routes read the whole body into memory before any check. One large
# upload could take a free-plan server down for every user. This caps every
# request in one place, including chunked uploads that never say how big
# they are. DOCEX_MAX_UPLOAD_MB raises it for a client that genuinely needs
# more (the default comfortably fits a batch of scanned receipts).

_DEFAULT_MAX_MB = 40


def _max_body_bytes() -> int:
    try:
        return max(1, int(os.environ.get("DOCEX_MAX_UPLOAD_MB", _DEFAULT_MAX_MB))) * 1024 * 1024
    except ValueError:
        return _DEFAULT_MAX_MB * 1024 * 1024


class BodySizeLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        limit = _max_body_bytes()
        too_big_msg = (f"That upload is too large (the limit is {limit // (1024 * 1024)} MB). "
                       "Split it into smaller files, or compress scans before attaching them.")
        for k, v in scope.get("headers") or []:
            if k == b"content-length":
                try:
                    if int(v) > limit:
                        await _send_json(send, 413, {"detail": too_big_msg})
                        return
                except ValueError:
                    pass
                break

        seen = 0
        started = False
        refused = False

        async def counted_receive():
            nonlocal seen, refused, started
            if refused:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg.get("type") == "http.request":
                seen += len(msg.get("body") or b"")
                if seen > limit:
                    # Answer now and tell the app the client went away, so it
                    # stops reading whatever parser it is in the middle of.
                    refused = True
                    if not started:
                        started = True
                        await _send_json(send, 413, {"detail": too_big_msg})
                    return {"type": "http.disconnect"}
            return msg

        async def tracking_send(msg):
            nonlocal started
            if refused:
                return          # we have already answered
            if msg.get("type") == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, counted_receive, tracking_send)
        except Exception:
            if not refused:
                raise


async def _send_json(send, status: int, body: dict) -> None:
    import json as _json
    raw = _json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(raw)).encode())]})
    await send({"type": "http.response.body", "body": raw})
