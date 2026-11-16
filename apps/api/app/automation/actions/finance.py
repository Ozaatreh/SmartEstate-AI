from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.automation.contracts import ActionContext
from app.automation.registry import action
from app.core.permissions import Perm
from app.modules.finance.models import Budget
from app.modules.finance.service import FinanceService
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService


class EvaluateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_id: uuid.UUID
    warning_pct: float = Field(gt=0)
    critical_pct: float = Field(gt=0)
    document_code: str | None = None
    document_over_budget: bool = False


@action(
    "finance.evaluate_budget",
    label="Evaluate budget position",
    input_model=EvaluateIn,
    description="Recomputes the budget position from the ledger and checks the utilisation thresholds.",
)
def evaluate_budget(ctx: ActionContext, data: EvaluateIn) -> dict:
    budget = ctx.session.get(Budget, data.budget_id)
    if budget is None:
        return {"found": False}
    pos = FinanceService(ctx.session).position(budget.id)
    used = float(pos.utilisation_pct)
    crossed = [t for t, pct in (("critical", data.critical_pct), ("warning", data.warning_pct)) if used >= pct]
    level = crossed[0] if crossed else None
    owner = budget.project.name if budget.project else (budget.department.name if budget.department else "—")
    label = f"{budget.category.name} · {owner} · FY{budget.fiscal_year}"
    ctx.log.info(f"{label}: {used:.1f}% used, SAR {pos.available:,.2f} available" + (f" — {level} threshold reached" if level else ""))
    return {
        "found": True,
        "budget_id": str(budget.id),
        "label": label,
        "fiscal_year": budget.fiscal_year,
        "allocated": str(pos.capacity),
        "committed": str(pos.committed),
        "available": str(pos.available),
        "utilisation_pct": used,
        "threshold": level,
        "over_budget_document": data.document_over_budget,
        "document_code": data.document_code,
    }


class AlertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_id: uuid.UUID
    label: str
    threshold: str
    utilisation_pct: float
    available: Decimal


@action(
    "finance.alert_threshold",
    label="Alert finance about budget utilisation",
    input_model=AlertIn,
    description="Notifies budget managers once per budget and threshold.",
)
def alert_threshold(ctx: ActionContext, data: AlertIn) -> dict:
    recipients = IdentityRepository(ctx.session).users_with_permission(Perm.FINANCE_BUDGETS_MANAGE.value)
    for uid in recipients:
        NotificationService(ctx.session).notify(
            uid,
            type="finance.budget_threshold",
            level="danger" if data.threshold == "critical" else "warning",
            title=f"Budget {'fully used' if data.threshold == 'critical' else 'running low'}: {data.utilisation_pct:.1f}% used",
            body=f"{data.label} · SAR {data.available:,.2f} available",
            link=f"/finance/budgets/{data.budget_id}",
            entity_type="budget",
            entity_id=str(data.budget_id),
            dedupe_key=f"budget:{data.budget_id}:threshold:{data.threshold}",
        )
    return {"notified": len(recipients), "threshold": data.threshold}


class OverBudgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: uuid.UUID
    document_code: str
    event_type: str
    label: str
    available: Decimal


@action(
    "finance.alert_over_budget_document",
    label="Flag over-budget request to finance",
    input_model=OverBudgetIn,
    description="Tells finance early that a request exceeds its budget (approval still decides — nothing is blocked or approved here).",
)
def alert_over_budget(ctx: ActionContext, data: OverBudgetIn) -> dict:
    recipients = IdentityRepository(ctx.session).users_with_permission(Perm.FINANCE_BUDGETS_MANAGE.value)
    stage = "sent for approval" if data.event_type.endswith("sent_for_approval") else "submitted"
    for uid in recipients:
        NotificationService(ctx.session).notify(
            uid,
            type="finance.over_budget_request",
            level="warning",
            title=f"Over-budget request {stage}: {data.document_code}",
            body=f"{data.label} · only SAR {data.available:,.2f} available",
            link=f"/procurement/requests/{data.entity_id}",
            entity_type="purchase_request",
            entity_id=str(data.entity_id),
            dedupe_key=f"pr:{data.entity_id}:over_budget:{stage}",
        )
    return {"notified": len(recipients)}
