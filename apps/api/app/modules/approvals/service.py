"""Generic approval engine (deterministic Python; no AI, no workflow builder).

Rules (ARCHITECTURE.md D-8, D-11):
- Policy band by amount: ≤ 50k department · ≤ 250k + finance · above + executive (data in approval_policies).
- Over-budget documents always also need finance and executive approval.
- Department level goes to the department manager. Escalation: if there is no manager (or no user
  account), or the requester *is* the manager, the step escalates up the manager's reporting line;
  if nobody is found it goes to the pool of `approvals.department.approve` holders.
- Finance / executive levels go to the pool of users holding that level's permission.
- Segregation of duties: requesters never approve their own documents; one person decides at most one
  step per request (also enforced by a unique constraint).
- Decisions lock the approval request row; duplicate or concurrent decisions are refused.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.automation import events
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.common.money import q2
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, PermissionDenied
from app.core.permissions import SUPER_ADMIN_ROLE, Perm
from app.modules.approvals.models import ApprovalDecision, ApprovalPolicy, ApprovalRequest, ApprovalStep
from app.modules.approvals.schemas import (
    ApprovalDetail,
    ApprovalOut,
    DecisionOut,
    PersonRef,
    PolicyOut,
    PolicyStepOut,
    StepOut,
)
from app.modules.approvals.subjects import subject_for
from app.modules.audit.service import AuditService
from app.modules.hr.models import Department, Employee
from app.modules.identity.models import Role, User
from app.modules.identity.principal import Principal
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService

LEVEL_PERMISSION = {
    "department": Perm.APPROVALS_DEPARTMENT.value,
    "finance": Perm.APPROVALS_FINANCE.value,
    "executive": Perm.APPROVALS_EXECUTIVE.value,
}
LEVEL_LABEL = {"department": "Department manager", "finance": "Finance", "executive": "Executive"}
POOL_LABEL = {"department": "Department approvers", "finance": "Finance approvers", "executive": "Executive approvers"}
LEVEL_ORDER = ("department", "finance", "executive")
SORTABLE = {"created_at": ApprovalRequest.created_at, "amount": ApprovalRequest.amount, "code": ApprovalRequest.entity_code}


def _now() -> datetime:
    return datetime.now(UTC)


def _person(user: User | None) -> PersonRef | None:
    return PersonRef(id=user.id, full_name=user.full_name) if user else None


class ApprovalService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)
        self.notifications = NotificationService(session)

    # --- policies ------------------------------------------------------------------------------------
    def policies(self, entity_type: str) -> list[PolicyOut]:
        rows = self.session.scalars(
            select(ApprovalPolicy)
            .where(ApprovalPolicy.entity_type == entity_type, ApprovalPolicy.is_active.is_(True))
            .order_by(ApprovalPolicy.min_amount)
        )
        return [
            PolicyOut(
                id=p.id,
                entity_type=p.entity_type,
                name=p.name,
                min_amount=p.min_amount,
                max_amount=p.max_amount,
                steps=[PolicyStepOut(step_order=s.step_order, level=s.level, label=s.label) for s in p.steps],
            )
            for p in rows
        ]

    def policy_for(self, entity_type: str, amount: Decimal) -> ApprovalPolicy:
        amount = q2(amount)
        policy = self.session.scalar(
            select(ApprovalPolicy)
            .where(
                ApprovalPolicy.entity_type == entity_type,
                ApprovalPolicy.is_active.is_(True),
                or_(ApprovalPolicy.min_amount < amount, and_(ApprovalPolicy.min_amount == 0, amount == 0)),
                or_(ApprovalPolicy.max_amount.is_(None), ApprovalPolicy.max_amount >= amount),
            )
            .order_by(ApprovalPolicy.min_amount.desc())
            .limit(1)
        )
        if policy is None:
            raise BusinessRuleViolation(
                "No approval policy covers this amount. Ask an administrator to configure one.", code="no_approval_policy"
            )
        return policy

    def planned_levels(self, entity_type: str, amount: Decimal, *, over_budget: bool) -> tuple[ApprovalPolicy, list[str]]:
        policy = self.policy_for(entity_type, amount)
        levels = [s.level for s in policy.steps]
        if over_budget:  # D-8: over-budget documents need finance and executive approval
            levels = [lv for lv in LEVEL_ORDER if lv in levels or lv in ("finance", "executive")]
        return policy, levels

    # --- opening --------------------------------------------------------------------------------------
    def open_request(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        entity_code: str,
        title: str,
        amount: Decimal,
        requested_by: uuid.UUID,
        department_id: uuid.UUID,
        over_budget: bool,
        actor_user_id: uuid.UUID,
    ) -> ApprovalRequest:
        """Creates the approval request inside the caller's transaction and activates its first step."""
        policy, levels = self.planned_levels(entity_type, amount, over_budget=over_budget)
        req = ApprovalRequest(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=entity_code,
            title=title,
            amount=q2(amount),
            requested_by=requested_by,
            policy_id=policy.id,
            flags={"over_budget": over_budget, "department_id": str(department_id)},
        )
        for i, level in enumerate(levels, start=1):
            req.steps.append(ApprovalStep(step_order=i, level=level, label=LEVEL_LABEL[level], required_permission=LEVEL_PERMISSION[level]))
        self.session.add(req)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise Conflict("This document already has an open approval request.", code="approval_already_open") from exc
        self.audit.record(
            "approval.requested",
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=f"{entity_code} sent for approval: {', '.join(LEVEL_LABEL[lv] for lv in levels)}",
            changes={"policy": policy.name, "amount": str(req.amount), "over_budget": over_budget},
        )
        self._activate(req, req.steps[0], department_id)
        events.emit(
            self.session,
            "approval.requested",
            entity_type="approval_request",
            entity_id=req.id,
            actor_user_id=actor_user_id,
            payload={
                "subject_type": entity_type,
                "subject_id": str(entity_id),
                "code": entity_code,
                "amount": str(req.amount),
                "levels": levels,
                "over_budget": over_budget,
            },
        )
        return req

    def _activate(self, req: ApprovalRequest, step: ApprovalStep, department_id: uuid.UUID | None) -> None:
        step.status = "pending"
        step.activated_at = _now()
        req.current_step = step.step_order
        deciders = {s.decision.decided_by for s in req.steps if s.decision}
        if step.level == "department":
            assignee, reason = self._department_approver(department_id, req.requested_by, deciders)
            step.assigned_user_id = assignee.id if assignee else None
            step.escalation_reason = reason
        self.session.flush()
        link = subject_for(req.entity_type).link(str(req.entity_id))
        title = f"Approval needed: {req.entity_code}"
        body = f"{req.title} · SAR {req.amount:,.2f} · {step.label} approval"
        recipients = (
            [step.assigned_user_id] if step.assigned_user_id else self._pool_users(step.required_permission, req.requested_by, deciders)
        )
        for uid in recipients:
            self.notifications.notify(
                uid,
                type="approval.requested",
                level="warning",
                title=title,
                body=body,
                link=link,
                entity_type=req.entity_type,
                entity_id=str(req.entity_id),
                dedupe_key=f"approval:{req.id}:step:{step.step_order}",
            )

    def _department_approver(
        self, department_id: uuid.UUID | None, requester: uuid.UUID, deciders: set[uuid.UUID]
    ) -> tuple[User | None, str | None]:
        dept = self.session.get(Department, department_id) if department_id else None
        if dept is None or dept.manager is None:
            return None, "Department has no manager; routed to department approvers."
        candidate: Employee | None = dept.manager
        reasons: list[str] = []
        hops = 0
        while candidate is not None and hops < 20:
            user = candidate.user
            if candidate.is_active and user is not None and user.is_active and user.id != requester and user.id not in deciders:
                return user, ("; ".join(reasons) + f"; escalated to {candidate.full_name}.") if reasons else None
            if user is None or not user.is_active or not candidate.is_active:
                reasons.append(f"{candidate.full_name} has no active user account")
            elif user.id == requester:
                reasons.append("Requester manages the department")
            else:
                reasons.append(f"{candidate.full_name} already decided an earlier step")
            candidate = candidate.manager
            hops += 1
        return None, "; ".join(reasons) + "; routed to department approvers."

    def _pool_users(self, permission: str, requester: uuid.UUID, deciders: set[uuid.UUID]) -> list[uuid.UUID]:
        rows = IdentityRepository(self.session).users_with_permission(permission)
        return [u for u in rows if u != requester and u not in deciders]

    # --- SLA: reminders, escalation, route checks (called by the Purchase Request Approval workflow) ---------------
    def overdue_steps(self, older_than_hours: float, *, assigned_only: bool = False) -> list[ApprovalStep]:
        stmt = (
            select(ApprovalStep)
            .join(ApprovalRequest, ApprovalRequest.id == ApprovalStep.request_id)
            .where(
                ApprovalStep.status == "pending",
                ApprovalRequest.status == "pending",
                ApprovalStep.activated_at < func.clock_timestamp() - func.make_interval(0, 0, 0, 0, 0, 0, older_than_hours * 3600),
            )
            .order_by(ApprovalStep.activated_at)
        )
        if assigned_only:
            stmt = stmt.where(ApprovalStep.assigned_user_id.is_not(None))
        return list(self.session.scalars(stmt).unique())

    def _recipients(self, req: ApprovalRequest, step: ApprovalStep) -> list[uuid.UUID]:
        deciders = {s.decision.decided_by for s in req.steps if s.decision}
        return [step.assigned_user_id] if step.assigned_user_id else self._pool_users(step.required_permission, req.requested_by, deciders)

    def remind(self, step: ApprovalStep, *, day_key: str) -> int:
        """Reminder to whoever must decide the step; at most one per step per day (dedupe)."""
        req = step.request
        hours = int((_now() - step.activated_at).total_seconds() // 3600) if step.activated_at else 0
        recipients = self._recipients(req, step)
        for uid in recipients:
            self.notifications.notify(
                uid,
                type="approval.reminder",
                level="warning",
                title=f"Reminder: {req.entity_code} awaits your decision",
                body=f"{req.title} · SAR {req.amount:,.2f} · waiting {hours} h at {step.label}",
                link=subject_for(req.entity_type).link(str(req.entity_id)),
                entity_type=req.entity_type,
                entity_id=str(req.entity_id),
                dedupe_key=f"approval:{req.id}:step:{step.step_order}:reminder:{day_key}",
            )
        return len(recipients)

    def escalate(self, step_id: uuid.UUID, *, after_hours: float) -> dict[str, str] | None:
        """Moves an overdue personally-assigned step up the assignee's reporting line (or to the level's pool).
        Skips requests that are being decided right now (SKIP LOCKED) and re-checks everything under the lock."""
        req = self.session.scalar(
            select(ApprovalRequest)
            .join(ApprovalStep, ApprovalStep.request_id == ApprovalRequest.id)
            .where(ApprovalStep.id == step_id)
            .with_for_update(of=ApprovalRequest, skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if req is None:
            return None
        self.session.refresh(req, attribute_names=["steps"])
        step = next((s for s in req.steps if s.id == step_id), None)
        if (
            req.status != "pending"
            or step is None
            or step.status != "pending"
            or step.assigned_user_id is None
            or step.activated_at is None
            or (_now() - step.activated_at).total_seconds() < after_hours * 3600
        ):
            return None
        deciders = {s.decision.decided_by for s in req.steps if s.decision}
        previous = step.assignee
        employee = self.session.scalar(select(Employee).where(Employee.user_id == step.assigned_user_id))
        candidate = employee.manager if employee else None
        new_user: User | None = None
        hops = 0
        while candidate is not None and hops < 20:
            u = candidate.user
            if (
                candidate.is_active
                and u is not None
                and u.is_active
                and u.id not in (req.requested_by, step.assigned_user_id)
                and u.id not in deciders
            ):
                new_user = u
                break
            candidate, hops = candidate.manager, hops + 1
        target = new_user.full_name if new_user else POOL_LABEL[step.level]
        note = f"Escalated after {int(after_hours)} h without a decision: {previous.full_name if previous else 'assignee'} → {target}."
        step.assigned_user_id = new_user.id if new_user else None
        step.escalation_reason = f"{step.escalation_reason}; {note}" if step.escalation_reason else note
        step.activated_at = _now()  # the SLA restarts for the new approver
        self.session.flush()
        self.session.refresh(step, attribute_names=["assignee"])
        self.audit.record(
            "approval.escalated",
            actor_user_id=None,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            summary=f"{req.entity_code}: {note}",
            changes={"step": step.step_order, "to": target},
        )
        link = subject_for(req.entity_type).link(str(req.entity_id))
        for uid in self._recipients(req, step):
            self.notifications.notify(
                uid,
                type="approval.escalated",
                level="warning",
                title=f"Escalated to you: {req.entity_code}",
                body=f"{req.title} · SAR {req.amount:,.2f} · {note}",
                link=link,
                entity_type=req.entity_type,
                entity_id=str(req.entity_id),
                dedupe_key=f"approval:{req.id}:step:{step.step_order}:escalated:{target}",
            )
        if previous is not None:
            self.notifications.notify(
                previous.id,
                type="approval.escalated_away",
                level="info",
                title=f"{req.entity_code} was escalated",
                body=note,
                link=link,
                entity_type=req.entity_type,
                entity_id=str(req.entity_id),
                dedupe_key=f"approval:{req.id}:step:{step.step_order}:escalated_from:{previous.id}",
            )
        return {"code": req.entity_code, "step": step.label, "from": previous.full_name if previous else "—", "to": target}

    def verify_route(self, approval_id: uuid.UUID) -> dict[str, object]:
        """Checks the open step can actually be decided: an active assigned user, or at least one eligible pool member."""
        req = self.session.get(ApprovalRequest, approval_id)
        if req is None or req.status != "pending" or req.current_step is None:
            return {"status": "closed"}
        step = next(s for s in req.steps if s.step_order == req.current_step)
        if step.assigned_user_id is not None:
            if step.assignee is not None and step.assignee.is_active:
                return {"status": "ok", "code": req.entity_code, "step": step.label, "approvers": 1, "assignee": step.assignee.full_name}
            step.assigned_user_id = None
            step.escalation_reason = (
                step.escalation_reason + "; " if step.escalation_reason else ""
            ) + "Assigned approver is inactive; routed to pool."
            self.audit.record(
                "approval.rerouted",
                actor_user_id=None,
                entity_type=req.entity_type,
                entity_id=req.entity_id,
                summary=f"{req.entity_code}: assigned approver inactive; routed to {POOL_LABEL[step.level].lower()}",
            )
        recipients = self._recipients(req, step)
        return {"status": "ok" if recipients else "no_approvers", "code": req.entity_code, "step": step.label, "approvers": len(recipients)}

    # --- deciding ----------------------------------------------------------------------------------------
    def eligibility(self, principal: Principal, req: ApprovalRequest) -> tuple[bool, str | None]:
        if req.status != "pending" or req.current_step is None:
            return False, "This request is no longer awaiting a decision."
        step = next(s for s in req.steps if s.step_order == req.current_step)
        if req.requested_by == principal.user_id:
            return False, "You can't approve a request you submitted."
        if any(s.decision and s.decision.decided_by == principal.user_id for s in req.steps):
            return False, "You already decided an earlier step of this request."
        if step.assigned_user_id is not None:
            if step.assigned_user_id == principal.user_id or principal.is_super_admin:
                return True, None
            return False, f"Waiting on {step.assignee.full_name if step.assignee else 'the assigned approver'}."
        if principal.has(step.required_permission):
            return True, None
        return False, f"Waiting on {POOL_LABEL[step.level].lower()}."

    def approve(self, principal: Principal, approval_id: uuid.UUID, comment: str | None) -> ApprovalRequest:
        return self._decide(principal, approval_id, "approved", (comment or "").strip() or None)

    def reject(self, principal: Principal, approval_id: uuid.UUID, comment: str) -> ApprovalRequest:
        if not comment or not comment.strip():
            raise BusinessRuleViolation("Add a comment explaining the rejection.", code="comment_required")
        return self._decide(principal, approval_id, "rejected", comment.strip())

    def _decide(self, principal: Principal, approval_id: uuid.UUID, decision: str, comment: str | None) -> ApprovalRequest:
        req = self.session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update(of=ApprovalRequest)
            .execution_options(populate_existing=True)
        )
        if req is None or not self._can_view(principal, req):
            raise NotFound("Approval request not found.")
        self.session.refresh(req, attribute_names=["steps"])
        if req.status != "pending":
            raise Conflict("This request has already been decided.", code="already_decided")
        ok, reason = self.eligibility(principal, req)
        if not ok:
            raise PermissionDenied(reason or "You can't decide this step.", code="not_eligible_approver")
        step = next(s for s in req.steps if s.step_order == req.current_step)
        now = _now()
        self.session.add(
            ApprovalDecision(step_id=step.id, request_id=req.id, decided_by=principal.user_id, decision=decision, comment=comment)
        )
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict("This step was already decided.", code="already_decided") from exc
        step.status, step.decided_at = decision, now
        self.session.refresh(step, attribute_names=["decision"])
        subject = subject_for(req.entity_type)
        link = subject.link(str(req.entity_id))
        audit_kw = {"actor_user_id": principal.user_id, "entity_type": req.entity_type, "entity_id": req.entity_id}
        as_admin = principal.is_super_admin and step.assigned_user_id not in (None, principal.user_id)

        if decision == "rejected":
            for s in req.steps:
                if s.status == "waiting":
                    s.status = "skipped"
            req.status, req.current_step, req.completed_at = "rejected", None, now
            self.audit.record(
                "approval.rejected",
                **audit_kw,
                summary=f"{step.label} rejected {req.entity_code}: {comment}",
                changes={"step": step.step_order, "level": step.level, "override_by_super_admin": as_admin},
            )
            subject.on_rejected(self.session, req, principal, comment or "")
            self.notifications.notify(
                req.requested_by,
                type="approval.rejected",
                level="danger",
                title=f"{req.entity_code} was rejected",
                body=f"{principal.full_name} ({step.label}): {comment}",
                link=link,
                entity_type=req.entity_type,
                entity_id=str(req.entity_id),
                dedupe_key=f"approval:{req.id}:rejected",
            )
        else:
            self.audit.record(
                "approval.step_approved",
                **audit_kw,
                summary=f"{step.label} approved {req.entity_code}" + (f": {comment}" if comment else ""),
                changes={"step": step.step_order, "level": step.level, "override_by_super_admin": as_admin},
            )
            nxt = next((s for s in req.steps if s.status == "waiting"), None)
            if nxt is not None:
                dept_id = self._entity_department(req)
                self._activate(req, nxt, dept_id)
                self.notifications.notify(
                    req.requested_by,
                    type="approval.progress",
                    level="info",
                    title=f"{req.entity_code} moved to {nxt.label}",
                    body=f"Approved by {principal.full_name} ({step.label}).",
                    link=link,
                    entity_type=req.entity_type,
                    entity_id=str(req.entity_id),
                    dedupe_key=f"approval:{req.id}:progress:{step.step_order}",
                )
            else:
                req.status, req.current_step, req.completed_at = "approved", None, now
                self.audit.record("approval.completed", **audit_kw, summary=f"{req.entity_code} fully approved")
                subject.on_approved(self.session, req, principal)
                self.notifications.notify(
                    req.requested_by,
                    type="approval.approved",
                    level="success",
                    title=f"{req.entity_code} was approved",
                    body=f"Final approval by {principal.full_name} ({step.label}).",
                    link=link,
                    entity_type=req.entity_type,
                    entity_id=str(req.entity_id),
                    dedupe_key=f"approval:{req.id}:approved",
                )
        events.emit(
            self.session,
            "approval.decided",
            entity_type="approval_request",
            entity_id=req.id,
            actor_user_id=principal.user_id,
            payload={
                "subject_type": req.entity_type,
                "subject_id": str(req.entity_id),
                "code": req.entity_code,
                "decision": decision,
                "step": step.step_order,
                "level": step.level,
                "request_status": req.status,
            },
        )
        self.session.commit()
        return req

    def _entity_department(self, req: ApprovalRequest) -> uuid.UUID | None:
        return req.flags.get("department_id") and uuid.UUID(req.flags["department_id"])

    # --- reading ------------------------------------------------------------------------------------------
    def _can_view(self, principal: Principal, req: ApprovalRequest) -> bool:
        if principal.has(Perm.APPROVALS_READ_ALL) or req.requested_by == principal.user_id:
            return True
        return any(
            s.assigned_user_id == principal.user_id
            or (s.decision and s.decision.decided_by == principal.user_id)
            or (s.assigned_user_id is None and s.status == "pending" and principal.has(s.required_permission))
            for s in req.steps
        )

    def _inbox_filter(self, principal: Principal):
        """Pending steps this principal may decide now."""
        step_ok = [ApprovalStep.status == "pending"]
        if not principal.is_super_admin:
            step_ok.append(
                or_(
                    ApprovalStep.assigned_user_id == principal.user_id,
                    and_(ApprovalStep.assigned_user_id.is_(None), ApprovalStep.required_permission.in_(sorted(principal.permissions))),
                )
            )
        already = exists().where(ApprovalDecision.request_id == ApprovalRequest.id, ApprovalDecision.decided_by == principal.user_id)
        return and_(
            ApprovalRequest.status == "pending",
            ApprovalRequest.requested_by != principal.user_id,
            ~already,
            exists().where(
                ApprovalStep.request_id == ApprovalRequest.id, ApprovalStep.step_order == ApprovalRequest.current_step, *step_ok
            ),
        )

    def pending_count(self, principal: Principal) -> int:
        return self.session.scalar(select(func.count()).select_from(ApprovalRequest).where(self._inbox_filter(principal))) or 0

    def list(self, principal: Principal, params: ListParams, *, box: str, status: str | None = None) -> tuple[list[ApprovalOut], int, int]:
        stmt = select(ApprovalRequest).join(User, User.id == ApprovalRequest.requested_by).options(selectinload(ApprovalRequest.steps))
        if box == "pending":
            stmt = stmt.where(self._inbox_filter(principal))
        elif box == "decided":
            stmt = stmt.where(
                exists().where(ApprovalDecision.request_id == ApprovalRequest.id, ApprovalDecision.decided_by == principal.user_id)
            )
        elif box == "mine":
            stmt = stmt.where(ApprovalRequest.requested_by == principal.user_id)
        elif box == "all" and not principal.has(Perm.APPROVALS_READ_ALL):
            raise PermissionDenied(details={"required_permission": Perm.APPROVALS_READ_ALL.value})
        if status:
            stmt = stmt.where(ApprovalRequest.status == status)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    ApprovalRequest.entity_code.ilike(term, escape="\\"),
                    ApprovalRequest.title.ilike(term, escape="\\"),
                    User.full_name.ilike(term, escape="\\"),
                )
            )
        stmt = apply_sort(stmt, params.sort, SORTABLE, "-created_at" if box != "pending" else "created_at")
        rows, total, pages = paginate(self.session, stmt, params)
        return [self._out(principal, r) for r in rows], total, pages

    def get(self, principal: Principal, approval_id: uuid.UUID) -> ApprovalDetail:
        req = self.session.get(ApprovalRequest, approval_id)
        if req is None or not self._can_view(principal, req):
            raise NotFound("Approval request not found.")
        return self.detail(principal, req)

    def latest_for_entity(self, entity_type: str, entity_id: uuid.UUID) -> ApprovalRequest | None:
        return self.session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.entity_type == entity_type, ApprovalRequest.entity_id == entity_id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        )

    def detail(self, principal: Principal, req: ApprovalRequest) -> ApprovalDetail:
        base = self._out(principal, req)
        ok, reason = self.eligibility(principal, req)
        steps = [
            StepOut(
                step_order=s.step_order,
                level=s.level,
                label=s.label,
                status=s.status,
                assignee=_person(s.assignee),
                pool_label=POOL_LABEL[s.level] if s.assigned_user_id is None and s.status in ("pending", "waiting") else None,
                escalation_reason=s.escalation_reason,
                activated_at=s.activated_at,
                decided_at=s.decided_at,
                decision=DecisionOut(
                    decision=s.decision.decision,
                    comment=s.decision.comment,
                    decided_by=_person(s.decision.decider),  # type: ignore[arg-type]
                    created_at=s.decision.created_at,
                )
                if s.decision
                else None,
            )
            for s in req.steps
        ]
        return ApprovalDetail(
            **base.model_dump(),
            policy_name=req.policy.name,
            steps=steps,
            allowed_actions=["approve", "reject"] if ok else [],
            blocked_reason=None if ok else reason,
        )

    def _out(self, principal: Principal, req: ApprovalRequest) -> ApprovalOut:
        subject = subject_for(req.entity_type)
        current = next((s for s in req.steps if s.step_order == req.current_step), None)
        waiting = None
        if current is not None:
            waiting = current.assignee.full_name if current.assignee else POOL_LABEL[current.level]
        ok, _ = self.eligibility(principal, req)
        return ApprovalOut(
            id=req.id,
            entity_type=req.entity_type,
            entity_label=subject.label,
            entity_id=req.entity_id,
            entity_code=req.entity_code,
            title=req.title,
            amount=req.amount,
            status=req.status,
            flags=req.flags,
            requester=_person(req.requester),  # type: ignore[arg-type]
            current_step=req.current_step,
            current_step_label=current.label if current else None,
            waiting_on=waiting,
            link=subject.link(str(req.entity_id)),
            created_at=req.created_at,
            completed_at=req.completed_at,
            can_decide=ok,
        )


__all__ = ["ApprovalService", "SUPER_ADMIN_ROLE", "Role"]
