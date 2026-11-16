"""Password hashing (Argon2id) and session tokens (signed JWT carried in an HttpOnly cookie)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

_hasher = PasswordHasher()  # Argon2id with library defaults (RFC 9106 low-memory profile)
# Verified against when the account does not exist, so response time does not reveal it.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class SessionClaims:
    user_id: uuid.UUID
    token_version: int
    session_id: str
    expires_at: datetime


def create_session_token(settings: Settings, user_id: uuid.UUID, token_version: int) -> tuple[str, SessionClaims]:
    now = datetime.now(UTC)
    claims = SessionClaims(
        user_id=user_id,
        token_version=token_version,
        session_id=uuid.uuid4().hex,
        expires_at=now + timedelta(minutes=settings.session_ttl_minutes),
    )
    token = jwt.encode(
        {
            "sub": str(user_id),
            "tv": token_version,
            "sid": claims.session_id,
            "iat": now,
            "exp": claims.expires_at,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, claims


def decode_session_token(settings: Settings, token: str) -> SessionClaims | None:
    try:
        data = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "tv", "sid", "exp", "iat"]},
        )
        return SessionClaims(
            user_id=uuid.UUID(data["sub"]),
            token_version=int(data["tv"]),
            session_id=str(data["sid"]),
            expires_at=datetime.fromtimestamp(data["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        return None
