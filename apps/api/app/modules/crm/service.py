from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.automation import events
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.core.errors import BusinessRuleViolation, NotFound, PermissionDenied
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.crm.models import Lead, LeadActivity, SalesAssignmentState
from app.modules.crm.scoring import LeadFacts, score
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService

Source = Literal["website", "walk_in", "referral", "phone", "campaign", "property_assistant", "social"]
SORTABLE = {"created_at": Lead.created_at, "score": Lead.score, "full_name": Lead.full_name}


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    preferred_language: Literal["en", "ar"] = "en"
    source: Source
    interest: str | None = Field(default=None, max_length=300)
    budget_min: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    bedrooms_wanted: int | None = Field(default=None, ge=0, le=10)
    consent: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _checks(self) -> LeadCreate:
        if not self.phone and not self.email:
            raise ValueError("Provide a phone number or an email address.")
        if self.budget_min is not None and self.budget_max is not None and self.budget_max < self.budget_min:
            raise ValueError("Maximum budget must be at least the minimum.")
        return self


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


def lead_out(lead: Lead) -> LeadOut:
    return LeadOut(
        id=lead.id,
        code=lead.code,
        full_name=lead.full_name,
        phone=lead.phone,
        email=lead.email,
        source=lead.source,
        interest=lead.interest,
        budget_min=lead.budget_min,
        budget_max=lead.budget_max,
        bedrooms_wanted=lead.bedrooms_wanted,
        stage=lead.stage,
        score=lead.score,
        grade=lead.grade,
        score_reasons=lead.score_reasons,
        owner={"id": str(lead.owner.id), "full_name": lead.owner.full_name} if lead.owner else None,
        assigned_at=lead.assigned_at,
        next_follow_up_at=lead.next_follow_up_at,
        created_at=lead.created_at,
    )


