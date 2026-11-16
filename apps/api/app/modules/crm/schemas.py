from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Source = Literal["website", "walk_in", "referral", "phone", "campaign", "property_assistant", "social"]
Stage = Literal["new", "contacted", "qualified", "viewing", "negotiation", "won", "lost"]
Timeline = Literal["immediate", "within_3_months", "within_6_months", "over_6_months"]
ActivityType = Literal["note", "call", "email", "whatsapp", "viewing"]
MAX_MONEY = Decimal("9999999999999999.99")


def _budget_ok(lo: Decimal | None, hi: Decimal | None) -> None:
    if lo is not None and hi is not None and hi < lo:
        raise ValueError("Maximum budget must be at least the minimum.")


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    preferred_language: Literal["en", "ar"] = "en"
    source: Source
    interest: str | None = Field(default=None, max_length=300)
    budget_min: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY, decimal_places=2)
    bedrooms_wanted: int | None = Field(default=None, ge=0, le=10)
    consent: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    project_id: uuid.UUID | None = None
    interested_unit_id: uuid.UUID | None = None
    timeline: Timeline | None = None

    @model_validator(mode="after")
    def _checks(self) -> LeadCreate:
        if not self.phone and not self.email:
            raise ValueError("Provide a phone number or an email address.")
        _budget_ok(self.budget_min, self.budget_max)
        return self


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    preferred_language: Literal["en", "ar"] | None = None
    interest: str | None = Field(default=None, max_length=300)
    budget_min: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY, decimal_places=2)
    bedrooms_wanted: int | None = Field(default=None, ge=0, le=10)
    notes: str | None = Field(default=None, max_length=2000)
    project_id: uuid.UUID | None = None
    interested_unit_id: uuid.UUID | None = None
    timeline: Timeline | None = None
    next_follow_up_at: datetime | None = None


class StageChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Stage
    reason: str | None = Field(default=None, max_length=500)


class ActivityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ActivityType
    body: str = Field(min_length=2, max_length=1000)
    occurred_at: datetime | None = None
    next_follow_up_at: datetime | None = None


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_user_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=300)


class Ref(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class UserRef(BaseModel):
    id: uuid.UUID
    full_name: str


class LeadOut(BaseModel):
    id: uuid.UUID
    code: str
    full_name: str
    phone: str | None
    email: str | None
    source: str
    interest: str | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    bedrooms_wanted: int | None
    stage: str
    score: int | None
    grade: str | None
    score_reasons: list[dict[str, object]] | None
    owner: dict[str, str] | None
    assigned_at: datetime | None
    next_follow_up_at: datetime | None
    created_at: datetime
    # Phase 5
    project: Ref | None = None
    interested_unit: Ref | None = None
    timeline: str | None = None
    last_activity_at: datetime | None = None
    follow_up_overdue: bool = False


class ReservationBrief(BaseModel):
    id: uuid.UUID
    code: str
    status: str
    unit: Ref
    expires_at: datetime
    deposit_amount: Decimal | None


class LeadDetail(LeadOut):
    preferred_language: str
    notes: str | None
    consent_given_at: datetime | None
    stage_changed_at: datetime | None
    close_reason: str | None
    created_by: UserRef | None
    allowed_actions: list[str]
    allowed_stages: list[str]
    reservations: list[ReservationBrief]


class ActivityOut(BaseModel):
    id: uuid.UUID
    type: str
    body: str
    performed_by: UserRef | None
    occurred_at: datetime
    reservation_id: uuid.UUID | None


class LeadStats(BaseModel):
    new: int = 0
    contacted: int = 0
    qualified: int = 0
    viewing: int = 0
    negotiation: int = 0
    won: int = 0
    lost: int = 0
    open: int = 0
    overdue: int = 0
    unassigned: int = 0


# --- reservations ---------------------------------------------------------------------------------
class ReservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: uuid.UUID
    unit_id: uuid.UUID
    hours: int = Field(default=72, ge=1, le=720)
    deposit_amount: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)


class ReservationCancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class ReservationOut(BaseModel):
    id: uuid.UUID
    code: str
    status: str
    unit: Ref
    unit_status: str
    list_price: Decimal
    lead: Ref
    lead_owner: UserRef | None
    reserved_by: UserRef | None
    reserved_at: datetime
    expires_at: datetime
    deposit_amount: Decimal | None
    notes: str | None
    cancel_reason: str | None
    cancelled_at: datetime | None
    converted_at: datetime | None
    expired_at: datetime | None
    allowed_actions: list[str] = []


class UnitReservationInfo(BaseModel):
    """What any inventory reader may see about a unit's active reservation; the lead only when visible to them."""

    code: str
    status: str
    reserved_at: datetime
    expires_at: datetime
    reserved_by: str | None
    lead: Ref | None
    reservation_id: uuid.UUID | None
