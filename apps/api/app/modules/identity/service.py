from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import NotAuthenticated, TooManyRequests
from app.core.permissions import ALL_PERMISSIONS, SUPER_ADMIN_ROLE
from app.core.security import SessionClaims, create_session_token, hash_password, needs_rehash, verify_password
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.identity.principal import Principal
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import MeResponse, RoleSummary
from app.modules.identity.throttle import IpThrottle

log = logging.getLogger(__name__)

INVALID_CREDENTIALS = "The email or password is incorrect."


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


class AuthService:
    def __init__(self, session: Session, settings: Settings, ip_throttle: IpThrottle):
        self.session = session
        self.settings = settings
        self.repo = IdentityRepository(session)
        self.audit = AuditService(session)
        self.ip_throttle = ip_throttle

    # --- sign-in -----------------------------------------------------------------
    def login(self, email: str, password: str, ip: str | None) -> tuple[User, str, SessionClaims]:
        ip_key = ip or "unknown"
        if self.ip_throttle.is_blocked(ip_key):
            self.audit.record("auth.login_throttled", actor_user_id=None, summary=f"Sign-in throttled for {email}", ip_address=ip)
            self.session.commit()
            raise TooManyRequests("Too many failed sign-in attempts. Try again later.", code="login_throttled")

        now = datetime.now(UTC)
        user = self.repo.get_user_by_email(email, for_update=True)

        if user is not None and user.locked_until is not None and user.locked_until > now:
            self.audit.record("auth.login_locked", actor_user_id=user.id, entity_type="user", entity_id=user.id, ip_address=ip)
            self.session.commit()
            raise TooManyRequests(
                "Too many failed attempts. This account is temporarily locked.", code="account_locked",
                details={"retry_after_seconds": int((user.locked_until - now).total_seconds())},
            )

        password_ok = verify_password(password, user.password_hash if user else None)
        if user is None or not password_ok or not user.is_active:
            self._register_failure(user, email, ip, ip_key, now, inactive=bool(user and password_ok))
            raise NotAuthenticated(INVALID_CREDENTIALS, code="invalid_credentials")

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        self.audit.record("auth.login_succeeded", actor_user_id=user.id, entity_type="user", entity_id=user.id, ip_address=ip)
        self.session.commit()
        token, claims = create_session_token(self.settings, user.id, user.token_version)
        return user, token, claims

    def _register_failure(self, user: User | None, email: str, ip: str | None, ip_key: str, now: datetime, *, inactive: bool) -> None:
        self.ip_throttle.record_failure(ip_key)
        if user is not None and not inactive:
            user.failed_login_count += 1
            if user.failed_login_count >= self.settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=self.settings.login_lock_minutes)
                user.failed_login_count = 0
                self.audit.record("auth.account_locked", actor_user_id=user.id, entity_type="user", entity_id=user.id, ip_address=ip)
        self.audit.record(
            "auth.login_failed",
            actor_user_id=user.id if user else None,
            entity_type="user" if user else None,
            entity_id=user.id if user else None,
            summary="Inactive account" if inactive else f"Failed sign-in for {email[:254]}",
            ip_address=ip,
        )
        self.session.commit()

    # --- sign-out ----------------------------------------------------------------
    def logout(self, principal: Principal, ip: str | None) -> None:
        """Invalidates every session of the user (token_version bump)."""
        user = self.repo.get_user(principal.user_id)
        if user is None:
            return
        user.token_version += 1
        self.audit.record("auth.logout", actor_user_id=user.id, entity_type="user", entity_id=user.id, ip_address=ip)
        self.session.commit()

    # --- per-request principal -----------------------------------------------------
    def principal_from_claims(self, claims: SessionClaims) -> Principal:
        user = self.repo.get_user(claims.user_id)
        if user is None or not user.is_active or user.token_version != claims.token_version:
            raise NotAuthenticated(code="session_expired", message="Your session has ended. Sign in again.")
        return build_principal(user)


def build_principal(user: User) -> Principal:
    role_codes = frozenset(r.code for r in user.roles)
    perms = ALL_PERMISSIONS if SUPER_ADMIN_ROLE in role_codes else frozenset(p.code for r in user.roles for p in r.permissions)
    return Principal(user_id=user.id, email=user.email, full_name=user.full_name, role_codes=role_codes, permissions=perms)


def me_response(user: User, principal: Principal, session_expires_at: datetime | None = None) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        job_title=user.job_title,
        initials=initials(user.full_name),
        roles=[RoleSummary.model_validate(r) for r in user.roles],
        permissions=sorted(principal.permissions),
        is_super_admin=principal.is_super_admin,
        last_login_at=user.last_login_at,
        session_expires_at=session_expires_at,
    )
