"""Public website inquiries ("Contact us", "Request a viewing") → CRM leads.

Pipeline (all server-side; the website's own checks are a convenience, never the protection):

1. Strict validation (``InquiryIn``: unknown fields rejected, consent required, phone/e-mail format, dates).
2. Spam signals, answered with the *same* success response so bots learn nothing:
   - a honeypot field humans never see (``website``) must stay empty;
   - a signed form token proves the form was loaded at least ``MIN_FILL_SECONDS`` before submitting.
3. Rate limits per client IP and per contact (phone/e-mail) → 429.
4. Atomic de-duplication: under one PostgreSQL transaction-level advisory lock, an open lead with the same e-mail or
   phone created in the last ``DEDUPE_HOURS`` gets a timeline entry (and its owner a notification); otherwise a new
   ``website`` lead is created, with ``lead.created`` emitted so the existing workflow scores and assigns it. The lock
   serialises concurrent submissions, so two identical requests can't both create a lead. The visitor always gets the
   same response, so the form never reveals whether someone is already a lead.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.modules.audit.service import AuditService
from app.modules.crm.models import OPEN_STAGES, Lead
from app.modules.crm.schemas import LeadCreate
from app.modules.crm.service import CRMService
from app.modules.notifications.service import NotificationService
from app.public import catalog

INQUIRY_LOCK_KEY = 7_220_001  # pg_advisory_xact_lock key reserved for inquiry de-duplication
DEDUPE_HOURS = 24
MIN_FILL_SECONDS = 3
MAX_FORM_AGE_SECONDS = 2 * 60 * 60
MAX_VIEWING_DAYS_AHEAD = 90
PHONE_CHARS = re.compile(r"^[+0-9 ()\-.]{7,40}$")
ACCEPTED_MESSAGE = "Thank you — our sales team will contact you shortly."


class InquiryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["contact", "viewing"]
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=1000)
    project_code: str | None = Field(default=None, max_length=20)
    unit_code: str | None = Field(default=None, max_length=30)
    preferred_date: date | None = None
    preferred_language: Literal["en", "ar"] = "en"
    consent: bool
    website: str = Field(default="", max_length=200)  # honeypot: hidden from people, filled by naive bots
    form_token: str = Field(min_length=10, max_length=200)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if not v:
            return None
        digits = re.sub(r"\D", "", v)
        if not PHONE_CHARS.match(v) or not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid phone number.")
        return v

    @field_validator("email", "message", "project_code", "unit_code", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _rules(self) -> InquiryIn:
        if not self.consent:
            raise ValueError("Please agree to be contacted so we can reply.")
        if not self.phone and not self.email:
            raise ValueError("Provide a phone number or an e-mail address.")
        if self.kind == "contact" and not self.message:
            raise ValueError("Please write a message.")
        if self.kind == "viewing":
            if not self.project_code:
                raise ValueError("Choose the project you'd like to visit.")
            if self.preferred_date is None:
                raise ValueError("Choose a preferred date for the viewing.")
            today = datetime.now(UTC).date()
            if not today <= self.preferred_date <= today + timedelta(days=MAX_VIEWING_DAYS_AHEAD):
                raise ValueError(f"Choose a date within the next {MAX_VIEWING_DAYS_AHEAD} days.")
        return self


class InquiryAccepted(BaseModel):
    status: Literal["received"] = "received"
    message: str = ACCEPTED_MESSAGE


class FormToken(BaseModel):
    token: str
    min_fill_seconds: int = MIN_FILL_SECONDS


# --- form token ---------------------------------------------------------------------------------------------------
def _sign(settings: Settings, issued: int) -> str:
    key = hashlib.sha256(b"inquiry-form:" + settings.secret_key.get_secret_value().encode()).digest()
    return hmac.new(key, str(issued).encode(), hashlib.sha256).hexdigest()[:32]


def issue_token(settings: Settings, now: float | None = None) -> FormToken:
    issued = int(now if now is not None else time.time())
    return FormToken(token=f"{issued}.{_sign(settings, issued)}")


def token_verdict(settings: Settings, token: str, now: float | None = None) -> Literal["ok", "too_fast", "expired", "invalid"]:
    try:
        issued_s, sig = token.split(".", 1)
        issued = int(issued_s)
    except ValueError:
        return "invalid"
    if not hmac.compare_digest(sig, _sign(settings, issued)):
        return "invalid"
    age = (now if now is not None else time.time()) - issued
    if age < MIN_FILL_SECONDS:
        return "too_fast"
    if age > MAX_FORM_AGE_SECONDS:
        return "expired"
    return "ok"


# --- contact keys ---------------------------------------------------------------------------------------------------
def phone_key(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-9:] if len(digits) >= 7 else None


def contact_keys(data: InquiryIn) -> list[str]:
    keys = []
    if data.email:
        keys.append("e:" + str(data.email).lower())
    if pk := phone_key(data.phone):
        keys.append("p:" + pk)
    return keys


# --- the transaction ------------------------------------------------------------------------------------------------
class InquiryService:
    def __init__(self, session: Session):
        self.session = session

    def _resolve(self, data: InquiryIn):
        """Project/unit codes must refer to *published* listings; anything else is a validation error."""
        project = unit = None
        try:
            if data.project_code:
                project = catalog.get_published_project(self.session, data.project_code)
            if data.unit_code:
                unit = catalog.find_unit(self.session, data.unit_code, project.code if project else None)
                project = project or unit.project
        except Exception as exc:  # NotFound → field error, without saying what exists
            field = "unit_code" if data.unit_code and project is not None else "project_code"
            raise ValidationFailed(details={"fields": [{"field": field, "message": "Choose a listing from our website."}]}) from exc
        return project, unit

    def _existing_lead(self, data: InquiryIn) -> Lead | None:
        conditions = []
        if data.email:
            conditions.append(func.lower(Lead.email) == str(data.email).lower())
        if pk := phone_key(data.phone):
            conditions.append(func.right(func.regexp_replace(func.coalesce(Lead.phone, ""), r"\D", "", "g"), 9) == pk)
        since = datetime.now(UTC) - timedelta(hours=DEDUPE_HOURS)
        return self.session.scalars(
            select(Lead)
            .where(or_(*conditions), Lead.stage.in_(OPEN_STAGES), Lead.created_at >= since)
            .order_by(Lead.created_at.desc())
            .limit(1)
            .with_for_update(of=Lead)
        ).first()

    @staticmethod
    def _timeline_text(data: InquiryIn, project, unit) -> str:
        what = "Viewing request" if data.kind == "viewing" else "Contact request"
        where = f" · {project.name}" if project else ""
        unit_txt = f" · unit {catalog.unit_code(unit)}" if unit else ""
        when = f" · preferred date {data.preferred_date.isoformat()}" if data.preferred_date else ""
        msg = f"\n{data.message}" if data.message else ""
        return f"Website {what.lower()}{where}{unit_txt}{when}{msg}"[:1000]

    def submit(self, data: InquiryIn) -> None:
        project, unit = self._resolve(data)
        crm = CRMService(self.session)
        # Serialise de-duplication: concurrent submissions wait here, so the second one sees the first one's lead.
        self.session.execute(select(func.pg_advisory_xact_lock(INQUIRY_LOCK_KEY)))
        existing = self._existing_lead(data)
        text = self._timeline_text(data, project, unit)
        if existing is not None:
            crm._activity(existing.id, "note", text, dedupe=None, actor=None)
            AuditService(self.session).record(
                "public.inquiry_merged",
                actor_user_id=None,
                entity_type="lead",
                entity_id=existing.id,
                summary=f"{existing.code}: repeat website {data.kind} inquiry",
            )
            if existing.owner_user_id:
                NotificationService(self.session).notify(
                    existing.owner_user_id,
                    type="crm.inquiry",
                    level="info",
                    title=f"New website inquiry for {existing.code}",
                    body="The lead sent another inquiry from the website.",
                    link=f"/crm/leads/{existing.id}",
                    entity_type="lead",
                    entity_id=str(existing.id),
                )
        else:
            interest = " · ".join(
                x
                for x in (
                    "Viewing request" if data.kind == "viewing" else "Website inquiry",
                    project.name if project else None,
                    catalog.unit_code(unit) if unit else None,
                )
                if x
            )
            lead = crm.create_lead_from_website(
                LeadCreate(
                    full_name=data.full_name,
                    phone=data.phone,
                    email=data.email,
                    preferred_language=data.preferred_language,
                    source="website",
                    interest=interest[:300],
                    bedrooms_wanted=unit.bedrooms if unit else None,
                    consent=True,
                    project_id=project.id if project else None,
                    interested_unit_id=unit.id if unit else None,
                )
            )
            crm._activity(lead.id, "note", text, dedupe=None, actor=None)
        self.session.commit()  # lead/activity, audit, event and notification together; releases the lock
