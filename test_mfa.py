"""
Two-factor authentication.

The first test is the one that matters most and is easiest to skip: the codes
are checked against RFC 6238's own published vectors. A TOTP implementation
that is subtly wrong still looks perfect in isolation — it generates six digits
and verifies its own digits happily — and only fails when a real authenticator
app produces something different. By then twenty people cannot sign in.

After that: the failures that actually happen. Phones run fast or slow. Codes
get shoulder-surfed and replayed within the same thirty seconds. Phones get
lost. And somebody, eventually, is locked out during a payment run.

Run: python test_mfa.py
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="docex-mfa-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))
os.environ["DOCEX_ORG"] = "mfatest"
ORG = "mfatest"

import mfa  # noqa: E402

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
    except mfa.MfaError as exc:
        check(label, not contains or contains.lower() in str(exc).lower(), str(exc))
    except Exception as exc:                                     # noqa: BLE001
        check(f"{label} (wrong exception: {type(exc).__name__}: {exc})", False)
    else:
        check(f"{label} (nothing raised)", False)


# ─── is it really TOTP? ─────────────────────────────────────────────────────


def test_rfc_6238_vectors() -> None:
    print("\nRFC 6238's own published test vectors")
    # The RFC's SHA-1 seed is the ASCII "12345678901234567890".
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")

    # (unix time, expected code) — straight from RFC 6238 Appendix B, SHA-1.
    for ts, expected in [
        (59,          "287082"),
        (1111111109,  "081804"),
        (1111111111,  "050471"),
        (1234567890,  "005924"),
        (2000000000,  "279037"),
        (20000000000, "353130"),
    ]:
        got = mfa.current_code(secret, at=ts)
        check(f"t={ts} → {expected}", got == expected, f"got {got}")

    # If this block passes, Google Authenticator, Authy, 1Password and Microsoft
    # Authenticator will all agree with us — which is the actual requirement.


def test_the_uri_an_app_scans() -> None:
    print("\nThe QR code an authenticator app reads")
    uri = mfa.provisioning_uri("JBSWY3DPEHPK3PXP", "amina@neem.org")
    for part in ("otpauth://totp/", "secret=JBSWY3DPEHPK3PXP", "issuer=DOCex",
                 "digits=6", "period=30"):
        check(f"contains {part}", part in uri)
    check("the email is URL-escaped, not raw",
          "amina%40neem.org" in uri, uri)


# ─── enrolment ──────────────────────────────────────────────────────────────


def test_enrolment_is_not_live_until_proven() -> None:
    print("\nA half-finished setup must not lock anyone out")
    uid = "user-enrol"
    setup = mfa.begin_enrolment(uid, "amina@neem.org", ORG)
    check("a secret was issued", len(setup["secret"]) >= 16)
    check("with a scannable URI", setup["uri"].startswith("otpauth://"))

    st = mfa.status(uid, ORG)
    check("but it is NOT active yet", st["enrolled"] is False)
    check("it is marked pending", st["pending"] is True)
    raises("and verifying against it is refused",
           lambda: mfa.verify(uid, mfa.current_code(setup["secret"]), ORG),
           contains="not set up")
    # If a mistyped setup went live immediately, the user would be locked out
    # of the system they need in order to get paid.

    raises("a wrong confirmation code is rejected",
           lambda: mfa.confirm_enrolment(uid, "000000", ORG),
           contains="not right")

    codes = mfa.confirm_enrolment(uid, mfa.current_code(setup["secret"]), ORG)
    check("confirming with a real code switches it on",
          mfa.is_enrolled(uid, ORG))
    check("ten recovery codes were issued", len(codes) == 10)
    check("they are readable, not cryptic", all("-" in c for c in codes))
    check("and all different", len(set(codes)) == 10)

    raises("enrolling twice is refused",
           lambda: mfa.begin_enrolment(uid, "amina@neem.org", ORG),
           contains="already set up")


def test_the_secret_is_the_only_copy() -> None:
    print("\nRecovery codes are stored as hashes, never in readable form")
    uid = "user-hash"
    setup = mfa.begin_enrolment(uid, "hash@neem.org", ORG)
    codes = mfa.confirm_enrolment(uid, mfa.current_code(setup["secret"]), ORG)
    raw = str(store.get_store().get(ORG, "mfa", uid))
    for c in codes:
        if c in raw:
            check("no recovery code is stored readable", False, c)
            break
    else:
        check("no recovery code is stored readable", True)
    check("only hashes are kept",
          len(store.get_store().get(ORG, "mfa", uid)["recovery_hashes"]) == 10)


# ─── the failures that actually happen ──────────────────────────────────────


def test_a_phone_clock_that_drifts() -> None:
    print("\nSomebody's phone is 25 seconds fast — they must still get in")
    uid = "user-drift"
    setup = mfa.begin_enrolment(uid, "drift@neem.org", ORG)
    secret = setup["secret"]
    mfa.confirm_enrolment(uid, mfa.current_code(secret), ORG)

    now = time.time()
    check("a code from 30s ago is accepted",
          mfa.verify(uid, mfa.current_code(secret, at=now - 30), ORG, at=now))
    check("a code from 30s ahead is accepted",
          mfa.verify(uid, mfa.current_code(secret, at=now + 30), ORG, at=now))
    check("but ten minutes out is refused",
          not mfa.verify(uid, mfa.current_code(secret, at=now - 600), ORG, at=now))
    # Tight enough to be a real control, loose enough that nobody is locked out
    # by a phone whose clock is not set automatically.


def test_a_code_cannot_be_used_twice() -> None:
    print("\nA code read over someone's shoulder cannot be replayed")
    uid = "user-replay"
    setup = mfa.begin_enrolment(uid, "replay@neem.org", ORG)
    secret = setup["secret"]
    mfa.confirm_enrolment(uid, mfa.current_code(secret), ORG)

    now = time.time()
    code = mfa.current_code(secret, at=now)
    check("the code works once", mfa.verify(uid, code, ORG, at=now))
    check("and is dead the second time",
          not mfa.verify(uid, code, ORG, at=now + 5),
          "a TOTP code is valid for a whole window; without this, someone who "
          "glanced at the phone has 30 seconds to reuse it")


def test_nonsense_is_refused() -> None:
    print("\nGarbage in the code box")
    uid = "user-junk"
    setup = mfa.begin_enrolment(uid, "junk@neem.org", ORG)
    mfa.confirm_enrolment(uid, mfa.current_code(setup["secret"]), ORG)
    for bad, why in [("", "empty"), ("12345", "too short"),
                     ("1234567", "too long"), ("abcdef", "letters"),
                     ("000000", "a guess")]:
        check(f"{why} refused", not mfa.verify(uid, bad, ORG))


def test_a_lost_phone() -> None:
    print("\nThe phone is gone the morning of a payment run")
    uid = "user-lost"
    setup = mfa.begin_enrolment(uid, "lost@neem.org", ORG)
    codes = mfa.confirm_enrolment(uid, mfa.current_code(setup["secret"]), ORG)

    check("a recovery code gets them in", mfa.verify(uid, codes[0], ORG))
    check("the same one cannot be used again", not mfa.verify(uid, codes[0], ORG))
    check("nine remain", mfa.status(uid, ORG)["recovery_codes_left"] == 9)
    check("a different one still works", mfa.verify(uid, codes[1], ORG))
    check("case and dashes do not matter",
          mfa.verify(uid, codes[2].lower().replace("-", ""), ORG))
    check("an invented recovery code is refused",
          not mfa.verify(uid, "ZZZZ-ZZZZ", ORG))

    fresh = mfa.regenerate_recovery_codes(uid, ORG)
    check("regenerating issues ten new codes", len(fresh) == 10)
    check("and kills every old one", not mfa.verify(uid, codes[3], ORG))
    check("while the new ones work", mfa.verify(uid, fresh[0], ORG))


def test_an_administrator_can_reset_it() -> None:
    print("\nAdministrator resets a locked-out approver")
    uid = "user-reset"
    setup = mfa.begin_enrolment(uid, "reset@neem.org", ORG)
    mfa.confirm_enrolment(uid, mfa.current_code(setup["secret"]), ORG)
    check("enrolled", mfa.is_enrolled(uid, ORG))

    mfa.disable(uid, ORG, actor="admin@neem.org")
    check("no longer enrolled", not mfa.is_enrolled(uid, ORG))
    rec = store.get_store().get(ORG, "mfa", uid)
    check("who turned it off is recorded", rec["disabled_by"] == "admin@neem.org")
    check("and when", bool(rec["disabled_at"]))
    # Switching off a control on an account that can release money is exactly
    # the event an auditor looks for. It is recorded, not quietly deleted.

    again = mfa.begin_enrolment(uid, "reset@neem.org", ORG)
    mfa.confirm_enrolment(uid, mfa.current_code(again["secret"]), ORG)
    check("they can enrol a new phone", mfa.is_enrolled(uid, ORG))
    check("the old secret no longer works",
          not mfa.verify(uid, mfa.current_code(setup["secret"]), ORG))


# ─── who has to use it ──────────────────────────────────────────────────────


def test_the_policy() -> None:
    print("\nRequired for people who can release money, not for everyone")
    for coll, rid in (("config", "mfa_policy"),):
        try:
            store.get_store().delete(ORG, coll, rid)
        except Exception:
            pass

    check("off until an organisation turns it on",
          mfa.get_policy(ORG)["enabled"] is False)
    check("so nothing is required yet",
          not mfa.is_required_for("approver", ORG))

    mfa.set_policy(ORG, enabled=True)
    check("approvers are required", mfa.is_required_for("approver", ORG))
    check("administrators are required", mfa.is_required_for("admin", ORG))
    check("viewers are not", not mfa.is_required_for("viewer", ORG))
    check("reviewers are not — they cannot release payment",
          not mfa.is_required_for("reviewer", ORG))

    mfa.set_policy(ORG, enabled=True, required_roles=["viewer", "reviewer",
                                                      "approver", "admin"])
    check("an org whose auditor wants everyone can have that, by config",
          mfa.is_required_for("viewer", ORG))

    mfa.set_policy(ORG, enabled=True, grace_days=14)
    check("a grace period is configurable",
          mfa.get_policy(ORG)["grace_days"] == 14)
    # Switching this on for twenty people with no warning is how a finance team
    # misses a payment run.


def test_org_isolation() -> None:
    print("\nOne organisation's enrolment is not another's")
    uid = "shared-id"
    setup = mfa.begin_enrolment(uid, "a@neem.org", ORG)
    mfa.confirm_enrolment(uid, mfa.current_code(setup["secret"]), ORG)
    check("enrolled here", mfa.is_enrolled(uid, ORG))
    check("not enrolled in another org", not mfa.is_enrolled(uid, "otherorg"))
    check("and its policy is separate",
          mfa.get_policy("otherorg")["enabled"] is False)


if __name__ == "__main__":
    try:
        test_rfc_6238_vectors()
        test_the_uri_an_app_scans()
        test_enrolment_is_not_live_until_proven()
        test_the_secret_is_the_only_copy()
        test_a_phone_clock_that_drifts()
        test_a_code_cannot_be_used_twice()
        test_nonsense_is_refused()
        test_a_lost_phone()
        test_an_administrator_can_reset_it()
        test_the_policy()
        test_org_isolation()
        print(f"\n{_passed} passed, {_failed} failed")
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    raise SystemExit(1 if _failed else 0)
