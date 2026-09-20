"""
Two-factor enforcement — the grace period is a clock, not a suggestion.

Before this existed, an organisation could switch on "MFA required for
approvers", the security page would say "Required for your role", and an
approver who never enrolled could go on releasing payments forever. The policy
and the grace period were stored; nothing read the clock.

These tests are HTTP-level, through the real middleware, because that is where
the control lives (api/security.py) — a rule enforced route by route protects
the routes somebody remembered.

Run: python test_mfa_enforcement.py
"""
from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-mfa-enf-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as auth_mod  # noqa: E402

auth_mod._SECRET_FILE = Path(_TMP) / ".auth_secret"
auth_mod._secret_cache = None

import mfa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402

client = TestClient(m.app, raise_server_exceptions=False)
PW = "correct-horse-battery"
ORG = auth_mod._org(None)
_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


# ─── helpers ────────────────────────────────────────────────────────────────

_admin_hdr: dict | None = None


def admin_headers() -> dict:
    global _admin_hdr
    if _admin_hdr is None:
        client.post("/auth/register", json={
            "email": "root@org", "name": "Root", "password": PW,
            "department": "finance", "role": "admin"})
        _admin_hdr = bearer(login("root@org"))
        # The bootstrap admin is subject to the policy too. Enrol it up front
        # so the rest of the suite is about the people it creates.
        enrol(_admin_hdr)
    return _admin_hdr


def register(email: str, role: str) -> dict:
    r = client.post("/auth/register", headers=admin_headers(), json={
        "email": email, "name": email.split("@")[0], "password": PW,
        "department": "finance", "role": role})
    assert r.status_code == 200, r.text
    return r.json()


def login(email: str, code: str | None = None):
    body = {"email": email, "password": PW}
    if code:
        body["mfa_code"] = code
    return client.post("/auth/login", json=body)


def bearer(res) -> dict:
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def enrol(headers: dict) -> None:
    """Complete enrolment the way a phone would."""
    begun = client.post("/auth/mfa/begin", headers=headers)
    assert begun.status_code == 200, begun.text
    code = mfa.current_code(begun.json()["secret"])
    done = client.post("/auth/mfa/confirm", headers=headers, json={"code": code})
    assert done.status_code == 200, done.text


def backdate_user(email: str, days: int) -> None:
    """Pretend the account was created `days` ago."""
    user = auth_mod.get_by_email(email, ORG)
    assert user is not None
    then = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    user.created_at = then.isoformat(timespec="seconds")
    auth_mod._save(user, ORG)


def backdate_policy(days: int) -> None:
    """Pretend the requirement was switched on `days` ago."""
    raw = store.get_store().get(ORG, "config", "mfa_policy") or {}
    then = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    raw["updated_at"] = then.isoformat(timespec="seconds")
    store.get_store().put(ORG, "config", "mfa_policy", raw)


def blocked_by_mfa(res) -> bool:
    return res.status_code == 403 and res.json().get("mfa_setup_required") is True


# ─── tests ──────────────────────────────────────────────────────────────────


def test_policy_off_means_nothing_is_enforced() -> None:
    print("\nWith the policy off, nobody is asked for anything")
    store.get_store().delete(ORG, "config", "mfa_policy")
    admin_headers()
    register("a1@org", "approver")
    res = login("a1@org")
    check("login succeeds", res.status_code == 200)
    check("not required", res.json()["mfa_setup_required"] is False)
    check("no deadline", res.json()["mfa_deadline"] is None)
    check("not overdue", res.json()["mfa_overdue"] is False)
    hdr = bearer(res)
    check("the dashboard opens", client.get("/dashboard", headers=hdr).status_code == 200)


