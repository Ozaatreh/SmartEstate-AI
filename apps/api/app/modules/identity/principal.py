"""The authenticated caller, loaded from the database on every request (never trusted from the token)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.errors import PermissionDenied
from app.core.permissions import SUPER_ADMIN_ROLE


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str
    full_name: str
    role_codes: frozenset[str]
    permissions: frozenset[str]

    @property
    def is_super_admin(self) -> bool:
        return SUPER_ADMIN_ROLE in self.role_codes

    def has(self, permission: str) -> bool:
        return self.is_super_admin or permission in self.permissions

    def has_any(self, permissions: Iterable[str]) -> bool:
        return any(self.has(p) for p in permissions)


def ensure_permission(principal: Principal, permission: str) -> None:
    """Called inside services, so REST, AI tools and workflows are all covered."""
    if not principal.has(permission):
        raise PermissionDenied(details={"required_permission": permission})
