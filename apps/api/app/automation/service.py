"""Automation Management service (route → service → repository). Every operator action is permission-checked and audited."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.automation.contracts import Workflow
from app.automation.engine import Engine, parameters_for
from app.automation.manager import sync_definitions, validate_parameters
from app.automation.models import WorkflowDefinition, WorkflowExecution
from app.automation.registry import ACTIONS, WORKFLOWS, load_catalog
from app.automation.repository import AutomationRepository
from app.automation.schemas import (
    ExecutionDetail,
    ExecutionOut,
    LogOut,
    Overview,
    ParameterOut,
    StepDefOut,
    StepRunOut,
    WorkerOut,
    WorkflowDetail,
    WorkflowOut,
    WorkflowStats,
    WorkflowUpdate,
)
from app.common.listing import ListParams, apply_sort, paginate
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission

WINDOW_HOURS = 24
_synced = False
SORTABLE = {"created_at": WorkflowExecution.created_at, "duration_ms": WorkflowExecution.duration_ms, "status": WorkflowExecution.status}


def steps_of(wf: type[Workflow]) -> list[StepDefOut]:
    return [
        StepDefOut(
            key=s.key,
            label=s.label,
            action=s.action,
            action_label=ACTIONS[s.action].label,
            action_description=ACTIONS[s.action].description,
            advisory=ACTIONS[s.action].advisory,
            condition=(s.when.description or s.when.name) if s.when else None,
            on_error=s.on_error,
        )
        for s in wf.steps
    ]


class AutomationService:
    def __init__(self, session: Session):
        global _synced
        self.session = session
        self.repo = AutomationRepository(session)
        self.audit = AuditService(session)
        load_catalog()
        if not _synced or len(self.repo.definitions()) < len(WORKFLOWS):
            sync_definitions(session)
            session.commit()
            _synced = True

    # --- workflows ------------------------------------------------------------------------------------------
    def list_workflows(self, principal: Principal) -> list[WorkflowOut]:
        ensure_permission(principal, Perm.AUTOMATION_WORKFLOWS_READ)
        since = datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)
        stats, last = self.repo.stats(since), self.repo.last_executions()
        return [self._wf_out(d, stats.get(d.key, {}), last.get(d.key)) for d in self.repo.definitions()]

    def get_workflow(self, principal: Principal, key: str) -> WorkflowDetail:
        ensure_permission(principal, Perm.AUTOMATION_WORKFLOWS_READ)
        d = self.repo.definition(key)
        if d is None:
            raise NotFound("Workflow not found.")
        since = datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)
        base = self._wf_out(d, self.repo.stats(since).get(key, {}), self.repo.last_executions().get(key))
        wf = WORKFLOWS.get(key)
        values = parameters_for(wf, d.parameters) if wf else d.parameters
        params = [
            ParameterOut(
                name=n,
                type=s.type,
                label=s.label,
                description=s.description,
                value=values.get(n),
                default=s.default,
                minimum=s.minimum,
                maximum=s.maximum,
                unit=s.unit,
            )
            for n, s in (wf.parameters.items() if wf else [])
        ]
        return WorkflowDetail(
            **base.model_dump(),
            conditions=[c.description or c.name for c in (wf.conditions if wf else ())],
            steps=steps_of(wf) if wf else [],
            parameters=params,
            can_manage=principal.has(Perm.AUTOMATION_WORKFLOWS_MANAGE),
            can_operate=principal.has(Perm.AUTOMATION_EXECUTIONS_OPERATE),
        )

    def update_workflow(self, principal: Principal, key: str, data: WorkflowUpdate) -> WorkflowDefinition:
        ensure_permission(principal, Perm.AUTOMATION_WORKFLOWS_MANAGE)
        d = self.repo.definition(key, lock=True)
        wf = WORKFLOWS.get(key)
        if d is None or wf is None:
            raise NotFound("Workflow not found.")
        changes: dict[str, object] = {}
        if data.parameters is not None:
            clean = validate_parameters(wf, data.parameters)
            merged = {**parameters_for(wf, d.parameters), **clean}
            if "warning_pct" in merged and "critical_pct" in merged and merged["critical_pct"] < merged["warning_pct"]:
                raise BusinessRuleViolation("The critical threshold must be at least the warning threshold.", code="invalid_thresholds")
            if "hot_score" in merged and "warm_score" in merged and merged["hot_score"] <= merged["warm_score"]:
                raise BusinessRuleViolation("The hot score must be higher than the warm score.", code="invalid_thresholds")
            if (
                all(k in merged for k in ("weight_price", "weight_delivery", "weight_rating"))
                and merged["weight_price"] + merged["weight_delivery"] + merged["weight_rating"] <= 0
            ):
                raise BusinessRuleViolation("At least one weight must be above zero.", code="invalid_weights")
            changes["parameters"] = {k: [d.parameters.get(k), v] for k, v in clean.items() if d.parameters.get(k) != v}
            d.parameters = merged
        for name in ("is_enabled", "timeout_seconds", "max_attempts"):
            value = getattr(data, name)
            if value is not None and value != getattr(d, name):
                changes[name] = [getattr(d, name), value]
                setattr(d, name, value)
        if data.is_enabled and d.schedule_minutes and (d.next_run_at is None or d.next_run_at < datetime.now(UTC)):
            d.next_run_at = datetime.now(UTC)
        self.audit.record(
            "automation.workflow_updated",
            actor_user_id=principal.user_id,
            entity_type="workflow",
            entity_id=key,
            summary=f"{d.name} configuration changed",
            changes=changes or None,
        )
        self.session.commit()
        return d

    def run_now(self, principal: Principal, key: str) -> uuid.UUID:
        ensure_permission(principal, Perm.AUTOMATION_EXECUTIONS_OPERATE)
        d = self.repo.definition(key)
        if d is None or key not in WORKFLOWS:
            raise NotFound("Workflow not found.")
        if not d.schedule_minutes:
            raise BusinessRuleViolation(
                "Only scheduled workflows can be run on demand; event workflows run when their event happens.", code="not_runnable"
            )
        if not d.is_enabled:
            raise BusinessRuleViolation("Enable the workflow before running it.", code="workflow_disabled")
        execution_id = Engine(lambda: self.session, "api").run_now(self.session, key, principal.user_id)
        self.audit.record(
            "automation.workflow_run",
            actor_user_id=principal.user_id,
            entity_type="workflow",
            entity_id=key,
            summary=f"{d.name} run requested",
            changes={"execution_id": str(execution_id)},
        )
        self.session.commit()
        return execution_id

    # --- executions -------------------------------------------------------------------------------------------
    def list_executions(
        self,
        principal: Principal,
        params: ListParams,
        *,
        workflow_key: str | None,
        status: str | None,
        trigger_type: str | None,
        entity_id: str | None,
    ) -> tuple[list[ExecutionOut], int, int]:
        ensure_permission(principal, Perm.AUTOMATION_WORKFLOWS_READ)
        stmt = self.repo.execution_query(
            workflow_key=workflow_key, status=status, trigger_type=trigger_type, entity_id=entity_id, q=params.q
        )
        rows, total, pages = paginate(self.session, apply_sort(stmt, params.sort, SORTABLE, "-created_at"), params)
        events = self.repo.events_for([r.event_id for r in rows if r.event_id])
        return [self._exec_out(r, events.get(r.event_id) if r.event_id else None) for r in rows], total, pages

    def get_execution(self, principal: Principal, execution_id: uuid.UUID) -> ExecutionDetail:
        ensure_permission(principal, Perm.AUTOMATION_WORKFLOWS_READ)
        e = self.repo.execution(execution_id)
        if e is None:
            raise NotFound("Execution not found.")
        base = self._exec_out(e, self.repo.event(e.event_id))
        wf = WORKFLOWS.get(e.workflow_key)
        who = self.session.get(User, e.triggered_by_user_id) if e.triggered_by_user_id else None
        return ExecutionDetail(
            **base.model_dump(),
            context=e.context,
            result=e.result,
            triggered_by=who.full_name if who else None,
            steps=[StepRunOut.model_validate(s) for s in self.repo.steps(e.id)],
            planned_steps=steps_of(wf) if wf else [],
            logs=[LogOut.model_validate(entry) for entry in self.repo.logs(e.id)],
            allowed_actions=self._allowed(principal, e),
        )

    def retry(self, principal: Principal, execution_id: uuid.UUID) -> WorkflowExecution:
        """Re-queues a failed or cancelled execution for one more attempt. Completed steps are not repeated."""
        ensure_permission(principal, Perm.AUTOMATION_EXECUTIONS_OPERATE)
        e = self.repo.execution(execution_id, lock=True)
        if e is None:
            raise NotFound("Execution not found.")
        if e.status not in ("failed", "cancelled"):
            raise Conflict("Only failed or cancelled executions can be retried.", code="not_retryable")
        d = self.repo.definition(e.workflow_key)
        if d is None or not d.is_enabled or e.workflow_key not in WORKFLOWS:
            raise BusinessRuleViolation("The workflow is disabled or no longer registered.", code="workflow_disabled")
        before = e.status
        e.status, e.available_at, e.max_attempts, e.finished_at = "pending", datetime.now(UTC), e.attempt + 1, None
        self.audit.record(
            "automation.execution_retried",
            actor_user_id=principal.user_id,
            entity_type="workflow_execution",
            entity_id=e.id,
            summary=f"{d.name}: retry requested after {before} ({e.error_code})",
            changes={"status": [before, "pending"]},
        )
        self.session.commit()
        return e

    def cancel(self, principal: Principal, execution_id: uuid.UUID) -> WorkflowExecution:
        ensure_permission(principal, Perm.AUTOMATION_EXECUTIONS_OPERATE)
        e = self.repo.execution(execution_id, lock=True)
        if e is None:
            raise NotFound("Execution not found.")
        if e.status != "pending":
            raise Conflict("Only queued executions can be cancelled (running ones finish or time out).", code="not_cancellable")
        e.status, e.finished_at = "cancelled", datetime.now(UTC)
        self.audit.record(
            "automation.execution_cancelled",
            actor_user_id=principal.user_id,
            entity_type="workflow_execution",
            entity_id=e.id,
            summary=f"{e.workflow_key}: execution cancelled",
        )
        self.session.commit()
        return e

    def overview(self, principal: Principal) -> Overview:
        ensure_permission(principal, Perm.AUTOMATION_WORKFLOWS_READ)
        c = self.repo.overview_counts(datetime.now(UTC) - timedelta(hours=WINDOW_HOURS))
        done = c["succeeded"] + c["failed"]
        workers = [
            WorkerOut(
                worker_id=w.worker_id,
                hostname=w.hostname,
                pid=w.pid,
                started_at=w.started_at,
                last_seen_at=w.last_seen_at,
                executions_completed=w.executions_completed,
                online=online,
            )
            for w, online in self.repo.workers()
        ]
        return Overview(
            window_hours=WINDOW_HOURS,
            executions=c["executions"],
            succeeded=c["succeeded"],
            failed=c["failed"],
            skipped=c["skipped"],
            in_progress=c["in_progress"],
            success_rate=round(c["succeeded"] * 100 / done, 1) if done else None,
            queued_events=c["queued_events"],
            queued_executions=c["queued_executions"],
            retry_scheduled=c["retry_scheduled"],
            workers=workers,
            workers_online=sum(1 for w in workers if w.online),
        )

    # --- helpers ----------------------------------------------------------------------------------------------
    def _allowed(self, principal: Principal, e: WorkflowExecution) -> list[str]:
        if not principal.has(Perm.AUTOMATION_EXECUTIONS_OPERATE):
            return []
        return ["retry"] if e.status in ("failed", "cancelled") else ["cancel"] if e.status == "pending" else []

    def _wf_out(self, d: WorkflowDefinition, stats: dict[str, int | None], last: WorkflowExecution | None) -> WorkflowOut:
        return WorkflowOut(
            key=d.key,
            name=d.name,
            description=d.description,
            category=d.category,
            version=d.version,
            is_enabled=d.is_enabled,
            is_registered=d.is_registered,
            event_types=list(d.event_types or []),
            schedule_minutes=d.schedule_minutes,
            timeout_seconds=d.timeout_seconds,
            max_attempts=d.max_attempts,
            next_run_at=d.next_run_at,
            last_run_at=d.last_run_at,
            stats=WorkflowStats(
                window_hours=WINDOW_HOURS,
                **{k: v or 0 for k, v in stats.items() if k != "avg_duration_ms"},
                avg_duration_ms=stats.get("avg_duration_ms"),
                last_execution_id=last.id if last else None,
                last_status=last.status if last else None,
                last_finished_at=last.finished_at if last else None,
            ),
        )

    def _exec_out(self, e: WorkflowExecution, event) -> ExecutionOut:
        wf = WORKFLOWS.get(e.workflow_key)
        payload = (event.payload if event else e.context.get("payload")) or {}
        return ExecutionOut(
            id=e.id,
            workflow_key=e.workflow_key,
            workflow_name=wf.name if wf else e.workflow_key,
            workflow_version=e.workflow_version,
            trigger_type=e.trigger_type,
            event_type=event.event_type if event else e.context.get("event_type"),
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            entity_label=payload.get("code"),
            status=e.status,
            attempt=e.attempt,
            max_attempts=e.max_attempts,
            available_at=e.available_at,
            started_at=e.started_at,
            finished_at=e.finished_at,
            duration_ms=e.duration_ms,
            error_code=e.error_code,
            error_message=e.error_message,
            lease_owner=e.lease_owner,
            lease_expires_at=e.lease_expires_at,
            created_at=e.created_at,
        )
