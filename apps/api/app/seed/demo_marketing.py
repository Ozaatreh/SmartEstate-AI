"""Demo Marketing Specialist account (Phase 7B). Additive and idempotent; development / test only.

    python -m app.seed.demo_marketing

Creates only the fictional "Lina Farouk" Marketing Specialist account (``marketing.specialist@<demo domain>``) when it
is missing, with the role created by migration 0011 and the SEED_DEMO_PASSWORD. Nothing else is created, updated or
deleted — existing users, roles and data are left exactly as they are.
"""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.modules.identity.models import Role, User
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService

ROLE, NAME, TITLE, LOCAL = "marketing_specialist", "Lina Farouk", "Marketing Specialist", "marketing.specialist"


def run() -> int:
    settings = get_settings()
    if not settings.seeds_demo_data:
        print("Demo accounts are only created in development/test (or a staging demo with SEED_DEMO_DATA=true).", file=sys.stderr)
        return 2
    if settings.seed_demo_password is None or len(settings.seed_demo_password.get_secret_value()) < 12:
        print("SEED_DEMO_PASSWORD must be set (at least 12 characters).", file=sys.stderr)
        return 2
    email = f"{LOCAL}@{settings.seed_admin_email.split('@', 1)[1]}"
    with get_sessionmaker()() as session:
        repo = IdentityRepository(session)
        if repo.get_user_by_email(email) is not None:
            print(f"{email} already exists; nothing changed.")
            return 0
        role = repo.get_role(ROLE)
        if not isinstance(role, Role):
            print("The marketing_specialist role is missing; run the migrations first (alembic upgrade head).", file=sys.stderr)
            return 2
        user = User(
            email=email,
            password_hash=hash_password(settings.seed_demo_password.get_secret_value()),
            full_name=NAME,
            job_title=TITLE,
            roles=[role],
        )
        session.add(user)
        session.flush()
        NotificationService(session).notify(
            user.id,
            type="system.welcome",
            level="info",
            dedupe_key="welcome",
            title="Welcome to SmartEstate AI",
            body="Your workspace is ready. Modules appear in the sidebar as they become available to your role.",
        )
        session.commit()
    print(f"Created demo account {email} (Marketing Specialist).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
