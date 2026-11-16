from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.automation.contracts import ActionContext
from app.automation.registry import action
from app.modules.crm.service import CRMService


class ScoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: uuid.UUID
    hot_score: int = Field(ge=0, le=100)
    warm_score: int = Field(ge=0, le=100)


@action(
    "crm.score_lead",
    label="Score lead",
    input_model=ScoreIn,
    description="Deterministic points for source, completeness, budget and consent.",
)
def score_lead(ctx: ActionContext, data: ScoreIn) -> dict:
    lead = CRMService(ctx.session).apply_score(data.lead_id, hot=data.hot_score, warm=data.warm_score)
    ctx.log.info(f"{lead.code} scored {lead.score}/100 ({lead.grade})", reasons=lead.score_reasons)
    return {"lead_code": lead.code, "score": lead.score, "grade": lead.grade, "reasons": lead.score_reasons}


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: uuid.UUID
    follow_up_hours: int = Field(ge=1, le=720)


@action(
    "crm.assign_lead",
    label="Assign lead (round-robin)",
    input_model=AssignIn,
    description="Assigns the lead to the next sales user and sets the follow-up deadline. Leaves owned leads unchanged.",
)
def assign_lead(ctx: ActionContext, data: AssignIn) -> dict:
    lead, changed = CRMService(ctx.session).assign_round_robin(data.lead_id, follow_up_hours=data.follow_up_hours)
    owner = lead.owner.full_name if lead.owner else None
    ctx.log.info(f"{lead.code} {'assigned to' if changed else 'already owned by'} {owner}")
    return {
        "owner": owner,
        "owner_user_id": str(lead.owner_user_id) if lead.owner_user_id else None,
        "newly_assigned": changed,
        "next_follow_up_at": lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else None,
    }


class NotifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: uuid.UUID


@action("crm.notify_lead_owner", label="Notify lead owner", input_model=NotifyIn)
def notify_owner(ctx: ActionContext, data: NotifyIn) -> dict:
    svc = CRMService(ctx.session)
    return {"notified": svc.notify_owner(svc.lock(data.lead_id))}


# --- Phase 5: follow-up SLA and reservation expiry ---------------------------------------------------
class EscalateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_leads: int = Field(default=200, ge=1, le=1000)


@action(
    "crm.escalate_overdue",
    label="Escalate overdue follow-ups",
    input_model=EscalateIn,
    description="Escalates open leads whose follow-up date has passed to sales management and reminds the owner. "
    "Deduplicated per lead per day.",
)
def escalate_overdue(ctx: ActionContext, data: EscalateIn) -> dict:
    done = CRMService(ctx.session).escalate_overdue(limit=data.max_leads)
    for d in done:
        ctx.log.info(f"{d['code']}: follow-up overdue by {d['overdue_hours']} h — escalated (owner {d['owner']})")
    if not done:
        ctx.log.info("No new overdue follow-ups to escalate")
    return {"escalated": len(done), "leads": [d["code"] for d in done]}


class ExpireIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_size: int = Field(default=200, ge=1, le=1000)


@action(
    "crm.expire_reservations",
    label="Expire overdue reservations",
    input_model=ExpireIn,
    description="Expires active reservations past their expiry time, releases each unit and notifies the lead owner. "
    "Converted or cancelled reservations are never touched.",
)
def expire_reservations(ctx: ActionContext, data: ExpireIn) -> dict:
    from app.modules.crm.reservations import ReservationService

    done = ReservationService(ctx.session).expire_due(limit=data.batch_size)
    for d in done:
        ctx.log.info(f"{d['code']}: expired; {d['unit']} released ({d['lead']})")
    if not done:
        ctx.log.info("No reservations due for expiry")
    return {"expired": len(done), "reservations": [d["code"] for d in done]}