def test_inside_the_grace_period_you_are_prompted_not_blocked() -> None:
    print("\nInside the grace period: prompted, still working")
    mfa.set_policy(ORG, enabled=True, grace_days=7)
    register("a2@org", "approver")
    res = login("a2@org")
    body = res.json()
    check("login succeeds", res.status_code == 200)
    check("setup is required", body["mfa_setup_required"] is True)
    check("a deadline is given", bool(body["mfa_deadline"]))
    check("but it is not overdue", body["mfa_overdue"] is False)
    deadline = dt.datetime.fromisoformat(body["mfa_deadline"])
    days_left = (deadline - dt.datetime.now(dt.timezone.utc)).days
    check("the deadline is about seven days out", 6 <= days_left <= 7, str(days_left))
    hdr = bearer(res)
    check("the dashboard still opens", client.get("/dashboard", headers=hdr).status_code == 200)
    st = client.get("/auth/mfa", headers=hdr).json()
    check("status reports the deadline for the security page",
          st["required_for_you"] and st["deadline"] == body["mfa_deadline"] and st["overdue"] is False)


def test_after_the_grace_period_the_session_is_locked_to_setup() -> None:
    print("\nAfter the grace period: locked to setup, and only setup")
    mfa.set_policy(ORG, enabled=True, grace_days=7)
    backdate_policy(30)
    register("a3@org", "approver")
    backdate_user("a3@org", 10)
    res = login("a3@org")
    check("login itself still works — they proved their password",
          res.status_code == 200)
    check("and says so", res.json()["mfa_overdue"] is True)
    hdr = bearer(res)
    check("the dashboard is refused", blocked_by_mfa(client.get("/dashboard", headers=hdr)))
    check("requisitions are refused", blocked_by_mfa(client.get("/requisitions", headers=hdr)))
    check("the refusal names the reason",
          "required" in client.get("/dashboard", headers=hdr).json()["detail"].lower())
    check("/auth/me still answers", client.get("/auth/me", headers=hdr).status_code == 200)
    check("/auth/mfa still answers", client.get("/auth/mfa", headers=hdr).status_code == 200)
    check("enrolment can begin", client.post("/auth/mfa/begin", headers=hdr).status_code == 200)


def test_enrolling_unlocks_it() -> None:
    print("\nEnrolling is the way out")
    hdr = bearer(login("a3@org"))
    # begin was already called above; begin again is refused only once
    # confirmed, so re-begin to get a fresh secret we hold.
    begun = client.post("/auth/mfa/begin", headers=hdr)
    check("a fresh secret can be issued while unconfirmed", begun.status_code == 200)
    code = mfa.current_code(begun.json()["secret"])
    done = client.post("/auth/mfa/confirm", headers=hdr, json={"code": code})
    check("confirmation succeeds", done.status_code == 200, done.text)
    check("the same session now reaches the dashboard",
          client.get("/dashboard", headers=hdr).status_code == 200)
    # And a fresh login now needs the code, and reports nothing outstanding.
    res = login("a3@org")
    check("next login asks for the code", res.status_code == 401
          and res.headers.get("X-DOCex-MFA") == "required")
    res = login("a3@org", mfa.current_code(begun.json()["secret"]))
    check("with the code it succeeds", res.status_code == 200)
    check("nothing outstanding", res.json()["mfa_setup_required"] is False
          and res.json()["mfa_overdue"] is False)


def test_roles_the_policy_does_not_name_are_never_locked() -> None:
    print("\nA viewer is never locked out over a rule for approvers")
    mfa.set_policy(ORG, enabled=True, grace_days=0)
    backdate_policy(30)
    register("v1@org", "viewer")
    backdate_user("v1@org", 30)
    res = login("v1@org")
    check("not required", res.json()["mfa_setup_required"] is False)
    check("not overdue", res.json()["mfa_overdue"] is False)
    hdr = bearer(res)
    check("dashboard opens", client.get("/dashboard", headers=hdr).status_code == 200)


def test_the_clock_starts_when_the_rule_lands_not_retroactively() -> None:
    print("\nAn old account gets the full grace period from the day the rule changed")
    store.get_store().delete(ORG, "config", "mfa_policy")
    register("a4@org", "approver")
    backdate_user("a4@org", 400)          # had an account for over a year
    mfa.set_policy(ORG, enabled=True, grace_days=7)   # switched on today
    res = login("a4@org")
    check("required", res.json()["mfa_setup_required"] is True)
    check("but NOT overdue — the year before the rule does not count",
          res.json()["mfa_overdue"] is False)
    hdr = bearer(res)
    check("dashboard opens", client.get("/dashboard", headers=hdr).status_code == 200)


