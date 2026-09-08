"""
Two-factor authentication — the six digits from an authenticator app.

WHY THIS EXISTS
Every other control in DOCex assumes the person signing in is who they claim.
Until now, a stolen or guessed password was enough to become an approver, and
an approver can release money. Long passwords, lockout and constant-time
comparison all raise the cost of guessing; none of them help once a password
has actually leaked — reused from another site, typed into a phishing page,
read off a sticky note.

A second factor is the only control that survives a password being known.

WHY IT IS BUILT HERE RATHER THAN INSTALLED
TOTP (RFC 6238) is about forty lines: an HMAC over a time counter, truncated to
six digits. The whole of it is hashlib, hmac, struct and base64 — all standard
library. Adding a dependency to a money path means trusting an extra supply
chain forever, in exchange for saving an afternoon. Not worth it.

The one genuinely fiddly part is that clocks drift, so verification accepts the
neighbouring windows too. Get that wrong and users are locked out by their own
phone being thirty seconds fast.

WHO IS REQUIRED TO USE IT
Configurable, defaulting to anyone who can authorise payment — approvers and
administrators. A viewer who only reads dashboards is not worth locking out of
their own work over. That default is an organisation-level setting, not a rule
in code, because a client whose auditor demands it for everyone should get it
without a code change.

RECOVERY CODES
Phones get lost, wiped and stolen, and an approver who cannot sign in during a
payment run is an emergency. Ten single-use codes are issued at enrolment,
shown once, stored only as hashes. Using one consumes it. When they run low,
the honest answer is the same as for a forgotten password: an administrator
resets the second factor, and the reset is recorded.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
import secrets
import struct
import time
from typing import Optional

import store

_MFA = "mfa"                       # store collection
_DIGITS = 6
_PERIOD = 30                       # seconds per code, the universal default
_DRIFT_WINDOWS = 1                 # accept ±30s for clock skew
_RECOVERY_CODES = 10

# A used code is remembered for this long so it cannot be replayed. Slightly
# more than the acceptance window, which is all that is needed.
_REPLAY_MEMORY = _PERIOD * (2 * _DRIFT_WINDOWS + 2)


class MfaError(ValueError):
    """Bad code, not enrolled, already enrolled — callers map to HTTP 4xx."""


def _org(org_id: Optional[str] = None) -> str:
    explicit = (org_id or "").strip()
    if explicit:
        return store.require_org(explicit)
    return store.require_org((os.environ.get("DOCEX_ORG") or "default").strip()
                             or "default")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ─── the algorithm ──────────────────────────────────────────────────────────


def generate_secret() -> str:
    """A fresh shared secret, base32 as every authenticator app expects.

    160 bits, per RFC 4226's recommendation. Base32 without padding because
    some apps mishandle the '=' characters when a secret is typed by hand.
    """
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code_at(secret: str, counter: int) -> str:
    """One TOTP code. RFC 6238 over RFC 4226's dynamic truncation."""
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret.upper() + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** _DIGITS)).zfill(_DIGITS)


