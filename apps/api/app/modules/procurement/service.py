"""Procurement: suppliers, purchase requests, quotations — and the purchase-request lifecycle.

    draft ──submit──▶ sourcing ──send for approval──▶ pending_approval ──▶ approved (budget committed)
      │                  │                                         └────▶ rejected
      └──cancel──────────┴──cancel──▶ cancelled

Every state change runs in one transaction with an audit entry. The budget commitment for an approved
request is written by the approval decision transaction (idempotent, budget row locked).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automation import events
from app.common.codes import next_code
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.common.money import ZERO, line_total, q2, total
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, PermissionDenied
from app.core.permissions import Perm
from app.modules.approvals.models import ApprovalRequest
from app.modules.approvals.schemas import PersonRef
from app.modules.approvals.service import LEVEL_LABEL, ApprovalService
from app.modules.approvals.subjects import register_subject
from app.modules.audit.service import AuditService
from app.modules.finance.models import BudgetCategory, OperationalProject
from app.modules.finance.schemas import CategoryOut, ProjectRef
from app.modules.finance.service import FinanceService
from app.modules.hr.models import Department, Employee
from app.modules.hr.schemas import DepartmentRef
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.notifications.service import NotificationService
from app.modules.procurement.models import PurchaseRequest, PurchaseRequestItem, QuotationItem, Supplier, SupplierQuotation
from app.modules.procurement.schemas import (
    BudgetImpact,
    BudgetPreviewIn,
    CancelIn,
    Comparison,
    ComparisonCell,
    ComparisonRow,
    ItemIn,
    ItemOut,
    QuotationIn,
    QuotationItemOut,
    QuotationOut,
    RequestCreate,
    RequestDetail,
    RequestOut,
    RequestStats,
    RequestUpdate,
    SupplierIn,
    SupplierOut,
    SupplierRef,
    SupplierUpdate,
)

ENTITY = "purchase_request"
SUPPLIER_SORT = {"name": Supplier.name, "code": Supplier.code, "category": Supplier.category, "rating": Supplier.rating}
REQUEST_SORT = {
    "created_at": PurchaseRequest.created_at,
    "code": PurchaseRequest.code,
    "estimated_total": PurchaseRequest.estimated_total,
    "needed_by": PurchaseRequest.needed_by,
    "title": PurchaseRequest.title,
}
OPEN_PROJECT_STATUSES = ("planned", "active")


def _now() -> datetime:
    return datetime.now(UTC)


class ProcurementService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)
        self.finance = FinanceService(session)
        self.approvals = ApprovalService(session)
        self.notifications = NotificationService(session)

    # =============================================================================== suppliers
    def list_suppliers(
        self, principal: Principal, params: ListParams, *, status: str | None, category: str | None
    ) -> tuple[list[SupplierOut], int, int]:
        ensure_permission(principal, Perm.PROCUREMENT_SUPPLIERS_READ)
        stmt = select(Supplier)
        if status:
            stmt = stmt.where(Supplier.status == status)
        if category:
            stmt = stmt.where(Supplier.category == category)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    Supplier.name.ilike(term, escape="\\"),
                    Supplier.code.ilike(term, escape="\\"),
                    Supplier.contact_name.ilike(term, escape="\\"),
                    Supplier.city.ilike(term, escape="\\"),
                )
            )
        stmt = apply_sort(stmt, params.sort, SUPPLIER_SORT, "name")
        rows, total_, pages = paginate(self.session, stmt, params)
        stats = self._supplier_stats([s.id for s in rows])
        return [self._supplier_out(s, *stats.get(s.id, (0, 0))) for s in rows], total_, pages

    def supplier_categories(self, principal: Principal) -> list[str]:
        ensure_permission(principal, Perm.PROCUREMENT_SUPPLIERS_READ)
        return list(self.session.scalars(select(Supplier.category).distinct().order_by(Supplier.category)))

    def get_supplier(self, principal: Principal, supplier_id: uuid.UUID) -> SupplierOut:
        ensure_permission(principal, Perm.PROCUREMENT_SUPPLIERS_READ)
        s = self.session.get(Supplier, supplier_id)
        if s is None:
            raise NotFound("Supplier not found.")
        return self._supplier_out(s, *self._supplier_stats([s.id]).get(s.id, (0, 0)))

    def create_supplier(self, principal: Principal, data: SupplierIn) -> Supplier:
        ensure_permission(principal, Perm.PROCUREMENT_SUPPLIERS_MANAGE)
        s = Supplier(
            code=next_code(self.session, "supplier"),
            **{**data.model_dump(), "name": data.name.strip(), "email": str(data.email) if data.email else None},
        )
        self.session.add(s)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict(
                "A supplier with this name already exists.",
                code="supplier_exists",
                details={"fields": [{"field": "name", "message": "Already exists."}]},
            ) from exc
        self.audit.record(
            "procurement.supplier_created",
            actor_user_id=principal.user_id,
            entity_type="supplier",
            entity_id=s.id,
            summary=f"{s.code} · {s.name}",
        )
        self.session.commit()
        return s

    def update_supplier(self, principal: Principal, supplier_id: uuid.UUID, data: SupplierUpdate) -> Supplier:
        ensure_permission(principal, Perm.PROCUREMENT_SUPPLIERS_MANAGE)
        s = self.session.get(Supplier, supplier_id)
        if s is None:
            raise NotFound("Supplier not found.")
        changes: dict[str, object] = {}
        for name in data.model_fields_set:
            value = getattr(data, name)
            if name in ("name", "category") and not value:
                continue
            if name == "email" and value is not None:
                value = str(value)
            if value != getattr(s, name):
                changes[name] = [str(getattr(s, name)) if getattr(s, name) is not None else None, str(value) if value is not None else None]
                setattr(s, name, value)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict("A supplier with this name already exists.", code="supplier_exists") from exc
        self.audit.record(
            "procurement.supplier_updated",
            actor_user_id=principal.user_id,
            entity_type="supplier",
            entity_id=s.id,
            summary=f"{s.code} · {s.name}",
            changes=changes or None,
        )
        self.session.commit()
        return s

    def _supplier_stats(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        if not ids:
            return {}
        rows = self.session.execute(
            select(SupplierQuotation.supplier_id, func.count(), func.count().filter(SupplierQuotation.status == "selected"))
            .where(SupplierQuotation.supplier_id.in_(ids))
            .group_by(SupplierQuotation.supplier_id)
        ).all()
        return {sid: (int(n), int(sel)) for sid, n, sel in rows}

    def _supplier_out(self, s: Supplier, quotes: int, selected: int) -> SupplierOut:
        return SupplierOut(
            id=s.id,
            code=s.code,
            name=s.name,
            category=s.category,
            contact_name=s.contact_name,
            email=s.email,
            phone=s.phone,
            vat_number=s.vat_number,
            city=s.city,
            rating=s.rating,
            status=s.status,
            notes=s.notes,
            quotation_count=quotes,
            selected_count=selected,
        )

    # ======================================================================= purchase requests: read
    def _employee(self, user_id: uuid.UUID) -> Employee | None:
        return self.session.scalar(select(Employee).where(Employee.user_id == user_id))

    def _managed_department_ids(self, principal: Principal) -> list[uuid.UUID]:
        emp = self._employee(principal.user_id)
        if emp is None:
            return []
        return list(self.session.scalars(select(Department.id).where(Department.manager_employee_id == emp.id)))

    def can_view(self, principal: Principal, pr: PurchaseRequest) -> bool:
        if pr.requester_user_id == principal.user_id or principal.has_any((Perm.PROCUREMENT_REQUESTS_READ_ALL, Perm.APPROVALS_READ_ALL)):
            return True
        if pr.department_id in self._managed_department_ids(principal):
            return True
        approval = self.approvals.latest_for_entity(ENTITY, pr.id)
        return approval is not None and self.approvals._can_view(principal, approval)

    def _get(self, principal: Principal, request_id: uuid.UUID, *, lock: bool = False) -> PurchaseRequest:
        stmt = select(PurchaseRequest).where(PurchaseRequest.id == request_id)
        if lock:
            stmt = stmt.with_for_update(of=PurchaseRequest).execution_options(populate_existing=True)
        pr = self.session.scalar(stmt)
        if pr is None or not self.can_view(principal, pr):
            raise NotFound("Purchase request not found.")
        return pr

    def list_requests(
        self, principal: Principal, params: ListParams, *, scope: str, status: str | None, department_id: uuid.UUID | None
    ) -> tuple[list[RequestOut], int, int]:
        stmt = select(PurchaseRequest).join(User, User.id == PurchaseRequest.requester_user_id)
        if scope == "all":
            if not principal.has_any((Perm.PROCUREMENT_REQUESTS_READ_ALL, Perm.APPROVALS_READ_ALL)):
                raise PermissionDenied(details={"required_permission": Perm.PROCUREMENT_REQUESTS_READ_ALL.value})
        elif scope == "department":
            stmt = stmt.where(PurchaseRequest.department_id.in_(self._managed_department_ids(principal)))
        else:
            stmt = stmt.where(PurchaseRequest.requester_user_id == principal.user_id)
        if status:
            stmt = stmt.where(PurchaseRequest.status == status)
        if department_id:
            stmt = stmt.where(PurchaseRequest.department_id == department_id)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    PurchaseRequest.code.ilike(term, escape="\\"),
                    PurchaseRequest.title.ilike(term, escape="\\"),
                    User.full_name.ilike(term, escape="\\"),
                )
            )
        stmt = apply_sort(stmt, params.sort, REQUEST_SORT, "-created_at")
        rows, total_, pages = paginate(self.session, stmt, params)
        waiting = self._waiting_on([r.id for r in rows if r.status == "pending_approval"])
        return [self._out(r, waiting.get(r.id)) for r in rows], total_, pages

    def stats(self, principal: Principal, *, scope: str) -> RequestStats:
        stmt = select(
            PurchaseRequest.status,
            func.count(),
            func.coalesce(
                func.sum(
                    case(
                        (PurchaseRequest.approved_total.is_not(None), PurchaseRequest.approved_total), else_=PurchaseRequest.estimated_total
                    )
                ),
                0,
            ),
        ).group_by(PurchaseRequest.status)
        if scope == "all":
            if not principal.has_any((Perm.PROCUREMENT_REQUESTS_READ_ALL, Perm.APPROVALS_READ_ALL)):
                raise PermissionDenied(details={"required_permission": Perm.PROCUREMENT_REQUESTS_READ_ALL.value})
        elif scope == "department":
            stmt = stmt.where(PurchaseRequest.department_id.in_(self._managed_department_ids(principal)))
        else:
            stmt = stmt.where(PurchaseRequest.requester_user_id == principal.user_id)
        counts = {s: (int(n), Decimal(v)) for s, n, v in self.session.execute(stmt).all()}
        get = lambda s: counts.get(s, (0, ZERO))  # noqa: E731
        return RequestStats(
            draft=get("draft")[0],
            sourcing=get("sourcing")[0],
            pending_approval=get("pending_approval")[0],
            closed=get("closed")[0],
            approved=get("approved")[0],
            rejected=get("rejected")[0],
            cancelled=get("cancelled")[0],
            approved_value=q2(get("approved")[1]),
            in_approval_value=q2(get("pending_approval")[1]),
        )

    def _waiting_on(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        out: dict[uuid.UUID, str] = {}
        for req in self.session.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.entity_type == ENTITY, ApprovalRequest.entity_id.in_(ids), ApprovalRequest.status == "pending"
            )
        ):
            o = self.approvals._out(Principal(uuid.uuid4(), "", "", frozenset(), frozenset()), req)
            out[req.entity_id] = f"{o.current_step_label} · {o.waiting_on}"
        return out

    def detail(self, principal: Principal, request_id: uuid.UUID) -> RequestDetail:
        pr = self._get(principal, request_id)
        approval = self.approvals.latest_for_entity(ENTITY, pr.id)
        approval_detail = self.approvals.detail(principal, approval) if approval else None
        quotes = self._quotations_out(pr)
        base = self._out(
            pr,
            f"{approval_detail.current_step_label} · {approval_detail.waiting_on}"
            if approval_detail and approval_detail.status == "pending"
            else None,
        )
        actions = self._allowed_actions(principal, pr)
        from app.modules.procurement.orders import OrderService

        orders = OrderService(self.session)
        if orders.can_create(principal, pr):
            actions.append("create_purchase_order")
        if approval_detail and approval_detail.allowed_actions:
            actions += approval_detail.allowed_actions
        return RequestDetail(
            **base.model_dump(),
            justification=pr.justification,
            fiscal_year=pr.fiscal_year,
            category_detail=CategoryOut.model_validate(pr.category),
            items=[ItemOut.model_validate(i) for i in pr.items],
            quotations=quotes,
            comparison=self._comparison(pr, quotes),
            selected_quotation_id=pr.selected_quotation_id,
            budget_impact=self._impact(pr),
            approval=approval_detail,
            allowed_actions=actions,
            cancel_reason=pr.cancel_reason,
            sent_for_approval_at=pr.sent_for_approval_at,
            purchase_orders=orders.summaries_for_request(pr.id),
        )

    def _allowed_actions(self, principal: Principal, pr: PurchaseRequest) -> list[str]:
        own = pr.requester_user_id == principal.user_id
        buyer = principal.has(Perm.PROCUREMENT_QUOTATIONS_MANAGE)
        actions: list[str] = []
        if pr.status == "draft" and own:
            actions += ["edit", "submit", "cancel"]
        if pr.status == "sourcing":
            if own or buyer:
                actions.append("cancel")
            if buyer:
                actions.append("manage_quotations")
                if pr.selected_quotation_id:
                    actions.append("send_for_approval")
        return actions

    def _out(self, pr: PurchaseRequest, waiting_on: str | None) -> RequestOut:
        return RequestOut(
            id=pr.id,
            code=pr.code,
            title=pr.title,
            status=pr.status,
            priority=pr.priority,
            requester=PersonRef(id=pr.requester.id, full_name=pr.requester.full_name),
            department=DepartmentRef.model_validate(pr.department),
            project=ProjectRef.model_validate(pr.project) if pr.project else None,
            category=pr.category.name,
            estimated_total=pr.estimated_total,
            approved_total=pr.approved_total,
            over_budget=pr.over_budget,
            quotation_count=len(pr.quotations),
            needed_by=pr.needed_by,
            created_at=pr.created_at,
            submitted_at=pr.submitted_at,
            decided_at=pr.decided_at,
            waiting_on=waiting_on,
        )

    def _quotations_out(self, pr: PurchaseRequest) -> list[QuotationOut]:
        quotes = list(pr.quotations)
        lowest = min((q.total_amount for q in quotes), default=None)
        return [
            QuotationOut(
                id=q.id,
                supplier=SupplierRef.model_validate(q.supplier),
                supplier_rating=q.supplier.rating,
                reference=q.reference,
                valid_until=q.valid_until,
                delivery_days=q.delivery_days,
                payment_terms=q.payment_terms,
                notes=q.notes,
                total_amount=q.total_amount,
                status=q.status,
                items=[QuotationItemOut.model_validate(i) for i in q.items],
                is_lowest=lowest is not None and q.total_amount == lowest,
                difference_from_lowest=q2(q.total_amount - lowest) if lowest is not None else ZERO,
                created_at=q.created_at,
            )
            for q in quotes
        ]

    def _comparison(self, pr: PurchaseRequest, quotes: list[QuotationOut]) -> Comparison:
        rows: list[ComparisonRow] = []
        for item in pr.items:
            cells = [(q.id, next((i for i in q.items if i.request_item_id == item.id), None)) for q in quotes]
            prices = [c.unit_price for _, c in cells if c is not None]
            low = min(prices) if prices else None
            rows.append(
                ComparisonRow(
                    request_item_id=item.id,
                    line_no=item.line_no,
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    estimated_unit_price=item.estimated_unit_price,
                    cells=[
                        ComparisonCell(quotation_id=qid, unit_price=c.unit_price, line_total=c.line_total, is_lowest=c.unit_price == low)
                        for qid, c in cells
                        if c is not None
                    ],
                )
            )
        lowest = min(quotes, key=lambda q: q.total_amount, default=None)
        timed = [q for q in quotes if q.delivery_days is not None]
        fastest = min(timed, key=lambda q: q.delivery_days or 0, default=None)
        return Comparison(
            rows=rows,
            lowest_quotation_id=lowest.id if lowest else None,
            fastest_quotation_id=fastest.id if fastest else None,
            savings_vs_estimate=q2(pr.estimated_total - lowest.total_amount) if lowest else None,
        )

    def _impact(self, pr: PurchaseRequest) -> BudgetImpact:
        amount = pr.approved_total if pr.approved_total is not None else pr.estimated_total
        check = self.finance.check(
            department_id=pr.department_id, project_id=pr.project_id, category_id=pr.category_id, fiscal_year=pr.fiscal_year, amount=amount
        )
        committed = pr.status == "approved"
        position = check.position
        available_after = check.available_after if not committed else (position.available if position else None)
        try:
            _, levels = self.approvals.planned_levels(ENTITY, amount, over_budget=check.over_budget and not committed)
        except BusinessRuleViolation:
            levels = []
        return BudgetImpact(
            found=check.found,
            budget_id=check.budget_id,
            scope_label=self._scope_label(pr.department, pr.project),
            category=pr.category.name,
            fiscal_year=pr.fiscal_year,
            position=position.out() if position else None,
            amount=amount,
            available_after=available_after,
            over_budget=pr.over_budget if committed else check.over_budget,
            committed_by_this_request=committed,
            approval_levels=[LEVEL_LABEL[lv] for lv in levels],
        )

    @staticmethod
    def _scope_label(dept: Department, project: OperationalProject | None) -> str:
        return f"{project.code} · {project.name}" if project else f"{dept.name} department"

    def preview(self, principal: Principal, data: BudgetPreviewIn) -> BudgetImpact:
        ensure_permission(principal, Perm.PROCUREMENT_REQUESTS_CREATE)
        dept = self.session.get(Department, data.department_id)
        project = self.session.get(OperationalProject, data.project_id) if data.project_id else None
        category = self.session.get(BudgetCategory, data.category_id)
        if dept is None or category is None or (data.project_id and project is None):
            raise BusinessRuleViolation("Choose a valid department, project and category.", code="invalid_budget_scope")
        check = self.finance.check(
            department_id=dept.id, project_id=data.project_id, category_id=category.id, fiscal_year=data.fiscal_year, amount=data.amount
        )
        _, levels = self.approvals.planned_levels(ENTITY, max(data.amount, Decimal("0.01")), over_budget=check.over_budget)
        return BudgetImpact(
            found=check.found,
            budget_id=check.budget_id,
            scope_label=self._scope_label(dept, project),
            category=category.name,
            fiscal_year=data.fiscal_year,
            position=check.position.out() if check.position else None,
            amount=q2(data.amount),
            available_after=check.available_after,
            over_budget=check.over_budget,
            approval_levels=[LEVEL_LABEL[lv] for lv in levels],
        )

    # ===================================================================== purchase requests: write
    def create_request(self, principal: Principal, data: RequestCreate) -> PurchaseRequest:
        ensure_permission(principal, Perm.PROCUREMENT_REQUESTS_CREATE)
        employee = self._employee(principal.user_id)
        department_id = data.department_id or (employee.department_id if employee else None)
        if department_id is None:
            raise BusinessRuleViolation(
                "Choose the department this request is for.",
                code="department_required",
                details={"fields": [{"field": "department_id", "message": "Choose a department."}]},
            )
        pr = PurchaseRequest(
            code=next_code(self.session, "purchase_request"),
            title=data.title.strip(),
            justification=data.justification.strip(),
            requester_user_id=principal.user_id,
            requester_employee_id=employee.id if employee else None,
            department_id=department_id,
            project_id=data.project_id,
            category_id=data.category_id,
            fiscal_year=data.fiscal_year or date.today().year,
            needed_by=data.needed_by,
            priority=data.priority,
        )
        self._validate_scope(pr)
        self._set_items(pr, data.items)
        self.session.add(pr)
        self.session.flush()
        self.audit.record(
            "purchase_request.created",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} drafted · SAR {pr.estimated_total:,.2f}",
            changes={"estimated_total": str(pr.estimated_total)},
        )
        self.session.commit()
        return pr

    def update_request(self, principal: Principal, request_id: uuid.UUID, data: RequestUpdate) -> PurchaseRequest:
        pr = self._get(principal, request_id, lock=True)
        self._require(pr.status == "draft" and pr.requester_user_id == principal.user_id, "Only the requester can edit a draft request.")
        fields = data.model_fields_set
        for name in ("title", "justification", "department_id", "category_id", "fiscal_year", "priority"):
            if name in fields and getattr(data, name) is not None:
                setattr(
                    pr,
                    name,
                    getattr(data, name).strip()
                    if isinstance(getattr(data, name), str) and name in ("title", "justification")
                    else getattr(data, name),
                )
        if "project_id" in fields:
            pr.project_id = data.project_id
        if "needed_by" in fields:
            pr.needed_by = data.needed_by
        self.session.flush()
        self.session.refresh(pr, attribute_names=["department", "project", "category"])
        self._validate_scope(pr)
        if data.items is not None:
            pr.items.clear()
            self.session.flush()
            self._set_items(pr, data.items)
        self.audit.record(
            "purchase_request.updated",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} edited · SAR {pr.estimated_total:,.2f}",
        )
        self.session.commit()
        return pr

    def submit(self, principal: Principal, request_id: uuid.UUID) -> PurchaseRequest:
        pr = self._get(principal, request_id, lock=True)
        self._require(pr.requester_user_id == principal.user_id, "Only the requester can submit this request.", forbidden=True)
        self._require(pr.status == "draft", "Only draft requests can be submitted.")
        ensure_permission(principal, Perm.PROCUREMENT_REQUESTS_CREATE)
        self._validate_scope(pr)
        if not pr.items or pr.estimated_total <= 0:
            raise BusinessRuleViolation("Add at least one item with a price before submitting.", code="items_required")
        check = self._budget_check(pr, pr.estimated_total)
        pr.status, pr.submitted_at = "sourcing", _now()
        self.audit.record(
            "purchase_request.submitted",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} submitted · budget available SAR {check.position.available:,.2f}"  # type: ignore[union-attr]
            + (" · over budget" if check.over_budget else ""),
            changes={
                "estimated_total": str(pr.estimated_total),
                "available": str(check.position.available),  # type: ignore[union-attr]
                "over_budget": check.over_budget,
            },
        )
        for uid in self.approvals._pool_users(Perm.PROCUREMENT_QUOTATIONS_MANAGE.value, pr.requester_user_id, set()):
            self.notifications.notify(
                uid,
                type="procurement.sourcing",
                level="info",
                title=f"New request to source: {pr.code}",
                body=f"{pr.title} · est. SAR {pr.estimated_total:,.2f}",
                link=self.link(pr.id),
                entity_type=ENTITY,
                entity_id=str(pr.id),
                dedupe_key=f"pr:{pr.id}:sourcing",
            )
        self._emit(
            pr,
            "purchase_request.submitted",
            actor_user_id=principal.user_id,
            amount=str(pr.estimated_total),
            budget_id=str(pr.budget_id),
            over_budget=check.over_budget,
        )
        self.session.commit()
        return pr

    def cancel(self, principal: Principal, request_id: uuid.UUID, data: CancelIn) -> PurchaseRequest:
        pr = self._get(principal, request_id, lock=True)
        self._require("cancel" in self._allowed_actions(principal, pr), "This request can't be cancelled now.")
        before = pr.status
        pr.status, pr.cancel_reason, pr.decided_at = "cancelled", data.reason.strip(), _now()
        self.audit.record(
            "purchase_request.cancelled",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} cancelled: {pr.cancel_reason}",
            changes={"status": [before, "cancelled"]},
        )
        if pr.requester_user_id != principal.user_id:
            self.notifications.notify(
                pr.requester_user_id,
                type="procurement.cancelled",
                level="warning",
                title=f"{pr.code} was cancelled",
                body=f"{principal.full_name}: {pr.cancel_reason}",
                link=self.link(pr.id),
                entity_type=ENTITY,
                entity_id=str(pr.id),
                dedupe_key=f"pr:{pr.id}:cancelled",
            )
        self._emit(pr, "purchase_request.cancelled", actor_user_id=principal.user_id)
        self.session.commit()
        return pr

    # --- quotations -----------------------------------------------------------------------------------
    def add_quotation(self, principal: Principal, request_id: uuid.UUID, data: QuotationIn) -> SupplierQuotation:
        pr = self._sourcing(principal, request_id)
        supplier = self.session.get(Supplier, data.supplier_id)
        if supplier is None or supplier.status != "active":
            raise BusinessRuleViolation(
                "Choose an active supplier.",
                code="invalid_supplier",
                details={"fields": [{"field": "supplier_id", "message": "Choose an active supplier."}]},
            )
        if any(q.supplier_id == supplier.id for q in pr.quotations):
            raise Conflict(f"A quotation from {supplier.name} is already recorded for this request.", code="quotation_exists")
        quote = SupplierQuotation(request_id=pr.id, supplier_id=supplier.id, created_by=principal.user_id, total_amount=ZERO)
        self._apply_quotation(pr, quote, data)
        pr.quotations.append(quote)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict("A quotation from this supplier is already recorded.", code="quotation_exists") from exc
        self.audit.record(
            "purchase_request.quotation_added",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"Quotation from {supplier.name}: SAR {quote.total_amount:,.2f}",
            changes={"supplier": supplier.code, "total": str(quote.total_amount)},
        )
        self._emit(
            pr,
            "purchase_request.quotation_added",
            actor_user_id=principal.user_id,
            quotation_id=str(quote.id),
            quotation_count=len(pr.quotations),
        )
        self.session.commit()
        return quote

    def update_quotation(
        self, principal: Principal, request_id: uuid.UUID, quotation_id: uuid.UUID, data: QuotationIn
    ) -> SupplierQuotation:
        pr = self._sourcing(principal, request_id)
        quote = self._quote(pr, quotation_id)
        if data.supplier_id != quote.supplier_id:
            raise BusinessRuleViolation("The supplier of a quotation can't be changed; record a new quotation instead.")
        before = quote.total_amount
        self._apply_quotation(pr, quote, data)
        if quote.status == "selected":
            pr.approved_total = quote.total_amount
        self.audit.record(
            "purchase_request.quotation_updated",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"Quotation from {quote.supplier.name} updated",
            changes={"total": [str(before), str(quote.total_amount)]},
        )
        self.session.commit()
        return quote

    def delete_quotation(self, principal: Principal, request_id: uuid.UUID, quotation_id: uuid.UUID) -> None:
        pr = self._sourcing(principal, request_id)
        quote = self._quote(pr, quotation_id)
        if pr.selected_quotation_id == quote.id:
            pr.selected_quotation_id, pr.approved_total = None, None
            self.session.flush()
        name = quote.supplier.name
        pr.quotations.remove(quote)
        self.audit.record(
            "purchase_request.quotation_removed",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"Quotation from {name} removed",
        )
        self.session.commit()

    def select_quotation(self, principal: Principal, request_id: uuid.UUID, quotation_id: uuid.UUID) -> PurchaseRequest:
        pr = self._sourcing(principal, request_id)
        quote = self._quote(pr, quotation_id)
        if quote.supplier.status != "active":
            raise BusinessRuleViolation("This supplier is no longer active.", code="invalid_supplier")
        if quote.valid_until and quote.valid_until < date.today():
            raise BusinessRuleViolation("This quotation has expired. Ask the supplier for an updated quotation.", code="quotation_expired")
        for q in pr.quotations:
            q.status = "not_selected"
        self.session.flush()  # release the "one selected" unique index before setting the new one
        quote.status = "selected"
        pr.selected_quotation_id, pr.approved_total = quote.id, quote.total_amount
        self.audit.record(
            "purchase_request.quotation_selected",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{quote.supplier.name} selected · SAR {quote.total_amount:,.2f}",
            changes={"supplier": quote.supplier.code, "total": str(quote.total_amount)},
        )
        self._emit(pr, "purchase_request.quotation_selected", actor_user_id=principal.user_id, quotation_id=str(quote.id))
        self.session.commit()
        return pr

    def send_for_approval(self, principal: Principal, request_id: uuid.UUID) -> PurchaseRequest:
        pr = self._sourcing(principal, request_id)
        quote = next((q for q in pr.quotations if q.id == pr.selected_quotation_id), None)
        if quote is None:
            raise BusinessRuleViolation("Select a supplier quotation first.", code="quotation_required")
        if quote.valid_until and quote.valid_until < date.today():
            raise BusinessRuleViolation("The selected quotation has expired.", code="quotation_expired")
        if quote.total_amount <= 0:
            raise BusinessRuleViolation("The selected quotation has no amount.", code="invalid_quotation")
        check = self._budget_check(pr, quote.total_amount)
        pr.approved_total = quote.total_amount
        pr.status, pr.sent_for_approval_at = "pending_approval", _now()
        self.approvals.open_request(
            entity_type=ENTITY,
            entity_id=pr.id,
            entity_code=pr.code,
            title=pr.title,
            amount=quote.total_amount,
            requested_by=pr.requester_user_id,
            department_id=pr.department_id,
            over_budget=check.over_budget,
            actor_user_id=principal.user_id,
        )
        self.audit.record(
            "purchase_request.sent_for_approval",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} sent for approval · {quote.supplier.name} · SAR {quote.total_amount:,.2f}"
            + (" · over budget" if check.over_budget else ""),
            changes={
                "amount": str(quote.total_amount),
                "available": str(check.position.available),  # type: ignore[union-attr]
                "over_budget": check.over_budget,
            },
        )
        self._emit(
            pr,
            "purchase_request.sent_for_approval",
            actor_user_id=principal.user_id,
            amount=str(quote.total_amount),
            budget_id=str(pr.budget_id),
            over_budget=check.over_budget,
        )
        self.session.commit()
        return pr

    # --- approval subject callbacks (run inside the approval decision transaction) -------------------------
    def on_approved(self, approval: ApprovalRequest, actor: Principal) -> None:
        pr = self.session.scalar(
            select(PurchaseRequest)
            .where(PurchaseRequest.id == approval.entity_id)
            .with_for_update(of=PurchaseRequest)
            .execution_options(populate_existing=True)
        )
        if pr is None or pr.status != "pending_approval":
            raise Conflict("The purchase request is no longer awaiting approval.", code="invalid_state")
        if pr.budget_id is None or pr.approved_total is None:
            raise BusinessRuleViolation("The request has no budget to commit against.", code="budget_not_found")
        entry = self.finance.commit(
            budget_id=pr.budget_id,
            amount=pr.approved_total,
            source_type=ENTITY,
            source_id=pr.id,
            source_code=pr.code,
            actor_user_id=actor.user_id,
            description=f"{pr.code} · {pr.title}",
        )
        position = self.finance.position(pr.budget_id)
        pr.status, pr.decided_at = "approved", _now()
        pr.over_budget = position.available < 0
        self.audit.record(
            "purchase_request.approved",
            actor_user_id=actor.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} approved · SAR {pr.approved_total:,.2f} committed",
            changes={"ledger_entry_id": str(entry.id), "committed": str(entry.amount), "available_after": str(position.available)},
        )
        for uid in self.approvals._pool_users(Perm.PROCUREMENT_QUOTATIONS_MANAGE.value, actor.user_id, set()):
            self.notifications.notify(
                uid,
                type="procurement.approved",
                level="success",
                title=f"{pr.code} approved — ready to order",
                body=f"{pr.title} · SAR {pr.approved_total:,.2f}",
                link=self.link(pr.id),
                entity_type=ENTITY,
                entity_id=str(pr.id),
                dedupe_key=f"pr:{pr.id}:approved",
            )
        self._emit(pr, "purchase_request.approved", actor_user_id=actor.user_id, amount=str(pr.approved_total), budget_id=str(pr.budget_id))

    def on_rejected(self, approval: ApprovalRequest, actor: Principal, comment: str) -> None:
        pr = self.session.scalar(
            select(PurchaseRequest)
            .where(PurchaseRequest.id == approval.entity_id)
            .with_for_update(of=PurchaseRequest)
            .execution_options(populate_existing=True)
        )
        if pr is None or pr.status != "pending_approval":
            raise Conflict("The purchase request is no longer awaiting approval.", code="invalid_state")
        pr.status, pr.decided_at = "rejected", _now()
        self.audit.record(
            "purchase_request.rejected",
            actor_user_id=actor.user_id,
            entity_type=ENTITY,
            entity_id=pr.id,
            summary=f"{pr.code} rejected: {comment}",
        )
        self._emit(pr, "purchase_request.rejected", actor_user_id=actor.user_id)

    # --- helpers -------------------------------------------------------------------------------------------------
    def _emit(self, pr: PurchaseRequest, event: str, *, actor_user_id: uuid.UUID | None, **payload: object) -> None:
        events.emit(
            self.session,
            event,
            entity_type=ENTITY,
            entity_id=pr.id,
            actor_user_id=actor_user_id,
            payload={"code": pr.code, "status": pr.status, **payload},
        )

    @staticmethod
    def link(request_id: uuid.UUID | str) -> str:
        return f"/procurement/requests/{request_id}"

    def _budget_check(self, pr: PurchaseRequest, amount: Decimal):
        check = self.finance.check(
            department_id=pr.department_id, project_id=pr.project_id, category_id=pr.category_id, fiscal_year=pr.fiscal_year, amount=amount
        )
        if not check.found:
            raise BusinessRuleViolation(
                f"No active {pr.category.name} budget exists for {self._scope_label(pr.department, pr.project)} in {pr.fiscal_year}. "
                "Ask Finance to set one up.",
                code="budget_not_found",
            )
        pr.budget_id = check.budget_id
        pr.over_budget = check.over_budget
        pr.budget_available_at_check = check.position.available  # type: ignore[union-attr]
        pr.budget_checked_at = _now()
        return check

    def _validate_scope(self, pr: PurchaseRequest) -> None:
        dept = self.session.get(Department, pr.department_id)
        if dept is None or not dept.is_active:
            raise BusinessRuleViolation(
                "Choose an active department.",
                code="invalid_department",
                details={"fields": [{"field": "department_id", "message": "Choose an active department."}]},
            )
        category = self.session.get(BudgetCategory, pr.category_id)
        if category is None or not category.is_active:
            raise BusinessRuleViolation(
                "Choose a budget category.",
                code="invalid_category",
                details={"fields": [{"field": "category_id", "message": "Choose a budget category."}]},
            )
        if pr.project_id:
            project = self.session.get(OperationalProject, pr.project_id)
            if project is None or project.status not in OPEN_PROJECT_STATUSES:
                raise BusinessRuleViolation(
                    "Choose a planned or active project.",
                    code="invalid_project",
                    details={"fields": [{"field": "project_id", "message": "Choose a planned or active project."}]},
                )

    def _set_items(self, pr: PurchaseRequest, items: list[ItemIn]) -> None:
        for n, item in enumerate(items, start=1):
            pr.items.append(
                PurchaseRequestItem(
                    line_no=n,
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    estimated_unit_price=q2(item.estimated_unit_price),
                    line_total=line_total(item.quantity, q2(item.estimated_unit_price)),
                )
            )
        pr.estimated_total = total(i.line_total for i in pr.items)

    def _apply_quotation(self, pr: PurchaseRequest, quote: SupplierQuotation, data: QuotationIn) -> None:
        by_item = {i.request_item_id: i for i in data.items}
        expected = {i.id for i in pr.items}
        if set(by_item) != expected or len(by_item) != len(data.items):
            raise BusinessRuleViolation("Enter exactly one price for every requested item.", code="quotation_items_mismatch")
        quote.reference, quote.valid_until, quote.delivery_days = data.reference, data.valid_until, data.delivery_days
        quote.payment_terms, quote.notes = data.payment_terms, data.notes
        quote.items.clear()
        self.session.flush()
        for item in pr.items:
            price = q2(by_item[item.id].unit_price)
            quote.items.append(QuotationItem(request_item_id=item.id, unit_price=price, line_total=line_total(item.quantity, price)))
        quote.total_amount = total(i.line_total for i in quote.items)

    def _sourcing(self, principal: Principal, request_id: uuid.UUID) -> PurchaseRequest:
        ensure_permission(principal, Perm.PROCUREMENT_QUOTATIONS_MANAGE)
        pr = self._get(principal, request_id, lock=True)
        self._require(pr.status == "sourcing", "Quotations can only be managed while the request is in sourcing.")
        return pr

    @staticmethod
    def _quote(pr: PurchaseRequest, quotation_id: uuid.UUID) -> SupplierQuotation:
        quote = next((q for q in pr.quotations if q.id == quotation_id), None)
        if quote is None:
            raise NotFound("Quotation not found.")
        return quote

    @staticmethod
    def _require(condition: bool, message: str, *, forbidden: bool = False) -> None:
        if not condition:
            if forbidden:
                raise PermissionDenied(message)
            raise Conflict(message, code="invalid_state")


class PurchaseRequestSubject:
    entity_type = ENTITY
    label = "Purchase request"

    def link(self, entity_id: str) -> str:
        return ProcurementService.link(entity_id)

    def on_approved(self, session: Session, approval: ApprovalRequest, actor: Principal) -> None:
        ProcurementService(session).on_approved(approval, actor)

    def on_rejected(self, session: Session, approval: ApprovalRequest, actor: Principal, comment: str) -> None:
        ProcurementService(session).on_rejected(approval, actor, comment)


register_subject(PurchaseRequestSubject())
