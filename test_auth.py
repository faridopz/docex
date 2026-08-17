"""Checks for auth.py: hashing, tokens, RBAC-relevant lookups.
Run: python test_auth.py"""
from __future__ import annotations

import tempfile
from pathlib import Path

import auth as auth_mod

_u = Path(tempfile.mkdtemp(prefix="docex_users_"))
auth_mod._USER_DIR = _u
auth_mod._SECRET_FILE = _u / ".auth_secret"
auth_mod._secret_cache = None  # force re-derive against temp file

_fail = 0


def check(name, got, want):
    global _fail
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def expect(name, fn, exc=auth_mod.AuthError):
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected error, none raised")
        _fail += 1
    except exc:
        print(f"PASS  {name}: raised as expected")


# ── password hashing round-trips and rejects wrong passwords ──
h, s = auth_mod.hash_password("correct horse")
check("verify correct password", auth_mod.verify_password("correct horse", h, s), True)
check("reject wrong password", auth_mod.verify_password("wrong", h, s), False)
check("salt makes hashes unique", auth_mod.hash_password("same-password")[0] != auth_mod.hash_password("same-password")[0], True)
expect("weak password rejected", lambda: auth_mod.hash_password("123"), exc=ValueError)

# ── user creation + uniqueness ──
u = auth_mod.create_user("bola@taconnect-ng.org", "Bola", "s3cret!", "finance", "approver")
check("user department", u.department, "finance")
check("public view hides hash", "password_hash" in auth_mod.public(u).model_dump(), False)
expect("duplicate email rejected",
       lambda: auth_mod.create_user("BOLA@taconnect-ng.org", "Dup", "s3cret!", "finance"))

# ── authenticate ──
check("authenticate ok", auth_mod.authenticate("bola@taconnect-ng.org", "s3cret!").id, u.id)
expect("authenticate wrong pw", lambda: auth_mod.authenticate("bola@taconnect-ng.org", "nope"))
expect("authenticate unknown user", lambda: auth_mod.authenticate("ghost@x.org", "whatever"))

# ── tokens: issue, verify, tamper, expiry ──
tok = auth_mod.issue_token(u)
check("valid token resolves to user", auth_mod.verify_token(tok).id, u.id)
expect("tampered signature rejected", lambda: auth_mod.verify_token(tok[:-3] + "aaa"))
expect("garbage token rejected", lambda: auth_mod.verify_token("not-a-token"))
expired = auth_mod.issue_token(u, ttl=-10)
expect("expired token rejected", lambda: auth_mod.verify_token(expired))

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All auth checks passed.")
