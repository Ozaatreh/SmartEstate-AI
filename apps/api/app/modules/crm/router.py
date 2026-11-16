from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.crm.service import CRMService, LeadCreate, LeadOut, lead_out

router = APIRouter(prefix="/crm", tags=["crm"])


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(body: LeadCreate, principal: CurrentPrincipal, session: SessionDep) -> LeadOut:
    return lead_out(CRMService(session).create_lead(principal, body))


@router.get("/leads", response_model=Page[LeadOut])
def list_leads(
    principal: CurrentPrincipal, session: SessionDep, params: ListParams = Depends(list_params), scope: Literal["mine", "all"] = "mine"
) -> Page[LeadOut]:
    rows, total, pages = CRMService(session).list(principal, params, scope=scope)
    return Page(items=[lead_out(r) for r in rows], total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> LeadOut:
    return lead_out(CRMService(session).get(principal, lead_id))
