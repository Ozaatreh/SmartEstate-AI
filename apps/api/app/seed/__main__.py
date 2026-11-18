"""Seed: permission catalogue, default roles and (development only) demo accounts. Idempotent.

    python -m app.seed

- Permissions are synced from ``app.core.permissions`` (added / description updated).
- Roles are created with their default grants; **existing role grants are never overwritten**
  (roles are data once they exist). New catalogue permissions are only added to Super Admin implicitly.
- Demo accounts (one per role, fictional) are created only when APP_ENV is development or test,
  all with SEED_DEMO_PASSWORD. Existing accounts are left untouched.
"""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation.manager import sync_definitions
from app.core.config import Settings, get_settings
from app.core.permissions import DEFAULT_ROLES, PERMISSION_DESCRIPTIONS, SUPER_ADMIN_ROLE, Perm
from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.modules.audit.service import AuditService
from app.modules.identity.models import Permission, Role, User
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService
from app.seed.demo_business import seed_demo_business
from app.seed.demo_realestate import seed_demo_realestate
from app.seed.reference import seed_reference

# Fictional demo people (no real persons). Email domain .demo is not routable.
DEMO_USERS: tuple[tuple[str, str, str, str], ...] = (
    ("super_admin", "Layla Haddad", "System Administrator", "admin"),
    ("executive", "Faisal Al-Rashid", "Chief Executive Officer", "ceo"),
    ("finance_manager", "Noura Al-Qahtani", "Finance Manager", "finance"),
    ("hr_manager", "Omar Saleh", "HR Manager", "hr"),
    ("department_manager", "Reem Al-Otaibi", "Head of Construction", "construction.head"),
    ("procurement_officer", "Khalid Mansour", "Procurement Officer", "procurement"),
    ("sales_manager", "Sara Al-Harbi", "Sales Manager", "sales.manager"),
    ("sales_agent", "Yousef Nasser", "Sales Consultant", "sales.agent"),
    ("marketing_manager", "Huda Al-Zahrani", "Marketing Manager", "marketing"),
    ("marketing_specialist", "Lina Farouk", "Marketing Specialist", "marketing.specialist"),
    ("employee", "Ahmed Karim", "Site Engineer", "employee"),
)


def sync_permissions(session: Session) -> dict[str, Permission]:
    """Creates missing catalogue permissions; remembers which ones are new in ``session.info``."""
    repo = IdentityRepository(session)
    existing = {p.code: p for p in repo.list_permissions()}
    created: set[str] = set()
    for perm in Perm:
        desc = PERMISSION_DESCRIPTIONS[perm]
        if perm.value in existing:
            existing[perm.value].description = desc
        else:
            p = Permission(code=perm.value, module=perm.value.split(".")[0], description=desc)
            session.add(p)
            existing[perm.value] = p
            created.add(perm.value)
    session.flush()
    session.info["seed_new_permissions"] = created
    return existing


def sync_roles(session: Session, perms: dict[str, Permission]) -> dict[str, Role]:
    """Creates missing roles with their default grants. For existing roles, only permissions that were
    *introduced in this run* are granted (once) — grants edited by administrators are never changed."""
    repo = IdentityRepository(session)
    new_perms: set[str] = session.info.get("seed_new_permissions", set())
    roles: dict[str, Role] = {}
    for spec in DEFAULT_ROLES:
        role = repo.get_role(spec.code)
        if role is None:
            grants = [] if spec.code == SUPER_ADMIN_ROLE else [perms[p.value] for p in sorted(spec.permissions)]
            role = Role(code=spec.code, name=spec.name, description=spec.description, is_system=True, permissions=grants)
            session.add(role)
        elif spec.code != SUPER_ADMIN_ROLE:
            held = {p.code for p in role.permissions}
            for p in sorted(spec.permissions):
                if p.value in new_perms and p.value not in held:
                    role.permissions.append(perms[p.value])
        roles[spec.code] = role
    session.flush()
    return roles


