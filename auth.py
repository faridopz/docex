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

Persistence: one JSON file per user under {root}/users/. This matches the rest
of DOCex's file-based storage. Email is unique (enforced on create).

NOTE: local-disk storage is ephemeral on the Render container (see CLAUDE.md).
For the demo that's acceptable; a durable user store is a Phase-2 item.
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

from models import Department, Role, User, UserPublic

_ROOT = Path(__file__).parent
_USER_DIR = _ROOT / "users"
_SECRET_FILE = _ROOT / ".auth_secret"

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


def _ensure_dir() -> None:
    _USER_DIR.mkdir(parents=True, exist_ok=True)


def _path(user_id: str) -> Path:
    if not user_id or "/" in user_id or "\\" in user_id or ".." in user_id:
        raise ValueError(f"Invalid user id: {user_id!r}")
    return _USER_DIR / f"{user_id}.json"


def _save(user: User) -> User:
    _ensure_dir()
    user.updated_at = _now_iso()
    if not user.created_at:
        user.created_at = user.updated_at
    _path(user.id).write_text(user.model_dump_json(indent=2))
    return user


def _iter_all() -> list[User]:
    _ensure_dir()
    out: list[User] = []
    for p in _USER_DIR.glob("*.json"):
        try:
            out.append(User.model_validate_json(p.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupt user {p.name}: {exc}")
    return out


def get_by_email(email: str) -> Optional[User]:
    want = (email or "").strip().lower()
    for u in _iter_all():
        if u.email.lower() == want:
            return u
    return None


def get_by_id(user_id: str) -> Optional[User]:
    path = _path(user_id)
    if not path.exists():
        return None
    try:
        return User.model_validate_json(path.read_text())
    except Exception:
        return None


def public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id, email=user.email, name=user.name, department=user.department,
        role=user.role, active=user.active, created_at=user.created_at,
    )


def list_public() -> list[UserPublic]:
    return [public(u) for u in sorted(_iter_all(), key=lambda u: u.created_at or "")]


# ─── user lifecycle ─────────────────────────────────────────────────────────


class AuthError(ValueError):
    """Bad credentials / duplicate email / invalid token — mapped to HTTP 4xx."""


def create_user(
    email: str,
    name: str,
    password: str,
    department: Department,
    role: Role = "reviewer",
) -> User:
    email = (email or "").strip().lower()
    if "@" not in email:
        raise AuthError("A valid email is required.")
    if get_by_email(email):
        raise AuthError("A user with that email already exists.")
    # Departments are org-defined data (departments.py) — reject a typo/unknown
    # key rather than creating a user nobody's queue will ever show.
    try:
        import departments as _departments
        _departments.require(department)
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
    return _save(user)


def authenticate(email: str, password: str) -> User:
    user = get_by_email(email)
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


def issue_token(user: User, ttl: int = _TOKEN_TTL) -> str:
    payload = {"uid": user.id, "exp": int(dt.datetime.now(dt.timezone.utc).timestamp()) + ttl}
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
    user = get_by_id(payload.get("uid", ""))
    if user is None or not user.active:
        raise AuthError("Account not found or disabled.")
    return user
