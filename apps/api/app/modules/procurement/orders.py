"""Purchase orders (Phase 4).

Budget rule (deliberate deviation from the roadmap, approved before Phase 4): the budget commitment is
written once, at the purchase request's final approval (ledger key ``purchase_request:<id>:commitment``).
Purchase orders never commit budget. Lifecycle: draft → issued → cancelled.

- At most one active (draft / issued) order per request — partial unique index + check under lock.
- Lines and prices are copied from the request's selected quotation, so an order's total always equals
  the committed amount; only delivery details are editable.
- Cancelling offers two outcomes:
  * ``release_budget=True``: writes the request's single release entry (ledger key
    ``purchase_request:<id>:release`` — idempotent) and closes the request; refused while another
    active order still needs the commitment.
  * ``release_budget=False``: keeps the commitment so a replacement order can be created
    (``replaces_order_id`` links it to the cancelled one).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automation import events
from app.common.codes import next_code
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.common.money import line_total, total
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, PermissionDenied
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.finance.models import BudgetLedgerEntry
from app.modules.finance.service import FinanceService
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.notifications.service import NotificationService
from app.modules.procurement.models import PurchaseOrder, PurchaseOrderLine, PurchaseRequest
from app.modules.procurement.schemas import (
    OrderCancelIn,
    OrderCreateIn,
    OrderDetail,
    OrderLineOut,
    OrderOut,
    OrderRef,
    OrderSummary,
    OrderUpdateIn,
    SupplierRef,
)

ENTITY = "purchase_order"
REQUEST_ENTITY = "purchase_request"
ACTIVE = ("draft", "issued")
SORTABLE = {"created_at": PurchaseOrder.created_at, "code": PurchaseOrder.code, "total_amount": PurchaseOrder.total_amount}


def _now() -> datetime:
    return datetime.now(UTC)


def commitment_key(request_id: uuid.UUID) -> str:
    return f"{REQUEST_ENTITY}:{request_id}:commitment"


def release_key(request_id: uuid.UUID) -> str:
    return f"{REQUEST_ENTITY}:{request_id}:release"


class OrderService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)
        self.finance = FinanceService(session)
        self.notifications = NotificationService(session)

    # ------------------------------------------------------------------ visibility
    def _sees_all(self, principal: Principal) -> bool:
        return principal.has_any((Perm.PROCUREMENT_ORDERS_MANAGE, Perm.PROCUREMENT_REQUESTS_READ_ALL, Perm.APPROVALS_READ_ALL))

    def _can_view(self, principal: Principal, order: PurchaseOrder) -> bool:
        if self._sees_all(principal):
            return True
        from app.modules.procurement.service import ProcurementService

        return ProcurementService(self.session).can_view(principal, order.request)

    def _get(self, principal: Principal, order_id: uuid.UUID, *, lock: bool = False) -> PurchaseOrder:
        stmt = select(PurchaseOrder).where(PurchaseOrder.id == order_id)
        if lock:
            stmt = stmt.with_for_update(of=PurchaseOrder).execution_options(populate_existing=True)
        order = self.session.scalar(stmt)
        if order is None or not self._can_view(principal, order):
            raise NotFound("Purchase order not found.")
        return order

    def _lock_request(self, request_id: uuid.UUID) -> PurchaseRequest:
        pr = self.session.scalar(
            select(PurchaseRequest)
            .where(PurchaseRequest.id == request_id)
            .with_for_update(of=PurchaseRequest)
            .execution_options(populate_existing=True)
        )
        if pr is None:
            raise NotFound("Purchase request not found.")
        return pr

    def _active_orders(self, request_id: uuid.UUID, *, excluding: uuid.UUID | None = None) -> list[PurchaseOrder]:
        stmt = select(PurchaseOrder).where(PurchaseOrder.request_id == request_id, PurchaseOrder.status.in_(ACTIVE))
        if excluding is not None:
            stmt = stmt.where(PurchaseOrder.id != excluding)
        return list(self.session.scalars(stmt).unique())

    def _ledger(self, key: str) -> BudgetLedgerEntry | None:
        return self.session.scalar(select(BudgetLedgerEntry).where(BudgetLedgerEntry.idempotency_key == key))

    # ------------------------------------------------------------------ create / update / issue
    def create(self, principal: Principal, request_id: uuid.UUID, data: OrderCreateIn) -> PurchaseOrder:
        ensure_permission(principal, Perm.PROCUREMENT_ORDERS_MANAGE)
        pr = self._lock_request(request_id)
        if pr.status != "approved":
            raise Conflict("Purchase orders can only be created for fully approved requests.", code="request_not_approved")
        quote = next((q for q in pr.quotations if q.id == pr.selected_quotation_id), None)
        if quote is None or pr.budget_id is None:
            raise BusinessRuleViolation("The request has no selected quotation or budget.", code="request_incomplete")
        commitment = self._ledger(commitment_key(pr.id))
        if commitment is None:
            raise BusinessRuleViolation(
                "The request's budget commitment is missing; the order can't be created.", code="commitment_missing"
            )
        if self._active_orders(pr.id):
            raise Conflict("This request already has an active purchase order. Cancel it first to replace it.", code="active_order_exists")
        previous = self.session.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.request_id == pr.id, PurchaseOrder.status == "cancelled")
            .order_by(PurchaseOrder.cancelled_at.desc())
            .limit(1)
        )
        prices = {qi.request_item_id: qi.unit_price for qi in quote.items}
        order = PurchaseOrder(
            code=next_code(self.session, "purchase_order"),
            request_id=pr.id,
            quotation_id=quote.id,
            supplier_id=quote.supplier_id,
            budget_id=pr.budget_id,
            replaces_order_id=previous.id if previous else None,
            payment_terms=quote.payment_terms,
            expected_delivery_date=data.expected_delivery_date,
            delivery_address=data.delivery_address,
            notes=data.notes,
            created_by=principal.user_id,
            total_amount=Decimal("0"),
        )
        for item in pr.items:
            price = prices[item.id]
            order.lines.append(
                PurchaseOrderLine(
                    request_item_id=item.id,
                    line_no=item.line_no,
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    unit_price=price,
                    line_total=line_total(item.quantity, price),
                )
            )
        order.total_amount = total(line.line_total for line in order.lines)
        if order.total_amount != commitment.amount:
            raise BusinessRuleViolation("The quotation total no longer matches the committed amount.", code="amount_mismatch")
        self.session.add(order)
        try:
            self.session.flush()
        except IntegrityError as exc:  # concurrent creation lost the race on the partial unique index
            self.session.rollback()
            raise Conflict("This request already has an active purchase order.", code="active_order_exists") from exc
        self._record(
            order,
            principal,
            "created",
            f"{order.code} drafted for {quote.supplier.name} · SAR {order.total_amount:,.2f}"
            + (f" (replaces {previous.code})" if previous else ""),
        )
        self.session.commit()
        return order

    def update(self, principal: Principal, order_id: uuid.UUID, data: OrderUpdateIn) -> PurchaseOrder:
        ensure_permission(principal, Perm.PROCUREMENT_ORDERS_MANAGE)
        order = self._get(principal, order_id, lock=True)
        if order.status != "draft":
            raise Conflict("Only draft purchase orders can be edited.", code="invalid_state")
        changes: dict[str, object] = {}
        for name in data.model_fields_set:
            value = getattr(data, name)
            if value != getattr(order, name):
                changes[name] = [
                    str(getattr(order, name)) if getattr(order, name) is not None else None,
                    str(value) if value is not None else None,
                ]
                setattr(order, name, value)
        self.audit.record(
            "purchase_order.updated",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=order.id,
            summary=f"{order.code} delivery details updated",
            changes=changes or None,
        )
        self.session.commit()
        return order

    def issue(self, principal: Principal, order_id: uuid.UUID) -> PurchaseOrder:
        ensure_permission(principal, Perm.PROCUREMENT_ORDERS_MANAGE)
        order = self._get(principal, order_id, lock=True)
        if order.status != "draft":
            raise Conflict("Only draft purchase orders can be issued.", code="invalid_state")
        pr = self._lock_request(order.request_id)
        if pr.status != "approved":
            raise Conflict("The purchase request is no longer approved.", code="request_not_approved")
        order.status, order.issued_at, order.issued_by = "issued", _now(), principal.user_id
        self._record(order, principal, "issued", f"{order.code} issued to {order.supplier.name} · SAR {order.total_amount:,.2f}")
        self.notifications.notify(
            pr.requester_user_id,
            type="procurement.order_issued",
            level="success",
            title=f"{order.code} issued for {pr.code}",
            body=f"{order.supplier.name} · SAR {order.total_amount:,.2f}",
            link=f"/procurement/orders/{order.id}",
            entity_type=ENTITY,
            entity_id=str(order.id),
            dedupe_key=f"po:{order.id}:issued",
        )
        self.session.commit()
        return order

    # ------------------------------------------------------------------ cancel (+ single release)
    def cancel(self, principal: Principal, order_id: uuid.UUID, data: OrderCancelIn) -> PurchaseOrder:
        ensure_permission(principal, Perm.PROCUREMENT_ORDERS_MANAGE)
        order = self._get(principal, order_id, lock=True)
        if order.status not in ACTIVE:
            raise Conflict("This purchase order is already cancelled.", code="already_cancelled")
        pr = self._lock_request(order.request_id)
        before = order.status
        order.status, order.cancelled_at, order.cancelled_by, order.cancel_reason = (
            "cancelled",
            _now(),
            principal.user_id,
            data.reason.strip(),
        )
        released: BudgetLedgerEntry | None = None
        if data.release_budget:
            released = self._release_commitment(pr, excluding_order=order.id, actor=principal, reason=order.cancel_reason or "")
            order.budget_released = True
        self.session.flush()
        outcome = (
            f"budget released (SAR {-released.amount:,.2f}) and {pr.code} closed"
            if released is not None
            else "commitment kept for a replacement order"
        )
        self._record(
            order,
            principal,
            "cancelled",
            f"{order.code} cancelled ({before}): {order.cancel_reason} — {outcome}",
            changes={"status": [before, "cancelled"], "release_budget": data.release_budget},
        )
        self.notifications.notify(
            pr.requester_user_id,
            type="procurement.order_cancelled",
            level="warning",
            title=f"{order.code} was cancelled",
            body=f"{order.cancel_reason} — {outcome}.",
            link=f"/procurement/requests/{pr.id}",
            entity_type=REQUEST_ENTITY,
            entity_id=str(pr.id),
            dedupe_key=f"po:{order.id}:cancelled",
        )
        self.session.commit()
        return order

    def _release_commitment(
        self, pr: PurchaseRequest, *, excluding_order: uuid.UUID | None, actor: Principal, reason: str
    ) -> BudgetLedgerEntry:
        """Releases the request's commitment exactly once. Caller holds the request row lock."""
        if self._active_orders(pr.id, excluding=excluding_order):
            raise BusinessRuleViolation(
                "Another active purchase order still needs this commitment; cancel it first.", code="commitment_in_use"
            )
        if pr.status != "approved":
            raise Conflict("The request's commitment was already released.", code="already_released")
        commitment = self._ledger(commitment_key(pr.id))
        if commitment is None:
            raise BusinessRuleViolation("The request has no budget commitment to release.", code="commitment_missing")
        if self._ledger(release_key(pr.id)) is not None:
            raise Conflict("The request's commitment was already released.", code="already_released")
        entry = self.finance.release(
            budget_id=commitment.budget_id,
            amount=commitment.amount,
            source_type=REQUEST_ENTITY,
            source_id=pr.id,
            source_code=pr.code,
            actor_user_id=actor.user_id,
            description=f"{pr.code} · order cancelled: {reason}"[:300],
        )
        pr.status = "closed"
        self.audit.record(
            "purchase_request.closed",
            actor_user_id=actor.user_id,
            entity_type=REQUEST_ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} closed · SAR {commitment.amount:,.2f} released",
            changes={"ledger_entry_id": str(entry.id)},
        )
        events.emit(
            self.session,
            "purchase_request.closed",
            entity_type=REQUEST_ENTITY,
            entity_id=pr.id,
            actor_user_id=actor.user_id,
            payload={"code": pr.code, "status": pr.status, "released": str(commitment.amount), "budget_id": str(commitment.budget_id)},
        )
        return entry

    def _record(self, order: PurchaseOrder, principal: Principal, verb: str, summary: str, changes: dict | None = None) -> None:
        self.audit.record(
            f"purchase_order.{verb}",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=order.id,
            summary=summary,
            changes=changes,
        )
        # Mirror on the request so its activity timeline shows the ordering history.
        self.audit.record(
            f"purchase_request.order_{verb}",
            actor_user_id=principal.user_id,
            entity_type=REQUEST_ENTITY,
            entity_id=order.request_id,
            summary=summary,
        )
        events.emit(
            self.session,
            f"purchase_order.{verb}",
            entity_type=ENTITY,
            entity_id=order.id,
            actor_user_id=principal.user_id,
            payload={"code": order.code, "request_id": str(order.request_id), "status": order.status, "amount": str(order.total_amount)},
        )

    # ------------------------------------------------------------------ reading
    def list(
        self, principal: Principal, params: ListParams, *, status: str | None, request_id: uuid.UUID | None
    ) -> tuple[list[OrderOut], int, int]:
        if not principal.has_any(
            (Perm.PROCUREMENT_ORDERS_MANAGE, Perm.PROCUREMENT_REQUESTS_READ_ALL, Perm.APPROVALS_READ_ALL, Perm.PROCUREMENT_REQUESTS_CREATE)
        ):
            raise PermissionDenied(details={"required_permission": Perm.PROCUREMENT_ORDERS_MANAGE.value})
        stmt = select(PurchaseOrder).join(PurchaseRequest, PurchaseRequest.id == PurchaseOrder.request_id)
        if not self._sees_all(principal):
            from app.modules.procurement.service import ProcurementService

            managed = ProcurementService(self.session)._managed_department_ids(principal)
            stmt = stmt.where(or_(PurchaseRequest.requester_user_id == principal.user_id, PurchaseRequest.department_id.in_(managed)))
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)
        if request_id:
            stmt = stmt.where(PurchaseOrder.request_id == request_id)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    PurchaseOrder.code.ilike(term, escape="\\"),
                    PurchaseRequest.code.ilike(term, escape="\\"),
                    PurchaseRequest.title.ilike(term, escape="\\"),
                )
            )
        rows, total_, pages = paginate(self.session, apply_sort(stmt, params.sort, SORTABLE, "-created_at"), params)
        return [self._out(o) for o in rows], total_, pages

    def detail(self, principal: Principal, order_id: uuid.UUID) -> OrderDetail:
        order = self._get(principal, order_id)
        replaced_by = self.session.scalar(select(PurchaseOrder).where(PurchaseOrder.replaces_order_id == order.id))
        replaces = self.session.get(PurchaseOrder, order.replaces_order_id) if order.replaces_order_id else None
        names = {
            u.id: u.full_name
            for u in self.session.scalars(
                select(User).where(User.id.in_([i for i in (order.created_by, order.issued_by, order.cancelled_by) if i]))
            )
        }
        commitment = self._ledger(commitment_key(order.request_id))
        release = self._ledger(release_key(order.request_id))
        return OrderDetail(
            **self._out(order).model_dump(),
            payment_terms=order.payment_terms,
            delivery_address=order.delivery_address,
            notes=order.notes,
            lines=[OrderLineOut.model_validate(line) for line in order.lines],
            cancel_reason=order.cancel_reason,
            created_by=names.get(order.created_by),
            issued_by=names.get(order.issued_by),
            cancelled_by=names.get(order.cancelled_by),
            replaces=OrderRef(id=replaces.id, code=replaces.code) if replaces else None,
            replaced_by=OrderRef(id=replaced_by.id, code=replaced_by.code) if replaced_by else None,
            committed_amount=commitment.amount if commitment else None,
            released_amount=-release.amount if release else None,
            allowed_actions=self._allowed(principal, order),
        )

    def summaries_for_request(self, request_id: uuid.UUID) -> list[OrderSummary]:
        rows = self.session.scalars(select(PurchaseOrder).where(PurchaseOrder.request_id == request_id).order_by(PurchaseOrder.created_at))
        return [
            OrderSummary(
                id=o.id,
                code=o.code,
                status=o.status,
                total_amount=o.total_amount,
                issued_at=o.issued_at,
                budget_released=o.budget_released,
                supplier=o.supplier.name,
            )
            for o in rows.unique()
        ]

    def can_create(self, principal: Principal, pr: PurchaseRequest) -> bool:
        return pr.status == "approved" and principal.has(Perm.PROCUREMENT_ORDERS_MANAGE) and not self._active_orders(pr.id)

    def _allowed(self, principal: Principal, order: PurchaseOrder) -> list[str]:
        if not principal.has(Perm.PROCUREMENT_ORDERS_MANAGE):
            return []
        return {"draft": ["edit", "issue", "cancel"], "issued": ["cancel"]}.get(order.status, [])

    def _out(self, o: PurchaseOrder) -> OrderOut:
        pr = o.request
        return OrderOut(
            id=o.id,
            code=o.code,
            status=o.status,
            total_amount=o.total_amount,
            supplier=SupplierRef.model_validate(o.supplier),
            request_id=pr.id,
            request_code=pr.code,
            request_title=pr.title,
            request_status=pr.status,
            expected_delivery_date=o.expected_delivery_date,
            issued_at=o.issued_at,
            cancelled_at=o.cancelled_at,
            budget_released=o.budget_released,
            created_at=o.created_at,
        )
