"""Real estate inventory (Phase 5): projects, buildings, units and payment plans.

All NOVA Residences records are fictional; rows created by the demo seed carry ``is_demo_data = true``.
Unit status changes to ``reserved`` / ``sold`` (and back to ``available``) happen only through CRM
reservations, inside the same transaction as the reservation row (see ``crm.reservations``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check

PROJECT_STATUSES = ("planning", "launched", "under_construction", "completed")
UNIT_TYPES = ("studio", "apartment", "duplex", "penthouse", "townhouse")
UNIT_STATUSES = ("available", "reserved", "sold", "blocked")
FREQUENCIES = ("monthly", "quarterly", "semi_annual", "annual")
# Phase 7C data classification: marketing outputs use only "cleared" plans; unclassified plans stay out (fail closed).
PLAN_MARKETING_STATUSES = ("unreviewed", "cleared", "excluded")


class ReProject(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "re_projects"
    __table_args__ = (
        enum_check("status", PROJECT_STATUSES),
        # Phase 7D location rules (see migration 0013).
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coordinates_paired"),
        CheckConstraint("NOT location_verified OR latitude IS NOT NULL", name="verified_needs_coordinates"),
        CheckConstraint("NOT (location_verified AND is_demo_data)", name="verified_not_demo"),
        CheckConstraint("illustrative_latitude BETWEEN -90 AND 90", name="illustrative_latitude_range"),
        CheckConstraint("illustrative_longitude BETWEEN -180 AND 180", name="illustrative_longitude_range"),
        CheckConstraint("(illustrative_latitude IS NULL) = (illustrative_longitude IS NULL)", name="illustrative_paired"),
        CheckConstraint("illustrative_latitude IS NULL OR illustrative_label IS NOT NULL", name="illustrative_needs_label"),
        CheckConstraint("NOT (location_verified AND illustrative_latitude IS NOT NULL)", name="illustrative_not_with_verified"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    district: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planning", server_default="planning")
    launch_date: Mapped[date | None] = mapped_column(Date)
    handover_date: Mapped[date | None] = mapped_column(Date)
    amenities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    media: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Phase 7A: shown on the public marketing website and to the public assistant only when true (off by default).
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Phase 7D: location. Coordinates are shown publicly (map, directions) only once a person marks them verified,
    # and a fictional demo project can never be verified — it must not be pinned to a real place.
    address: Mapped[str | None] = mapped_column(String(250))
    country: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    location_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    location_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    # Illustrative map point: a *reference* place shown on the map for a project with no verified location (e.g. a
    # fictional demo project). Kept apart from the property-location fields above; never shown as the address, never
    # "verified", and always labelled "Illustrative Location — Not the Actual Property Location" on the website.
    illustrative_label: Mapped[str | None] = mapped_column(String(120))
    illustrative_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    illustrative_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    illustrative_source: Mapped[str | None] = mapped_column(String(250))  # where the coordinates come from (internal)

    buildings: Mapped[list[ReBuilding]] = relationship(back_populates="project", order_by="ReBuilding.code", lazy="selectin")
    payment_plans: Mapped[list[RePaymentPlan]] = relationship(
        back_populates="project", order_by="RePaymentPlan.down_payment_pct", lazy="selectin"
    )


class ReBuilding(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "re_buildings"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_re_buildings_project_code"),
        CheckConstraint("floors > 0 AND floors <= 200", name="floors_range"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_projects.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    floors: Mapped[int] = mapped_column(Integer, nullable=False)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    project: Mapped[ReProject] = relationship(back_populates="buildings")


class ReUnit(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "re_units"
    __table_args__ = (
        UniqueConstraint("building_id", "unit_number", name="uq_re_units_building_number"),
        enum_check("unit_type", UNIT_TYPES),
        enum_check("status", UNIT_STATUSES),
        CheckConstraint("area_sqm > 0", name="area_positive"),
        CheckConstraint("list_price > 0", name="price_positive"),
        CheckConstraint("bedrooms >= 0 AND bedrooms <= 20", name="bedrooms_range"),
        CheckConstraint("bathrooms >= 0 AND bathrooms <= 20", name="bathrooms_range"),
        CheckConstraint("floor >= 0", name="floor_non_negative"),
        Index("ix_re_units_search", "project_id", "status", "bedrooms", "list_price"),
        Index("ix_re_units_building_floor", "building_id", "floor"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_projects.id", ondelete="RESTRICT"), nullable=False)
    building_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_buildings.id", ondelete="RESTRICT"), nullable=False)
    unit_number: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(15), nullable=False)
    bedrooms: Mapped[int] = mapped_column(Integer, nullable=False)
    bathrooms: Mapped[int] = mapped_column(Integer, nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    area_sqm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    view: Mapped[str | None] = mapped_column(String(60))
    list_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="available", server_default="available")
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    project: Mapped[ReProject] = relationship(lazy="joined")
    building: Mapped[ReBuilding] = relationship(lazy="joined")


class RePaymentPlan(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "re_payment_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_re_payment_plans_project_name"),
        enum_check("installment_frequency", FREQUENCIES),
        enum_check("marketing_status", PLAN_MARKETING_STATUSES),
        CheckConstraint("down_payment_pct BETWEEN 0 AND 100", name="down_payment_range"),
        CheckConstraint("handover_pct BETWEEN 0 AND 100", name="handover_range"),
        CheckConstraint("down_payment_pct + handover_pct <= 100", name="shares_within_total"),
        CheckConstraint("installments >= 0 AND installments <= 240", name="installments_range"),
        CheckConstraint("installments > 0 OR down_payment_pct + handover_pct = 100", name="installments_cover_rest"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_projects.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    down_payment_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    installments: Mapped[int] = mapped_column(Integer, nullable=False)
    installment_frequency: Mapped[str] = mapped_column(String(12), nullable=False, default="monthly", server_default="monthly")
    handover_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"), server_default="0")
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Set by a person, never inferred from the plan's name. Only "cleared" plans reach marketing outputs.
    marketing_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unreviewed", server_default="unreviewed")

    project: Mapped[ReProject] = relationship(back_populates="payment_plans")
