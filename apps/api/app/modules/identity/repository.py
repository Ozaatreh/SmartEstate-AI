from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole


class IdentityRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_user(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str, *, for_update: bool = False) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        if for_update:
            stmt = stmt.with_for_update()
        return self.session.scalar(stmt)

    def get_role(self, code: str) -> Role | None:
        return self.session.scalar(select(Role).where(Role.code == code))

    def get_permission(self, code: str) -> Permission | None:
        return self.session.scalar(select(Permission).where(Permission.code == code))

    def users_with_permission(self, code: str) -> list[uuid.UUID]:
        """Active users holding a permission through one of their roles (explicit grants only)."""
        return list(self.session.scalars(
            select(User.id).join(UserRole, UserRole.user_id == User.id).join(RolePermission, RolePermission.role_id == UserRole.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Permission.code == code, User.is_active.is_(True)).distinct().order_by(User.id)
        ))

    def list_permissions(self) -> list[Permission]:
        return list(self.session.scalars(select(Permission).order_by(Permission.code)))
