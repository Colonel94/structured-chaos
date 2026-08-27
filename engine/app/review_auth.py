"""Password and session authentication for the reviewer workspace.

Session and CSRF tokens are random bearer values; only SHA-256 digests are stored. Passwords use
stdlib scrypt with a per-user random salt, keeping the authentication boundary dependency-light.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

# Linear-time (no catastrophic backtracking): dot-free labels separated by literal dots. The old
# r"[^\s@]+\.[^\s@]+" overlapped (`.` is also matched by [^\s@]) → polynomial ReDoS (CodeQL py/polynomial-redos).
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$")
SESSION_COOKIE = "adaptive_intake_session"
CSRF_COOKIE = "adaptive_intake_csrf"


@dataclass(frozen=True)
class Identity:
    user_id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    role: str
    workspace_name: str


def normalise_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


def validate_password(value: str) -> None:
    if len(value) < 10 or len(value) > 128:
        raise ValueError("Password must be between 10 and 128 characters.")


def _password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> tuple[bytes, bytes]:
    validate_password(password)
    salt = secrets.token_bytes(16)
    return salt, _password_digest(password, salt)


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    try:
        actual = _password_digest(password, salt)
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_account(
    factory: sessionmaker[Session], *, email: str, password: str, display_name: str, workspace: str
) -> tuple[Identity, str, str]:
    email = normalise_email(email)
    name = display_name.strip()
    workspace_name = workspace.strip()
    if not (2 <= len(name) <= 80):
        raise ValueError("Name must be between 2 and 80 characters.")
    if not (2 <= len(workspace_name) <= 120):
        raise ValueError("Workspace name must be between 2 and 120 characters.")
    salt, password_hash = hash_password(password)
    session = factory()
    try:
        row = session.execute(
            text("""
                SELECT user_id, tenant_id FROM create_review_identity(
                    :email, :name, :salt, :password_hash, :workspace_name)
            """),
            {
                "email": email,
                "name": name,
                "salt": salt,
                "password_hash": password_hash,
                "workspace_name": workspace_name,
            },
        ).one()
        user_id, tenant_id = row[0], row[1]
        identity = Identity(user_id, tenant_id, email, name, "admin", workspace_name)
        session_token, csrf_token = _insert_session(session, identity)
        session.commit()
        return identity, session_token, csrf_token
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def login(
    factory: sessionmaker[Session], *, email: str, password: str
) -> tuple[Identity, str, str] | None:
    email = normalise_email(email)
    session = factory()
    try:
        row = (
            session.execute(
                text("""
                SELECT user_id AS id, email, display_name, password_salt, password_hash,
                       tenant_id, role, workspace_name
                  FROM lookup_review_login(:email)
            """),
                {"email": email},
            )
            .mappings()
            .first()
        )
        if row is None:
            _password_digest(
                password, bytes(16)
            )  # keep unknown-email timing close to a failed password
            return None
        if not verify_password(password, bytes(row.password_salt), bytes(row.password_hash)):
            return None
        identity = Identity(
            row.id, row.tenant_id, row.email, row.display_name, row.role, row.workspace_name
        )
        session_token, csrf_token = _insert_session(session, identity)
        session.commit()
        return identity, session_token, csrf_token
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _insert_session(session: Session, identity: Identity) -> tuple[str, str]:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    session.execute(
        text("""
            SELECT create_review_session(
                :user_id, :tenant_id, :token_hash, :csrf_hash, :expires_at)
        """),
        {
            "user_id": identity.user_id,
            "tenant_id": identity.tenant_id,
            "token_hash": token_digest(session_token),
            "csrf_hash": token_digest(csrf_token),
            "expires_at": datetime.now(UTC) + timedelta(hours=12),
        },
    )
    return session_token, csrf_token


def resolve_session(factory: sessionmaker[Session], token: str) -> Identity | None:
    session = factory()
    try:
        row = (
            session.execute(
                text("""
                SELECT user_id, tenant_id, email, display_name, role, workspace_name
                  FROM lookup_review_session(:token_hash)
            """),
                {"token_hash": token_digest(token)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return Identity(
            row.user_id,
            row.tenant_id,
            row.email,
            row.display_name,
            row.role,
            row.workspace_name,
        )
    finally:
        session.close()


def valid_csrf(factory: sessionmaker[Session], session_token: str, csrf_token: str) -> bool:
    session = factory()
    try:
        stored = session.execute(
            text("""
                SELECT lookup_review_csrf(:token_hash)
            """),
            {"token_hash": token_digest(session_token)},
        ).scalar_one_or_none()
        return stored is not None and hmac.compare_digest(stored, token_digest(csrf_token))
    finally:
        session.close()


def revoke_session(factory: sessionmaker[Session], token: str) -> None:
    session = factory()
    try:
        session.execute(
            text("SELECT revoke_review_session(:token_hash)"),
            {"token_hash": token_digest(token)},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
