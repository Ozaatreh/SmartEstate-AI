from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

MAX_MONEY = Decimal("9999999999999999.99")
ProjectStatus = Literal["planning", "launched", "under_construction", "completed"]
UnitType = Literal["studio", "apartment", "duplex", "penthouse", "townhouse"]
UnitStatus = Literal["available", "reserved", "sold", "blocked"]
Frequency = Literal["monthly", "quarterly", "semi_annual", "annual"]
MarketingStatus = Literal["unreviewed", "cleared", "excluded"]
CODE = r"^[A-Za-z0-9][A-Za-z0-9\-]*$"


def clean_amenities(values: list[str]) -> list[str]:
    out = [a.strip() for a in values if a.strip()]
    if any(len(a) > 80 for a in out):
        raise ValueError("Each amenity is at most 80 characters.")
    return list(dict.fromkeys(out))


LOCAL_MEDIA_FILE = r"^[A-Za-z0-9][A-Za-z0-9_\-]*(/[A-Za-z0-9][A-Za-z0-9_\-.]*)*\.(jpg|jpeg|png|webp)$"


class MediaItem(BaseModel):
    """A project media entry: either a web link (``url``) or an uploaded image (``file`` under COLLATERAL_MEDIA_DIR,
    see docs/MARKETING_ASSETS.md). An uploaded image is used by brochures/posters and shown on the website only once
    approved with its source and licence; its file path is never exposed by the public API."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl | None = None
    file: str | None = Field(default=None, max_length=200, pattern=LOCAL_MEDIA_FILE)
    caption: str | None = Field(default=None, max_length=150)
    kind: Literal["image", "video", "brochure", "tour"] = "image"
    approved: bool | None = None
    source: str | None = Field(default=None, max_length=150)
    licence: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def _one_target(self) -> MediaItem:
        if (self.url is None) == (self.file is None):
            raise ValueError("Each media item needs either a web link or a local file, not both.")
        if self.file is not None and self.kind != "image":
            raise ValueError("Local media files must be images.")
        if self.file is not None and ".." in self.file.split("/"):
            raise ValueError("Invalid local file path.")
        if self.approved and not ((self.source or "").strip() and (self.licence or "").strip()):
            raise ValueError("An approved image needs its source and licence.")
        return self

    def stored(self) -> dict:
        """JSON stored on the project: only the fields that are set, so existing entries round-trip unchanged."""
        return self.model_dump(mode="json", exclude_none=True)


# --- projects -------------------------------------------------------------------------------------
class ProjectRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=20, pattern=CODE)
    name: str = Field(min_length=2, max_length=150)
    city: str = Field(min_length=2, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    status: ProjectStatus = "planning"
    launch_date: date | None = None
    handover_date: date | None = None
    amenities: list[str] = Field(default_factory=list, max_length=40)
    media: list[MediaItem] = Field(default_factory=list, max_length=30)
    is_published: bool = False
    # Phase 7D location (optional). Coordinates must come as a pair; "verified" needs coordinates.
    address: str | None = Field(default=None, max_length=250)
    country: str | None = Field(default=None, max_length=80)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    location_verified: bool = False
    # Illustrative map point (optional): a labelled reference place, never the property's address.
    illustrative_label: str | None = Field(default=None, max_length=120)
    illustrative_latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    illustrative_longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    illustrative_source: str | None = Field(default=None, max_length=250)

    @field_validator("amenities")
    @classmethod
    def _amenities(cls, v: list[str]) -> list[str]:
        return clean_amenities(v)

    @model_validator(mode="after")
    def _dates(self) -> ProjectIn:
        if self.launch_date and self.handover_date and self.handover_date < self.launch_date:
            raise ValueError("Handover cannot be before launch.")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=150)
    city: str | None = Field(default=None, min_length=2, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    status: ProjectStatus | None = None
    launch_date: date | None = None
    handover_date: date | None = None
    amenities: list[str] | None = Field(default=None, max_length=40)
    media: list[MediaItem] | None = Field(default=None, max_length=30)
    is_published: bool | None = None
    address: str | None = Field(default=None, max_length=250)
    country: str | None = Field(default=None, max_length=80)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    location_verified: bool | None = None
    illustrative_label: str | None = Field(default=None, max_length=120)
    illustrative_latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    illustrative_longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    illustrative_source: str | None = Field(default=None, max_length=250)

    @field_validator("amenities")
    @classmethod
    def _amenities(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else clean_amenities(v)


class StatusCounts(BaseModel):
    available: int = 0
    reserved: int = 0
    sold: int = 0
    blocked: int = 0
    total: int = 0


class ProjectOut(ProjectRef):
    city: str
    district: str | None
    status: str
    launch_date: date | None
    handover_date: date | None
    is_demo_data: bool
    is_published: bool
    building_count: int
    units: StatusCounts
    price_from: Decimal | None
    price_to: Decimal | None


class BuildingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name: str
    floors: int
    is_demo_data: bool
    units: StatusCounts = StatusCounts()


class PaymentPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    down_payment_pct: Decimal
    installments: int
    installment_frequency: str
    handover_pct: Decimal
    description: str | None
    is_active: bool
    is_demo_data: bool
    marketing_status: MarketingStatus


class ProjectDetail(ProjectOut):
    description: str | None
    amenities: list[str]
    media: list[dict]
    buildings: list[BuildingOut]
    payment_plans: list[PaymentPlanOut]
    address: str | None
    country: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    location_verified: bool
    location_verified_at: datetime | None
    location_verified_by: str | None  # full name
    illustrative_label: str | None
    illustrative_latitude: Decimal | None
    illustrative_longitude: Decimal | None
    illustrative_source: str | None
    can_manage: bool
    created_at: datetime


# --- buildings ------------------------------------------------------------------------------------
class BuildingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=20, pattern=CODE)
    name: str = Field(min_length=2, max_length=120)
    floors: int = Field(ge=1, le=200)


class BuildingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    floors: int | None = Field(default=None, ge=1, le=200)


# --- payment plans --------------------------------------------------------------------------------
class PaymentPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    down_payment_pct: Decimal = Field(ge=0, le=100, decimal_places=2)
    installments: int = Field(ge=0, le=240)
    installment_frequency: Frequency = "monthly"
    handover_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True
    marketing_status: MarketingStatus = "unreviewed"

    @model_validator(mode="after")
    def _shares(self) -> PaymentPlanIn:
        if self.down_payment_pct + self.handover_pct > 100:
            raise ValueError("Down payment and handover shares cannot exceed 100%.")
        if self.installments == 0 and self.down_payment_pct + self.handover_pct != 100:
            raise ValueError("Without installments, down payment and handover must add up to 100%.")
        return self


class PaymentPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    down_payment_pct: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    installments: int | None = Field(default=None, ge=0, le=240)
    installment_frequency: Frequency | None = None
    handover_pct: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None
    marketing_status: MarketingStatus | None = None


class PlanBreakdown(BaseModel):
    plan_id: uuid.UUID
    name: str
    down_payment_pct: Decimal
    down_payment: Decimal
    installments: int
    installment_frequency: str
    installment_amount: Decimal | None
    last_installment_amount: Decimal | None
    handover_pct: Decimal
    handover_payment: Decimal
    total: Decimal


# --- units ----------------------------------------------------------------------------------------
class UnitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_id: uuid.UUID
    unit_number: str = Field(min_length=1, max_length=20, pattern=CODE)
    unit_type: UnitType
    bedrooms: int = Field(ge=0, le=20)
    bathrooms: int = Field(ge=0, le=20)
    floor: int = Field(ge=0, le=200)
    area_sqm: Decimal = Field(gt=0, le=Decimal("99999999.99"), decimal_places=2)
    view: str | None = Field(default=None, max_length=60)
    list_price: Decimal = Field(gt=0, le=MAX_MONEY, decimal_places=2)
    status: Literal["available", "blocked"] = "available"
    is_public: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class UnitUpdate(BaseModel):
    """``status`` can only toggle available ↔ blocked; reserved / sold come from reservations."""

    model_config = ConfigDict(extra="forbid")

    unit_type: UnitType | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    bathrooms: int | None = Field(default=None, ge=0, le=20)
    floor: int | None = Field(default=None, ge=0, le=200)
    area_sqm: Decimal | None = Field(default=None, gt=0, le=Decimal("99999999.99"), decimal_places=2)
    view: str | None = Field(default=None, max_length=60)
    list_price: Decimal | None = Field(default=None, gt=0, le=MAX_MONEY, decimal_places=2)
    status: UnitStatus | None = None
    is_public: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BuildingRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class UnitOut(BaseModel):
    id: uuid.UUID
    project: ProjectRef
    building: BuildingRef
    unit_number: str
    unit_type: str
    bedrooms: int
    bathrooms: int
    floor: int
    area_sqm: Decimal
    view: str | None
    list_price: Decimal
    price_per_sqm: Decimal
    status: str
    is_public: bool
    is_demo_data: bool


class UnitDetail(UnitOut):
    notes: str | None
    payment_plans: list[PlanBreakdown]
    allowed_status_changes: list[str]
    can_manage: bool
    created_at: datetime
    updated_at: datetime


# --- availability grid ----------------------------------------------------------------------------
class GridUnit(BaseModel):
    id: uuid.UUID
    unit_number: str
    unit_type: str
    bedrooms: int
    area_sqm: Decimal
    list_price: Decimal
    status: str


class GridFloor(BaseModel):
    floor: int
    units: list[GridUnit]


class GridBuilding(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    floors: int
    units: StatusCounts
    rows: list[GridFloor]


class Availability(BaseModel):
    project: ProjectRef
    totals: StatusCounts
    buildings: list[GridBuilding]
