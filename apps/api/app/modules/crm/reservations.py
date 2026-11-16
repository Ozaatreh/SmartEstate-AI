"""Unit reservations (Phase 5C).

Invariants:
- At most one ``active`` reservation per unit: partial unique index ``uq_unit_reservations_active_unit`` plus the unit
  row lock taken before any check (two concurrent reservations → one succeeds, the other gets 409).
- The reservation, the unit status and the lead stage change in one transaction.
- Lock order is always reservation → unit → lead (create: unit → lead), so concurrent operations can't deadlock.
- Expiry only touches rows that are still ``active`` and past ``expires_at`` (``FOR UPDATE SKIP LOCKED`` + status re-check),
  so a converted or cancelled reservation can never expire.
- Deposits are informational only: nothing is posted to any budget or financial ledger.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automation import events
from app.common.codes import next_code
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, PermissionDenied
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.crm.models import OPEN_STAGES, Lead, UnitReservation
from app.modules.crm.schemas import Ref, ReservationIn, ReservationOut, UnitReservationInfo, UserRef
from app.modules.crm.service import STAGE_ORDER, CRMService, _ref_unit
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService
from app.modules.realestate.models import ReUnit
from app.modules.realestate.service import RealEstateService

ENTITY = "unit_reservation"
SORTABLE = {"reserved_at": UnitReservation.reserved_at, "expires_at": UnitReservation.expires_at, "code": UnitReservation.code}


def _now() -> datetime:
    return datetime.now(UTC)


class ReservationService:
    def __init__(self, session: Session):
        self.session = session
        self.crm = CRMService(session)
        self.inventory = RealEstateService(session)
        self.audit = AuditService(session)

    # ------------------------------------------------------------------ scope
    def _can_operate(self, principal: Principal, lead: Lead) -> bool:
        if not principal.has(Perm.CRM_RESERVATIONS_MANAGE):
            return False
        return principal.has(Perm.CRM_LEADS_MANAGE) or lead.owner_user_id == principal.user_id

    def _ensure_operate(self, principal: Principal, lead: Lead) -> None:
        ensure_permission(principal, Perm.CRM_RESERVATIONS_MANAGE)
        if not self._can_operate(principal, lead):
            raise PermissionDenied("Only the lead's owner or a sales manager can manage its reservations.")

    def _visible(self, principal: Principal, r: UnitReservation) -> bool:
        return (
            principal.has(Perm.CRM_LEADS_READ_ALL)
            or r.lead.owner_user_id == principal.user_id
            or r.reserved_by == principal.user_id
            or r.lead.created_by == principal.user_id
        )

    def _get(self, principal: Principal, reservation_id: uuid.UUID, *, lock: bool = False) -> UnitReservation:
        stmt = select(UnitReservation).where(UnitReservation.id == reservation_id)
        if lock:
            stmt = stmt.with_for_update(of=UnitReservation).execution_options(populate_existing=True)
        r = self.session.scalar(stmt)
        if r is None or not self._visible(principal, r):
            raise NotFound("Reservation not found.")
        return r

    # ------------------------------------------------------------------ create
    def create(self, principal: Principal, data: ReservationIn) -> UnitReservation:
        ensure_permission(principal, Perm.CRM_RESERVATIONS_MANAGE)
        unit = self.inventory.lock_unit(data.unit_id)  # lock order: unit → lead
        lead = self.crm.lock(data.lead_id)
        if not self.crm._visible(principal, lead):
            raise NotFound("Lead not found.")
        self._ensure_operate(principal, lead)
        if lead.stage not in OPEN_STAGES:
            raise BusinessRuleViolation(f"A {lead.stage} lead can't reserve a unit.", code="lead_closed")
        if unit.status != "available":
            raise Conflict(f"Unit {unit.building.code}-{unit.unit_number} is {unit.status}.", code="unit_unavailable")
        if lead.project_id is not None and lead.project_id != unit.project_id:
            raise BusinessRuleViolation("The unit belongs to a different project than the lead.", code="unit_project_mismatch")
        now = _now()
        reservation = UnitReservation(
            code=next_code(self.session, "reservation"),
            unit_id=unit.id,
            lead_id=lead.id,
            reserved_by=principal.user_id,
            reserved_at=now,
            expires_at=now + timedelta(hours=data.hours),
            deposit_amount=data.deposit_amount,
            notes=data.notes,
        )
        self.session.add(reservation)
        try:
            self.session.flush()
        except IntegrityError as exc:  # the partial unique index is the last line of defence
            self.session.rollback()
            raise Conflict("This unit already has an active reservation.", code="unit_unavailable") from exc
        label = f"{unit.building.code}-{unit.unit_number}"
        self.inventory.transition_unit(unit, "reserved", actor_user_id=principal.user_id, reason=f"{reservation.code} for {lead.code}")
        lead.interested_unit_id = unit.id
        if lead.project_id is None:
            lead.project_id = unit.project_id
        deposit = f" · deposit SAR {data.deposit_amount:,.2f} (informational)" if data.deposit_amount else ""
        self.crm._activity(
            lead.id,
            "system",
            f"{reservation.code}: reserved {label} until {reservation.expires_at:%d %b %Y %H:%M} UTC{deposit}",
            dedupe=None,
            actor=principal.user_id,
            reservation_id=reservation.id,
        )
        if STAGE_ORDER.index(lead.stage) < STAGE_ORDER.index("negotiation"):
            self.crm._set_stage(lead, "negotiation", reason=f"Reserved {label}", actor=principal.user_id, reservation_id=reservation.id)
        self._record(principal.user_id, reservation, "created", f"{reservation.code}: {label} for {lead.code} · {data.hours} h{deposit}")
        self.session.commit()
        return reservation

    # ------------------------------------------------------------------ cancel / convert
    def cancel(self, principal: Principal, reservation_id: uuid.UUID, reason: str) -> UnitReservation:
        r = self._get(principal, reservation_id, lock=True)
        self._ensure_operate(principal, r.lead)
        if r.status != "active":
            raise Conflict(f"The reservation is already {r.status}.", code="reservation_not_active")
        unit = self.inventory.lock_unit(r.unit_id)
        self.crm.lock(r.lead_id)
        now = _now()
        r.status, r.cancelled_at, r.cancelled_by, r.cancel_reason = "cancelled", now, principal.user_id, reason.strip()
        self.inventory.transition_unit(unit, "available", actor_user_id=principal.user_id, reason=f"{r.code} cancelled")
        label = f"{unit.building.code}-{unit.unit_number}"
        self.crm._activity(
            r.lead_id,
            "system",
            f"{r.code}: reservation of {label} cancelled — {r.cancel_reason}"[:1000],
            dedupe=None,
            actor=principal.user_id,
            reservation_id=r.id,
        )
        self._record(principal.user_id, r, "cancelled", f"{r.code}: {label} released — {r.cancel_reason}")
        self.session.commit()
        return r

    def convert(self, principal: Principal, reservation_id: uuid.UUID) -> UnitReservation:
        r = self._get(principal, reservation_id, lock=True)
        self._ensure_operate(principal, r.lead)
        if r.status != "active":
            raise Conflict(f"The reservation is already {r.status}.", code="reservation_not_active")
        unit = self.inventory.lock_unit(r.unit_id)
        lead = self.crm.lock(r.lead_id)
        now = _now()
        r.status, r.converted_at, r.converted_by = "converted", now, principal.user_id
        self.inventory.transition_unit(unit, "sold", actor_user_id=principal.user_id, reason=f"{r.code} converted to a sale")
        label = f"{unit.building.code}-{unit.unit_number}"
        self.crm._activity(
            lead.id, "system", f"{r.code}: converted to a sale — {label} sold", dedupe=None, actor=principal.user_id, reservation_id=r.id
        )
        if lead.stage in OPEN_STAGES:
            self.crm._set_stage(lead, "won", reason=f"Bought {label} ({r.code})", actor=principal.user_id, reservation_id=r.id)
        self._record(principal.user_id, r, "converted", f"{r.code}: {label} sold to {lead.code}")
        self.session.commit()
        return r

    # ------------------------------------------------------------------ expiry (system actor, used by crm.reservation_expiry)
    def expire_due(self, *, now: datetime | None = None, limit: int = 200) -> list[dict[str, str]]:
        now = now or _now()
        due = list(
            self.session.scalars(
                select(UnitReservation)
                .where(UnitReservation.status == "active", UnitReservation.expires_at < now)
                .order_by(UnitReservation.expires_at)
                .limit(limit)
                .with_for_update(of=UnitReservation, skip_locked=True)
                .execution_options(populate_existing=True)
            ).unique()
        )
        notifications = NotificationService(self.session)
        done: list[dict[str, str]] = []
        for r in due:
            if r.status != "active" or r.expires_at >= now:  # re-check under the lock
                continue
            unit = self.inventory.lock_unit(r.unit_id)
            lead = self.crm.lock(r.lead_id)
            r.status, r.expired_at = "expired", now
            label = f"{unit.building.code}-{unit.unit_number}"
            if unit.status == "reserved":
                self.inventory.transition_unit(unit, "available", actor_user_id=None, reason=f"{r.code} expired")
            self.crm._activity(
                lead.id,
                "system",
                f"{r.code}: reservation of {label} expired; unit released",
                dedupe=f"reservation:{r.id}:expired",
                reservation_id=r.id,
            )
            recipient = lead.owner_user_id or r.reserved_by
            if recipient:
                notifications.notify(
                    recipient,
                    type="crm.reservation_expired",
                    level="warning",
                    title=f"{r.code} expired",
                    body=f"{label} is available again ({lead.code}).",
                    link=f"/crm/leads/{lead.id}",
                    entity_type="lead",
                    entity_id=str(lead.id),
                    dedupe_key=f"reservation:{r.id}:expired",
                )
            self._record(None, r, "expired", f"{r.code}: {label} released after expiry")
            done.append({"code": r.code, "unit": label, "lead": lead.code})
        return done

    # ------------------------------------------------------------------ reading
    def list(self, principal: Principal, params: ListParams, *, scope: str, status: str | None, lead_id, unit_id):
        if not principal.has_any((Perm.CRM_RESERVATIONS_MANAGE, Perm.CRM_LEADS_READ_ALL, Perm.CRM_LEADS_WORK)):
            raise PermissionDenied(details={"required_permission": Perm.CRM_RESERVATIONS_MANAGE.value})
        stmt = select(UnitReservation).join(Lead, Lead.id == UnitReservation.lead_id)
        if scope == "all":
            ensure_permission(principal, Perm.CRM_LEADS_READ_ALL)
        else:
            stmt = stmt.where(or_(Lead.owner_user_id == principal.user_id, UnitReservation.reserved_by == principal.user_id))
        if status:
            stmt = stmt.where(UnitReservation.status == status)
        if lead_id:
            stmt = stmt.where(UnitReservation.lead_id == lead_id)
        if unit_id:
            stmt = stmt.where(UnitReservation.unit_id == unit_id)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.join(ReUnit, ReUnit.id == UnitReservation.unit_id).where(
                or_(
                    UnitReservation.code.ilike(term, escape="\\"),
                    Lead.code.ilike(term, escape="\\"),
                    Lead.full_name.ilike(term, escape="\\"),
                    ReUnit.unit_number.ilike(term, escape="\\"),
                )
            )
        rows, total, pages = paginate(self.session, apply_sort(stmt, params.sort, SORTABLE, "-reserved_at"), params)
        return [self._out(principal, r) for r in rows], total, pages

    def detail(self, principal: Principal, reservation_id: uuid.UUID) -> ReservationOut:
        return self._out(principal, self._get(principal, reservation_id))

    def for_unit(self, principal: Principal, unit_id: uuid.UUID) -> UnitReservationInfo | None:
        self.inventory.get_unit(principal, unit_id)  # inventory read permission + existence
        r = self.session.scalar(select(UnitReservation).where(UnitReservation.unit_id == unit_id, UnitReservation.status == "active"))
        if r is None:
            return None
        visible = self._visible(principal, r)
        return UnitReservationInfo(
            code=r.code,
            status=r.status,
            reserved_at=r.reserved_at,
            expires_at=r.expires_at,
            reserved_by=r.reserver.full_name if r.reserver else None,
            lead=Ref(id=r.lead.id, code=r.lead.code, name=r.lead.full_name) if visible else None,
            reservation_id=r.id if visible else None,
        )

    def sales_users(self, principal: Principal) -> list[dict]:
        ensure_permission(principal, Perm.CRM_LEADS_MANAGE)
        ids = IdentityRepository(self.session).users_with_permission(Perm.CRM_LEADS_WORK.value)
        users = self.session.scalars(select(User).where(User.id.in_(ids)).order_by(User.full_name)) if ids else []
        return [{"id": str(u.id), "full_name": u.full_name} for u in users]

    def _out(self, principal: Principal, r: UnitReservation) -> ReservationOut:
        owner = r.lead.owner
        actions: list[str] = []
        if r.status == "active" and self._can_operate(principal, r.lead):
            actions = ["cancel", "convert"]
        return ReservationOut(
            id=r.id,
            code=r.code,
            status=r.status,
            unit=_ref_unit(r.unit),
            unit_status=r.unit.status,
            list_price=r.unit.list_price,
            lead=Ref(id=r.lead.id, code=r.lead.code, name=r.lead.full_name),
            lead_owner=UserRef(id=owner.id, full_name=owner.full_name) if owner else None,
            reserved_by=UserRef(id=r.reserver.id, full_name=r.reserver.full_name) if r.reserver else None,
            reserved_at=r.reserved_at,
            expires_at=r.expires_at,
            deposit_amount=r.deposit_amount,
            notes=r.notes,
            cancel_reason=r.cancel_reason,
            cancelled_at=r.cancelled_at,
            converted_at=r.converted_at,
            expired_at=r.expired_at,
            allowed_actions=actions,
        )

    def _record(self, actor: uuid.UUID | None, r: UnitReservation, verb: str, summary: str) -> None:
        self.audit.record(f"crm.reservation_{verb}", actor_user_id=actor, entity_type=ENTITY, entity_id=r.id, summary=summary)
        self.audit.record(f"crm.reservation_{verb}", actor_user_id=actor, entity_type="lead", entity_id=r.lead_id, summary=summary)
        events.emit(
            self.session,
            f"reservation.{verb}",
            entity_type=ENTITY,
            entity_id=r.id,
            actor_user_id=actor,
            payload={"code": r.code, "unit_id": str(r.unit_id), "lead_id": str(r.lead_id), "status": r.status},
        )
