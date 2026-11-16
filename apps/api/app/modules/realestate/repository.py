from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.listing import escape_like
from app.modules.realestate.models import ReBuilding, RePaymentPlan, ReProject, ReUnit


class RealEstateRepository:
    def __init__(self, session: Session):
        self.session = session

    # --- projects ---------------------------------------------------------------------------------
    def get_project(self, project_id: uuid.UUID) -> ReProject | None:
        return self.session.get(ReProject, project_id)

    def project_by_code(self, code: str) -> ReProject | None:
        return self.session.scalar(select(ReProject).where(func.upper(ReProject.code) == code.upper()))

    def projects_stmt(self, q: str | None, status: str | None) -> Select:
        stmt = select(ReProject)
        if status:
            stmt = stmt.where(ReProject.status == status)
        if q:
            term = f"%{escape_like(q)}%"
            stmt = stmt.where(
                or_(
                    ReProject.name.ilike(term, escape="\\"),
                    ReProject.code.ilike(term, escape="\\"),
                    ReProject.city.ilike(term, escape="\\"),
                )
            )
        return stmt

    def status_counts(self, *, project_ids: list[uuid.UUID] | None = None, by: str = "project") -> dict[uuid.UUID, dict[str, int]]:
        key = ReUnit.project_id if by == "project" else ReUnit.building_id
        stmt = select(key, ReUnit.status, func.count()).group_by(key, ReUnit.status)
        if project_ids is not None:
            stmt = stmt.where(ReUnit.project_id.in_(project_ids))
        out: dict[uuid.UUID, dict[str, int]] = {}
        for k, status, n in self.session.execute(stmt).all():
            out.setdefault(k, {})[status] = int(n)
        return out

    def price_ranges(self, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
        rows = self.session.execute(
            select(ReUnit.project_id, func.min(ReUnit.list_price), func.max(ReUnit.list_price))
            .where(ReUnit.project_id.in_(project_ids))
            .group_by(ReUnit.project_id)
        ).all()
        return {p: (lo, hi) for p, lo, hi in rows}

    def building_counts(self, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        rows = self.session.execute(
            select(ReBuilding.project_id, func.count()).where(ReBuilding.project_id.in_(project_ids)).group_by(ReBuilding.project_id)
        ).all()
        return {p: int(n) for p, n in rows}

    # --- buildings --------------------------------------------------------------------------------
    def get_building(self, building_id: uuid.UUID) -> ReBuilding | None:
        return self.session.get(ReBuilding, building_id)

    def building_by_code(self, project_id: uuid.UUID, code: str) -> ReBuilding | None:
        return self.session.scalar(
            select(ReBuilding).where(ReBuilding.project_id == project_id, func.upper(ReBuilding.code) == code.upper())
        )

    def max_unit_floor(self, building_id: uuid.UUID) -> int | None:
        return self.session.scalar(select(func.max(ReUnit.floor)).where(ReUnit.building_id == building_id))

    def unit_count(self, *, building_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None) -> int:
        stmt = select(func.count()).select_from(ReUnit)
        if building_id:
            stmt = stmt.where(ReUnit.building_id == building_id)
        if project_id:
            stmt = stmt.where(ReUnit.project_id == project_id)
        return int(self.session.scalar(stmt) or 0)

    # --- units ------------------------------------------------------------------------------------
    def get_unit(self, unit_id: uuid.UUID, *, lock: bool = False) -> ReUnit | None:
        if not lock:
            return self.session.get(ReUnit, unit_id)
        return self.session.scalar(
            select(ReUnit).where(ReUnit.id == unit_id).with_for_update(of=ReUnit).execution_options(populate_existing=True)
        )

    def unit_by_number(self, building_id: uuid.UUID, number: str) -> ReUnit | None:
        return self.session.scalar(
            select(ReUnit).where(ReUnit.building_id == building_id, func.upper(ReUnit.unit_number) == number.upper())
        )

    def units_stmt(
        self,
        *,
        project_id: uuid.UUID | None = None,
        building_id: uuid.UUID | None = None,
        status: str | None = None,
        unit_type: str | None = None,
        bedrooms: int | None = None,
        min_bedrooms: int | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        q: str | None = None,
    ) -> Select:
        stmt = select(ReUnit)
        for col, val in (
            (ReUnit.project_id, project_id),
            (ReUnit.building_id, building_id),
            (ReUnit.status, status),
            (ReUnit.unit_type, unit_type),
            (ReUnit.bedrooms, bedrooms),
        ):
            if val is not None:
                stmt = stmt.where(col == val)
        if min_bedrooms is not None:
            stmt = stmt.where(ReUnit.bedrooms >= min_bedrooms)
        if price_min is not None:
            stmt = stmt.where(ReUnit.list_price >= price_min)
        if price_max is not None:
            stmt = stmt.where(ReUnit.list_price <= price_max)
        if q:
            term = f"%{escape_like(q)}%"
            stmt = stmt.where(or_(ReUnit.unit_number.ilike(term, escape="\\"), ReUnit.view.ilike(term, escape="\\")))
        return stmt

    def project_units(self, project_id: uuid.UUID) -> list[ReUnit]:
        return list(
            self.session.scalars(
                select(ReUnit).where(ReUnit.project_id == project_id).order_by(ReUnit.building_id, ReUnit.floor.desc(), ReUnit.unit_number)
            ).unique()
        )

    def count_available_fitting(self, *, project_id: uuid.UUID | None, upper: Decimal, lower: Decimal | None, bedrooms: int | None) -> int:
        stmt = select(func.count()).select_from(ReUnit).where(ReUnit.status == "available", ReUnit.list_price <= upper)
        if lower is not None:
            stmt = stmt.where(ReUnit.list_price >= lower)
        if project_id is not None:
            stmt = stmt.where(ReUnit.project_id == project_id)
        if bedrooms:
            stmt = stmt.where(ReUnit.bedrooms >= bedrooms)
        return int(self.session.scalar(stmt) or 0)

    # --- payment plans ----------------------------------------------------------------------------
    def get_plan(self, plan_id: uuid.UUID) -> RePaymentPlan | None:
        return self.session.get(RePaymentPlan, plan_id)

    def plan_by_name(self, project_id: uuid.UUID, name: str) -> RePaymentPlan | None:
        return self.session.scalar(
            select(RePaymentPlan).where(RePaymentPlan.project_id == project_id, func.lower(RePaymentPlan.name) == name.strip().lower())
        )
