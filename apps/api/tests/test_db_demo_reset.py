"""RESET_DEMO_PASSWORDS: a one-time, staging-only way to set every fictional demo account's password again."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import verify_password
from app.modules.audit.models import AuditLog
from app.seed.__main__ import reset_demo_passwords

pytestmark = pytest.mark.db

NEW = "New-Evaluator-Pass-42"
BASE = {"database_url": "postgresql+psycopg://u:p@h/db", "secret_key": "x" * 48, "_env_file": None}


def test_resets_only_demo_accounts_clears_lockout_and_signs_out(db, make_user):
    demo = make_user("sales_agent")  # @smartestate.demo
    other = make_user("sales_agent", email="real.person@example.com")
    demo.failed_login_count, demo.locked_until = 5, datetime.now(UTC) + timedelta(minutes=15)
    before_tv, other_hash = demo.token_version, other.password_hash
    db.commit()

    settings = Settings(app_env="staging", seed_demo_data=True, reset_demo_passwords=True, seed_demo_password=NEW, **BASE)
    assert reset_demo_passwords(db, settings) >= 1
    db.commit()
    db.refresh(demo)
    db.refresh(other)
    assert verify_password(NEW, demo.password_hash)
    assert demo.failed_login_count == 0 and demo.locked_until is None
    assert demo.token_version == before_tv + 1
    assert other.password_hash == other_hash  # non-demo accounts are never touched
    assert db.scalar(select(AuditLog).where(AuditLog.action == "identity.demo_passwords_reset")) is not None


def test_reset_needs_a_strong_password_and_is_refused_in_production(db):
    with pytest.raises(SystemExit):
        reset_demo_passwords(db, Settings(app_env="staging", seed_demo_password="short", **BASE))
    with pytest.raises(ValidationError, match="RESET_DEMO_PASSWORDS"):
        Settings(app_env="production", reset_demo_passwords=True, **BASE)
