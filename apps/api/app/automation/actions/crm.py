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