def current_code(secret: str, at: Optional[float] = None) -> str:
    """What the user's phone is showing right now. For tests and support."""
    return _code_at(secret, int((at if at is not None else time.time()) // _PERIOD))


def _codes_in_window(secret: str, at: float) -> list[tuple[int, str]]:
    counter = int(at // _PERIOD)
    return [(counter + d, _code_at(secret, counter + d))
            for d in range(-_DRIFT_WINDOWS, _DRIFT_WINDOWS + 1)]


def provisioning_uri(secret: str, email: str, issuer: str = "DOCex") -> str:
    """The otpauth:// URI an authenticator app scans as a QR code."""
    from urllib.parse import quote
    label = quote(f"{issuer}:{email}", safe="")
    return (f"otpauth://totp/{label}?secret={secret}"
            f"&issuer={quote(issuer, safe='')}&algorithm=SHA1"
            f"&digits={_DIGITS}&period={_PERIOD}")


# ─── recovery codes ─────────────────────────────────────────────────────────


def _hash_recovery(code: str) -> str:
    """Recovery codes are credentials, so only their hashes are stored.

    A plain SHA-256 rather than PBKDF2, deliberately: these are 40 random bits
    that nobody chooses and nobody reuses, so there is no dictionary to attack
    and no other account to unlock. Iteration would buy nothing.
    """
    return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()


def _new_recovery_codes(n: int = _RECOVERY_CODES) -> list[str]:
    # Excludes characters that get misread when copied off a screen in a hurry.
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    out = []
    for _ in range(n):
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        out.append(f"{raw[:4]}-{raw[4:]}")
    return out


# ─── enrolment ──────────────────────────────────────────────────────────────


def status(user_id: str, org_id: Optional[str] = None) -> dict:
    rec = store.get_store().get(_org(org_id), _MFA, user_id) or {}
    return {
        "enrolled": bool(rec.get("confirmed")),
        "pending": bool(rec.get("secret") and not rec.get("confirmed")),
        "recovery_codes_left": len(rec.get("recovery_hashes") or []),
        "enrolled_at": rec.get("confirmed_at"),
    }


def is_enrolled(user_id: str, org_id: Optional[str] = None) -> bool:
    return status(user_id, org_id)["enrolled"]


def begin_enrolment(user_id: str, email: str,
                    org_id: Optional[str] = None,
                    issuer: str = "DOCex") -> dict:
    """Create a secret and return what the app needs to scan it.

    Deliberately NOT active yet. The secret is stored unconfirmed until the
    user proves their app is generating matching codes — otherwise a mistyped
    setup locks somebody out of a system they must use to get paid.
    """
    org = _org(org_id)
    existing = store.get_store().get(org, _MFA, user_id) or {}
    if existing.get("confirmed"):
        raise MfaError("Two-factor authentication is already set up for this "
                       "account. Reset it before enrolling again.")
    secret = generate_secret()
    store.get_store().put(org, _MFA, user_id, {
        "id": user_id,
        "secret": secret,
        "confirmed": False,
        "created_at": _now_iso(),
        "recovery_hashes": [],
        "used_counters": [],
    })
    return {
        "secret": secret,
        "uri": provisioning_uri(secret, email, issuer),
        "digits": _DIGITS,
        "period": _PERIOD,
    }


def confirm_enrolment(user_id: str, code: str,
                      org_id: Optional[str] = None) -> list[str]:
    """Prove the app works, switch it on, and return the recovery codes ONCE."""
    org = _org(org_id)
    rec = store.get_store().get(org, _MFA, user_id) or {}
    if not rec.get("secret"):
        raise MfaError("Start setting up two-factor authentication first.")
    if rec.get("confirmed"):
        raise MfaError("Two-factor authentication is already set up.")
    if not _matches(rec["secret"], code):
        raise MfaError("That code is not right. Check your authenticator app "
                       "is showing the current code, and that your phone's "
                       "clock is set automatically.")
    codes = _new_recovery_codes()
    rec.update({
        "confirmed": True,
        "confirmed_at": _now_iso(),
        "recovery_hashes": [_hash_recovery(c) for c in codes],
    })
    store.get_store().put(org, _MFA, user_id, rec)
    return codes


def disable(user_id: str, org_id: Optional[str] = None, *,
            actor: str = "") -> None:
    """Remove the second factor. Administrator action, or the user's own.

    Recorded rather than deleted quietly: turning off a control on an account
    that can release money is exactly the event an auditor looks for.
    """
    org = _org(org_id)
    rec = store.get_store().get(org, _MFA, user_id) or {}
    store.get_store().put(org, _MFA, user_id, {
        "id": user_id,
        "secret": "",
        "confirmed": False,
        "recovery_hashes": [],
        "used_counters": [],
        "disabled_at": _now_iso(),
        "disabled_by": (actor or "").strip().lower() or None,
        "previously_enrolled_at": rec.get("confirmed_at"),
    })


# ─── verification ───────────────────────────────────────────────────────────


def _matches(secret: str, code: str, at: Optional[float] = None) -> bool:
    supplied = (code or "").strip().replace(" ", "")
    if not supplied.isdigit() or len(supplied) != _DIGITS:
        return False
    now = at if at is not None else time.time()
    # compare_digest on every candidate, and no early return, so the time taken
    # does not reveal which window matched.
    matched = False
    for _, candidate in _codes_in_window(secret, now):
        if hmac.compare_digest(candidate, supplied):
            matched = True
    return matched


def verify(user_id: str, code: str, org_id: Optional[str] = None,
           at: Optional[float] = None) -> bool:
    """Check a six-digit code, or a recovery code. Consumes what it uses.

    A TOTP code stays valid for its whole window, so without this a code
    captured over someone's shoulder could be replayed seconds later. Used
    counters are remembered just long enough to close that gap.
    """
    org = _org(org_id)
    rec = store.get_store().get(org, _MFA, user_id) or {}
    if not rec.get("confirmed") or not rec.get("secret"):
        raise MfaError("Two-factor authentication is not set up for this account.")

    supplied = (code or "").strip().replace(" ", "")
    now = at if at is not None else time.time()

    # Recovery code? Longer and contains letters, so it cannot be confused
    # with a TOTP code.
    if not supplied.isdigit():
        wanted = _hash_recovery(supplied)
        hashes = list(rec.get("recovery_hashes") or [])
        for i, h in enumerate(hashes):
            if hmac.compare_digest(h, wanted):
                hashes.pop(i)                       # single use, always
                rec["recovery_hashes"] = hashes
                rec["last_recovery_used_at"] = _now_iso()
                store.get_store().put(org, _MFA, user_id, rec)
                return True
        return False

    counter_now = int(now // _PERIOD)
    used = [int(c) for c in (rec.get("used_counters") or [])
            if counter_now - int(c) <= (_REPLAY_MEMORY // _PERIOD)]

    for counter, candidate in _codes_in_window(rec["secret"], now):
        if hmac.compare_digest(candidate, supplied):
            if counter in used:
                return False                        # already used; no replay
            used.append(counter)
            rec["used_counters"] = used
            rec["last_used_at"] = _now_iso()
            store.get_store().put(org, _MFA, user_id, rec)
            return True

    rec["used_counters"] = used
    store.get_store().put(org, _MFA, user_id, rec)
    return False


def regenerate_recovery_codes(user_id: str,
                              org_id: Optional[str] = None) -> list[str]:
    """Fresh set, shown once. Invalidates every previous code."""
    org = _org(org_id)
    rec = store.get_store().get(org, _MFA, user_id) or {}
    if not rec.get("confirmed"):
        raise MfaError("Two-factor authentication is not set up for this account.")
    codes = _new_recovery_codes()
    rec["recovery_hashes"] = [_hash_recovery(c) for c in codes]
    rec["recovery_regenerated_at"] = _now_iso()
    store.get_store().put(org, _MFA, user_id, rec)
    return codes


# ─── who has to use it ──────────────────────────────────────────────────────


_CONFIG = "config"
_POLICY_ID = "mfa_policy"

# Default: anyone who can authorise a payment. A viewer reading a dashboard is
# not worth locking out of their own work over, and a rule that feels
# gratuitous is a rule people work around.
_DEFAULT_REQUIRED_ROLES = ("approver", "admin")


def get_policy(org_id: Optional[str] = None) -> dict:
    raw = store.get_store().get(_org(org_id), _CONFIG, _POLICY_ID) or {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "required_roles": list(raw.get("required_roles")
                               or _DEFAULT_REQUIRED_ROLES),
        "grace_days": int(raw.get("grace_days", 7)),
    }


def set_policy(org_id: Optional[str] = None, *, enabled: bool = True,
               required_roles: Optional[list[str]] = None,
               grace_days: int = 7) -> dict:
    """Turn it on for an organisation.

    `grace_days` exists because switching this on for twenty people at once,
    with no warning, is how a finance team misses a payment run. During the
    grace period they are prompted and can still work; afterwards it is
    required.
    """
    policy = {
        "enabled": bool(enabled),
        "required_roles": list(required_roles or _DEFAULT_REQUIRED_ROLES),
        "grace_days": max(0, int(grace_days)),
        "updated_at": _now_iso(),
    }
    store.get_store().put(_org(org_id), _CONFIG, _POLICY_ID, policy)
    return policy


def is_required_for(role: str, org_id: Optional[str] = None) -> bool:
    policy = get_policy(org_id)
    return policy["enabled"] and role in policy["required_roles"]
