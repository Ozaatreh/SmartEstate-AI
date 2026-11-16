from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentPrincipal, SessionDep
from app.automation.schemas import ExecutionDetail, ExecutionOut, Overview, RunNowOut, WorkflowDetail, WorkflowOut, WorkflowUpdate
from app.automation.service import AutomationService
from app.common.listing import ListParams, Page, list_params

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/overview", response_model=Overview)
def overview(principal: CurrentPrincipal, session: SessionDep) -> Overview:
    return AutomationService(session).overview(principal)


@router.get("/workflows", response_model=list[WorkflowOut])
def list_workflows(principal: CurrentPrincipal, session: SessionDep) -> list[WorkflowOut]:
    return AutomationService(session).list_workflows(principal)


@router.get("/workflows/{key}", response_model=WorkflowDetail)
def get_workflow(key: str, principal: CurrentPrincipal, session: SessionDep) -> WorkflowDetail:
    return AutomationService(session).get_workflow(principal, key)


@router.patch("/workflows/{key}", response_model=WorkflowDetail)
def update_workflow(key: str, body: WorkflowUpdate, principal: CurrentPrincipal, session: SessionDep) -> WorkflowDetail:
    svc = AutomationService(session)
    svc.update_workflow(principal, key, body)
    return svc.get_workflow(principal, key)


@router.post("/workflows/{key}/run", response_model=RunNowOut, status_code=status.HTTP_202_ACCEPTED)
def run_workflow(key: str, principal: CurrentPrincipal, session: SessionDep) -> RunNowOut:
    return RunNowOut(execution_id=AutomationService(session).run_now(principal, key))


@router.get("/executions", response_model=Page[ExecutionOut])
def list_executions(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    workflow_key: str | None = Query(default=None, max_length=80),
    status: Literal["pending", "running", "succeeded", "failed", "skipped", "cancelled", "retrying"] | None = None,
    trigger_type: Literal["event", "schedule", "manual"] | None = None,
    entity_id: str | None = Query(default=None, max_length=64),
) -> Page[ExecutionOut]:
    items, total, pages = AutomationService(session).list_executions(
        principal, params, workflow_key=workflow_key, status=status, trigger_type=trigger_type, entity_id=entity_id
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/executions/{execution_id}", response_model=ExecutionDetail)
def get_execution(execution_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ExecutionDetail:
    return AutomationService(session).get_execution(principal, execution_id)


@router.post("/executions/{execution_id}/retry", response_model=ExecutionDetail)
def retry_execution(execution_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ExecutionDetail:
    svc = AutomationService(session)
    svc.retry(principal, execution_id)
    return svc.get_execution(principal, execution_id)


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionDetail)
def cancel_execution(execution_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ExecutionDetail:
    svc = AutomationService(session)
    svc.cancel(principal, execution_id)
    return svc.get_execution(principal, execution_id)