def test_someone_invited_after_the_rule_gets_their_own_grace() -> None:
    print("\nSomeone invited after the rule is on gets their own grace period")
    mfa.set_policy(ORG, enabled=True, grace_days=7)
    backdate_policy(60)                   # rule has been on for two months
    register("a5@org", "approver")        # created today
    res = login("a5@org")
    check("required", res.json()["mfa_setup_required"] is True)
    check("not overdue — their seven days start today",
          res.json()["mfa_overdue"] is False)


def test_an_admin_reset_puts_an_overdue_person_back_in_setup() -> None:
    print("\nAfter an administrator resets a second factor, the clock applies again")
    mfa.set_policy(ORG, enabled=True, grace_days=7)
    backdate_policy(30)
    reg = register("a6@org", "approver")
    backdate_user("a6@org", 30)
    hdr = bearer(login("a6@org"))
    check("overdue and locked", blocked_by_mfa(client.get("/dashboard", headers=hdr)))
    enrol(hdr)
    check("enrolled and working", client.get("/dashboard", headers=hdr).status_code == 200)
    reset = client.post(f"/auth/users/{reg['id']}/mfa/reset", headers=admin_headers())
    check("administrator can reset it", reset.status_code == 200, reset.text)
    # Stronger than sending them back to setup: the reset ends their sessions
    # outright, so the held token is dead rather than merely restricted. That
    # matters — an admin resets a second factor precisely when they suspect
    # the account, and a still-working session would defeat the point.
    after = client.get("/dashboard", headers=hdr)
    check("the held session is dead, not merely restricted", after.status_code == 401,
          str(after.status_code))
    fresh = login("a6@org")
    check("signing in again works — no code to give", fresh.status_code == 200)
    check("and reports them overdue", fresh.json()["mfa_overdue"] is True)
    check("and that fresh session is locked to setup",
          blocked_by_mfa(client.get("/dashboard", headers=bearer(fresh))))


def test_grace_zero_is_immediate_for_old_accounts() -> None:
    print("\ngrace_days=0 means today, not never")
    mfa.set_policy(ORG, enabled=True, grace_days=0)
    backdate_policy(1)
    register("a7@org", "approver")
    backdate_user("a7@org", 1)
    hdr = bearer(login("a7@org"))
    check("locked", blocked_by_mfa(client.get("/dashboard", headers=hdr)))


def test_a_broken_policy_record_does_not_lock_the_organisation_out() -> None:
    print("\nA corrupt policy record fails open, not closed — the password check already ran")
    store.get_store().put(ORG, "config", "mfa_policy", {
        "enabled": True, "required_roles": ["approver"], "grace_days": "seven",
        "updated_at": "not a date"})
    register("a8@org", "approver")
    res = login("a8@org")
    check("login does not 500", res.status_code == 200, str(res.status_code))
    check("the unreadable grace value falls back to the default, not to zero",
          mfa.get_policy(ORG)["grace_days"] == 7)
    check("the unparseable timestamp does not make them overdue",
          res.json()["mfa_overdue"] is False)
    hdr = bearer(res)
    check("the dashboard opens", client.get("/dashboard", headers=hdr).status_code == 200)
    store.get_store().delete(ORG, "config", "mfa_policy")


if __name__ == "__main__":
    print("Two-factor enforcement — the grace period is a clock")
    test_policy_off_means_nothing_is_enforced()
    test_inside_the_grace_period_you_are_prompted_not_blocked()
    test_after_the_grace_period_the_session_is_locked_to_setup()
    test_enrolling_unlocks_it()
    test_roles_the_policy_does_not_name_are_never_locked()
    test_the_clock_starts_when_the_rule_lands_not_retroactively()
    test_someone_invited_after_the_rule_gets_their_own_grace()
    test_an_admin_reset_puts_an_overdue_person_back_in_setup()
    test_grace_zero_is_immediate_for_old_accounts()
    test_a_broken_policy_record_does_not_lock_the_organisation_out()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
