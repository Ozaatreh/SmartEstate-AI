from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.approvals.schemas import ApprovalDetail, ApprovalOut, DecisionIn, PendingCount, PolicyOut, RejectIn
from app.modules.approvals.service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalOut])
def list_approvals(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    box: Literal["pending", "decided", "mine", "all"] = "pending",
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
) -> Page[ApprovalOut]:
    items, total, pages = ApprovalService(session).list(principal, params, box=box, status=status)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/pending-count", response_model=PendingCount)
def pending_count(principal: CurrentPrincipal, session: SessionDep) -> PendingCount:
    return PendingCount(pending=ApprovalService(session).pending_count(principal))


@router.get("/policies", response_model=list[PolicyOut])
def policies(principal: CurrentPrincipal, session: SessionDep, entity_type: str = "purchase_request") -> list[PolicyOut]:
    return ApprovalService(session).policies(entity_type)


@router.get("/{approval_id}", response_model=ApprovalDetail)
def get_approval(approval_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ApprovalDetail:
    return ApprovalService(session).get(principal, approval_id)


@router.post("/{approval_id}/approve", response_model=ApprovalDetail)
def approve(approval_id: uuid.UUID, body: DecisionIn, principal: CurrentPrincipal, session: SessionDep) -> ApprovalDetail:
    svc = ApprovalService(session)
    svc.approve(principal, approval_id, body.comment)
    return svc.get(principal, approval_id)


@router.post("/{approval_id}/reject", response_model=ApprovalDetail)
def reject(approval_id: uuid.UUID, body: RejectIn, principal: CurrentPrincipal, session: SessionDep) -> ApprovalDetail:
    svc = ApprovalService(session)
    svc.reject(principal, approval_id, body.comment)
    return svc.get(principal, approval_id)
