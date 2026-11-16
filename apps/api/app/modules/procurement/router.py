from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.audit.router import AuditLogOut
from app.modules.audit.service import AuditService
from app.modules.procurement.orders import OrderService
from app.modules.procurement.schemas import (
    BudgetImpact,
    BudgetPreviewIn,
    CancelIn,
    OrderCancelIn,
    OrderCreateIn,
    OrderDetail,
    OrderOut,
    OrderUpdateIn,
    QuotationIn,
    RequestCreate,
    RequestDetail,
    RequestOut,
    RequestStats,
    RequestUpdate,
    SupplierIn,
    SupplierOut,
    SupplierUpdate,
)
from app.modules.procurement.service import ENTITY, ProcurementService

router = APIRouter(prefix="/procurement", tags=["procurement"])
Scope = Literal["mine", "department", "all"]


# --- suppliers ------------------------------------------------------------------------------------
@router.get("/suppliers", response_model=Page[SupplierOut])
def list_suppliers(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    status: Literal["active", "inactive", "blocked"] | None = None,
    category: str | None = None,
) -> Page[SupplierOut]:
    items, total, pages = ProcurementService(session).list_suppliers(principal, params, status=status, category=category)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/suppliers/categories", response_model=list[str])
def supplier_categories(principal: CurrentPrincipal, session: SessionDep) -> list[str]:
    return ProcurementService(session).supplier_categories(principal)


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierIn, principal: CurrentPrincipal, session: SessionDep) -> SupplierOut:
    svc = ProcurementService(session)
    return svc.get_supplier(principal, svc.create_supplier(principal, body).id)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> SupplierOut:
    return ProcurementService(session).get_supplier(principal, supplier_id)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: uuid.UUID, body: SupplierUpdate, principal: CurrentPrincipal, session: SessionDep) -> SupplierOut:
    svc = ProcurementService(session)
    svc.update_supplier(principal, supplier_id, body)
    return svc.get_supplier(principal, supplier_id)


