"""
An administrator with two-step sign-in can sign in from the real website.

Reported 28 Sep 2026: admin@neemfoundation.org could not sign in — every
attempt said "Your session has expired". The password was right. The server
answered, correctly, "Enter the 6-digit code" with the header X-DOCex-MFA:
required — but the website and the API are on different sites, and a
browser hides every response header the API does not explicitly expose. The
screen never saw the flag, never showed the code box, and fell back to the
generic 401 sentence meant for expired sessions. Every test ran same-origin,
where nothing is hidden, so nothing caught it.

Also covered: a rejected sign-in never tells the person their "session has
expired" — they have no session yet.

Run: python test_login_mfa_crossorigin.py
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-mfa-cors-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import mfa  # noqa: E402

_passed = _failed = 0
PW = "correct-horse-battery"
SITE = "http://localhost:3000"      # a different origin from the API, like production


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def test_the_browser_can_read_the_code_flag() -> None:
    print("\nCross-site sign-in with two-step sign-in on: the flag is readable")
    from fastapi.testclient import TestClient
    import api.main as m

    u = A.create_user("boss@acme.org", "Boss", PW, "finance", "admin", org_id="acme")
    setup = mfa.begin_enrolment(u.id, u.email, "acme")
    mfa.confirm_enrolment(u.id, mfa.current_code(setup["secret"]), "acme")

    c = TestClient(m.app, raise_server_exceptions=False)
    r = c.post("/auth/login", json={"email": "boss@acme.org", "password": PW},
               headers={"Origin": SITE})
    check("password right, code missing: 401 asking for the code", r.status_code == 401
          and "6-digit" in r.text, f"{r.status_code} {r.text[:120]}")
    check("the flag header is sent", r.headers.get("x-docex-mfa") == "required", str(dict(r.headers)))
    exposed = [h.strip().lower() for h in r.headers.get("access-control-expose-headers", "").split(",")]
    check("and the browser is allowed to read it (Access-Control-Expose-Headers)",
          "x-docex-mfa" in exposed, r.headers.get("access-control-expose-headers", "(none)"))

    code = mfa.current_code(setup["secret"])
    r = c.post("/auth/login", json={"email": "boss@acme.org", "password": PW, "mfa_code": code},
               headers={"Origin": SITE})
    check("with the code, signed in", r.status_code == 200 and r.json().get("token"),
          f"{r.status_code} {r.text[:120]}")


def test_the_screen_never_says_session_expired_at_sign_in() -> None:
    print("\nThe sign-in screen's messages (web/lib/errors.ts, run with node)")
    web = Path(__file__).parent / "web"
    script = r"""
const ts = require('typescript');
const fs = require('fs');
const src = fs.readFileSync('lib/errors.ts', 'utf8');
const out = ts.transpileModule(src, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: 'es2019'}}).outputText;
const m = {exports: {}}; new Function('module', 'exports', 'require', out)(m, m.exports, require);
const f = m.exports.friendlyError;
const code = f(401, JSON.stringify({detail: 'Enter the 6-digit code from your authenticator app.'})).message;
const wrongCode = f(401, JSON.stringify({detail: 'That code is not right, or has already been used.'})).message;
const expired = f(401, JSON.stringify({detail: 'Session expired — please sign in again.'})).message;
console.log(JSON.stringify({code, wrongCode, expired}));
"""
    try:
        res = subprocess.run(["node", "-e", script], cwd=web, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        check("node available", False, "node not installed")
        return
    if res.returncode != 0:
        check("errors.ts evaluated", False, res.stderr[-300:])
        return
    import json
    msg = json.loads(res.stdout.strip().splitlines()[-1])
    check("asked for a code: says so, not 'session expired'",
          "code" in msg["code"].lower() and "expired" not in msg["code"].lower(), msg["code"])
    check("wrong code: says so", "code" in msg["wrongCode"].lower() and "expired" not in msg["wrongCode"].lower(),
          msg["wrongCode"])
    check("a real expired session still says expired", "expired" in msg["expired"].lower(), msg["expired"])


if __name__ == "__main__":
    print("Two-step sign-in works from the real, cross-site website")
    test_the_browser_can_read_the_code_flag()
    test_the_screen_never_says_session_expired_at_sign_in()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
