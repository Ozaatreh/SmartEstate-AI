"""Automation worker — a separate process (never inside the API).

    python -m app.automation.worker            # run until stopped (Ctrl+C / SIGTERM)
    python -m app.automation.worker --once     # drain the queue once and exit

Any number of workers can run; claiming uses FOR UPDATE SKIP LOCKED and leases.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import socket
import threading
import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from app.automation.engine import Engine
from app.automation.manager import sync_definitions
from app.automation.models import WorkerHeartbeat
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker

log = logging.getLogger("app.automation.worker")


def _heartbeat(maker, worker_id: str, started: datetime, completed: int) -> None:
    now = datetime.now(UTC)
    with maker() as s:
        s.execute(
            insert(WorkerHeartbeat)
            .values(
                worker_id=worker_id,
                hostname=socket.gethostname()[:120],
                pid=os.getpid(),
                started_at=started,
                last_seen_at=now,
                executions_completed=completed,
            )
            .on_conflict_do_update(index_elements=["worker_id"], set_={"last_seen_at": now, "executions_completed": completed})
        )
        s.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SmartEstate automation worker")
    parser.add_argument("--once", action="store_true", help="Process everything that is due, then exit")
    parser.add_argument("--poll", type=float, default=2.0, help="Seconds to wait when the queue is empty")
    parser.add_argument("--batch", type=int, default=10, help="Executions to claim per tick")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    import app.main  # noqa: F401  (registers approval subjects and every model)

    maker = get_sessionmaker()
    with maker() as s:
        n = sync_definitions(s)
        s.commit()
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    engine = Engine(maker, worker_id)
    started = datetime.now(UTC)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError):  # not in the main thread
            signal.signal(sig, lambda *_: stop.set())
    log.info("Automation worker %s started (%d workflows registered)", worker_id, n)
    completed = 0
    while not stop.is_set():
        try:
            _heartbeat(maker, worker_id, started, completed)
            result = engine.tick(max_executions=args.batch)
            completed += result.executed
            if result.busy:
                log.info(
                    "tick",
                    extra={
                        "recovered": result.recovered,
                        "dispatched": result.dispatched,
                        "scheduled": result.scheduled,
                        "executed": result.executed,
                    },
                )
            if args.once and not result.busy:
                break
            if not result.busy:
                stop.wait(args.poll)
        except Exception:
            log.exception("Worker tick failed; retrying shortly")
            stop.wait(min(30.0, args.poll * 5))
    log.info("Automation worker %s stopped after %d executions", worker_id, completed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