# --- purchase requests -------------------------------------------------------------------------------
@router.get("/requests", response_model=Page[RequestOut])
def list_requests(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    scope: Scope = "mine",
    status: Literal["draft", "sourcing", "pending_approval", "approved", "rejected", "cancelled", "closed"] | None = None,
    department_id: uuid.UUID | None = None,
) -> Page[RequestOut]:
    items, total, pages = ProcurementService(session).list_requests(
        principal, params, scope=scope, status=status, department_id=department_id
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/requests/stats", response_model=RequestStats)
def request_stats(principal: CurrentPrincipal, session: SessionDep, scope: Scope = "mine") -> RequestStats:
    return ProcurementService(session).stats(principal, scope=scope)


@router.post("/requests/budget-preview", response_model=BudgetImpact)
def budget_preview(body: BudgetPreviewIn, principal: CurrentPrincipal, session: SessionDep) -> BudgetImpact:
    return ProcurementService(session).preview(principal, body)


@router.post("/requests", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def create_request(body: RequestCreate, principal: CurrentPrincipal, session: SessionDep) -> RequestDetail:
    svc = ProcurementService(session)
    return svc.detail(principal, svc.create_request(principal, body).id)


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(request_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> RequestDetail:
    return ProcurementService(session).detail(principal, request_id)


@router.patch("/requests/{request_id}", response_model=RequestDetail)
def update_request(request_id: uuid.UUID, body: RequestUpdate, principal: CurrentPrincipal, session: SessionDep) -> RequestDetail:
    svc = ProcurementService(session)
    svc.update_request(principal, request_id, body)
    return svc.detail(principal, request_id)


@router.get("/requests/{request_id}/activity", response_model=list[AuditLogOut])
def request_activity(request_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> list[AuditLogOut]:
    ProcurementService(session).detail(principal, request_id)  # visibility check
    return [AuditLogOut.of(r) for r in AuditService(session).for_entity(ENTITY, request_id)]


def _action(name: str):
    def endpoint(request_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> RequestDetail:
        svc = ProcurementService(session)
        getattr(svc, name)(principal, request_id)
        return svc.detail(principal, request_id)

    endpoint.__name__ = name
    return endpoint


router.add_api_route("/requests/{request_id}/submit", _action("submit"), methods=["POST"], response_model=RequestDetail)
router.add_api_route(
    "/requests/{request_id}/send-for-approval", _action("send_for_approval"), methods=["POST"], response_model=RequestDetail
)


@router.post("/requests/{request_id}/cancel", response_model=RequestDetail)
def cancel_request(request_id: uuid.UUID, body: CancelIn, principal: CurrentPrincipal, session: SessionDep) -> RequestDetail:
    svc = ProcurementService(session)
    svc.cancel(principal, request_id, body)
    return svc.detail(principal, request_id)


@router.post("/requests/{request_id}/quotations", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def add_quotation(request_id: uuid.UUID, body: QuotationIn, principal: CurrentPrincipal, session: SessionDep) -> RequestDetail:
    svc = ProcurementService(session)
    svc.add_quotation(principal, request_id, body)
    return svc.detail(principal, request_id)


@router.put("/requests/{request_id}/quotations/{quotation_id}", response_model=RequestDetail)
def update_quotation(
    request_id: uuid.UUID, quotation_id: uuid.UUID, body: QuotationIn, principal: CurrentPrincipal, session: SessionDep
) -> RequestDetail:
    svc = ProcurementService(session)
    svc.update_quotation(principal, request_id, quotation_id, body)
    return svc.detail(principal, request_id)


@router.delete("/requests/{request_id}/quotations/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quotation(request_id: uuid.UUID, quotation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> Response:
    ProcurementService(session).delete_quotation(principal, request_id, quotation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/requests/{request_id}/quotations/{quotation_id}/select", response_model=RequestDetail)
def select_quotation(request_id: uuid.UUID, quotation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> RequestDetail:
    svc = ProcurementService(session)
    svc.select_quotation(principal, request_id, quotation_id)
    return svc.detail(principal, request_id)


# --- purchase orders (Phase 4) ---------------------------------------------------------------------
@router.post("/requests/{request_id}/purchase-orders", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
def create_order(request_id: uuid.UUID, body: OrderCreateIn, principal: CurrentPrincipal, session: SessionDep) -> OrderDetail:
    svc = OrderService(session)
    order = svc.create(principal, request_id, body)
    return svc.detail(principal, order.id)


@router.get("/purchase-orders", response_model=Page[OrderOut])
def list_orders(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    status: Literal["draft", "issued", "cancelled"] | None = None,
    request_id: uuid.UUID | None = None,
) -> Page[OrderOut]:
    items, total, pages = OrderService(session).list(principal, params, status=status, request_id=request_id)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.get("/purchase-orders/{order_id}", response_model=OrderDetail)
def get_order(order_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> OrderDetail:
    return OrderService(session).detail(principal, order_id)


@router.patch("/purchase-orders/{order_id}", response_model=OrderDetail)
def update_order(order_id: uuid.UUID, body: OrderUpdateIn, principal: CurrentPrincipal, session: SessionDep) -> OrderDetail:
    svc = OrderService(session)
    svc.update(principal, order_id, body)
    return svc.detail(principal, order_id)


@router.post("/purchase-orders/{order_id}/issue", response_model=OrderDetail)
def issue_order(order_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> OrderDetail:
    svc = OrderService(session)
    svc.issue(principal, order_id)
    return svc.detail(principal, order_id)


@router.post("/purchase-orders/{order_id}/cancel", response_model=OrderDetail)
def cancel_order(order_id: uuid.UUID, body: OrderCancelIn, principal: CurrentPrincipal, session: SessionDep) -> OrderDetail:
    svc = OrderService(session)
    svc.cancel(principal, order_id, body)
    return svc.detail(principal, order_id)
