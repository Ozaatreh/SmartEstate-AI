"""Real estate inventory service. Permission checks, audit and events live here (route → service → repository).

Unit status rules:
- Users with ``realestate.inventory.manage`` may only toggle ``available ↔ blocked``.
- ``reserved`` and ``sold`` (and the release back to ``available``) are set exclusively by CRM reservations via
  :meth:`RealEstateService.transition_unit`, inside the reservation's transaction and under the unit row lock.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automation import events
from app.common.listing import ListParams, apply_sort, paginate
from app.common.money import q2
from app.core.errors import BusinessRuleViolation, Conflict, NotFound
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.realestate.models import ReBuilding, RePaymentPlan, ReProject, ReUnit
from app.modules.realestate.plans import breakdown
from app.modules.realestate.repository import RealEstateRepository
from app.modules.realestate.schemas import (
    Availability,
    BuildingIn,
    BuildingOut,
    BuildingRef,
    BuildingUpdate,
    GridBuilding,
    GridFloor,
    GridUnit,
    PaymentPlanIn,
    PaymentPlanOut,
    PaymentPlanUpdate,
    PlanBreakdown,
    ProjectDetail,
    ProjectIn,
    ProjectOut,
    ProjectRef,
    ProjectUpdate,
    StatusCounts,
    UnitDetail,
    UnitIn,
    UnitOut,
    UnitUpdate,
)

PROJECT_SORT = {"name": ReProject.name, "code": ReProject.code, "created_at": ReProject.created_at}
UNIT_SORT = {
    "list_price": ReUnit.list_price,
    "area_sqm": ReUnit.area_sqm,
    "unit_number": ReUnit.unit_number,
    "floor": ReUnit.floor,
    "bedrooms": ReUnit.bedrooms,
}
# Reservation-driven transitions (the only way into / out of reserved and sold).
RESERVATION_TRANSITIONS = {("available", "reserved"), ("reserved", "available"), ("reserved", "sold")}
MANUAL_TRANSITIONS = {("available", "blocked"), ("blocked", "available")}


def _counts(raw: dict[str, int] | None) -> StatusCounts:
    raw = raw or {}
    return StatusCounts(**{k: raw.get(k, 0) for k in ("available", "reserved", "sold", "blocked")}, total=sum(raw.values()))


def _changes(obj: object, data: dict) -> dict[str, list]:
    out: dict[str, list] = {}
    for k, v in data.items():
        old = getattr(obj, k)
        if old != v:
            out[k] = [str(old) if old is not None else None, str(v) if v is not None else None]
            setattr(obj, k, v)
    return out


class RealEstateService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = RealEstateRepository(session)
        self.audit = AuditService(session)

    # ------------------------------------------------------------------ helpers
    def _read(self, principal: Principal) -> None:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_READ)

    def _manage(self, principal: Principal) -> None:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)

    def _record(self, principal: Principal | None, action: str, entity_type: str, entity_id: uuid.UUID, summary: str, changes=None) -> None:
        self.audit.record(
            f"realestate.{action}",
            actor_user_id=principal.user_id if principal else None,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            changes=changes or None,
        )

    def _project(self, project_id: uuid.UUID) -> ReProject:
        project = self.repo.get_project(project_id)
        if project is None:
            raise NotFound("Project not found.")
        return project

    def _flush_unique(self, message: str, code: str) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict(message, code=code) from exc

    # ------------------------------------------------------------------ projects
    def list_projects(self, principal: Principal, params: ListParams, *, status: str | None) -> tuple[list[ProjectOut], int, int]:
        self._read(principal)
        rows, total, pages = paginate(
            self.session, apply_sort(self.repo.projects_stmt(params.q, status), params.sort, PROJECT_SORT, "name"), params
        )
        return self._projects_out(rows), total, pages

    def _projects_out(self, rows: list[ReProject]) -> list[ProjectOut]:
        ids = [p.id for p in rows]
        counts = self.repo.status_counts(project_ids=ids)
        prices = self.repo.price_ranges(ids)
        buildings = self.repo.building_counts(ids)
        return [
            ProjectOut(
                id=p.id,
                code=p.code,
                name=p.name,
                city=p.city,
                district=p.district,
                status=p.status,
                launch_date=p.launch_date,
                handover_date=p.handover_date,
                is_demo_data=p.is_demo_data,
                building_count=buildings.get(p.id, 0),
                units=_counts(counts.get(p.id)),
                price_from=prices.get(p.id, (None, None))[0],
                price_to=prices.get(p.id, (None, None))[1],
            )
            for p in rows
        ]

    def project_detail(self, principal: Principal, project_id: uuid.UUID) -> ProjectDetail:
        self._read(principal)
        p = self._project(project_id)
        by_building = self.repo.status_counts(project_ids=[p.id], by="building")
        base = self._projects_out([p])[0]
        return ProjectDetail(
            **base.model_dump(),
            description=p.description,
            amenities=list(p.amenities or []),
            media=list(p.media or []),
            buildings=[BuildingOut.model_validate(b).model_copy(update={"units": _counts(by_building.get(b.id))}) for b in p.buildings],
            payment_plans=[PaymentPlanOut.model_validate(pl) for pl in p.payment_plans],
            can_manage=principal.has(Perm.REALESTATE_INVENTORY_MANAGE),
            created_at=p.created_at,
        )

    def create_project(self, principal: Principal, data: ProjectIn) -> ReProject:
        self._manage(principal)
        if self.repo.project_by_code(data.code):
            raise Conflict(f"Project code {data.code.upper()} already exists.", code="duplicate_code")
        project = ReProject(
            **data.model_dump(exclude={"code", "media"}), code=data.code.upper(), media=[m.model_dump(mode="json") for m in data.media]
        )
        self.session.add(project)
        self._flush_unique("Project code already exists.", "duplicate_code")
        self._record(principal, "project_created", "re_project", project.id, f"{project.code} · {project.name}")
        self.session.commit()
        return project

    def update_project(self, principal: Principal, project_id: uuid.UUID, data: ProjectUpdate) -> ReProject:
        self._manage(principal)
        project = self._project(project_id)
        values = {k: getattr(data, k) for k in data.model_fields_set}
        if "media" in values and values["media"] is not None:
            values["media"] = [m.model_dump(mode="json") for m in data.media or []]
        for required in ("name", "city", "status", "amenities", "media"):
            if required in values and values[required] is None:
                values.pop(required)
        launch, handover = values.get("launch_date", project.launch_date), values.get("handover_date", project.handover_date)
        if launch and handover and handover < launch:
            raise BusinessRuleViolation("Handover cannot be before launch.", code="invalid_dates")
        changes = _changes(project, values)
        if changes:
            self._record(principal, "project_updated", "re_project", project.id, f"{project.code} updated", changes)
        self.session.commit()
        return project

    # ------------------------------------------------------------------ buildings
    def create_building(self, principal: Principal, project_id: uuid.UUID, data: BuildingIn) -> ReBuilding:
        self._manage(principal)
        project = self._project(project_id)
        if self.repo.building_by_code(project.id, data.code):
            raise Conflict(f"Building {data.code.upper()} already exists in {project.code}.", code="duplicate_code")
        building = ReBuilding(project_id=project.id, code=data.code.upper(), name=data.name.strip(), floors=data.floors)
        project.buildings.append(building)
        self._flush_unique("Building code already exists in this project.", "duplicate_code")
        self._record(
            principal, "building_created", "re_building", building.id, f"{project.code} · {building.code} ({building.floors} floors)"
        )
        self.session.commit()
        return building

    def update_building(self, principal: Principal, building_id: uuid.UUID, data: BuildingUpdate) -> ReBuilding:
        self._manage(principal)
        building = self.repo.get_building(building_id)
        if building is None:
            raise NotFound("Building not found.")
        values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if "floors" in values:
            top = self.repo.max_unit_floor(building.id)
            if top is not None and top > values["floors"]:
                raise BusinessRuleViolation(f"Units exist up to floor {top}; floors can't be lower.", code="floors_in_use")
        changes = _changes(building, values)
        if changes:
            self._record(principal, "building_updated", "re_building", building.id, f"{building.code} updated", changes)
        self.session.commit()
        return building

    def delete_building(self, principal: Principal, building_id: uuid.UUID) -> None:
        self._manage(principal)
        building = self.repo.get_building(building_id)
        if building is None:
            raise NotFound("Building not found.")
        if self.repo.unit_count(building_id=building.id):
            raise Conflict("Remove the building's units first.", code="building_in_use")
        self._record(principal, "building_deleted", "re_building", building.id, f"{building.code} deleted")
        self.session.delete(building)
        self.session.commit()

    # ------------------------------------------------------------------ payment plans
    def create_plan(self, principal: Principal, project_id: uuid.UUID, data: PaymentPlanIn) -> RePaymentPlan:
        self._manage(principal)
        project = self._project(project_id)
        if self.repo.plan_by_name(project.id, data.name):
            raise Conflict("A payment plan with this name already exists.", code="duplicate_name")
        plan = RePaymentPlan(project_id=project.id, **data.model_dump())
        project.payment_plans.append(plan)
        self._flush_unique("A payment plan with this name already exists.", "duplicate_name")
        self._record(principal, "payment_plan_created", "re_payment_plan", plan.id, f"{project.code} · {plan.name}")
        self.session.commit()
        return plan

    def update_plan(self, principal: Principal, plan_id: uuid.UUID, data: PaymentPlanUpdate) -> RePaymentPlan:
        self._manage(principal)
        plan = self.repo.get_plan(plan_id)
        if plan is None:
            raise NotFound("Payment plan not found.")
        values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None or k == "description"}
        down = values.get("down_payment_pct", plan.down_payment_pct)
        handover = values.get("handover_pct", plan.handover_pct)
        inst = values.get("installments", plan.installments)
        if down + handover > 100:
            raise BusinessRuleViolation("Down payment and handover shares cannot exceed 100%.", code="invalid_shares")
        if inst == 0 and down + handover != 100:
            raise BusinessRuleViolation("Without installments, down payment and handover must add up to 100%.", code="invalid_shares")
        changes = _changes(plan, values)
        if changes:
            self._flush_unique("A payment plan with this name already exists.", "duplicate_name")
            self._record(principal, "payment_plan_updated", "re_payment_plan", plan.id, f"{plan.name} updated", changes)
        self.session.commit()
        return plan

    # ------------------------------------------------------------------ units
    def list_units(self, principal: Principal, params: ListParams, **filters) -> tuple[list[UnitOut], int, int]:
        self._read(principal)
        stmt = apply_sort(self.repo.units_stmt(q=params.q, **filters), params.sort, UNIT_SORT, "unit_number")
        rows, total, pages = paginate(self.session, stmt, params)
        return [self.unit_out(u) for u in rows], total, pages

    def unit_out(self, u: ReUnit) -> UnitOut:
        return UnitOut(
            id=u.id,
            project=ProjectRef.model_validate(u.project),
            building=BuildingRef.model_validate(u.building),
            unit_number=u.unit_number,
            unit_type=u.unit_type,
            bedrooms=u.bedrooms,
            bathrooms=u.bathrooms,
            floor=u.floor,
            area_sqm=u.area_sqm,
            view=u.view,
            list_price=u.list_price,
            price_per_sqm=q2(u.list_price / u.area_sqm),
            status=u.status,
            is_public=u.is_public,
            is_demo_data=u.is_demo_data,
        )

    def get_unit(self, principal: Principal, unit_id: uuid.UUID) -> ReUnit:
        self._read(principal)
        unit = self.repo.get_unit(unit_id)
        if unit is None:
            raise NotFound("Unit not found.")
        return unit

    def unit_detail(self, principal: Principal, unit_id: uuid.UUID) -> UnitDetail:
        u = self.get_unit(principal, unit_id)
        can_manage = principal.has(Perm.REALESTATE_INVENTORY_MANAGE)
        return UnitDetail(
            **self.unit_out(u).model_dump(),
            notes=u.notes,
            payment_plans=[self.plan_breakdown(p, u.list_price) for p in u.project.payment_plans if p.is_active],
            allowed_status_changes=[b for a, b in sorted(MANUAL_TRANSITIONS) if a == u.status] if can_manage else [],
            can_manage=can_manage,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )

    @staticmethod
    def plan_breakdown(plan: RePaymentPlan, price: Decimal) -> PlanBreakdown:
        b = breakdown(price, plan.down_payment_pct, plan.installments, plan.handover_pct)
        return PlanBreakdown(
            plan_id=plan.id,
            name=plan.name,
            down_payment_pct=plan.down_payment_pct,
            down_payment=b.down_payment,
            installments=b.installments,
            installment_frequency=plan.installment_frequency,
            installment_amount=b.installment_amount,
            last_installment_amount=b.last_installment_amount,
            handover_pct=plan.handover_pct,
            handover_payment=b.handover_payment,
            total=b.total,
        )

    def create_unit(self, principal: Principal, data: UnitIn) -> ReUnit:
        self._manage(principal)
        building = self.repo.get_building(data.building_id)
        if building is None:
            raise NotFound("Building not found.")
        if data.floor > building.floors:
            raise BusinessRuleViolation(f"{building.code} has {building.floors} floors.", code="floor_out_of_range")
        if self.repo.unit_by_number(building.id, data.unit_number):
            raise Conflict(f"Unit {data.unit_number.upper()} already exists in {building.code}.", code="duplicate_unit")
        unit = ReUnit(project_id=building.project_id, **data.model_dump(exclude={"unit_number"}), unit_number=data.unit_number.upper())
        self.session.add(unit)
        self._flush_unique("This unit number already exists in the building.", "duplicate_unit")
        self.session.refresh(unit)
        self._record(principal, "unit_created", "re_unit", unit.id, f"{building.code}-{unit.unit_number} · SAR {unit.list_price:,.2f}")
        self.session.commit()
        return unit

    def update_unit(self, principal: Principal, unit_id: uuid.UUID, data: UnitUpdate) -> ReUnit:
        self._manage(principal)
        unit = self.repo.get_unit(unit_id, lock=True)  # same lock reservations take → no lost status updates
        if unit is None:
            raise NotFound("Unit not found.")
        values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None or k in ("view", "notes")}
        new_status = values.pop("status", None)
        if unit.status in ("reserved", "sold") and set(values) & {"list_price", "unit_type", "bedrooms", "area_sqm", "floor"}:
            raise Conflict(f"A {unit.status} unit's commercial details can't be changed.", code="unit_locked")
        if "floor" in values and values["floor"] > unit.building.floors:
            raise BusinessRuleViolation(f"{unit.building.code} has {unit.building.floors} floors.", code="floor_out_of_range")
        before = unit.status
        if new_status is not None and new_status != unit.status:
            if (unit.status, new_status) not in MANUAL_TRANSITIONS:
                raise Conflict(
                    f"Status can't change from {unit.status} to {new_status} directly; reserved and sold come from reservations.",
                    code="invalid_status_change",
                )
            values["status"] = new_status
        changes = _changes(unit, values)
        if changes:
            self._record(principal, "unit_updated", "re_unit", unit.id, f"{unit.building.code}-{unit.unit_number} updated", changes)
            if unit.status != before:
                self._emit_status(unit, before, principal.user_id)
        self.session.commit()
        return unit

    def delete_unit(self, principal: Principal, unit_id: uuid.UUID) -> None:
        self._manage(principal)
        unit = self.repo.get_unit(unit_id, lock=True)
        if unit is None:
            raise NotFound("Unit not found.")
        if unit.status in ("reserved", "sold"):
            raise Conflict(f"A {unit.status} unit can't be deleted.", code="unit_locked")
        label = f"{unit.building.code}-{unit.unit_number}"
        try:
            self.session.delete(unit)
            self.session.flush()
        except IntegrityError as exc:  # referenced by reservations or leads
            self.session.rollback()
            raise Conflict("The unit has reservation or lead history; block it instead.", code="unit_in_use") from exc
        self._record(principal, "unit_deleted", "re_unit", unit_id, f"{label} deleted")
        self.session.commit()

    # ------------------------------------------------------------------ availability grid
    def availability(self, principal: Principal, project_id: uuid.UUID) -> Availability:
        self._read(principal)
        project = self._project(project_id)
        units = self.repo.project_units(project.id)
        totals: dict[str, int] = {}
        grids: list[GridBuilding] = []
        for b in project.buildings:
            own = [u for u in units if u.building_id == b.id]
            counts: dict[str, int] = {}
            floors: dict[int, list[GridUnit]] = {}
            for u in own:
                counts[u.status] = counts.get(u.status, 0) + 1
                totals[u.status] = totals.get(u.status, 0) + 1
                floors.setdefault(u.floor, []).append(
                    GridUnit(
                        id=u.id,
                        unit_number=u.unit_number,
                        unit_type=u.unit_type,
                        bedrooms=u.bedrooms,
                        area_sqm=u.area_sqm,
                        list_price=u.list_price,
                        status=u.status,
                    )
                )
            rows = [GridFloor(floor=f, units=sorted(us, key=lambda x: x.unit_number)) for f, us in sorted(floors.items(), reverse=True)]
            grids.append(GridBuilding(id=b.id, code=b.code, name=b.name, floors=b.floors, units=_counts(counts), rows=rows))
        return Availability(project=ProjectRef.model_validate(project), totals=_counts(totals), buildings=grids)

    # ------------------------------------------------------------------ used by CRM reservations (no permission check)
    def lock_unit(self, unit_id: uuid.UUID) -> ReUnit:
        unit = self.repo.get_unit(unit_id, lock=True)
        if unit is None:
            raise NotFound("Unit not found.")
        return unit

    def transition_unit(self, unit: ReUnit, to: str, *, actor_user_id: uuid.UUID | None, reason: str) -> None:
        """Reservation-driven status change. The caller holds the unit row lock and owns the transaction."""
        before = unit.status
        if (before, to) not in RESERVATION_TRANSITIONS:
            raise Conflict(f"Unit {unit.unit_number} is {before}; it can't become {to}.", code="unit_unavailable")
        unit.status = to
        self.audit.record(
            "realestate.unit_status_changed",
            actor_user_id=actor_user_id,
            entity_type="re_unit",
            entity_id=unit.id,
            summary=f"{unit.building.code}-{unit.unit_number}: {before} → {to} ({reason})",
            changes={"status": [before, to]},
        )
        self._emit_status(unit, before, actor_user_id)

    def _emit_status(self, unit: ReUnit, before: str, actor_user_id: uuid.UUID | None) -> None:
        events.emit(
            self.session,
            "unit.status_changed",
            entity_type="re_unit",
            entity_id=unit.id,
            actor_user_id=actor_user_id,
            payload={"unit_number": unit.unit_number, "project_id": str(unit.project_id), "from": before, "to": unit.status},
        )
