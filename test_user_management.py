"""
Onboarding twenty people, and removing one.

DOCex was built for a single administrator who registered themselves. NEEM is
fifteen to twenty people across six departments, which changes what the account
system has to survive:

  - somebody other than the account holder creates the password
  - therefore that password must stop working the moment it is used once
  - people forget passwords, and there is no email-reset path
  - people leave, and their access must end the same day — not whenever their
    session happens to expire

Each of those is a test below. The most important one is
`test_a_temporary_password_opens_nothing_else`: a forced password change that
can be clicked past is not a security control, it is a suggestion.

Run: python test_user_management.py
"""
from __future__ import annotations

import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-users-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))
os.environ["DOCEX_ORG"] = "usertest"
os.environ.setdefault("AUTH_SECRET", "user-suite-secret-not-for-production")

import departments  # noqa: E402

ORG = "usertest"
departments.save(departments.default_registry(), ORG)

import auth  # noqa: E402
from api import security  # noqa: E402

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def raises(label: str, fn, *, contains: str = "") -> None:
    try:
        fn()
    except (auth.AuthError, ValueError) as exc:
        check(label, not contains or contains.lower() in str(exc).lower(), str(exc))
    except Exception as exc:                                     # noqa: BLE001
        check(f"{label} (wrong exception: {type(exc).__name__}: {exc})", False)
    else:
        check(f"{label} (nothing raised)", False)


def clear() -> None:
    for coll in ("users", "session_cutoffs", "login_attempts"):
        for rec in store.get_store().list(ORG, coll):
            rid = rec.get("id")
            if rid:
                store.get_store().delete(ORG, coll, rid)
    # login_attempts are keyed by a hash and carry no id field.
    st = store.get_store()
    for rec in st.list(ORG, "login_attempts"):
        pass


def an_admin() -> auth.User:
    return auth.create_user("admin@neem.org", "Admin", "AdminPass2026!x",
                            "finance", "admin", ORG)


# ─── the one-time password ──────────────────────────────────────────────────


def test_the_generated_password_is_usable_and_strong() -> None:
    print("\nA password that has to be read down a phone line")
    seen = set()
    for _ in range(200):
        p = auth.generate_temp_password()
        seen.add(p)
        auth.check_password_strength(p)          # raises if weak
    check("200 generated passwords, none repeated", len(seen) == 200)
    sample = auth.generate_temp_password()
    check("long enough to resist guessing", len(sample.replace("-", "")) >= 12)
    check("no characters that get misread (0 O 1 l I)",
          not (set("0O1lI") & set(sample)))
    check("grouped so it can be dictated", "-" in sample)


def test_invite_returns_the_password_once() -> None:
    print("\nThe administrator gets the password; the database never does")
    clear(); an_admin()
    user, temp = auth.invite_user("amina@neem.org", "Amina Bello", "program",
                                  "reviewer", ORG, invited_by="admin@neem.org")
    check("the account exists", auth.get_by_email("amina@neem.org", ORG) is not None)
    check("it is flagged for a password change", user.must_change_password is True)
    check("who invited them is recorded", user.invited_by == "admin@neem.org")
    check("the temporary password signs them in",
          auth.authenticate("amina@neem.org", temp, ORG).id == user.id)

    stored = store.get_store().get(ORG, "users", user.id)
    blob = str(stored)
    check("the password is nowhere in the stored record", temp not in blob)
    check("only a hash and a salt are kept",
          bool(stored.get("password_hash")) and bool(stored.get("password_salt")))


def test_a_temporary_password_opens_nothing_else() -> None:
    print("\nTHE POINT: a one-time password reaches the password screen, and stops")
    clear(); an_admin()
    user, _ = auth.invite_user("tunde@neem.org", "Tunde", "finance", "approver", ORG)

    allowed = security.PASSWORD_CHANGE_ALLOWED
    check("you can see who you are", "/auth/me" in allowed)
    check("you can set a password", "/auth/password" in allowed)
    check("you can sign out", "/auth/logout" in allowed)

    for blocked in ("/requisitions", "/requisitions/REQ-0001/approve", "/payments",
                    "/dashboard", "/auth/users", "/reconciliation/run"):
        check(f"but not {blocked}", blocked not in allowed)

    check("the flag the middleware reads is on the user record",
          auth.get_by_id(user.id, ORG).must_change_password is True)


