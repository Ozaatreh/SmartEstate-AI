"""CRM leads: registration, scoring, round-robin assignment (Phase 3) and the working pipeline (Phase 5).

Data scope (enforced here, not only in the UI):
- visible: ``crm.leads.read_all`` · the lead's owner · the user who registered it;
- workable (edit, stage, activities, follow-up): ``crm.leads.manage`` · or the owner holding ``crm.leads.work``;
- reassignment: ``crm.leads.manage`` only, to an active holder of ``crm.leads.work``.

Personal contact details never go into events, logs or audit summaries — only ids and codes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.util import identity_key

from app.automation import events
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, PermissionDenied
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.crm.models import OPEN_STAGES, Lead, LeadActivity, SalesAssignmentState, UnitReservation
from app.modules.crm.schemas import (
    ActivityIn,
    ActivityOut,
    AssignIn,
    LeadCreate,
    LeadDetail,
    LeadOut,
    LeadStats,
    LeadUpdate,
    Ref,
    ReservationBrief,
    StageChangeIn,
    UserRef,
)
from app.modules.crm.scoring import LeadFacts, score
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService
from app.modules.realestate.repository import RealEstateRepository

SORTABLE = {
    "created_at": Lead.created_at,
    "score": Lead.score,
    "full_name": Lead.full_name,
    "next_follow_up_at": Lead.next_follow_up_at,
    "last_activity_at": Lead.last_activity_at,
}
STAGE_ORDER = ("new", "contacted", "qualified", "viewing", "negotiation", "won")
CONTACT_FIELDS = {"full_name", "phone", "email"}
DEFAULT_FOLLOW_UP_HOURS = 48
UPPER_BUDGET_TOLERANCE = Decimal("1.10")  # only a minimum given → units up to 10% above it fit


def _now() -> datetime:
    return datetime.now(UTC)


def allowed_stage_targets(stage: str) -> list[str]:
    """Forward moves; ``lost`` from any open stage; reopening (to any open stage) only from ``lost``; ``won`` is final."""
    if stage == "lost":
        return list(OPEN_STAGES)
    if stage == "won":
        return []
    idx = STAGE_ORDER.index(stage)
    return [*STAGE_ORDER[idx + 1 :], "lost"]


def _ref_project(lead: Lead) -> Ref | None:
    return Ref(id=lead.project.id, code=lead.project.code, name=lead.project.name) if lead.project else None


def _ref_unit(unit) -> Ref | None:
    if unit is None:
        return None
    return Ref(id=unit.id, code=f"{unit.building.code}-{unit.unit_number}", name=f"{unit.unit_type.title()} · {unit.bedrooms} BR")


def lead_out(lead: Lead) -> LeadOut:
    now = _now()
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
        project=_ref_project(lead),
        interested_unit=_ref_unit(lead.interested_unit),
        timeline=lead.timeline,
        last_activity_at=lead.last_activity_at,
        follow_up_overdue=bool(lead.next_follow_up_at and lead.next_follow_up_at < now and lead.stage in OPEN_STAGES),
    )


class CRMService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)
        self.realestate = RealEstateRepository(session)

    # ================================================================== scope helpers
    def _visible(self, principal: Principal, lead: Lead) -> bool:
        return principal.has(Perm.CRM_LEADS_READ_ALL) or lead.owner_user_id == principal.user_id or lead.created_by == principal.user_id

    def can_work(self, principal: Principal, lead: Lead) -> bool:
        return principal.has(Perm.CRM_LEADS_MANAGE) or (principal.has(Perm.CRM_LEADS_WORK) and lead.owner_user_id == principal.user_id)

    def _ensure_work(self, principal: Principal, lead: Lead) -> None:
        if not self.can_work(principal, lead):
            raise PermissionDenied(
                "Only the lead's owner or a sales manager can work this lead.",
                details={"required_permission": Perm.CRM_LEADS_MANAGE.value},
            )

    def get(self, principal: Principal, lead_id: uuid.UUID) -> Lead:
        lead = self.session.get(Lead, lead_id)
        if lead is None or not self._visible(principal, lead):
            raise NotFound("Lead not found.")
        return lead

    def _get_locked(self, principal: Principal, lead_id: uuid.UUID) -> Lead:
        lead = self.lock(lead_id)
        if not self._visible(principal, lead):
            raise NotFound("Lead not found.")
        return lead

    def _validate_links(self, project_id: uuid.UUID | None, unit_id: uuid.UUID | None) -> uuid.UUID | None:
        """Checks the project / unit exist and agree. Returns the effective project id."""
        if project_id is not None and self.realestate.get_project(project_id) is None:
            raise NotFound("Project not found.")
        if unit_id is not None:
            unit = self.realestate.get_unit(unit_id)
            if unit is None:
                raise NotFound("Unit not found.")
            if project_id is not None and unit.project_id != project_id:
                raise BusinessRuleViolation("The unit belongs to a different project.", code="unit_project_mismatch")
            return unit.project_id
        return project_id

    # ================================================================== create / read
    def create_lead(self, principal: Principal, data: LeadCreate) -> Lead:
        ensure_permission(principal, Perm.CRM_LEADS_CREATE)
        from app.common.codes import next_code

        project_id = self._validate_links(data.project_id, data.interested_unit_id)
        now = _now()
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
            consent_given_at=now if data.consent else None,
            project_id=project_id,
            interested_unit_id=data.interested_unit_id,
            timeline=data.timeline,
            stage_changed_at=now,
        )
        self.session.add(lead)
        self.session.flush()
        self.audit.record(
            "crm.lead_created",
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            summary=f"{lead.code} registered ({lead.source})",
        )
        events.emit(
            self.session,
            "lead.created",
            entity_type="lead",
            entity_id=lead.id,
            actor_user_id=principal.user_id,
            payload={"code": lead.code, "source": lead.source, "project_id": str(project_id) if project_id else None},
        )
        self.session.commit()
        return lead

    def _scope_stmt(self, principal: Principal, scope: str):
        if not principal.has_any((Perm.CRM_LEADS_CREATE, Perm.CRM_LEADS_WORK, Perm.CRM_LEADS_READ_ALL)):
            raise PermissionDenied(details={"required_permission": Perm.CRM_LEADS_WORK.value})
        stmt = select(Lead)
        if scope == "all":
            ensure_permission(principal, Perm.CRM_LEADS_READ_ALL)
        else:
            stmt = stmt.where(or_(Lead.owner_user_id == principal.user_id, Lead.created_by == principal.user_id))
        return stmt

    def list(
        self,
        principal: Principal,
        params: ListParams,
        *,
        scope: str,
        stage: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        overdue: bool | None = None,
        grade: str | None = None,
    ) -> tuple[list[Lead], int, int]:
        stmt = self._scope_stmt(principal, scope)
        if stage == "open":
            stmt = stmt.where(Lead.stage.in_(OPEN_STAGES))
        elif stage:
            stmt = stmt.where(Lead.stage == stage)
        if owner_user_id:
            stmt = stmt.where(Lead.owner_user_id == owner_user_id)
        if project_id:
            stmt = stmt.where(Lead.project_id == project_id)
        if grade:
            stmt = stmt.where(Lead.grade == grade)
        if overdue:
            stmt = stmt.where(Lead.stage.in_(OPEN_STAGES), Lead.next_follow_up_at < func.now())
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    Lead.full_name.ilike(term, escape="\\"),
                    Lead.code.ilike(term, escape="\\"),
                    Lead.email.ilike(term, escape="\\"),
                    Lead.phone.ilike(term, escape="\\"),
                )
            )
        return paginate(self.session, apply_sort(stmt, params.sort, SORTABLE, "-created_at"), params)

    def stats(self, principal: Principal, *, scope: str) -> LeadStats:
        base = self._scope_stmt(principal, scope).subquery()
        rows = self.session.execute(select(base.c.stage, func.count()).group_by(base.c.stage)).all()
        counts = {s: int(n) for s, n in rows}
        overdue, unassigned = self.session.execute(
            select(
                func.count().filter(base.c.stage.in_(OPEN_STAGES), base.c.next_follow_up_at < func.now()),
                func.count().filter(base.c.stage.in_(OPEN_STAGES), base.c.owner_user_id.is_(None)),
            )
        ).one()
        return LeadStats(**counts, open=sum(counts.get(s, 0) for s in OPEN_STAGES), overdue=int(overdue), unassigned=int(unassigned))

    def detail(self, principal: Principal, lead_id: uuid.UUID) -> LeadDetail:
        lead = self.get(principal, lead_id)
        workable = self.can_work(principal, lead)
        reservations = list(
            self.session.scalars(
                select(UnitReservation).where(UnitReservation.lead_id == lead.id).order_by(UnitReservation.reserved_at.desc())
            ).unique()
        )
        actions: list[str] = []
        if workable:
            actions += ["edit", "change_stage", "add_activity"]
            if lead.stage in OPEN_STAGES and principal.has(Perm.CRM_RESERVATIONS_MANAGE):
                actions.append("reserve")
        if principal.has(Perm.CRM_LEADS_MANAGE):
            actions.append("reassign")
        creator = self.session.get(User, lead.created_by) if lead.created_by else None
        return LeadDetail(
            **lead_out(lead).model_dump(),
            preferred_language=lead.preferred_language,
            notes=lead.notes,
            consent_given_at=lead.consent_given_at,
            stage_changed_at=lead.stage_changed_at,
            close_reason=lead.close_reason,
            created_by=UserRef(id=creator.id, full_name=creator.full_name) if creator else None,
            allowed_actions=actions,
            allowed_stages=allowed_stage_targets(lead.stage) if workable else [],
            reservations=[
                ReservationBrief(
                    id=r.id, code=r.code, status=r.status, unit=_ref_unit(r.unit), expires_at=r.expires_at, deposit_amount=r.deposit_amount
                )
                for r in reservations
            ],
        )

    def timeline(self, principal: Principal, lead_id: uuid.UUID) -> list[ActivityOut]:
        lead = self.get(principal, lead_id)
        rows = self.session.execute(
            select(LeadActivity, User.full_name)
            .outerjoin(User, User.id == LeadActivity.performed_by)
            .where(LeadActivity.lead_id == lead.id)
            .order_by(LeadActivity.occurred_at.desc(), LeadActivity.id)
        ).all()
        return [
            ActivityOut(
                id=a.id,
                type=a.type,
                body=a.body,
                performed_by=UserRef(id=a.performed_by, full_name=name) if a.performed_by and name else None,
                occurred_at=a.occurred_at,
                reservation_id=a.reservation_id,
            )
            for a, name in rows
        ]

    # ================================================================== working the lead
    def update(self, principal: Principal, lead_id: uuid.UUID, data: LeadUpdate) -> Lead:
        lead = self._get_locked(principal, lead_id)
        self._ensure_work(principal, lead)
        values = {k: getattr(data, k) for k in data.model_fields_set}
        if "email" in values and values["email"] is not None:
            values["email"] = str(values["email"])
        for required in ("full_name", "preferred_language"):
            if required in values and values[required] is None:
                values.pop(required)
        phone, email = values.get("phone", lead.phone), values.get("email", lead.email)
        if not phone and not email:
            raise BusinessRuleViolation("Keep a phone number or an email address.", code="contact_required")
        lo, hi = values.get("budget_min", lead.budget_min), values.get("budget_max", lead.budget_max)
        if lo is not None and hi is not None and hi < lo:
            raise BusinessRuleViolation("Maximum budget must be at least the minimum.", code="invalid_budget")
        if "next_follow_up_at" in values and values["next_follow_up_at"] is not None:
            follow = values["next_follow_up_at"]
            if follow.tzinfo is None:
                follow = follow.replace(tzinfo=UTC)
            if follow < _now() - timedelta(minutes=5):
                raise BusinessRuleViolation("The follow-up date must be in the future.", code="follow_up_in_past")
            if lead.stage not in OPEN_STAGES:
                raise BusinessRuleViolation("Closed leads have no follow-up.", code="lead_closed")
            values["next_follow_up_at"] = follow
        if "project_id" in values or "interested_unit_id" in values:
            project = values.get("project_id", lead.project_id)
            unit = values.get("interested_unit_id", lead.interested_unit_id)
            if "project_id" in values and "interested_unit_id" not in values and unit is not None:
                current = self.realestate.get_unit(unit)
                if current is not None and project is not None and current.project_id != project:
                    values["interested_unit_id"] = unit = None  # project changed → the unit no longer applies
            values["project_id"] = self._validate_links(project, unit)
        changes: dict[str, object] = {}
        for k, v in values.items():
            old = getattr(lead, k)
            if old != v:
                # Contact details are personal data: record that they changed, not their values.
                changes[k] = "changed" if k in CONTACT_FIELDS else [None if old is None else str(old), None if v is None else str(v)]
                setattr(lead, k, v)
        if changes:
            self.audit.record(
                "crm.lead_updated",
                actor_user_id=principal.user_id,
                entity_type="lead",
                entity_id=lead.id,
                summary=f"{lead.code} updated",
                changes=changes,
            )
            if "next_follow_up_at" in changes and lead.next_follow_up_at:
                self._activity(
                    lead.id,
                    "system",
                    f"Follow-up scheduled for {lead.next_follow_up_at:%d %b %Y %H:%M} UTC",
                    dedupe=None,
                    actor=principal.user_id,
                )
        self.session.commit()
        return lead

    def change_stage(self, principal: Principal, lead_id: uuid.UUID, data: StageChangeIn) -> Lead:
        lead = self._get_locked(principal, lead_id)
        self._ensure_work(principal, lead)
        target, before = data.stage, lead.stage
        if target == before:
            raise Conflict(f"The lead is already {before}.", code="same_stage")
        if target not in allowed_stage_targets(before):
            raise BusinessRuleViolation(f"A lead can't move from {before} to {target}.", code="invalid_transition")
        reason = (data.reason or "").strip()
        if target in ("won", "lost") and len(reason) < 3:
            raise BusinessRuleViolation("Give a reason for closing the lead (at least 3 characters).", code="reason_required")
        if target == "won" and self._active_reservation(lead.id):
            raise BusinessRuleViolation("Convert or cancel the active reservation first.", code="active_reservation")
        self._set_stage(lead, target, reason=reason or None, actor=principal.user_id)
        self.session.commit()
        return lead

    def _set_stage(self, lead: Lead, target: str, *, reason: str | None, actor: uuid.UUID | None, reservation_id=None) -> None:
        """Caller holds the lead lock. Records the transition in the timeline, the audit log and the outbox."""
        before = lead.stage
        now = _now()
        lead.stage, lead.stage_changed_at = target, now
        if target in ("won", "lost"):
            lead.close_reason, lead.next_follow_up_at = reason, None
        elif before == "lost":
            lead.close_reason = None
            lead.next_follow_up_at = now + timedelta(hours=DEFAULT_FOLLOW_UP_HOURS)
        label = f"Stage: {before} → {target}" + (f" — {reason}" if reason else "")
        self._activity(lead.id, "stage_change", label[:1000], dedupe=None, actor=actor, reservation_id=reservation_id)
        self.audit.record(
            "crm.lead_stage_changed",
            actor_user_id=actor,
            entity_type="lead",
            entity_id=lead.id,
            summary=f"{lead.code}: {before} → {target}",
            changes={"stage": [before, target]},
        )
        events.emit(
            self.session,
            "lead.stage_changed",
            entity_type="lead",
            entity_id=lead.id,
            actor_user_id=actor,
            payload={"code": lead.code, "from": before, "to": target},
        )

    def add_activity(self, principal: Principal, lead_id: uuid.UUID, data: ActivityIn) -> LeadActivity:
        lead = self._get_locked(principal, lead_id)
        self._ensure_work(principal, lead)
        now = _now()
        when = data.occurred_at or now
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        if when > now + timedelta(minutes=5):
            raise BusinessRuleViolation("Activities record what already happened; the time can't be in the future.", code="future_activity")
        activity = self._activity(lead.id, data.type, data.body.strip(), dedupe=None, actor=principal.user_id, occurred_at=when)
        if data.next_follow_up_at is not None:
            follow = data.next_follow_up_at if data.next_follow_up_at.tzinfo else data.next_follow_up_at.replace(tzinfo=UTC)
            if follow <= now:
                raise BusinessRuleViolation("The follow-up date must be in the future.", code="follow_up_in_past")
            if lead.stage in OPEN_STAGES:
                lead.next_follow_up_at = follow
        self.audit.record(
            "crm.lead_activity_added",
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            summary=f"{lead.code}: {data.type} logged",
        )
        self.session.commit()
        return activity

    def reassign(self, principal: Principal, lead_id: uuid.UUID, data: AssignIn) -> Lead:
        ensure_permission(principal, Perm.CRM_LEADS_MANAGE)
        lead = self._get_locked(principal, lead_id)
        if data.owner_user_id not in IdentityRepository(self.session).users_with_permission(Perm.CRM_LEADS_WORK.value):
            raise BusinessRuleViolation("The new owner must be an active sales user (crm.leads.work).", code="invalid_owner")
        if lead.owner_user_id == data.owner_user_id:
            raise Conflict("The lead already belongs to this user.", code="same_owner")
        before = lead.owner_user_id
        now = _now()
        lead.owner_user_id, lead.assigned_at = data.owner_user_id, now
        if lead.stage in OPEN_STAGES and lead.next_follow_up_at is None:
            lead.next_follow_up_at = now + timedelta(hours=DEFAULT_FOLLOW_UP_HOURS)
        self.session.flush()
        self.session.refresh(lead, attribute_names=["owner"])
        name = lead.owner.full_name if lead.owner else str(data.owner_user_id)
        reason = (data.reason or "").strip()
        activity = self._activity(
            lead.id, "assignment", f"Reassigned to {name}" + (f" — {reason}" if reason else ""), dedupe=None, actor=principal.user_id
        )
        self.audit.record(
            "crm.lead_reassigned",
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            summary=f"{lead.code} reassigned to {name}",
            changes={"owner_user_id": [str(before) if before else None, str(data.owner_user_id)]},
        )
        events.emit(
            self.session,
            "lead.assigned",
            entity_type="lead",
            entity_id=lead.id,
            actor_user_id=principal.user_id,
            payload={"code": lead.code, "owner_user_id": str(data.owner_user_id), "manual": True},
        )
        NotificationService(self.session).notify(
            data.owner_user_id,
            type="crm.lead_assigned",
            level="info",
            title=f"{lead.code} was assigned to you",
            body=f"Reassigned by a sales manager · stage {lead.stage}",
            link=f"/crm/leads/{lead.id}",
            entity_type="lead",
            entity_id=str(lead.id),
            dedupe_key=f"lead:{lead.id}:reassigned:{activity.id}",
        )
        self.session.commit()
        return lead

    def _active_reservation(self, lead_id: uuid.UUID) -> UnitReservation | None:
        return self.session.scalar(select(UnitReservation).where(UnitReservation.lead_id == lead_id, UnitReservation.status == "active"))

    # ================================================================== used by workflows (system actor)
    def lock(self, lead_id: uuid.UUID) -> Lead:
        lead = self.session.scalar(
            select(Lead).where(Lead.id == lead_id).with_for_update(of=Lead).execution_options(populate_existing=True)
        )
        if lead is None:
            raise NotFound("Lead not found.")
        return lead

    def fitting_units(self, lead: Lead) -> int | None:
        if lead.budget_max is None and lead.budget_min is None:
            return None
        upper = lead.budget_max if lead.budget_max is not None else (lead.budget_min or Decimal(0)) * UPPER_BUDGET_TOLERANCE
        return self.realestate.count_available_fitting(project_id=lead.project_id, upper=upper, lower=None, bedrooms=lead.bedrooms_wanted)

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
                timeline=lead.timeline,
                fitting_units=self.fitting_units(lead),
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

    def assign_round_robin(self, lead_id: uuid.UUID, *, follow_up_hours: int, pool: str | None = None) -> tuple[Lead, bool]:
        """Assigns to the next sales user (holders of crm.leads.work). Idempotent: an owned lead is left alone.

        The round-robin cursor is per pool: the lead's project code, or ``default`` without a project (decision C3)."""
        lead = self.lock(lead_id)
        if lead.owner_user_id is not None:
            return lead, False
        pool = pool or (lead.project.code if lead.project else "default")
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
        now = _now()
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
            summary=f"{lead.code} assigned round-robin (pool {pool})",
            changes={"owner_user_id": str(owner), "pool": pool},
        )
        events.emit(
            self.session,
            "lead.assigned",
            entity_type="lead",
            entity_id=lead.id,
            actor_user_id=None,
            payload={"code": lead.code, "owner_user_id": str(owner), "pool": pool, "manual": False},
        )
        return lead, True

    def notify_owner(self, lead: Lead) -> bool:
        if lead.owner_user_id is None:
            return False
        NotificationService(self.session).notify(
            lead.owner_user_id,
            type="crm.lead_assigned",
            level="success" if lead.grade == "hot" else "info",
            title=f"New {lead.grade or ''} lead: {lead.code}".replace("  ", " "),
            body=f"Score {lead.score}/100 · follow up by {lead.next_follow_up_at:%d %b %H:%M} UTC" if lead.next_follow_up_at else lead.code,
            link=f"/crm/leads/{lead.id}",
            entity_type="lead",
            entity_id=str(lead.id),
            dedupe_key=f"lead:{lead.id}:assigned",
        )
        return True

    def escalate_overdue(self, *, now: datetime | None = None, limit: int = 200) -> list[dict[str, str]]:
        """Follow-up SLA: escalates open leads whose follow-up is overdue to every sales manager (crm.leads.manage)
        and reminds the owner. Deduplicated per lead per day by the activity / notification dedupe keys."""
        now = now or _now()
        day = now.strftime("%Y-%m-%d")
        overdue = list(
            self.session.scalars(
                select(Lead)
                .where(Lead.stage.in_(OPEN_STAGES), Lead.next_follow_up_at.is_not(None), Lead.next_follow_up_at < now)
                .order_by(Lead.next_follow_up_at)
                .limit(limit)
                .with_for_update(of=Lead, skip_locked=True)
            ).unique()
        )
        if not overdue:
            return []
        managers = IdentityRepository(self.session).users_with_permission(Perm.CRM_LEADS_MANAGE.value)
        notifications = NotificationService(self.session)
        done: list[dict[str, str]] = []
        for lead in overdue:
            key = f"lead:{lead.id}:sla:{day}"
            hours = int((now - lead.next_follow_up_at).total_seconds() // 3600)
            inserted = self._activity(lead.id, "system", f"Follow-up overdue by {hours} h — escalated to sales management", dedupe=key)
            if inserted is None:
                continue  # already escalated today
            owner = lead.owner.full_name if lead.owner else "Unassigned"
            for manager in managers:
                if manager == lead.owner_user_id:
                    continue
                notifications.notify(
                    manager,
                    type="crm.follow_up_overdue",
                    level="warning",
                    title=f"Overdue follow-up: {lead.code}",
                    body=f"Owner: {owner} · overdue by {hours} h",
                    link=f"/crm/leads/{lead.id}",
                    entity_type="lead",
                    entity_id=str(lead.id),
                    dedupe_key=key,
                )
            if lead.owner_user_id:
                notifications.notify(
                    lead.owner_user_id,
                    type="crm.follow_up_overdue",
                    level="warning",
                    title=f"Follow-up overdue: {lead.code}",
                    body="Your sales manager has been notified.",
                    link=f"/crm/leads/{lead.id}",
                    entity_type="lead",
                    entity_id=str(lead.id),
                    dedupe_key=key,
                )
            self.audit.record(
                "crm.lead_escalated",
                actor_user_id=None,
                entity_type="lead",
                entity_id=lead.id,
                summary=f"{lead.code} follow-up overdue by {hours} h; escalated to {len(managers)} manager(s)",
            )
            events.emit(
                self.session,
                "lead.follow_up_overdue",
                entity_type="lead",
                entity_id=lead.id,
                actor_user_id=None,
                payload={"code": lead.code, "overdue_hours": hours, "day": day},
            )
            done.append({"code": lead.code, "owner": owner, "overdue_hours": str(hours)})
        return done

    # ================================================================== timeline rows
    def _activity(
        self,
        lead_id: uuid.UUID,
        type_: str,
        body: str,
        *,
        dedupe: str | None,
        actor: uuid.UUID | None = None,
        occurred_at: datetime | None = None,
        reservation_id: uuid.UUID | None = None,
    ) -> LeadActivity | None:
        """Appends a timeline row (idempotent when ``dedupe`` is given) and moves ``last_activity_at`` forward.
        Returns the row, or None when the dedupe key already existed."""
        when = occurred_at or _now()
        row_id = self.session.execute(
            insert(LeadActivity)
            .values(
                id=uuid.uuid4(),
                lead_id=lead_id,
                type=type_,
                body=body,
                dedupe_key=dedupe,
                performed_by=actor,
                occurred_at=when,
                reservation_id=reservation_id,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(LeadActivity.id)
        ).scalar_one_or_none()
        if row_id is None:
            return None
        self.session.execute(
            Lead.__table__.update()
            .where(Lead.id == lead_id)
            .values(
                last_activity_at=case(
                    (or_(Lead.last_activity_at.is_(None), Lead.last_activity_at < when), when), else_=Lead.last_activity_at
                )
            )
        )
        loaded = self.session.identity_map.get(identity_key(Lead, lead_id))
        if loaded is not None:
            self.session.expire(loaded, ["last_activity_at"])
        return self.session.get(LeadActivity, row_id)


__all__ = ["CRMService", "LeadCreate", "LeadOut", "allowed_stage_targets", "lead_out"]
