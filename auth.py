"""Role-based authentication backed by the datastore (Firestore or local).

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib, no extra dependency) using
a per-user random salt. Roles: admin, engineer, user.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import os
import secrets as _secrets

import datastore

ROLES = ("admin", "engineer", "user")
_ITERATIONS = 200_000
_USERS = "users"


class AuthError(RuntimeError):
    """Raised for invalid credentials or user-management errors."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hash_password(password: str) -> str:
    if not password or len(password) < 6:
        raise AuthError("Password must be at least 6 characters.")
    salt = _secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, AttributeError):
        return False


def _normalize(email: str) -> str:
    return (email or "").strip().lower()


def create_user(email: str, password: str, role: str) -> dict:
    email = _normalize(email)
    if "@" not in email:
        raise AuthError("A valid email is required.")
    if role not in ROLES:
        raise AuthError(f"Role must be one of {ROLES}.")
    if datastore.get_doc(_USERS, email):
        raise AuthError("A user with that email already exists.")
    record = {"email": email, "password_hash": hash_password(password), "role": role, "created_at": _now()}
    datastore.set_doc(_USERS, email, record)
    return {"email": email, "role": role}


def authenticate(email: str, password: str) -> dict:
    email = _normalize(email)
    record = datastore.get_doc(_USERS, email)
    if not record or not verify_password(password, record.get("password_hash", "")):
        raise AuthError("Invalid email or password.")
    return {"email": email, "role": record["role"]}


def set_role(email: str, role: str) -> None:
    email = _normalize(email)
    if role not in ROLES:
        raise AuthError(f"Role must be one of {ROLES}.")
    if not datastore.get_doc(_USERS, email):
        raise AuthError("No such user.")
    datastore.update_doc(_USERS, email, {"role": role})


def set_password(email: str, password: str) -> None:
    email = _normalize(email)
    if not datastore.get_doc(_USERS, email):
        raise AuthError("No such user.")
    datastore.update_doc(_USERS, email, {"password_hash": hash_password(password)})


def delete_user(email: str) -> None:
    datastore.delete_doc(_USERS, _normalize(email))


def list_users() -> list[dict]:
    return [{"email": user["email"], "role": user["role"], "created_at": user.get("created_at")}
            for user in datastore.list_docs(_USERS)]


def ensure_seed_admin() -> dict | None:
    """Create the initial admin from env on first run so the app is usable.

    Uses AEGIS_ADMIN_EMAIL / AEGIS_ADMIN_PASSWORD, defaulting to a clearly-labeled
    demo admin. Returns the created record, or None if any user already exists.
    """
    if datastore.count_docs(_USERS) > 0:
        return None
    email = os.getenv("AEGIS_ADMIN_EMAIL", "admin@aegisops.demo")
    password = os.getenv("AEGIS_ADMIN_PASSWORD", "admin12345")
    return create_user(email, password, "admin")


# Role gating -------------------------------------------------------------- #
_RANK = {"user": 0, "engineer": 1, "admin": 2}


def at_least(role: str, minimum: str) -> bool:
    return _RANK.get(role, -1) >= _RANK.get(minimum, 99)


def can_configure(role: str) -> bool:
    return role == "admin"


def can_operate(role: str) -> bool:
    """Run analysis control, configure live monitoring, approve/escalate."""
    return at_least(role, "engineer")
