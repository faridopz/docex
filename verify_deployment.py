#!/usr/bin/env python3
"""
Is this deployment safe to put a client's money in?

Everything else in this repo tests the code. This tests the DEPLOYMENT — the
running instance, over the network, the way a user or an attacker meets it.
The distinction matters because every failure this catches is invisible
locally: the code is identical, only the environment is wrong.

    python3 verify_deployment.py https://docex-api.onrender.com

What it checks, in the order that decides whether to keep going:

  1. It answers at all, and says which storage it is using.
  2. Nothing is readable without signing in. This runs against EVERY route the
     instance actually serves, discovered from its own OpenAPI schema — not a
     list someone maintained by hand and forgot to update.
  3. Sessions survive a restart (AUTH_SECRET is set, not per-container).
  4. CORS names the real frontend and does not accept anything that asks.
  5. Errors do not leak stack traces, file paths or the database URL.
  6. Brute force gets throttled.
  7. Rejections do not reveal which email addresses exist.

Optional, with credentials, it also proves the round trip a finance officer
depends on — sign in, write a record, read it back:

    python3 verify_deployment.py https://... --email me@org --password '...'

Then there is one gate this script CANNOT check for you, and it is the most
important one:

    DATA SURVIVES A REDEPLOY.

  Create a requisition, note its reference, trigger a redeploy, wait for the
  health check, and look for the same reference. If it is gone, nothing else
  here matters. `--durability` prints the exact steps.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

_passed = _failed = _warned = 0


def ok(label: str, detail: str = "") -> None:
    global _passed
    _passed += 1
    print(f"  \033[32mok\033[0m   {label}{('  — ' + detail) if detail else ''}")


def fail(label: str, detail: str = "") -> None:
    global _failed
    _failed += 1
    print(f"  \033[31mFAIL\033[0m {label}{('  — ' + detail) if detail else ''}")


def warn(label: str, detail: str = "") -> None:
    global _warned
    _warned += 1
    print(f"  \033[33mwarn\033[0m {label}{('  — ' + detail) if detail else ''}")


def request(url: str, *, method: str = "GET", token: str = "", body=None,
            headers: dict | None = None, timeout: int = 90):
    """Returns (status, text, headers). Never raises for an HTTP error."""
    data = None
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers or {})
    except Exception as e:                                       # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}", {}


# ─── 1. it is alive ─────────────────────────────────────────────────────────


def check_alive(base: str) -> bool:
    print("\n\033[1mIt answers\033[0m")
    t = time.perf_counter()
    status, text, _ = request(f"{base}/health")
    elapsed = time.perf_counter() - t
    if status != 200:
        fail("/health responds", f"got {status}: {text[:120]}")
        print("\n  Nothing else can be checked. Is the service deployed and awake?")
        return False
    ok("/health responds", f"{elapsed * 1000:.0f}ms")
    if elapsed > 5:
        warn("first response was slow",
             f"{elapsed:.1f}s — a sleeping free-tier instance? A finance officer "
             "meeting this concludes the system is broken.")
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            for key in ("storage", "store", "database", "version", "org"):
                if key in payload:
                    ok(f"/health reports {key}", str(payload[key])[:80])
    except Exception:
        pass
    return True


# ─── 2. nothing is readable without signing in ──────────────────────────────


def check_default_deny(base: str) -> None:
    """Ask the instance what routes it serves, then try every one of them.

    A hand-maintained list checks the routes somebody remembered. The OpenAPI
    schema is what the instance actually exposes right now, including whatever
    was added last week.
    """
    print("\n\033[1mNothing is readable without signing in\033[0m")

    status, text, _ = request(f"{base}/openapi.json")
    paths: list[tuple[str, str]] = []
    if status == 200:
        try:
            spec = json.loads(text)
            for path, methods in (spec.get("paths") or {}).items():
                for method in methods:
                    if method.upper() in ("GET", "DELETE"):
                        paths.append((method.upper(), path))
        except Exception:
            pass

    if not paths:
        warn("could not read the route list from /openapi.json",
             "falling back to a fixed list — this checks less than it should")
        paths = [("GET", p) for p in (
            "/compliance/checks", "/compliance/rulebooks", "/requisitions",
            "/payments", "/auth/users", "/dashboard", "/transactions",
            "/vouchers", "/vendors", "/advances/aging", "/treasury/accounts",
        )]

    try:
        sys.path.insert(0, ".")
        from api.security import is_public
    except Exception:
        def is_public(p: str) -> bool:                            # type: ignore
            return p in ("/health", "/auth/status", "/auth/login", "/auth/register",
                         "/docs", "/redoc", "/openapi.json")

    leaked: list[str] = []
    tested = 0
    for method, path in paths:
        if "{" in path or is_public(path):
            continue
        tested += 1
        status, body, _ = request(f"{base}{path}", method=method)
        if status not in (401, 403):
            leaked.append(f"{method} {path} → {status}")

    if leaked:
        for entry in leaked[:10]:
            fail("reachable without a session", entry)
        if len(leaked) > 10:
            fail(f"...and {len(leaked) - 10} more")
        print("\n  \033[31mSTOP. Do not put client data in this instance.\033[0m")
    else:
        ok(f"all {tested} parameterless routes require a session")

    # The allowlist itself must still work, or nobody can sign in.
    for path in ("/health", "/auth/status"):
        status, _, _ = request(f"{base}{path}")
        (ok if status == 200 else fail)(f"{path} is still public", f"{status}")

    # A token that is merely well-formed must not be accepted.
    for bad, why in [("not-a-token", "garbage"),
                     ("eyJhIjoxfQ.ZmFrZXNpZ25hdHVyZQ", "forged signature")]:
        status, _, _ = request(f"{base}/auth/me", token=bad)
        (ok if status in (401, 403) else fail)(f"a {why} token is refused", f"{status}")


# ─── 3. sessions survive a restart ──────────────────────────────────────────


def check_session_secret(base: str, token: str) -> None:
    print("\n\033[1mSessions are signed by a stable secret\033[0m")
    if not token:
        warn("skipped", "pass --email/--password to check this")
        print("      Without AUTH_SECRET set, each container invents its own "
              "signing key: every user is signed out on every deploy, and two "
              "instances never agree on a session. The only way to see it is "
              "to hold a token across a restart.")
        return
    status, _, _ = request(f"{base}/auth/me", token=token)
    if status == 200:
        ok("the token issued a moment ago is accepted")
        print("      To prove AUTH_SECRET is really set: keep this token, "
              "redeploy, and run again with it. If it stops working, the "
              "secret is per-container.")
    else:
        fail("the token was rejected immediately", f"{status}")


# ─── 4. CORS ────────────────────────────────────────────────────────────────


def check_cors(base: str, frontend: str) -> None:
    print("\n\033[1mCORS names the real frontend\033[0m")
    evil = "https://not-your-frontend.example"
    _, _, headers = request(f"{base}/health", headers={"Origin": evil})
    allowed = headers.get("access-control-allow-origin", "")
    if allowed == "*":
        fail("any origin is accepted", "'*' — a page on any site can call this API "
                                       "with a user's session")
    elif allowed == evil:
        fail("an arbitrary origin was reflected", evil)
    else:
        ok("an unknown origin is not accepted", allowed or "no CORS header")

    if frontend:
        _, _, headers = request(f"{base}/health", headers={"Origin": frontend})
        got = headers.get("access-control-allow-origin", "")
        if got == frontend:
            ok("the real frontend is accepted", frontend)
        else:
            fail("the real frontend is NOT accepted",
                 f"ALLOWED_ORIGINS must contain exactly {frontend} "
                 "(no trailing slash). Every request from the app will fail.")
    else:
        warn("frontend origin not checked", "pass --frontend https://…")


# ─── 5. errors say nothing useful to an attacker ────────────────────────────


def check_error_leaks(base: str) -> None:
    print("\n\033[1mErrors do not leak the inside of the system\033[0m")
    probes = [
        f"{base}/requisitions/../../etc/passwd",
        f"{base}/auth/users/%00",
        f"{base}/does-not-exist-{int(time.time())}",
    ]
    tells = [
        ("Traceback", "a Python traceback"),
        ("/app/", "server file paths"),
        ("site-packages", "server file paths"),
        ("postgresql://", "the database URL"),
        ("psycopg", "the database driver"),
        ("sqlite3.", "the database driver"),
        ("AUTH_SECRET", "a secret name"),
        ("sk-ant", "an API key"),
    ]
    leaked = False
    for url in probes:
        _, body, _ = request(url)
        for needle, what in tells:
            if needle in body:
                fail("an error response leaked", f"{what} at {url.split(base)[-1]}")
                leaked = True
    if not leaked:
        ok(f"{len(probes)} malformed requests returned nothing internal")


# ─── 6 & 7. guessing passwords ──────────────────────────────────────────────


def check_login_hardening(base: str) -> None:
    print("\n\033[1mGuessing a password gets harder, not easier\033[0m")
    victim = f"probe-{int(time.time())}@example.invalid"

    status, body, _ = request(f"{base}/auth/login", method="POST",
                              body={"email": victim, "password": "wrong-password"})
    if status == 0:
        warn("could not reach /auth/login", body[:80])
        return
    unknown_msg = body[:200]
    (ok if status == 401 else warn)("an unknown account is refused", f"{status}")

    codes = []
    for _ in range(10):
        st, bd, _ = request(f"{base}/auth/login", method="POST",
                            body={"email": victim, "password": "wrong-password"})
        codes.append(st)
        if st == 429:
            break
    if 429 in codes:
        ok("repeated failures are throttled", f"locked out after {len(codes)} attempts")
    else:
        fail("no throttling", "ten wrong passwords in a row all answered the same. "
                              "An attacker can guess as fast as the server replies.")

    # Enumeration: a wrong password for a REAL account should look identical to
    # a wrong password for one that does not exist.
    if "not found" in unknown_msg.lower() or "no such" in unknown_msg.lower():
        fail("the error reveals whether an account exists", unknown_msg[:90])
    else:
        ok("the error does not reveal whether an account exists")


# ─── the round trip that matters ────────────────────────────────────────────


def check_round_trip(base: str, email: str, password: str) -> str:
    print("\n\033[1mSigning in, and writing something down\033[0m")
    status, body, _ = request(f"{base}/auth/login", method="POST",
                              body={"email": email, "password": password})
    if status != 200:
        fail("sign-in", f"{status}: {body[:160]}")
        return ""
    try:
        payload = json.loads(body)
        token = payload["token"]
    except Exception:
        fail("sign-in returned no token", body[:120])
        return ""
    ok("signed in", email)

    if payload.get("must_change_password"):
        warn("this account is still on a one-time password",
             "it can reach nothing but the password screen — expected for a "
             "freshly invited user, wrong for the account you administer with")
        return token

    status, body, _ = request(f"{base}/auth/me", token=token)
    (ok if status == 200 else fail)("the session is accepted", f"{status}")

    status, body, _ = request(f"{base}/dashboard", token=token)
    (ok if status == 200 else fail)("the dashboard loads", f"{status}")

    # A read that touches stored records — proves the store is really wired up,
    # not merely that the process started.
    status, body, _ = request(f"{base}/requisitions", token=token)
    if status == 200:
        try:
            n = len(json.loads(body).get("requisitions", []))
            ok("requisitions read from storage", f"{n} record(s)")
        except Exception:
            ok("requisitions endpoint answered")
    else:
        warn("could not list requisitions", f"{status}")
    return token


# ─── the check this script cannot do ────────────────────────────────────────

DURABILITY = """
\033[1mThe one gate this script cannot check for you\033[0m

  Everything above passes on an instance that will lose every record on its
  next deploy, because losing them is silent: writing a file always succeeds.
  Only a redeploy proves durability, and only you can trigger one.

    1. Sign in and create a requisition. Write its reference down.  e.g. REQ-0007
    2. Trigger a redeploy (push an empty commit, or Render → Manual Deploy).
    3. Wait for the health check to go green.
    4. Sign in again and look for that reference.

  It is there            → storage is durable. Note the date in DEPLOYMENT.md.
  It is gone             → \033[31mSTOP.\033[0m The instance is writing to a disk the
                           platform replaces. Set DOCEX_DATABASE_URL to the
                           managed database and deploy again before any client
                           touches it.
  You are signed out     → AUTH_SECRET is not set, so each container signs
                           tokens with its own invented key.
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url", nargs="?", help="e.g. https://docex-api.onrender.com")
    ap.add_argument("--email", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--frontend", default="",
                    help="the exact frontend origin, e.g. https://docex.vercel.app")
    ap.add_argument("--durability", action="store_true",
                    help="print the redeploy test and exit")
    args = ap.parse_args()

    if args.durability:
        print(DURABILITY)
        return 0
    if not args.base_url:
        ap.error("a base URL is required (or use --durability)")

    base = args.base_url.rstrip("/")
    print(f"\033[1mVerifying {base}\033[0m")

    if not check_alive(base):
        return 1
    check_default_deny(base)

    token = ""
    if args.email and args.password:
        token = check_round_trip(base, args.email, args.password)
    else:
        print("\n\033[1mSigning in\033[0m")
        warn("skipped", "pass --email and --password to test the round trip")

    check_session_secret(base, token)
    check_cors(base, args.frontend.rstrip("/"))
    check_error_leaks(base)
    check_login_hardening(base)

    print(f"\n\033[1m{_passed} passed, {_failed} failed, {_warned} warnings\033[0m")
    print(DURABILITY)

    if _failed:
        print("\033[31mNot ready. Fix the failures above before a client signs in.\033[0m")
        return 1
    print("\033[32mNo failures. The redeploy test above is still yours to run.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