def test_setting_a_password_clears_the_flag() -> None:
    print("\nSetting your own password lets you in — and only then")
    clear(); an_admin()
    user, temp = auth.invite_user("grace@neem.org", "Grace", "finance", "reviewer", ORG)

    raises("the old password is required",
           lambda: auth.change_own_password(user, "wrong-password", "BrandNewPass2026!", ORG),
           contains="incorrect")
    raises("the new password cannot equal the old one",
           lambda: auth.change_own_password(user, temp, temp, ORG),
           contains="different")
    raises("and it still has to be strong",
           lambda: auth.change_own_password(user, temp, "password123", ORG))

    auth.change_own_password(user, temp, "GraceOwnPass2026!", ORG)
    fresh = auth.get_by_id(user.id, ORG)
    check("the flag is cleared", fresh.must_change_password is False)
    check("the new password works",
          auth.authenticate("grace@neem.org", "GraceOwnPass2026!", ORG).id == user.id)
    raises("the temporary password no longer does",
           lambda: auth.authenticate("grace@neem.org", temp, ORG))


def test_changing_a_password_ends_other_sessions() -> None:
    print("\nYou change your password because you think someone has it")
    clear(); an_admin()
    user, temp = auth.invite_user("sade@neem.org", "Sade", "finance", "reviewer", ORG)
    stolen = auth.issue_token(user, org_id=ORG)
    check("the attacker's token works right now",
          auth.verify_token(stolen).id == user.id)

    auth.change_own_password(user, temp, "SadeOwnPass2026!", ORG)
    raises("and stops working the moment the password changes",
           lambda: auth.verify_token(stolen), contains="session")


# ─── forgetting, and being locked out ───────────────────────────────────────


def test_admin_reset_is_the_recovery_path() -> None:
    print("\nThere is no reset email, so the administrator is the recovery path")
    clear(); an_admin()
    user, _first = auth.invite_user("bola@neem.org", "Bola", "compliance", "reviewer", ORG)
    auth.change_own_password(user, _first, "BolaOwnPass2026!", ORG)

    old_token = auth.issue_token(user, org_id=ORG)
    reset_user, temp2 = auth.reset_password(user.id, ORG, reset_by="admin@neem.org")
    check("a new temporary password is issued",
          auth.authenticate("bola@neem.org", temp2, ORG).id == user.id)
    check("and it must be changed again", reset_user.must_change_password is True)
    raises("sessions held before the reset are dead",
           lambda: auth.verify_token(old_token))
    raises("resetting an unknown account fails clearly",
           lambda: auth.reset_password("no-such-id", ORG), contains="no such user")


def test_reset_clears_a_lockout() -> None:
    print("\nEight wrong guesses locks the account; a reset unlocks it")
    clear(); an_admin()
    user, _temp = auth.invite_user("kemi@neem.org", "Kemi", "finance", "reviewer", ORG)
    for _ in range(8):
        try:
            auth.authenticate("kemi@neem.org", "definitely-wrong", ORG)
        except auth.AuthError:
            pass
    raises("the account is locked out",
           lambda: auth.authenticate("kemi@neem.org", "definitely-wrong", ORG),
           contains="too many")

    _, temp3 = auth.reset_password(user.id, ORG, reset_by="admin@neem.org")
    check("the reset lets them straight back in — no fifteen-minute wait",
          auth.authenticate("kemi@neem.org", temp3, ORG).id == user.id)


# ─── leaving ────────────────────────────────────────────────────────────────


