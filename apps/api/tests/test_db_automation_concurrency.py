"""Real concurrency: several workers (threads, separate connections) claim from one queue. Every execution
must be claimed and run exactly once. Uses committed rows and truncates all tables afterwards."""

from __future__ import annotations

import threading
import uuid
from collections import Counter

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.automation import events
from app.automation.engine import Engine
from app.automation.manager import sync_definitions
from app.automation.models import WorkflowExecution, WorkflowStepExecution
from app.core.security import hash_password
from app.modules.identity.models import User
from tests import automation_test_workflows as tw  # noqa: F401  (registers test workflows)

pytestmark = pytest.mark.db


@pytest.fixture
def committed(engine):
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    yield maker
    with engine.begin() as conn:
        tables = [
            r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))
        ]
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))


def test_concurrent_workers_claim_each_execution_once(committed):
    with committed() as s:
        sync_definitions(s)
        user = User(email=f"race-{uuid.uuid4().hex[:6]}@race.demo", password_hash=hash_password("x" * 12), full_name="Race")
        s.add(user)
        s.flush()
        for _ in range(40):
            events.emit(s, "test.noop", entity_type="test", entity_id=user.id, payload={"user_id": str(user.id)})
        s.commit()
    Engine(committed, "dispatcher").dispatch_events(limit=100)

    claimed: list[tuple[str, uuid.UUID]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    def worker(name: str) -> None:
        eng = Engine(committed, name)
        barrier.wait()
        while True:
            batch = eng.claim(limit=3)
            if not batch:
                return
            with lock:
                claimed.extend((name, eid) for eid, _ in batch)
            for eid, attempt in batch:
                eng.execute(eid, attempt)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    counts = Counter(eid for _, eid in claimed)
    assert len(counts) == 40 and set(counts.values()) == {1}, "an execution was claimed twice"
    assert len({name for name, _ in claimed}) > 1, "work should be shared between workers"
    with committed() as s:
        statuses = Counter(s.scalars(select(WorkflowExecution.status)).all())
        assert statuses == {"succeeded": 40}
        assert s.scalar(select(text("count(*)")).select_from(WorkflowStepExecution)) == 40  # one step record per execution
