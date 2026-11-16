"""Trigger Manager + Workflow Executor (AUTOMATION_ENGINE.md §§ 4, 7, 9, 10).

PostgreSQL is the queue:
- events and executions are claimed with ``FOR UPDATE SKIP LOCKED`` (many workers, no double work);
- a claimed execution holds a **lease** (owner + expiry). Every step commits only after re-locking the
  execution row and checking it still owns the lease (fencing), so a worker that lost its lease can't
  write anything;
- abandoned executions (lease expired, e.g. worker crash) are recovered by any worker;
- each step runs in its own transaction together with its step record, so a retried execution resumes
  after the last committed step and no step's effect happens twice;
- a step's time budget is enforced with PostgreSQL ``statement_timeout`` for database work plus a
  deadline check before commit; an overrun rolls the step back and counts as a transient failure.
All times come from the database clock (``clock_timestamp()``) so workers on different hosts agree.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.automation.conditions import evaluate
from app.automation.contracts import ActionContext, ExecutionContext, Step, Workflow
from app.automation.errors import LeaseLost, PermanentError, StepTimeout, backoff_seconds, classify
from app.automation.logs import ExecutionLogger
from app.automation.models import AutomationEvent, WorkflowDefinition, WorkflowExecution, WorkflowStepExecution
from app.automation.registry import ACTIONS, WORKFLOWS

log = logging.getLogger("app.automation")
NOW = func.clock_timestamp
LEASE_GRACE_SECONDS = 30
MAX_EVENT_ATTEMPTS = 5


def _secs(n: float):
    return func.make_interval(0, 0, 0, 0, 0, 0, n)


@dataclass
class TickResult:
    recovered: int = 0
    dispatched: int = 0
    scheduled: int = 0
    executed: int = 0

    @property
    def busy(self) -> bool:
        return bool(self.recovered or self.dispatched or self.scheduled or self.executed)


def parameters_for(workflow: type[Workflow], stored: dict[str, Any] | None) -> dict[str, Any]:
    values = {k: spec.default for k, spec in workflow.parameters.items()}
    values.update({k: v for k, v in (stored or {}).items() if k in workflow.parameters})
    return values


def _summary(value: Any, limit: int = 4000) -> Any:
    """Keep stored JSON small."""
    import json

    raw = json.dumps(value, default=str)
    return value if len(raw) <= limit else {"truncated": True, "preview": raw[:limit]}


class Engine:
    def __init__(self, session_factory: Callable[[], Session], worker_id: str):
        self.session_factory = session_factory
        self.worker_id = worker_id

    # ================================================================ trigger manager
    def dispatch_events(self, limit: int = 50) -> int:
        """Turns pending outbox events into executions of every enabled workflow subscribed to them."""
        with self.session_factory() as s:
            events = list(
                s.scalars(
                    select(AutomationEvent)
                    .where(AutomationEvent.status == "pending", AutomationEvent.available_at <= NOW())
                    .order_by(AutomationEvent.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            if not events:
                return 0
            definitions = list(
                s.scalars(
                    select(WorkflowDefinition).where(WorkflowDefinition.is_enabled.is_(True), WorkflowDefinition.is_registered.is_(True))
                )
            )
            for event in events:
                try:
                    with s.begin_nested():
                        created = 0
                        for d in definitions:
                            wf = WORKFLOWS.get(d.key)
                            if wf is None or event.event_type not in (d.event_types or []):
                                continue
                            created += self._create_execution(
                                s,
                                wf,
                                d,
                                "event",
                                str(event.id),
                                event_id=event.id,
                                entity_type=event.entity_type,
                                entity_id=event.entity_id,
                                context={
                                    "event_id": str(event.id),
                                    "event_type": event.event_type,
                                    "entity_type": event.entity_type,
                                    "entity_id": event.entity_id,
                                    "payload": event.payload,
                                    "occurred_at": event.created_at.isoformat(),
                                    "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
                                },
                            )
                        event.status, event.dispatched_at, event.executions_created = "dispatched", datetime.now(UTC), created
                except Exception as exc:  # keep other events flowing
                    event.attempts += 1
                    event.last_error = str(exc)[:500]
                    event.status = "failed" if event.attempts >= MAX_EVENT_ATTEMPTS else "pending"
                    event.available_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds(event.attempts, base=10))
                    log.exception("Event dispatch failed", extra={"event_id": str(event.id)})
            s.commit()
            return len(events)

    def fire_schedules(self) -> int:
        """Creates one execution per due schedule slot. Missed slots collapse into one run."""
        fired = 0
        with self.session_factory() as s:
            due = list(
                s.scalars(
                    select(WorkflowDefinition)
                    .where(
                        WorkflowDefinition.schedule_minutes.is_not(None),
                        WorkflowDefinition.is_enabled.is_(True),
                        WorkflowDefinition.is_registered.is_(True),
                        (WorkflowDefinition.next_run_at.is_(None)) | (WorkflowDefinition.next_run_at <= NOW()),
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            now = s.execute(select(NOW())).scalar_one()
            for d in due:
                wf = WORKFLOWS.get(d.key)
                if wf is None:
                    continue
                every = timedelta(minutes=d.schedule_minutes or 1)
                epoch = datetime(2000, 1, 1, tzinfo=UTC)
                slot = epoch + ((now - epoch) // every) * every
                fired += self._create_execution(s, wf, d, "schedule", slot.isoformat(), context={"slot": slot.isoformat()})
                d.last_run_at, d.next_run_at = now, slot + every
            s.commit()
        return fired

    def run_now(self, session: Session, workflow_key: str, user_id: uuid.UUID | None, context: dict[str, Any] | None = None) -> uuid.UUID:
        """Manual trigger (inside the caller's transaction)."""
        d = session.scalar(select(WorkflowDefinition).where(WorkflowDefinition.key == workflow_key))
        wf = WORKFLOWS.get(workflow_key)
        if d is None or wf is None:
            raise PermanentError(f"Unknown workflow {workflow_key}")
        ref = uuid.uuid4().hex
        self._create_execution(
            session,
            wf,
            d,
            "manual",
            ref,
            context={"requested_by": str(user_id) if user_id else None, **(context or {})},
            triggered_by=user_id,
        )
        return session.scalar(select(WorkflowExecution.id).where(WorkflowExecution.idempotency_key == wf().idempotency_key("manual", ref)))  # type: ignore[return-value]

    def _create_execution(
        self,
        s: Session,
        wf: type[Workflow],
        d: WorkflowDefinition,
        trigger_type: str,
        ref: str,
        *,
        context: dict[str, Any],
        event_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        triggered_by: uuid.UUID | None = None,
    ) -> int:
        key = wf().idempotency_key(trigger_type, ref)
        stmt = (
            insert(WorkflowExecution)
            .values(
                id=uuid.uuid4(),
                workflow_key=wf.key,
                workflow_version=wf.version,
                trigger_type=trigger_type,
                event_id=event_id,
                idempotency_key=key,
                entity_type=entity_type or wf.entity_type,
                entity_id=entity_id,
                status="pending",
                max_attempts=d.max_attempts,
                timeout_seconds=d.timeout_seconds,
                context=context,
                triggered_by_user_id=triggered_by,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(WorkflowExecution.id)
        )
        return len(s.execute(stmt).all())  # 0 when the idempotency key already existed

    # ================================================================ recovery & claiming
    def recover_abandoned(self, limit: int = 50) -> int:
        """Executions whose lease expired (worker crashed / hung) go back to the queue, or fail at max attempts."""
        recovered = 0
        with self.session_factory() as s:
            rows = list(
                s.scalars(
                    select(WorkflowExecution)
                    .where(WorkflowExecution.status == "running", WorkflowExecution.lease_expires_at < NOW())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for e in rows:
                owner = e.lease_owner
                final = e.attempt >= e.max_attempts
                e.status = "failed" if final else "pending"
                e.error_code, e.error_message = (
                    "abandoned",
                    f"Lease held by {owner} expired; " + ("no attempts left." if final else "requeued."),
                )
                e.lease_owner = e.lease_expires_at = None
                if final:
                    e.finished_at = datetime.now(UTC)
                else:
                    e.available_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds(e.attempt, base=5))
                recovered += 1
            s.commit()
        for e in rows:
            ExecutionLogger(self.session_factory, e.id, e.workflow_key, e.attempt).warning(
                f"Recovered abandoned execution ({e.status})", previous_owner=e.error_message
            )
        return recovered

    def claim(self, limit: int = 5) -> list[tuple[uuid.UUID, int]]:
        with self.session_factory() as s:
            ids = (
                select(WorkflowExecution.id)
                .where(WorkflowExecution.status == "pending", WorkflowExecution.available_at <= NOW())
                .order_by(WorkflowExecution.available_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .scalar_subquery()
            )
            rows = s.execute(
                update(WorkflowExecution)
                .where(WorkflowExecution.id.in_(ids))
                .values(
                    status="running",
                    attempt=WorkflowExecution.attempt + 1,
                    lease_owner=self.worker_id,
                    lease_expires_at=NOW() + _secs(1) * (WorkflowExecution.timeout_seconds + LEASE_GRACE_SECONDS),
                    started_at=func.coalesce(WorkflowExecution.started_at, NOW()),
                    updated_at=NOW(),
                )
                .returning(WorkflowExecution.id, WorkflowExecution.attempt)
            ).all()
            s.commit()
            return [(r[0], r[1]) for r in rows]

    # ================================================================ executor
    def tick(self, max_executions: int = 10) -> TickResult:
        r = TickResult(recovered=self.recover_abandoned(), dispatched=self.dispatch_events(), scheduled=self.fire_schedules())
        for execution_id, attempt in self.claim(max_executions):
            self.execute(execution_id, attempt)
            r.executed += 1
        return r

    def run_until_idle(self, max_rounds: int = 25) -> int:
        executed = 0
        for _ in range(max_rounds):
            r = self.tick()
            executed += r.executed
            if not r.busy:
                break
        return executed

    def execute(self, execution_id: uuid.UUID, attempt: int) -> str:
        with self.session_factory() as s:
            e = s.get(WorkflowExecution, execution_id)
            if e is None:
                return "missing"
            d = s.scalar(select(WorkflowDefinition).where(WorkflowDefinition.key == e.workflow_key))
            done = {
                r.step_key: r.output or {}
                for r in s.scalars(
                    select(WorkflowStepExecution).where(
                        WorkflowStepExecution.execution_id == execution_id, WorkflowStepExecution.status.in_(("succeeded", "skipped"))
                    )
                )
            }
            trigger_type, context, timeout, key = e.trigger_type, dict(e.context), e.timeout_seconds, e.workflow_key
            stored_params = d.parameters if d else {}
        logger = ExecutionLogger(self.session_factory, execution_id, key, attempt)
        wf_cls = WORKFLOWS.get(key)
        if wf_cls is None:
            return self._finish(
                execution_id, attempt, "failed", error=("unknown_workflow", f"Workflow {key} is not registered."), logger=logger
            )
        wf = wf_cls()
        ctx = ExecutionContext(
            execution_id=execution_id,
            workflow_key=key,
            trigger_type=trigger_type,
            trigger=context,
            parameters=parameters_for(wf_cls, stored_params),
            data=dict(done),
        )
        deadline = time.monotonic() + timeout
        logger.info(
            f"Attempt {attempt} started" + (f" · resuming after {len(done)} completed step(s)" if done else ""),
            worker=self.worker_id,
            timeout_seconds=timeout,
        )
        try:
            with self.session_factory() as s:
                passed, trace = evaluate(s, ctx, wf.conditions)
            for t in trace:
                logger.info(f"Condition {t['condition']}: {'passed' if t['passed'] else 'not met'} — {t['reason']}")
            if not passed:
                return self._finish(execution_id, attempt, "skipped", result={"skipped_because": trace[-1]["reason"]}, logger=logger)
            for index, step in enumerate(wf.steps):
                if step.key in ctx.data:
                    continue
                logger.step_key = step.key
                self._run_step(ctx, step, index, attempt, deadline, logger)
                logger.step_key = None
            return self._finish(execution_id, attempt, "succeeded", result=_summary(ctx.data), logger=logger)
        except LeaseLost as exc:
            logger.step_key = None
            logger.warning(f"Stopped: {exc}")
            return "lease_lost"
        except Exception as exc:
            logger.step_key = None
            transient, code, message = classify(exc)
            return self._fail(execution_id, attempt, transient, code, message, logger)

    def _run_step(self, ctx: ExecutionContext, step: Step, index: int, attempt: int, deadline: float, logger: ExecutionLogger) -> None:
        spec = ACTIONS[step.action]
        started = datetime.now(UTC)
        t0 = time.monotonic()
        raw_input: dict[str, Any] | None = None
        with self.session_factory() as s:
            try:
                self._fence(s, ctx.execution_id, attempt)
                if step.when is not None:
                    r = step.when.check(s, ctx)
                    if not r.passed:
                        logger.info(f"Step skipped: {r.reason}")
                        self._record_step(s, ctx, step, index, attempt, "skipped", started, t0, None, {"skipped": True, "reason": r.reason})
                        s.commit()
                        ctx.data[step.key] = {"skipped": True, "reason": r.reason}
                        return
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    raise StepTimeout(f"No time left for step {step.key}.")
                s.execute(text(f"SET LOCAL statement_timeout = {max(remaining_ms, 1)}"))
                built = step.build_input(ctx)
                raw_input = built.model_dump(mode="json") if isinstance(built, BaseModel) else dict(built)
                try:
                    data = spec.input_model.model_validate(raw_input)
                except ValidationError as exc:
                    raise PermanentError(f"Invalid input for {step.action}: {exc.errors()[0]['msg']}", code="invalid_input") from exc
                logger.info(f"Running {spec.label}", action=step.action)
                output = (
                    spec.func(
                        ActionContext(
                            session=s, execution=ctx, step_key=step.key, idempotency_key=f"{ctx.execution_id}:{step.key}", log=logger
                        ),
                        data,
                    )
                    or {}
                )
                if time.monotonic() > deadline:
                    raise StepTimeout(f"Step {step.key} exceeded the workflow time limit; its changes were rolled back.")
                s.execute(text("SET LOCAL statement_timeout = 0"))
                self._fence(s, ctx.execution_id, attempt)  # re-check right before commit
                self._record_step(s, ctx, step, index, attempt, "succeeded", started, t0, raw_input, _summary(output))
                s.commit()
                ctx.data[step.key] = output
                logger.info(f"{spec.label} succeeded", duration_ms=int((time.monotonic() - t0) * 1000))
            except Exception as exc:
                s.rollback()
                if isinstance(exc, LeaseLost):
                    raise
                transient, code, message = classify(exc)
                self._record_failed_step(ctx, step, index, attempt, started, t0, raw_input, code, message)
                if step.on_error == "continue":
                    logger.warning(f"{spec.label} failed but is optional: {message}", error_code=code)
                    ctx.data[step.key] = {"failed": True, "error_code": code, "error": message}
                    return
                logger.error(f"{spec.label} failed: {message}", error_code=code, transient=transient)
                raise

    def _record_step(
        self,
        s: Session,
        ctx: ExecutionContext,
        step: Step,
        index: int,
        attempt: int,
        status: str,
        started: datetime,
        t0: float,
        raw_input: dict[str, Any] | None,
        output: dict[str, Any] | None,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        s.add(
            WorkflowStepExecution(
                execution_id=ctx.execution_id,
                step_key=step.key,
                step_index=index,
                action_key=step.action,
                attempt=attempt,
                status=status,
                input=raw_input,
                output=output,
                error_code=code,
                error_message=(message or None) and message[:1000],
                started_at=started,
                finished_at=datetime.now(UTC),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        )

    def _record_failed_step(self, ctx, step, index, attempt, started, t0, raw_input, code, message) -> None:
        try:
            with self.session_factory() as s:
                self._fence(s, ctx.execution_id, attempt)
                self._record_step(s, ctx, step, index, attempt, "failed", started, t0, raw_input, None, code, message)
                s.commit()
        except LeaseLost:
            pass

    def _fence(self, s: Session, execution_id: uuid.UUID, attempt: int) -> None:
        ok = s.execute(
            select(WorkflowExecution.id)
            .where(
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == "running",
                WorkflowExecution.lease_owner == self.worker_id,
                WorkflowExecution.attempt == attempt,
            )
            .with_for_update(key_share=True)  # FOR NO KEY UPDATE: fences writers but lets log rows (FK) be inserted meanwhile
        ).first()
        if ok is None:
            raise LeaseLost("This worker no longer holds the execution lease.")

    def _fail(self, execution_id: uuid.UUID, attempt: int, transient: bool, code: str, message: str, logger: ExecutionLogger) -> str:
        with self.session_factory() as s:
            e = s.scalar(
                select(WorkflowExecution)
                .where(
                    and_(
                        WorkflowExecution.id == execution_id,
                        WorkflowExecution.lease_owner == self.worker_id,
                        WorkflowExecution.attempt == attempt,
                        WorkflowExecution.status == "running",
                    )
                )
                .with_for_update(key_share=True)
            )
            if e is None:
                return "lease_lost"
            retry = transient and e.attempt < e.max_attempts
            e.error_code, e.error_message = code, message[:1000]
            e.lease_owner = e.lease_expires_at = None
            if retry:
                delay = backoff_seconds(e.attempt)
                e.status, e.available_at = "pending", datetime.now(UTC) + timedelta(seconds=delay)
            else:
                e.status, e.finished_at = "failed", datetime.now(UTC)
                e.duration_ms = int((e.finished_at - e.started_at).total_seconds() * 1000) if e.started_at else None
            s.commit()
        if retry:
            logger.warning(f"Attempt {attempt} failed ({code}); retry {attempt + 1} scheduled in ~{delay}s.")
            return "retry_scheduled"
        logger.error(f"Execution failed ({code}){'' if transient else ' — not retryable'}." + (" No attempts left." if transient else ""))
        return "failed"

    def _finish(
        self,
        execution_id: uuid.UUID,
        attempt: int,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: tuple[str, str] | None = None,
        logger: ExecutionLogger,
    ) -> str:
        with self.session_factory() as s:
            e = s.scalar(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.id == execution_id,
                    WorkflowExecution.lease_owner == self.worker_id,
                    WorkflowExecution.attempt == attempt,
                )
                .with_for_update(key_share=True)
            )
            if e is None:
                return "lease_lost"
            now = datetime.now(UTC)
            e.status, e.finished_at, e.result = status, now, result
            e.duration_ms = int((now - e.started_at).total_seconds() * 1000) if e.started_at else None
            e.lease_owner = e.lease_expires_at = None
            if status == "succeeded" or status == "skipped":
                e.error_code = e.error_message = None
            if error:
                e.error_code, e.error_message = error
            s.commit()
        logger.info(f"Execution {status}")
        return status