def test_deactivation_ends_access_immediately() -> None:
    print("\nSomeone leaves at 10am and cannot approve anything at 3pm")
    clear(); an_admin()
    user, temp = auth.invite_user("leaver@neem.org", "Leaver", "finance", "approver", ORG)
    token = auth.issue_token(user, org_id=ORG)
    check("their session works while employed", auth.verify_token(token).id == user.id)

    auth.set_active(user.id, False, ORG, actor="admin@neem.org")
    raises("the live session dies at once", lambda: auth.verify_token(token))
    raises("and they cannot sign back in",
           lambda: auth.authenticate("leaver@neem.org", temp, ORG),
           contains="disabled")

    gone = auth.get_by_id(user.id, ORG)
    check("but the record is kept, not deleted", gone is not None)
    check("with the date and who did it",
          bool(gone.deactivated_at) and gone.deactivated_by == "admin@neem.org")
    # The approval trail must still be able to name who authorised a payment in
    # March about someone who left in April. Deleting the user would break that.

    auth.set_active(user.id, True, ORG, actor="admin@neem.org")
    check("reactivation works if they come back",
          auth.authenticate("leaver@neem.org", temp, ORG).id == user.id)
    check("and the deactivation stamp is cleared",
          auth.get_by_id(user.id, ORG).deactivated_at is None)


def test_the_org_cannot_lock_itself_out() -> None:
    print("\nThe last administrator cannot be removed")
    clear()
    admin = an_admin()
    auth.invite_user("reviewer@neem.org", "Rev", "finance", "reviewer", ORG)
    raises("deactivating the only admin is refused",
           lambda: auth.set_active(admin.id, False, ORG, actor="admin@neem.org"),
           contains="only active administrator")
    raises("and so is demoting them",
           lambda: auth.update_user(admin.id, ORG, role="reviewer"),
           contains="only administrator")

    second, _ = auth.invite_user("admin2@neem.org", "Second Admin", "finance", "admin", ORG)
    auth.set_active(admin.id, False, ORG, actor="admin2@neem.org")
    check("once a second admin exists, the first can be removed",
          auth.get_by_id(admin.id, ORG).active is False)


# ─── moving between teams ───────────────────────────────────────────────────


def test_people_change_department_and_role() -> None:
    print("\nPromotion should not mean a second account")
    clear(); an_admin()
    user, _ = auth.invite_user("mover@neem.org", "Mover", "program", "reviewer", ORG)
    updated = auth.update_user(user.id, ORG, department="finance", role="approver",
                               name="Mover Adebayo")
    check("department changed", updated.department == "finance")
    check("role changed", updated.role == "approver")
    check("name changed", updated.name == "Mover Adebayo")
    check("still the same account, so the history holds", updated.id == user.id)

    raises("a department that does not exist is refused",
           lambda: auth.update_user(user.id, ORG, department="marketing"))


def test_last_login_shows_who_never_started() -> None:
    print("\nAfter inviting twenty people, which ones actually signed in?")
    clear(); an_admin()
    used, temp = auth.invite_user("active@neem.org", "Active", "finance", "reviewer", ORG)
    auth.invite_user("never@neem.org", "Never", "finance", "reviewer", ORG)

    check("nobody has signed in yet", auth.get_by_id(used.id, ORG).last_login_at is None)
    auth.record_login(auth.authenticate("active@neem.org", temp, ORG), ORG)
    check("the one who signed in is stamped",
          bool(auth.get_by_id(used.id, ORG).last_login_at))
    never = auth.get_by_email("never@neem.org", ORG)
    check("the one who never did is still blank", never.last_login_at is None)


def test_public_view_leaks_no_credentials() -> None:
    print("\nThe admin user list carries no credential material")
    clear(); an_admin()
    auth.invite_user("view@neem.org", "View", "finance", "reviewer", ORG)
    for u in auth.list_public(ORG):
        d = u.model_dump()
        check(f"{u.email}: no password hash", "password_hash" not in d)
        check(f"{u.email}: no salt", "password_salt" not in d)


if __name__ == "__main__":
    try:
        test_the_generated_password_is_usable_and_strong()
        test_invite_returns_the_password_once()
        test_a_temporary_password_opens_nothing_else()
        test_setting_a_password_clears_the_flag()
        test_changing_a_password_ends_other_sessions()
        test_admin_reset_is_the_recovery_path()
        test_reset_clears_a_lockout()
        test_deactivation_ends_access_immediately()
        test_the_org_cannot_lock_itself_out()
        test_people_change_department_and_role()
        test_last_login_shows_who_never_started()
        test_public_view_leaks_no_credentials()
        print(f"\n{_passed} passed, {_failed} failed")
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    raise SystemExit(1 if _failed else 0)
