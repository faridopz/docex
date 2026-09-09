#!/usr/bin/env python3
"""
Can an administrator actually get twenty people into this system?

`verify_deployment.py` proves the instance is secure and reachable. This proves
the thing you will do in front of the client: invite somebody, watch them sign
in, watch them be stopped until they set their own password, and — the part
nobody tests until it is urgent — reset a colleague who is locked out and end
access for someone who has left.

Run it against the live instance, with an administrator's credentials:

    python3 verify_onboarding.py https://docex-api.onrender.com \\
        --email admin@neemfoundation.org --password '...'

It creates ONE throwaway account, walks it through the whole journey, then
deactivates it. Nothing else in the system is touched. The throwaway is left
deactivated rather than deleted, because DOCex deliberately has no delete — a
finance system must still be able to say who approved what.

Safe to run against production. It writes one user record and nothing else.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; B = "\033[1m"; D = "\033[2m"; X = "\033[0m"

_passed = _failed = 0


def ok(label: str, detail: str = "") -> None:
    global _passed
    _passed += 1
    print(f"  {G}ok{X}    {label}{('  ' + D + detail + X) if detail else ''}")


def bad(label: str, detail: str = "") -> None:
    global _failed
    _failed += 1
    print(f"  {R}FAIL{X}  {label}{('  — ' + detail) if detail else ''}")


def check(label: str, cond: bool, detail: str = "") -> bool:
    (ok if cond else bad)(label, detail)
    return cond


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def __call__(self, path, method="GET", token="", body=None, timeout=90):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=data,
                                     method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:
                return e.code, {}
        except Exception as e:                                    # noqa: BLE001
            return 0, {"error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    ap.add_argument("--email", required=True, help="an administrator's email")
    ap.add_argument("--password", required=True)
    ap.add_argument("--test-email", default="",
                    help="the throwaway account (default: onboarding-check@<time>.test)")
    a = ap.parse_args()

    api = Api(a.base_url)
    probe = a.test_email or f"onboarding-check-{int(time.time())}@docex.test"

    print(f"{B}Onboarding check — {api.base}{X}")
    print(f"{D}Throwaway account: {probe}{X}")

    # The instance may be asleep on a free plan. Wake it before timing anything.
    t = time.perf_counter()
    status, _ = api("/health")
    woke = time.perf_counter() - t
    if status != 200:
        bad("the instance is not answering", f"/health returned {status}")
        return 1
    ok("instance is awake", f"{woke * 1000:.0f}ms")
    if woke > 5:
        print(f"        {Y}That was a cold start. Hit the app a few minutes "
              f"before your meeting.{X}")

    # ── 1 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}1. The administrator signs in{X}")
    status, login = api("/auth/login", "POST",
                        body={"email": a.email, "password": a.password})
    if status == 401 and "code" in str(login).lower():
        bad("admin sign-in", "this account has two-factor on — use one without it")
        return 1
    if not check("admin signs in", status == 200, str(login)[:120]):
        return 1
    admin = login["token"]
    if login.get("must_change_password"):
        bad("this admin is still on a one-time password",
            "set a real password first, then re-run")
        return 1

    # ── 2 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}2. They invite a colleague{X}")
    status, inv = api("/auth/users/invite", "POST", admin,
                      {"email": probe, "name": "Onboarding Check",
                       "department": "program", "role": "reviewer"})
    if status == 409:
        bad("that email already exists", "pass a different --test-email")
        return 1
    if not check("invite accepted", status == 200, str(inv)[:160]):
        return 1
    temp = inv.get("temporary_password", "")
    user_id = (inv.get("user") or {}).get("id", "")
    check("a one-time password is returned", bool(temp))
    check("it can be read aloud without mistakes",
          "-" in temp and not (set("0O1lI") & set(temp)), temp)

    # ── 3 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}3. That colleague signs in for the first time{X}")
    status, first = api("/auth/login", "POST",
                        body={"email": probe, "password": temp})
    check("they can sign in", status == 200)
    check("and are told to set their own password",
          first.get("must_change_password") is True)
    tok = first.get("token", "")

    # ── 4 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}4. Until they do, the system is closed to them{X}")
    for path in ("/dashboard", "/requisitions", "/payments", "/auth/users"):
        status, _ = api(path, token=tok)
        check(f"{path} refused", status == 403, f"got {status}")
    status, _ = api("/auth/me", token=tok)
    check("/auth/me still works, so the app knows who they are", status == 200)

    # ── 5 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}5. They set their own password{X}")
    own = "TheirOwnPassword2026!"
    status, changed = api("/auth/password", "POST", tok,
                          {"current_password": temp, "new_password": own})
    check("password changed", status == 200, str(changed)[:120])
    fresh = changed.get("token", "")

    status, _ = api("/dashboard", token=fresh)
    check("the dashboard opens now", status == 200, f"got {status}")
    status, _ = api("/dashboard", token=tok)
    check("their previous session is dead", status == 401, f"got {status}")
    status, _ = api("/auth/login", "POST", body={"email": probe, "password": temp})
    check("the one-time password is spent", status == 401, f"got {status}")

    # ── 6 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}6. A reviewer cannot do an administrator's job{X}")
    status, _ = api("/auth/users", token=fresh)
    check("reviewer refused the user list", status == 403, f"got {status}")

    # ── 7 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}7. And they can actually work{X}")
    status, wf = api("/requisitions/workflow", token=fresh)
    if check("their approval chain loads", status == 200, str(wf)[:100]):
        steps = wf.get("steps") or (wf.get("workflow") or {}).get("steps") or []
        check(f"{len(steps)} approval step(s) configured", len(steps) > 0)
        cats = wf.get("allowed_categories") or \
            (wf.get("workflow") or {}).get("allowed_categories") or []
        check(f"{len(cats)} payment categories configured", len(cats) > 0)

    # ── 8 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}8. Somebody loses their password{X}")
    status, reset = api(f"/auth/users/{user_id}/reset-password", "POST", admin)
    check("the administrator can reset them", status == 200)
    check("a new one-time password is issued", bool(reset.get("temporary_password")))
    status, _ = api("/dashboard", token=fresh)
    check("the reset killed their live session", status == 401, f"got {status}")

    # ── 9 ──────────────────────────────────────────────────────────────────
    print(f"\n{B}9. Somebody leaves{X}")
    status, gone = api(f"/auth/users/{user_id}/deactivate", "POST", admin)
    check("access ended", status == 200 and gone.get("active") is False,
          str(gone)[:100])
    status, _ = api("/auth/login", "POST",
                    body={"email": probe,
                          "password": reset.get("temporary_password", "x")})
    check("they cannot sign in again", status == 401, f"got {status}")

    status, users = api("/auth/users", token=admin)
    emails = [u.get("email") for u in (users.get("users") or [])]
    check("but their record is KEPT, not deleted", probe in emails)
    print(f"        {D}The approval trail must still name who authorised a "
          f"payment in March about someone who left in April.{X}")

    # ── done ───────────────────────────────────────────────────────────────
    print(f"\n{B}{_passed} passed, {_failed} failed{X}")
    print(f"{D}The throwaway account {probe} is left deactivated. "
          f"It cannot sign in and holds nothing.{X}")
    if _failed:
        print(f"\n{R}Do not hand out logins until these pass.{X}")
        return 1
    print(f"\n{G}Onboarding works end to end. Safe to create real accounts.{X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
