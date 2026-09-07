"""
DOCex auth — users, departments, roles, and safe sessions.

Security choices (deliberately boring and standard):
  - Passwords are hashed with PBKDF2-HMAC-SHA256, 200k iterations, a per-user
    16-byte random salt. Plaintext is never stored and never logged.
  - Verification uses hmac.compare_digest (constant-time) to avoid timing leaks.
  - Sessions are HMAC-SHA256-signed tokens carrying (user_id, expiry). No
    server-side session store needed; tampering invalidates the signature.
  - The signing secret comes from AUTH_SECRET, else a persisted random secret
    in {root}/.auth_secret so sessions survive restarts (mirrors approval_tokens).

Persistence: users are records in the org-scoped store (store.py) under the
"users" collection. That gives two things the old {root}/users/ directory
never had:

  * DURABILITY — with DOCEX_DB set, users live in SQLite/Postgres and survive
    a redeploy. Before this change every client's logins were wiped on each
    Render deploy, which is not something a paying customer can be asked to
    tolerate.
  * TENANCY — users belong to an organisation. The org comes from DOCEX_ORG
    (one org per instance today) and is also stamped into the session token,
    so when multi-org lands the token already carries what it needs.

Tests redirect storage with store.set_store(JsonFileStore(tmpdir)) rather than
poking at a module-level directory.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import uuid
from pathlib import Path
from typing import Optional

import store
from models import Department, Role, User, UserPublic

_ROOT = Path(__file__).parent
_SECRET_FILE = _ROOT / ".auth_secret"
_USERS = "users"                       # store collection name


def _org(org_id: Optional[str] = None) -> str:
    """Resolve the organisation a call applies to.

    Explicit argument wins; otherwise DOCEX_ORG; otherwise "default". Mirrors
    api/context.default_org() so engine and route agree on the same tenant.
    """
    explicit = (org_id or "").strip()
    if explicit:
        return store.require_org(explicit)
    return store.require_org((os.environ.get("DOCEX_ORG") or "default").strip() or "default")


_PBKDF2_ITERS = 200_000
_TOKEN_TTL = 12 * 3600  # 12 hours
_secret_cache: Optional[bytes] = None


# ─── secret + token plumbing ────────────────────────────────────────────────


def _secret() -> bytes:
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    env = os.environ.get("AUTH_SECRET", "").strip()
    if env:
        _secret_cache = env.encode()
        return _secret_cache
    try:
        if _SECRET_FILE.exists():
            _secret_cache = _SECRET_FILE.read_bytes()
        else:
            _secret_cache = os.urandom(32)
            _SECRET_FILE.write_bytes(_secret_cache)
    except Exception:
        _secret_cache = _secret_cache or os.urandom(32)
    return _secret_cache


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


# ─── password hashing ───────────────────────────────────────────────────────


_PASSWORD_MIN = 10

# Passwords that a six-character minimum happily accepts and an attacker tries
# in the first second. Not a substitute for a breach corpus — it is the short
# list of what people actually type when a form says "at least 6 characters".
_WEAK_PASSWORDS = frozenset({
    "password", "password1", "password123", "passw0rd", "letmein", "welcome",
    "welcome1", "qwerty", "qwerty123", "123456", "1234567", "12345678",
    "123456789", "1234567890", "abc123", "admin", "admin123", "changeme",
    "iloveyou", "monkey", "dragon", "football", "sunshine", "princess",
    "docex", "docex123", "finance", "finance123", "nigeria", "nigeria123",
})


def check_password_strength(password: str) -> None:
    """Raise ValueError with a fixable message, or return silently.

    A finance system holding payment authority is the wrong place for a
    six-character minimum: an attacker who guesses one approver's password can
    release money. Ten characters with some variety, and a refusal of the
    handful of passwords everyone actually picks, costs a user nothing and
    removes the cheapest attack.

    Deliberately NOT a complexity maze (one upper, one symbol, one digit,
    no repeats) — those push people towards Password1! and a sticky note. Length
    plus a blocklist is the better trade.
    """
    if not password or len(password) < _PASSWORD_MIN:
        raise ValueError(
            f"Password must be at least {_PASSWORD_MIN} characters. A short "
            "phrase you can remember is stronger than a short jumble.")
    lowered = password.strip().lower()
    if lowered in _WEAK_PASSWORDS:
        raise ValueError(
            "That password is one of the first an attacker tries. Choose "
            "something else.")
    if len(set(lowered)) < 5:
        raise ValueError(
            "That password repeats too few different characters to be safe.")


def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    check_password_strength(password)
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    try:
        salt = bytes.fromhex(password_salt)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return hmac.compare_digest(candidate.hex(), password_hash)


# ─── persistence ────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _save(user: User, org_id: Optional[str] = None) -> User:
    user.updated_at = _now_iso()
    if not user.created_at:
        user.created_at = user.updated_at
    store.get_store().put(_org(org_id), _USERS, user.id, user.model_dump())
    return user


def _iter_all(org_id: Optional[str] = None) -> list[User]:
    out: list[User] = []
    for raw in store.get_store().list(_org(org_id), _USERS):
        try:
            out.append(User.model_validate(raw))
        except Exception as exc:
            print(f"Warning: skipping corrupt user {raw.get('id')}: {exc}")
    return out


def get_by_email(email: str, org_id: Optional[str] = None) -> Optional[User]:
    want = (email or "").strip().lower()
    for u in _iter_all(org_id):
        if u.email.lower() == want:
            return u
    return None


def get_by_id(user_id: str, org_id: Optional[str] = None) -> Optional[User]:
    if not user_id:
        return None
    try:
        raw = store.get_store().get(_org(org_id), _USERS, user_id)
    except store.StoreError:
        return None
    if raw is None:
        return None
    try:
        return User.model_validate(raw)
    except Exception:
        return None


def public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id, email=user.email, name=user.name, department=user.department,
        role=user.role, active=user.active, created_at=user.created_at,
    )


def list_public(org_id: Optional[str] = None) -> list[UserPublic]:
    return [public(u) for u in sorted(_iter_all(org_id), key=lambda u: u.created_at or "")]


def migrate_legacy_users(org_id: Optional[str] = None) -> int:
    """One-time import of accounts from the pre-store {root}/users/*.json layout.

    Only runs when the store has NO users for the org, so it can be called on
    every boot without ever overwriting a newer record. Legacy files are left
    in place (they're a free backup); delete the directory once you've signed
    in successfully. Returns the number of accounts imported.
    """
    legacy = _ROOT / "users"
    if not legacy.is_dir():
        return 0
    org = _org(org_id)
    if _iter_all(org):
        return 0
    imported = 0
    for path in sorted(legacy.glob("*.json")):
        try:
            user = User.model_validate_json(path.read_text())
        except Exception as exc:
            print(f"Warning: skipping legacy user {path.name}: {exc}")
            continue
        store.get_store().put(org, _USERS, user.id, user.model_dump())
        imported += 1
    if imported:
        print(f"[auth] Imported {imported} account(s) from legacy users/ into org '{org}'.")
    return imported


# ─── user lifecycle ─────────────────────────────────────────────────────────


class AuthError(ValueError):
    """Bad credentials / duplicate email / invalid token — mapped to HTTP 4xx."""


class RateLimited(AuthError):
    """Too many failed attempts. Routes map this to HTTP 429, not 401 — the
    caller needs to know that waiting will help and more guessing will not."""


def create_user(
    email: str,
    name: str,
    password: str,
    department: Department,
    role: Role = "reviewer",
    org_id: Optional[str] = None,
) -> User:
    org = _org(org_id)
    email = (email or "").strip().lower()
    if "@" not in email:
        raise AuthError("A valid email is required.")
    if get_by_email(email, org):
        raise AuthError("A user with that email already exists.")
    # Departments are org-defined data (departments.py) — reject a typo/unknown
    # key rather than creating a user nobody's queue will ever show.
    try:
        import departments as _departments
        _departments.require(department, org_id=org)
    except ImportError:  # pragma: no cover - registry optional
        pass
    except Exception as exc:
        raise AuthError(str(exc)) from exc
    pw_hash, pw_salt = hash_password(password)
    user = User(
        id=uuid.uuid4().hex,
        email=email,
        name=name.strip() or email.split("@")[0],
        department=department,
        role=role,
        password_hash=pw_hash,
        password_salt=pw_salt,
    )
    return _save(user, org)


def authenticate(email: str, password: str, org_id: Optional[str] = None) -> User:
    """Verify credentials, with brute-force protection.

    Without the throttle below, an attacker could try passwords as fast as the
    server answers — and PBKDF2 at 200k iterations only slows that to a few
    guesses a second, which is thousands an hour against an approver who can
    release payments.
    """
    org = _org(org_id)
    _guard_login_rate(email, org)

    user = get_by_email(email, org)
    # Run a dummy verify even when the user is missing, to keep timing uniform —
    # otherwise response time reveals which email addresses exist.
    if user is None:
        hashlib.pbkdf2_hmac("sha256", b"timing-equalizer", os.urandom(16),
                            _PBKDF2_ITERS)
        _record_failed_login(email, org)
        raise AuthError("Invalid email or password.")
    if not user.active:
        raise AuthError("This account is disabled.")
    if not verify_password(password, user.password_hash, user.password_salt):
        _record_failed_login(email, org)
        raise AuthError("Invalid email or password.")

    _clear_failed_logins(email, org)
    return user


# ─── brute-force protection ─────────────────────────────────────────────────
#
# Counted per (email, org) rather than per IP: an NGO office sits behind one
# NAT address, so per-IP limiting would lock out the whole finance team the
# moment one person fat-fingers their password. Attempts are stored, not held
# in memory, so a restart cannot be used to reset the counter.

_MAX_FAILED_LOGINS = 8
_LOCKOUT_SECONDS = 15 * 60
_ATTEMPTS = "login_attempts"


def _attempt_key(email: str) -> str:
    """A storage-safe key. The address itself is not stored as the id — an
    email is personal data and a record id ends up in file names and logs."""
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:32]


def _guard_login_rate(email: str, org_id: str) -> None:
    raw = store.get_store().get(org_id, _ATTEMPTS, _attempt_key(email)) or {}
    count = int(raw.get("count", 0))
    if count < _MAX_FAILED_LOGINS:
        return
    last = float(raw.get("last", 0))
    elapsed = dt.datetime.now(dt.timezone.utc).timestamp() - last
    if elapsed < _LOCKOUT_SECONDS:
        wait = int((_LOCKOUT_SECONDS - elapsed) / 60) + 1
        raise RateLimited(
            f"Too many failed sign-in attempts. Try again in {wait} minute"
            f"{'s' if wait != 1 else ''}, or ask an administrator to reset "
            "your password.")
    # Window elapsed — start the count again rather than leaving it locked.
    _clear_failed_logins(email, org_id)


def _record_failed_login(email: str, org_id: str) -> None:
    key = _attempt_key(email)
    raw = store.get_store().get(org_id, _ATTEMPTS, key) or {}
    store.get_store().put(org_id, _ATTEMPTS, key, {
        "count": int(raw.get("count", 0)) + 1,
        "last": dt.datetime.now(dt.timezone.utc).timestamp(),
    })


def _clear_failed_logins(email: str, org_id: str) -> None:
    try:
        store.get_store().delete(org_id, _ATTEMPTS, _attempt_key(email))
    except Exception:
        pass


# ─── session tokens ─────────────────────────────────────────────────────────


def issue_token(user: User, ttl: int = _TOKEN_TTL, org_id: Optional[str] = None) -> str:
    # "org" rides in the token so a future multi-org deployment can resolve
    # the tenant from the session alone, without changing the token format.
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    payload = {
        "uid": user.id,
        "org": _org(org_id),
        # Issued-at is what makes logout real. Tokens are stateless HMAC, so
        # nothing can "delete" one — but a token minted BEFORE the user's
        # sessions_valid_from can be refused, which revokes every session at
        # once. See logout().
        #
        # Sub-second precision, deliberately. With whole seconds, a token
        # issued in the SAME second as a logout compared equal and survived —
        # so signing out and being handed back a still-valid token was a real
        # possibility, and the window was a whole second wide.
        "iat": round(now, 6),
        "exp": int(now) + ttl,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> User:
    """Validate a session token and return the user, or raise AuthError."""
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise AuthError("Malformed token.") from exc
    expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise AuthError("Invalid token signature.")
    try:
        payload = json.loads(_unb64(body))
    except Exception as exc:
        raise AuthError("Corrupt token payload.") from exc
    if int(payload.get("exp", 0)) < int(dt.datetime.now(dt.timezone.utc).timestamp()):
        raise AuthError("Session expired — please sign in again.")
    # Tokens minted before the org claim existed have no "org"; fall back to
    # the instance default so nobody is logged out by the upgrade.
    user = get_by_id(payload.get("uid", ""), payload.get("org") or None)
    if user is None or not user.active:
        raise AuthError("Account not found or disabled.")

    # Was this token minted before the user last logged out (or changed their
    # password)? Tokens issued before that moment are dead, which is what makes
    # "sign out" mean something on a stateless token.
    cutoff = _sessions_valid_from(user, payload.get("org") or None)
    if cutoff and float(payload.get("iat", 0)) < cutoff:
        raise AuthError("Session ended — please sign in again.")
    return user


# ─── logout / session revocation ────────────────────────────────────────────
#
# A stateless signed token cannot be deleted, so clearing it in the browser is
# not a logout — anyone who captured it still holds a working credential until
# it expires. Recording a per-user cutoff turns "sign out" into a real
# revocation, and does the same job when a password is changed or an account is
# suspected compromised.

_SESSION_CUTOFF = "session_cutoffs"


def _sessions_valid_from(user: User, org_id: Optional[str] = None) -> float:
    raw = store.get_store().get(_org(org_id), _SESSION_CUTOFF, user.id) or {}
    return float(raw.get("valid_from", 0))


def logout(user: User, org_id: Optional[str] = None) -> None:
    """End every session this user currently holds.

    Not just the token in front of us: if a session was captured, the person
    logging out cannot know which token to kill, so we kill them all. The cost
    is being signed out on your other device, which is the right trade.
    """
    store.get_store().put(_org(org_id), _SESSION_CUTOFF, user.id, {
        "valid_from": round(dt.datetime.now(dt.timezone.utc).timestamp(), 6),
        "at": _now_iso(),
    })


def token_org(token: str) -> Optional[str]:
    """The org claim carried by a token, without verifying it. For routing only —
    never trust this for authorisation; verify_token() does that."""
    try:
        body = token.split(".", 1)[0]
        return json.loads(_unb64(body)).get("org") or None
    except Exception:
        return None
