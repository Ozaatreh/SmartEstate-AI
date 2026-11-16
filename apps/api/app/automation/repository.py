from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.automation.models import (
    AutomationEvent,
    WorkerHeartbeat,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowExecutionLog,
    WorkflowStepExecution,
)
from app.common.listing import escape_like


class AutomationRepository:
    def __init__(self, session: Session):
        self.session = session

    def definitions(self) -> list[WorkflowDefinition]:
        return list(self.session.scalars(select(WorkflowDefinition).order_by(WorkflowDefinition.category, WorkflowDefinition.name)))

    def definition(self, key: str, *, lock: bool = False) -> WorkflowDefinition | None:
        stmt = select(WorkflowDefinition).where(WorkflowDefinition.key == key)
        return self.session.scalar(stmt.with_for_update() if lock else stmt)

    def stats(self, since: datetime) -> dict[str, dict[str, int | None]]:
        e = WorkflowExecution
        rows = self.session.execute(
            select(e.workflow_key, e.status, func.count(), func.avg(e.duration_ms))
            .where(or_(e.created_at >= since, e.status.in_(("pending", "running"))))
            .group_by(e.workflow_key, e.status)
        ).all()
        out: dict[str, dict[str, int | None]] = {}
        for key, status, n, avg in rows:
            d = out.setdefault(key, {})
            d[status] = int(n)
            if status == "succeeded" and avg is not None:
                d["avg_duration_ms"] = int(avg)
        return out

    def last_executions(self) -> dict[str, WorkflowExecution]:
        sub = (
            select(WorkflowExecution.workflow_key, func.max(WorkflowExecution.created_at).label("latest"))
            .group_by(WorkflowExecution.workflow_key)
            .subquery()
        )
        rows = self.session.scalars(
            select(WorkflowExecution).join(
                sub, (sub.c.workflow_key == WorkflowExecution.workflow_key) & (sub.c.latest == WorkflowExecution.created_at)
            )
        )
        return {r.workflow_key: r for r in rows}

    def execution_query(
        self, *, workflow_key: str | None, status: str | None, trigger_type: str | None, entity_id: str | None, q: str | None
    ) -> Select[tuple[WorkflowExecution]]:
        stmt = select(WorkflowExecution).outerjoin(AutomationEvent, AutomationEvent.id == WorkflowExecution.event_id)
        if workflow_key:
            stmt = stmt.where(WorkflowExecution.workflow_key == workflow_key)
        if status == "retrying":
            stmt = stmt.where(WorkflowExecution.status == "pending", WorkflowExecution.attempt > 0)
        elif status:
            stmt = stmt.where(WorkflowExecution.status == status)
        if trigger_type:
            stmt = stmt.where(WorkflowExecution.trigger_type == trigger_type)
        if entity_id:
            stmt = stmt.where(WorkflowExecution.entity_id == entity_id)
        if q:
            term = f"%{escape_like(q)}%"
            stmt = stmt.where(
                or_(
                    WorkflowExecution.error_message.ilike(term, escape="\\"),
                    AutomationEvent.event_type.ilike(term, escape="\\"),
                    AutomationEvent.payload["code"].astext.ilike(term, escape="\\"),
                    WorkflowExecution.entity_id.ilike(term, escape="\\"),
                )
            )
        return stmt

    def execution(self, execution_id: uuid.UUID, *, lock: bool = False) -> WorkflowExecution | None:
        stmt = select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        return self.session.scalar(stmt.with_for_update() if lock else stmt)

    def event(self, event_id: uuid.UUID | None) -> AutomationEvent | None:
        return self.session.get(AutomationEvent, event_id) if event_id else None

    def events_for(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, AutomationEvent]:
        if not ids:
            return {}
        return {e.id: e for e in self.session.scalars(select(AutomationEvent).where(AutomationEvent.id.in_(ids)))}

    def steps(self, execution_id: uuid.UUID) -> list[WorkflowStepExecution]:
        return list(
            self.session.scalars(
                select(WorkflowStepExecution)
                .where(WorkflowStepExecution.execution_id == execution_id)
                .order_by(WorkflowStepExecution.started_at, WorkflowStepExecution.step_index)
            )
        )

    def logs(self, execution_id: uuid.UUID, limit: int = 500) -> list[WorkflowExecutionLog]:
        return list(
            self.session.scalars(
                select(WorkflowExecutionLog)
                .where(WorkflowExecutionLog.execution_id == execution_id)
                .order_by(WorkflowExecutionLog.seq)
                .limit(limit)
            )
        )

    def overview_counts(self, since: datetime) -> dict[str, int]:
        e = WorkflowExecution
        row = self.session.execute(
            select(
                func.count().filter(e.created_at >= since),
                func.count().filter(e.created_at >= since, e.status == "succeeded"),
                func.count().filter(e.created_at >= since, e.status == "failed"),
                func.count().filter(e.created_at >= since, e.status == "skipped"),
                func.count().filter(e.status.in_(("pending", "running"))),
                func.count().filter(e.status == "pending", e.attempt > 0),
                func.count().filter(e.status == "pending"),
            )
        ).one()
        events = self.session.scalar(select(func.count()).select_from(AutomationEvent).where(AutomationEvent.status == "pending")) or 0
        keys = ("executions", "succeeded", "failed", "skipped", "in_progress", "retry_scheduled", "queued_executions")
        return {**dict(zip(keys, (int(v) for v in row), strict=True)), "queued_events": int(events)}

    def workers(self) -> list[tuple[WorkerHeartbeat, bool]]:
        online = case((WorkerHeartbeat.last_seen_at >= func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 30), True), else_=False)
        return [
            (w, bool(o))
            for w, o in self.session.execute(select(WorkerHeartbeat, online).order_by(WorkerHeartbeat.last_seen_at.desc()).limit(20))
        ]