class CRMService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)

    # --- API --------------------------------------------------------------------------------------
    def create_lead(self, principal: Principal, data: LeadCreate) -> Lead:
        ensure_permission(principal, Perm.CRM_LEADS_CREATE)
        from app.common.codes import next_code

        lead = Lead(
            code=next_code(self.session, "lead"),
            full_name=data.full_name.strip(),
            phone=data.phone,
            email=str(data.email) if data.email else None,
            preferred_language=data.preferred_language,
            source=data.source,
            interest=data.interest,
            budget_min=data.budget_min,
            budget_max=data.budget_max,
            bedrooms_wanted=data.bedrooms_wanted,
            notes=data.notes,
            created_by=principal.user_id,
            consent_given_at=datetime.now(UTC) if data.consent else None,
        )
        self.session.add(lead)
        self.session.flush()
        self.audit.record(
            "crm.lead_created",
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            summary=f"{lead.code} · {lead.full_name} ({lead.source})",
        )
        events.emit(
            self.session,
            "lead.created",
            entity_type="lead",
            entity_id=lead.id,
            actor_user_id=principal.user_id,
            payload={"code": lead.code, "source": lead.source},
        )
        self.session.commit()
        return lead

    def _visible(self, principal: Principal, lead: Lead) -> bool:
        return principal.has(Perm.CRM_LEADS_READ_ALL) or lead.owner_user_id == principal.user_id or lead.created_by == principal.user_id

    def get(self, principal: Principal, lead_id: uuid.UUID) -> Lead:
        lead = self.session.get(Lead, lead_id)
        if lead is None or not self._visible(principal, lead):
            raise NotFound("Lead not found.")
        return lead

    def list(self, principal: Principal, params: ListParams, *, scope: str) -> tuple[list[Lead], int, int]:
        if not principal.has_any((Perm.CRM_LEADS_CREATE, Perm.CRM_LEADS_WORK, Perm.CRM_LEADS_READ_ALL)):
            raise PermissionDenied(details={"required_permission": Perm.CRM_LEADS_WORK.value})
        stmt = select(Lead)
        if scope == "all":
            ensure_permission(principal, Perm.CRM_LEADS_READ_ALL)
        else:
            stmt = stmt.where(or_(Lead.owner_user_id == principal.user_id, Lead.created_by == principal.user_id))
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(Lead.full_name.ilike(term, escape="\\"), Lead.code.ilike(term, escape="\\"), Lead.email.ilike(term, escape="\\"))
            )
        return paginate(self.session, apply_sort(stmt, params.sort, SORTABLE, "-created_at"), params)

    # --- used by the Lead Registration workflow (system actor) ---------------------------------------
    def lock(self, lead_id: uuid.UUID) -> Lead:
        lead = self.session.scalar(
            select(Lead).where(Lead.id == lead_id).with_for_update(of=Lead).execution_options(populate_existing=True)
        )
        if lead is None:
            raise NotFound("Lead not found.")
        return lead

    def apply_score(self, lead_id: uuid.UUID, *, hot: int, warm: int) -> Lead:
        lead = self.lock(lead_id)
        total, grade, reasons = score(
            LeadFacts(
                source=lead.source,
                has_email=bool(lead.email),
                has_phone=bool(lead.phone),
                budget_min=lead.budget_min,
                budget_max=lead.budget_max,
                bedrooms_wanted=lead.bedrooms_wanted,
                consent=lead.consent_given_at is not None,
                interest=bool(lead.interest),
            ),
            hot_threshold=hot,
            warm_threshold=warm,
        )
        changed = (lead.score, lead.grade) != (total, grade)
        lead.score, lead.grade, lead.score_reasons = total, grade, reasons
        if changed:
            self._activity(lead.id, "system", f"Scored {total}/100 ({grade})", dedupe=f"lead:{lead.id}:score:{total}")
            self.audit.record(
                "crm.lead_scored",
                actor_user_id=None,
                entity_type="lead",
                entity_id=lead.id,
                summary=f"{lead.code} scored {total} ({grade})",
            )
        return lead

    def assign_round_robin(self, lead_id: uuid.UUID, *, follow_up_hours: int, pool: str = "default") -> tuple[Lead, bool]:
        """Assigns to the next sales user (holders of crm.leads.work). Idempotent: an owned lead is left alone."""
        lead = self.lock(lead_id)
        if lead.owner_user_id is not None:
            return lead, False
        agents = IdentityRepository(self.session).users_with_permission(Perm.CRM_LEADS_WORK.value)
        if not agents:
            raise BusinessRuleViolation("No active sales users can receive leads (permission crm.leads.work).", code="no_sales_users")
        self.session.execute(insert(SalesAssignmentState).values(pool=pool).on_conflict_do_nothing(index_elements=["pool"]))
        state = self.session.scalar(select(SalesAssignmentState).where(SalesAssignmentState.pool == pool).with_for_update())
        if state is None:  # pragma: no cover - inserted just above
            raise BusinessRuleViolation("Assignment state unavailable.")
        last = state.last_assigned_user_id
        idx = (agents.index(last) + 1) % len(agents) if last in agents else 0
        owner = agents[idx]
        now = datetime.now(UTC)
        lead.owner_user_id, lead.assigned_at, lead.next_follow_up_at = owner, now, now + timedelta(hours=follow_up_hours)
        state.last_assigned_user_id = owner
        self.session.flush()
        self.session.refresh(lead, attribute_names=["owner"])
        self._activity(
            lead.id,
            "assignment",
            f"Assigned to {lead.owner.full_name if lead.owner else owner}; follow up within {follow_up_hours} h",
            dedupe=f"lead:{lead.id}:assigned",
        )
        self.audit.record(
            "crm.lead_assigned",
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            summary=f"{lead.code} assigned round-robin",
            changes={"owner_user_id": str(owner)},
        )
        return lead, True

    def notify_owner(self, lead: Lead) -> bool:
        if lead.owner_user_id is None:
            return False
        NotificationService(self.session).notify(
            lead.owner_user_id,
            type="crm.lead_assigned",
            level="success" if lead.grade == "hot" else "info",
            title=f"New {lead.grade or ''} lead: {lead.full_name}".replace("  ", " "),
            body=f"{lead.code} · score {lead.score}/100 · follow up by {lead.next_follow_up_at:%d %b %H:%M} UTC"
            if lead.next_follow_up_at
            else lead.code,
            entity_type="lead",
            entity_id=str(lead.id),
            dedupe_key=f"lead:{lead.id}:assigned",
        )
        return True

    def _activity(self, lead_id: uuid.UUID, type_: str, body: str, dedupe: str) -> None:
        self.session.execute(
            insert(LeadActivity)
            .values(id=uuid.uuid4(), lead_id=lead_id, type=type_, body=body, dedupe_key=dedupe)
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
        )


__all__ = ["CRMService", "LeadCreate", "LeadOut", "lead_out"]
