"""Test harness.

DB tests run only against TEST_DATABASE_URL (whose database name must end in ``_test``). The schema
is rebuilt once per run from the real Alembic migrations; each test runs inside a transaction that
is rolled back, so services may ``commit()`` freely (they commit a SAVEPOINT).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import Role, User
from app.seed.__main__ import sync_permissions, sync_roles

pytest_plugins = ["tests.business_fixtures"]

API_ROOT = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "Correct-Horse-Battery-9"
CSRF = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def engine(settings: Settings) -> Iterator[Engine]:
    url = settings.test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.exit("Refusing to run: TEST_DATABASE_URL must point to a database whose name ends in _test", 2)
    eng = create_engine(url, pool_pre_ping=True)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        cfg = Config(str(API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    conn = engine.connect()
    tx = conn.begin()
    yield conn
    tx.rollback()
    conn.close()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()


@pytest.fixture
def roles(db: Session) -> dict[str, Role]:
    perms = sync_permissions(db)
    result = sync_roles(db, perms)
    db.commit()
    return result


@pytest.fixture
def make_user(db: Session, roles: dict[str, Role]):
    hashed = hash_password(TEST_PASSWORD)

    def _make(role: str = "employee", *, email: str | None = None, active: bool = True, name: str = "Test User") -> User:
        user = User(
            email=email or f"{role}.{uuid.uuid4().hex[:8]}@smartestate.demo", password_hash=hashed,
            full_name=name, is_active=active, roles=[roles[role]] if role else [],
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def app(db: Session, settings: Settings):
    application = create_app(settings)
    application.dependency_overrides[get_session] = lambda: db
    return application


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def login(client: TestClient, user: User, password: str = TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": user.email, "password": password}, headers=CSRF)