def seed_demo_users(session: Session, settings: Settings, roles: dict[str, Role]) -> int:
    if settings.seed_demo_password is None or len(settings.seed_demo_password.get_secret_value()) < 12:
        raise SystemExit("SEED_DEMO_PASSWORD must be set (at least 12 characters) to create demo accounts.")
    password_hash = hash_password(settings.seed_demo_password.get_secret_value())
    repo = IdentityRepository(session)
    notifications = NotificationService(session)
    domain = settings.seed_admin_email.split("@", 1)[1]
    created = 0
    for role_code, name, title, local in DEMO_USERS:
        email = settings.seed_admin_email if role_code == SUPER_ADMIN_ROLE else f"{local}@{domain}"
        if repo.get_user_by_email(email) is not None:
            continue
        user = User(email=email, password_hash=password_hash, full_name=name, job_title=title, roles=[roles[role_code]])
        session.add(user)
        session.flush()
        notifications.notify(
            user.id,
            type="system.welcome",
            level="info",
            dedupe_key="welcome",
            title="Welcome to SmartEstate AI",
            body="Your workspace is ready. Modules appear in the sidebar as they become available to your role.",
        )
        created += 1
    return created


def reset_demo_passwords(session: Session, settings: Settings) -> int:
    """Set every fictional demo account (the seed e-mail domain, e.g. ``.demo``) to SEED_DEMO_PASSWORD, clear lockouts
    and invalidate existing sessions. Only for demo environments; returns how many accounts were reset."""
    if settings.seed_demo_password is None or len(settings.seed_demo_password.get_secret_value()) < 12:
        raise SystemExit("SEED_DEMO_PASSWORD must be set (at least 12 characters) to reset demo passwords.")
    domain = "@" + settings.seed_admin_email.split("@", 1)[1].lower()
    password_hash = hash_password(settings.seed_demo_password.get_secret_value())
    users = [u for u in session.scalars(select(User)) if u.email.lower().endswith(domain)]
    for user in users:
        user.password_hash = password_hash
        user.failed_login_count = 0
        user.locked_until = None
        user.token_version += 1  # signs out any existing session
    if users:
        AuditService(session).record(
            "identity.demo_passwords_reset",
            actor_user_id=None,
            entity_type="user",
            summary=f"Demo account passwords reset on start-up ({len(users)} accounts, {domain})",
        )
    return len(users)


def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    with get_sessionmaker()() as session:
        perms = sync_permissions(session)
        roles = sync_roles(session, perms)
        policies, categories = seed_reference(session)
        workflows = sync_definitions(session)
        created = 0
        demo = settings.seeds_demo_data
        if demo and not settings.is_dev_like and session.scalar(select(User).where(User.email == settings.seed_admin_email)):
            # Hosted demo: seed once, on first boot. Restarts never re-create records evaluators changed or removed.
            demo = False
            print("Hosted demo data already seeded; skipping.", file=sys.stderr)
        if demo:
            created = seed_demo_users(session, settings, roles)
        reset = 0
        if settings.reset_demo_passwords and settings.seeds_demo_data:
            reset = reset_demo_passwords(session, settings)
            print(f"Demo account passwords reset: {reset}. Remove RESET_DEMO_PASSWORDS now.", file=sys.stderr)
        session.commit()
        business = demo and seed_demo_business(session, settings.seed_admin_email.split("@", 1)[1])
        inventory = seed_demo_realestate(session) if demo else None
        session.commit()
    print(
        f"Seed complete: {len(perms)} permissions, {len(roles)} roles, {policies} approval policies, {categories} budget categories, "
        f"{workflows} workflows, "
        f"{created} demo accounts created"
        + ("; fictional demo organisation created." if business else ".")
        + (f" Fictional NOVA inventory: {inventory['units']} units added." if inventory else "")
    )
    if not settings.seeds_demo_data:
        print("Demo accounts are skipped outside development/test (set SEED_DEMO_DATA=true for a staging demo).", file=sys.stderr)


if __name__ == "__main__":
    run()
