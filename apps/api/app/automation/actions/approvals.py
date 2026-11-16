from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.automation.contracts import ActionContext
from app.automation.registry import action
from app.modules.approvals.service import ApprovalService


class VerifyRouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_type: str
    subject_id: uuid.UUID


@action(
    "approvals.verify_route",
    label="Verify approval route",
    input_model=VerifyRouteIn,
    description="Checks the open approval step has someone who can decide it; reroutes inactive assignees to the level's pool.",
)
def verify_route(ctx: ActionContext, data: VerifyRouteIn) -> dict:
    svc = ApprovalService(ctx.session)
    req = svc.latest_for_entity(data.subject_type, data.subject_id)
    if req is None:
        ctx.log.warning("No approval request found for the document.")
        return {"status": "no_request"}
    result = svc.verify_route(req.id)
    if result.get("status") == "no_approvers":
        ctx.log.warning(f"{result['code']}: nobody can currently decide the {result['step']} step.")
    else:
        ctx.log.info(f"Route check: {result.get('status')} ({result.get('approvers', 0)} approver(s))")
    return result


class RemindIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remind_after_hours: float = Field(gt=0)


@action(
    "approvals.send_reminders",
    label="Send approval reminders",
    input_model=RemindIn,
    description="Reminds approvers of steps waiting longer than the reminder threshold (once per step per day).",
)
def send_reminders(ctx: ActionContext, data: RemindIn) -> dict:
    svc = ApprovalService(ctx.session)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    steps = svc.overdue_steps(data.remind_after_hours)
    reminded = [{"code": s.request.entity_code, "step": s.label, "recipients": svc.remind(s, day_key=day)} for s in steps]
    ctx.log.info(f"{len(reminded)} overdue step(s) reminded")
    return {"overdue_steps": len(reminded), "reminders": reminded}


class EscalateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    escalate_after_hours: float = Field(gt=0)


@action(
    "approvals.escalate_overdue",
    label="Escalate overdue approvals",
    input_model=EscalateIn,
    description="Moves personally assigned steps past the escalation threshold up the approver's reporting line.",
)
def escalate_overdue(ctx: ActionContext, data: EscalateIn) -> dict:
    svc = ApprovalService(ctx.session)
    done = [
        r
        for s in svc.overdue_steps(data.escalate_after_hours, assigned_only=True)
        if (r := svc.escalate(s.id, after_hours=data.escalate_after_hours))
    ]
    for r in done:
        ctx.log.info(f"{r['code']} {r['step']}: escalated {r['from']} → {r['to']}")
    return {"escalated": len(done), "escalations": done}
