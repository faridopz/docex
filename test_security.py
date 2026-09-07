"""
Security controls — the ones an attacker actually uses.

Not a checklist rehearsal. Each test here corresponds to something that was
genuinely open before real client money went into this system:

  * unlimited password guesses against an approver who can release payments
  * a six-character minimum, so "123456" was a valid password
  * "sign out" that only cleared the browser, leaving a captured token working

Run: python test_security.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-sec-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as auth_mod  # noqa: E402

auth_mod._SECRET_FILE = Path(_TMP) / ".auth_secret"
auth_mod._secret_cache = None

from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402

client = TestClient(m.app, raise_server_exceptions=False)
GOOD_PASSWORD = "correct-horse-battery"
_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


# The first account bootstraps the instance; every later one needs an admin
# caller. Tests that forget this get a 401 and misread it as a policy failure —
# so the helper defaults to signing in as the bootstrap admin.
BOOTSTRAP = "root@org"
_admin_header: dict | None = None


def register(email: str, password: str = GOOD_PASSWORD, role: str = "admin",
             headers: dict | None = None, as_admin: bool = True):
    if headers is None and as_admin:
        headers = admin_headers()
    return client.post("/auth/register", headers=headers or {}, json={
        "email": email, "name": email.split("@")[0], "password": password,
        "department": "finance", "role": role})


def admin_headers() -> dict:
    """Sign in as the bootstrap admin, creating it on first use."""
    global _admin_header
    if _admin_header is None:
        client.post("/auth/register", json={
            "email": BOOTSTRAP, "name": "Root", "password": GOOD_PASSWORD,
            "department": "finance", "role": "admin"})
        _admin_header = {
            "Authorization": f"Bearer {login(BOOTSTRAP).json()['token']}"}
    return _admin_header


def login(email: str, password: str = GOOD_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def bearer(email: str, password: str = GOOD_PASSWORD) -> dict:
    return {"Authorization": f"Bearer {login(email, password).json()['token']}"}


def clear_lockout(email: str) -> None:
    auth_mod._clear_failed_logins(email, auth_mod._org())


# ─── passwords ──────────────────────────────────────────────────────────────


def test_password_policy() -> None:
    print("\nA password that guards payment authority is not 6 characters")
    admin_headers()   # bootstrap first, so later calls are authorised
    for weak, why in [
        ("123456", "the most common password there is"),
        ("short", "too short"),
        ("password123", "on every attacker's first list"),
        ("aaaaaaaaaaaa", "long but almost no variety"),
    ]:
        r = register(f"weak-{abs(hash(weak))}@org", weak)
        check(f"refused {weak!r} — {why}", r.status_code == 422,
              f"got {r.status_code}")

    r = register("good@org", GOOD_PASSWORD)
    check("a memorable passphrase is accepted", r.status_code == 200,
          r.text[:120])
    check("the refusal explains how to fix it",
          "at least 10 characters" in register("x@org", "abc").json()["detail"])
    # Long enough to clear the length rule, so the BLOCKLIST is what refuses it.
    check("and names the blocklist reason when that is why",
          "attacker tries" in register("y@org", "1234567890").json()["detail"])


def test_password_is_never_stored_or_returned() -> None:
    print("\nThe password itself never survives the request")
    body = register("hash@org").json()
    check("the hash is not in the response", "password_hash" not in body)
    check("nor the salt", "password_salt" not in body)
    check("nor the password", "password" not in body)

    user = auth_mod.get_by_email("hash@org")
    check("stored as a hash, not plaintext",
          GOOD_PASSWORD not in (user.password_hash or ""))
    check("with a per-user salt", len(user.password_salt) == 32)
    check("and it verifies", auth_mod.verify_password(
        GOOD_PASSWORD, user.password_hash, user.password_salt))
    check("a wrong password does not", not auth_mod.verify_password(
        "wrong-horse-battery", user.password_hash, user.password_salt))


# ─── brute force ────────────────────────────────────────────────────────────


def test_repeated_wrong_passwords_lock_the_account() -> None:
    print("\nGuessing is stopped, not merely slowed")
    register("brute@org")
    clear_lockout("brute@org")

    codes = [login("brute@org", f"wrong-guess-{i}").status_code for i in range(12)]
    check("the attempts stop being answered", 429 in codes, str(codes))
    check("and it takes fewer than ten tries",
          codes.index(429) < 10 if 429 in codes else False)

    # The important half: locked means locked, even for the real password.
    # Otherwise an attacker just interleaves guesses and nothing is protected.
    r = login("brute@org")
    check("the correct password is ALSO refused while locked",
          r.status_code == 429, f"got {r.status_code}")
    check("and the message says waiting helps",
          "Try again in" in r.json()["detail"])

    clear_lockout("brute@org")
    check("once the window clears, the real password works",
          login("brute@org").status_code == 200)


def test_lockout_is_per_account_not_per_office() -> None:
    print("\nOne person's typo does not lock out the whole office")
    register("alice@org")
    register("bob@org")
    clear_lockout("alice@org")
    clear_lockout("bob@org")

    for i in range(10):
        login("alice@org", f"nope-{i}")
    check("alice is locked", login("alice@org").status_code == 429)
    check("bob is unaffected", login("bob@org").status_code == 200)
    clear_lockout("alice@org")


def test_failed_attempts_survive_a_restart() -> None:
    print("\nA restart does not reset the counter")
    register("persist@org")
    clear_lockout("persist@org")
    for i in range(10):
        login("persist@org", f"bad-{i}")
    # Attempts live in the store, not in process memory, so a crash-loop
    # cannot be used to reset the count.
    key = auth_mod._attempt_key("persist@org")
    stored = store.get_store().get(auth_mod._org(), "login_attempts", key)
    check("the count is stored, not held in memory", bool(stored))
    check("and it counted the failures", int(stored["count"]) >= 8)
    check("the email is hashed, not used as the record id",
          "persist@org" not in key)
    clear_lockout("persist@org")


# ─── sessions ───────────────────────────────────────────────────────────────


def test_logout_actually_revokes() -> None:
    print("\nSigning out kills the token, not just the browser copy")
    register("out@org")
    h = bearer("out@org")
    check("the token works", client.get("/auth/me", headers=h).status_code == 200)
    check("logout succeeds", client.post("/auth/logout", headers=h).status_code == 200)
    # THE point. Clearing localStorage would leave this returning 200.
    check("the SAME token is now refused",
          client.get("/auth/me", headers=h).status_code == 401)
    check("a fresh sign-in still works",
          client.get("/auth/me", headers=bearer("out@org")).status_code == 200)


def test_logout_ends_every_session() -> None:
    print("\nSigning out covers the device you cannot reach")
    register("multi@org")
    phone = bearer("multi@org")
    laptop = bearer("multi@org")
    client.post("/auth/logout", headers=laptop)
    check("the other device is signed out too",
          client.get("/auth/me", headers=phone).status_code == 401)


def test_tokens_cannot_be_forged() -> None:
    print("\nA tampered token is refused")
    register("forge@org")
    token = login("forge@org").json()["token"]
    body, sig = token.split(".", 1)
    for label, bad in [
        ("altered signature", f"{body}.{'A' * len(sig)}"),
        ("altered payload", f"{'A' * len(body)}.{sig}"),
        ("no signature", body),
        ("empty", ""),
        ("random string", "not-a-token-at-all"),
    ]:
        code = client.get("/auth/me",
                          headers={"Authorization": f"Bearer {bad}"}).status_code
        check(f"{label} → 401", code == 401, f"got {code}")


def test_expired_tokens_are_refused() -> None:
    print("\nA session does not last for ever")
    register("expire@org")
    user = auth_mod.get_by_email("expire@org")
    stale = auth_mod.issue_token(user, ttl=-1)
    check("an expired token is refused",
          client.get("/auth/me",
                     headers={"Authorization": f"Bearer {stale}"}).status_code == 401)


# ─── access control ─────────────────────────────────────────────────────────


def test_roles_are_enforced_server_side() -> None:
    print("\nA viewer cannot do an admin's job by calling the API directly")
    admin = admin_headers()
    register("view@org", role="viewer", headers=admin)
    viewer = bearer("view@org")

    check("viewer cannot list users",
          client.get("/auth/users", headers=viewer).status_code == 403)
    check("viewer cannot create an account",
          register("sneak@org", role="admin", headers=viewer).status_code == 403)
    check("viewer cannot promote themselves",
          register("view@org", role="admin", headers=viewer).status_code == 403)
    check("admin can", client.get("/auth/users", headers=admin).status_code == 200)


def test_nothing_is_reachable_without_a_session() -> None:
    print("\nNo credentials, no data")
    for path in ("/requisitions", "/payments", "/audit/summary", "/auth/users",
                 "/timesheets", "/reconciliation", "/vendors", "/dashboard"):
        check(f"{path} → 401",
              client.get(path).status_code == 401)


# ─── information disclosure ─────────────────────────────────────────────────


def test_errors_do_not_leak_internals() -> None:
    print("\nAn error tells the user what to do, not how we are built")
    register("err@org")
    h = bearer("err@org")

    leaky = ("Traceback", "sqlite", "postgres", "/Users/", "/sessions/",
             "store.py", "psycopg", ".py\", line", "sk-ant", "SELECT ")
    for path in ("/timesheets/does-not-exist", "/requisitions/../../etc/passwd",
                 "/reconciliation/nope", "/payments/%2e%2e"):
        text = client.get(path, headers=h).text
        found = [t for t in leaky if t.lower() in text.lower()]
        check(f"{path} leaks nothing", not found, f"leaked {found}")


def test_login_does_not_reveal_which_emails_exist() -> None:
    print("\nA wrong password and an unknown account look the same")
    register("known@org")
    clear_lockout("known@org")
    a = login("known@org", "definitely-wrong-password")
    b = login("no-such-person@org", "definitely-wrong-password")
    check("same status", a.status_code == b.status_code == 401)
    check("same message", a.json()["detail"] == b.json()["detail"])
    clear_lockout("known@org")


def main() -> int:
    print("=" * 66)
    print("Security — the controls, exercised")
    print("=" * 66)
    for fn in (
        test_password_policy,
        test_password_is_never_stored_or_returned,
        test_repeated_wrong_passwords_lock_the_account,
        test_lockout_is_per_account_not_per_office,
        test_failed_attempts_survive_a_restart,
        test_logout_actually_revokes,
        test_logout_ends_every_session,
        test_tokens_cannot_be_forged,
        test_expired_tokens_are_refused,
        test_roles_are_enforced_server_side,
        test_nothing_is_reachable_without_a_session,
        test_errors_do_not_leak_internals,
        test_login_does_not_reveal_which_emails_exist,
    ):
        fn()
    print("\n" + "=" * 66)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 66)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
