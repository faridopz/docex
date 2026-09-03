"""
Auth coverage — no route is reachable without a session unless we said so.

This is the test that stops the hole reopening. Ninety routes were public
because each new router simply forgot to add `Depends(current_user)`, and
nothing anywhere would have told us. So instead of trusting decorators, this
enumerates every route the live app actually serves and calls it with no
credentials. Anything that isn't on the allowlist must answer 401.

When someone adds a route and this fails, that is the test working. Either the
route needs auth (fix the route) or it is genuinely public (add it to
api/security.PUBLIC_EXACT or PUBLIC_PATTERNS, with a comment saying why).

Run: python test_auth_coverage.py
"""
from __future__ import annotations

import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-authcov-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as auth_mod  # noqa: E402
from pathlib import Path  # noqa: E402

auth_mod._SECRET_FILE = Path(_TMP) / ".auth_secret"
auth_mod._secret_cache = None

from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402
from api import security  # noqa: E402

client = TestClient(m.app)

_passed = _failed = 0


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def _sample_path(path: str) -> str:
    """Replace {params} with a value so the route matches and we exercise the
    middleware rather than a 404 from the router."""
    out = []
    for part in path.split("/"):
        out.append("sample" if part.startswith("{") and part.endswith("}") else part)
    return "/".join(out)


def _routes() -> list[tuple[str, str]]:
    seen = []
    for r in m.app.routes:
        methods = getattr(r, "methods", None)
        if not methods:
            continue
        for meth in sorted(methods - {"HEAD", "OPTIONS"}):
            seen.append((meth, r.path))
    return sorted(set(seen))


def test_every_route_is_protected_or_deliberately_public() -> None:
    print("\nEvery route: 401 without credentials, or on the allowlist")
    leaked: list[str] = []
    checked = public = 0

    for meth, path in _routes():
        target = _sample_path(path)
        if security.is_public(path):
            public += 1
            continue
        checked += 1
        try:
            res = client.request(meth, target)
        except Exception:
            # A handler that blew up before returning still means the request
            # got past the gate, which is the thing we care about.
            leaked.append(f"{meth} {path} (reached handler and raised)")
            continue
        if res.status_code != 401:
            leaked.append(f"{meth} {path} -> {res.status_code}")

    print(f"       {checked} routes required auth · {public} deliberately public")
    if leaked:
        print("\n  Routes reachable WITHOUT credentials:")
        for entry in leaked[:40]:
            print(f"    · {entry}")
    check(f"no route leaks ({len(leaked)} found)", not leaked)


def test_the_allowlist_actually_works() -> None:
    print("\nPublic paths still work without a session")
    check("/health is reachable", client.get("/health").status_code == 200)
    check("/auth/status is reachable", client.get("/auth/status").status_code == 200)
    # login with bad credentials must reach the handler (401 from auth logic,
    # not from the middleware) — either way it must not be a middleware reject
    r = client.post("/auth/login", json={"email": "nobody@x.com", "password": "wrong"})
    check("/auth/login reaches its handler", r.status_code in (400, 401, 422))


def test_allowlist_patterns_are_tight() -> None:
    print("\nThe public patterns don't accidentally open anything else")
    should_be_public = [
        "/agents/attendance-payment/collections/public/abc123",
        "/agents/attendance-payment/collections/public/abc123/attendees",
        "/compliance/approve/verify/tok",
        "/compliance/approve/tok",
        "/compliance/approval-callback",
    ]
    for p in should_be_public:
        check(f"public: {p}", security.is_public(p))

    must_not_be_public = [
        "/compliance/checks",
        "/compliance/rulebooks",
        "/compliance/org-profile",
        "/agents/attendance-payment/collections",
        "/agents/attendance-payment/runs",
        "/transactions",
        "/vouchers",
        "/requisitions",
        "/dashboard",
        "/auth/users",
        "/org/config",
        # near-misses on the patterns — these must NOT slip through
        "/agents/attendance-payment/collections/public",
        "/agents/attendance-payment/collections/public/abc/attendees/extra",
        "/compliance/approve/verify/tok/extra",
    ]
    for p in must_not_be_public:
        check(f"protected: {p}", not security.is_public(p))


def test_a_bad_token_is_rejected() -> None:
    print("\nTokens are actually verified, not merely present")
    for label, header in [
        ("garbage token", "Bearer not-a-real-token"),
        ("empty bearer", "Bearer "),
        ("wrong scheme", "Basic abc123"),
        ("tampered signature", "Bearer eyJ1aWQiOiJ4In0.deadbeef"),
    ]:
        r = client.get("/compliance/rulebooks", headers={"Authorization": header})
        check(f"{label} rejected", r.status_code == 401)


def test_a_real_session_gets_through() -> None:
    print("\nA valid session reaches the routes")
    # First registered user becomes admin and bootstraps the instance.
    reg = client.post("/auth/register", json={
        "email": "cover@test.org", "name": "Cover", "password": "test-password-123",
        "department": "finance",
    })
    check("registration succeeded", reg.status_code == 200)
    tok = client.post("/auth/login", json={
        "email": "cover@test.org", "password": "test-password-123",
    }).json().get("token")
    check("login returned a token", bool(tok))

    h = {"Authorization": f"Bearer {tok}"}
    for path in ("/auth/me", "/org/config", "/departments", "/compliance/rulebooks"):
        r = client.get(path, headers=h)
        check(f"{path} reachable when signed in ({r.status_code})", r.status_code == 200)


def main() -> int:
    print("=" * 64)
    print("Auth coverage — default deny, allowlist the exceptions")
    print("=" * 64)
    test_every_route_is_protected_or_deliberately_public()
    test_the_allowlist_actually_works()
    test_allowlist_patterns_are_tight()
    test_a_bad_token_is_rejected()
    test_a_real_session_gets_through()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
