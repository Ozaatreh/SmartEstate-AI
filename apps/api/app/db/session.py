"""Engine and session management. Services own the transaction (commit); repositories never commit."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    return create_engine(s.database_url, echo=s.db_echo, pool_pre_ping=True, pool_size=5, max_overflow=5)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, rolled back if the service did not commit."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
