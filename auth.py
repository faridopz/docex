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


def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
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
    user = get_by_email(email, org_id)
    # Run a dummy verify even when the user is missing, to keep timing uniform.
    if user is None:
        hash_password("timing-equalizer-000")
        raise AuthError("Invalid email or password.")
    if not user.active:
        raise AuthError("This account is disabled.")
    if not verify_password(password, user.password_hash, user.password_salt):
        raise AuthError("Invalid email or password.")
    return user


# ─── session tokens ─────────────────────────────────────────────────────────


def issue_token(user: User, ttl: int = _TOKEN_TTL, org_id: Optional[str] = None) -> str:
    # "org" rides in the token so a future multi-org deployment can resolve
    # the tenant from the session alone, without changing the token format.
    payload = {
        "uid": user.id,
        "org": _org(org_id),
        "exp": int(dt.datetime.now(dt.timezone.utc).timestamp()) + ttl,
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
    return user


def token_org(token: str) -> Optional[str]:
    """The org claim carried by a token, without verifying it. For routing only —
    never trust this for authorisation; verify_token() does that."""
    try:
        body = token.split(".", 1)[0]
        return json.loads(_unb64(body)).get("org") or None
    except Exception:
        return None
