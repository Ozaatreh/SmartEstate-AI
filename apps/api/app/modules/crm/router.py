from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request, status

from app.ai.router import get_gateway
from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.crm.lead_summary import LeadSummaryOut, LeadSummaryService
from app.modules.crm.reservations import ReservationService
from app.modules.crm.schemas import (
    ActivityIn,
    ActivityOut,
    AssignIn,
    LeadCreate,
    LeadDetail,
    LeadOut,
    LeadStats,
    LeadUpdate,
    ReservationCancelIn,
    ReservationIn,
    ReservationOut,
    StageChangeIn,
    UnitReservationInfo,
)
from app.modules.crm.service import CRMService, lead_out

router = APIRouter(prefix="/crm", tags=["crm"])
StageFilter = Literal["new", "contacted", "qualified", "viewing", "negotiation", "won", "lost", "open"]


# --- leads ----------------------------------------------------------------------------------------
@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(body: LeadCreate, principal: CurrentPrincipal, session: SessionDep) -> LeadOut:
    return lead_out(CRMService(session).create_lead(principal, body))


@router.get("/leads", response_model=Page[LeadOut])
def list_leads(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    scope: Literal["mine", "all"] = "mine",
    stage: StageFilter | None = None,
    owner_user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    overdue: bool | None = None,
    grade: Literal["hot", "warm", "cold"] | None = None,
) -> Page[LeadOut]:
    rows, total, pages = CRMService(session).list(
        principal, params, scope=scope, stage=stage, owner_user_id=owner_user_id, project_id=project_id, overdue=overdue, grade=grade
    )
    return Page(items=[lead_out(r) for r in rows], total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/leads/stats", response_model=LeadStats)
def lead_stats(principal: CurrentPrincipal, session: SessionDep, scope: Literal["mine", "all"] = "mine") -> LeadStats:
    return CRMService(session).stats(principal, scope=scope)


@router.get("/leads/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> LeadDetail:
    return CRMService(session).detail(principal, lead_id)


@router.patch("/leads/{lead_id}", response_model=LeadDetail)
def update_lead(lead_id: uuid.UUID, body: LeadUpdate, principal: CurrentPrincipal, session: SessionDep) -> LeadDetail:
    svc = CRMService(session)
    svc.update(principal, lead_id, body)
    return svc.detail(principal, lead_id)


@router.post("/leads/{lead_id}/stage", response_model=LeadDetail)
def change_stage(lead_id: uuid.UUID, body: StageChangeIn, principal: CurrentPrincipal, session: SessionDep) -> LeadDetail:
    svc = CRMService(session)
    svc.change_stage(principal, lead_id, body)
    return svc.detail(principal, lead_id)


@router.post("/leads/{lead_id}/assign", response_model=LeadDetail)
def reassign_lead(lead_id: uuid.UUID, body: AssignIn, principal: CurrentPrincipal, session: SessionDep) -> LeadDetail:
    svc = CRMService(session)
    svc.reassign(principal, lead_id, body)
    return svc.detail(principal, lead_id)


@router.get("/leads/{lead_id}/activities", response_model=list[ActivityOut])
def lead_timeline(lead_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> list[ActivityOut]:
    return CRMService(session).timeline(principal, lead_id)


@router.post("/leads/{lead_id}/activities", response_model=list[ActivityOut], status_code=status.HTTP_201_CREATED)
def add_activity(lead_id: uuid.UUID, body: ActivityIn, principal: CurrentPrincipal, session: SessionDep) -> list[ActivityOut]:
    svc = CRMService(session)
    svc.add_activity(principal, lead_id, body)
    return svc.timeline(principal, lead_id)


@router.post("/leads/{lead_id}/ai-summary", response_model=LeadSummaryOut)
def lead_ai_summary(lead_id: uuid.UUID, request: Request, principal: CurrentPrincipal, session: SessionDep) -> LeadSummaryOut:
    """Advisory AI briefing for one lead (generated on demand, not stored). Owner with crm.leads.work or crm.leads.manage.
    503 with an ``ai_*`` code when AI is unavailable; the rest of the CRM is unaffected."""
    return LeadSummaryService(session, get_gateway(request)).generate(principal, lead_id)


@router.get("/sales-users", response_model=list[dict])
def sales_users(principal: CurrentPrincipal, session: SessionDep) -> list[dict]:
    """Possible owners for reassignment (managers only)."""
    return ReservationService(session).sales_users(principal)


# --- reservations ---------------------------------------------------------------------------------
@router.post("/reservations", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(body: ReservationIn, principal: CurrentPrincipal, session: SessionDep) -> ReservationOut:
    svc = ReservationService(session)
    return svc.detail(principal, svc.create(principal, body).id)


@router.get("/reservations", response_model=Page[ReservationOut])
def list_reservations(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    scope: Literal["mine", "all"] = "mine",
    status: Literal["active", "expired", "cancelled", "converted"] | None = None,
    lead_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
) -> Page[ReservationOut]:
    items, total, pages = ReservationService(session).list(principal, params, scope=scope, status=status, lead_id=lead_id, unit_id=unit_id)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/reservations/{reservation_id}", response_model=ReservationOut)
def get_reservation(reservation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ReservationOut:
    return ReservationService(session).detail(principal, reservation_id)


@router.post("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_reservation(
    reservation_id: uuid.UUID, body: ReservationCancelIn, principal: CurrentPrincipal, session: SessionDep
) -> ReservationOut:
    svc = ReservationService(session)
    svc.cancel(principal, reservation_id, body.reason)
    return svc.detail(principal, reservation_id)


@router.post("/reservations/{reservation_id}/convert", response_model=ReservationOut)
def convert_reservation(reservation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ReservationOut:
    svc = ReservationService(session)
    svc.convert(principal, reservation_id)
    return svc.detail(principal, reservation_id)


@router.get("/units/{unit_id}/reservation", response_model=UnitReservationInfo | None)
def unit_reservation(unit_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> UnitReservationInfo | None:
    return ReservationService(session).for_unit(principal, unit_id)
