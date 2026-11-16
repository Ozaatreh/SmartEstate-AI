from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.realestate.schemas import (
    Availability,
    BuildingIn,
    BuildingOut,
    BuildingUpdate,
    PaymentPlanIn,
    PaymentPlanOut,
    PaymentPlanUpdate,
    ProjectDetail,
    ProjectIn,
    ProjectOut,
    ProjectUpdate,
    UnitDetail,
    UnitIn,
    UnitOut,
    UnitUpdate,
)
from app.modules.realestate.service import RealEstateService

router = APIRouter(prefix="/realestate", tags=["realestate"])


# --- projects -------------------------------------------------------------------------------------
@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    status: Literal["planning", "launched", "under_construction", "completed"] | None = None,
) -> Page[ProjectOut]:
    items, total, pages = RealEstateService(session).list_projects(principal, params, status=status)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.post("/projects", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, principal: CurrentPrincipal, session: SessionDep) -> ProjectDetail:
    svc = RealEstateService(session)
    return svc.project_detail(principal, svc.create_project(principal, body).id)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ProjectDetail:
    return RealEstateService(session).project_detail(principal, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectDetail)
def update_project(project_id: uuid.UUID, body: ProjectUpdate, principal: CurrentPrincipal, session: SessionDep) -> ProjectDetail:
    svc = RealEstateService(session)
    svc.update_project(principal, project_id, body)
    return svc.project_detail(principal, project_id)


@router.get("/projects/{project_id}/availability", response_model=Availability)
def availability(project_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> Availability:
    return RealEstateService(session).availability(principal, project_id)


# --- buildings ------------------------------------------------------------------------------------
@router.post("/projects/{project_id}/buildings", response_model=BuildingOut, status_code=status.HTTP_201_CREATED)
def create_building(project_id: uuid.UUID, body: BuildingIn, principal: CurrentPrincipal, session: SessionDep) -> BuildingOut:
    return BuildingOut.model_validate(RealEstateService(session).create_building(principal, project_id, body))


@router.patch("/buildings/{building_id}", response_model=BuildingOut)
def update_building(building_id: uuid.UUID, body: BuildingUpdate, principal: CurrentPrincipal, session: SessionDep) -> BuildingOut:
    return BuildingOut.model_validate(RealEstateService(session).update_building(principal, building_id, body))


@router.delete("/buildings/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_building(building_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> Response:
    RealEstateService(session).delete_building(principal, building_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- payment plans --------------------------------------------------------------------------------
@router.post("/projects/{project_id}/payment-plans", response_model=PaymentPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(project_id: uuid.UUID, body: PaymentPlanIn, principal: CurrentPrincipal, session: SessionDep) -> PaymentPlanOut:
    return PaymentPlanOut.model_validate(RealEstateService(session).create_plan(principal, project_id, body))


@router.patch("/payment-plans/{plan_id}", response_model=PaymentPlanOut)
def update_plan(plan_id: uuid.UUID, body: PaymentPlanUpdate, principal: CurrentPrincipal, session: SessionDep) -> PaymentPlanOut:
    return PaymentPlanOut.model_validate(RealEstateService(session).update_plan(principal, plan_id, body))


# --- units ----------------------------------------------------------------------------------------
@router.get("/units", response_model=Page[UnitOut])
def list_units(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    project_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    status: Literal["available", "reserved", "sold", "blocked"] | None = None,
    unit_type: Literal["studio", "apartment", "duplex", "penthouse", "townhouse"] | None = None,
    bedrooms: int | None = Query(default=None, ge=0, le=20),
    min_bedrooms: int | None = Query(default=None, ge=0, le=20),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
) -> Page[UnitOut]:
    items, total, pages = RealEstateService(session).list_units(
        principal,
        params,
        project_id=project_id,
        building_id=building_id,
        status=status,
        unit_type=unit_type,
        bedrooms=bedrooms,
        min_bedrooms=min_bedrooms,
        price_min=price_min,
        price_max=price_max,
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.post("/units", response_model=UnitDetail, status_code=status.HTTP_201_CREATED)
def create_unit(body: UnitIn, principal: CurrentPrincipal, session: SessionDep) -> UnitDetail:
    svc = RealEstateService(session)
    return svc.unit_detail(principal, svc.create_unit(principal, body).id)


@router.get("/units/{unit_id}", response_model=UnitDetail)
def get_unit(unit_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> UnitDetail:
    return RealEstateService(session).unit_detail(principal, unit_id)


@router.patch("/units/{unit_id}", response_model=UnitDetail)
def update_unit(unit_id: uuid.UUID, body: UnitUpdate, principal: CurrentPrincipal, session: SessionDep) -> UnitDetail:
    svc = RealEstateService(session)
    svc.update_unit(principal, unit_id, body)
    return svc.unit_detail(principal, unit_id)


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(unit_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> Response:
    RealEstateService(session).delete_unit(principal, unit_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
