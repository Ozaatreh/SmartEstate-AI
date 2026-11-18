"""Internal (staff) tools for the BI agent. All read-only; each needs the permission of the module it reads.

Handlers call module services where a service already answers the question (budget summary, lead funnel, automation
overview) and otherwise run fixed, read-only aggregate queries. Results carry ids/codes and figures, not personal
contact data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from pydantic import Field
from sqlalchemy import func, select

from app.ai.tools.registry import Tool, ToolContext, ToolInput, ToolResult
from app.core.permissions import Perm

ZERO = Decimal("0")


def _pct(part: Decimal, whole: Decimal) -> float | None:
    return round(float(part * 100 / whole), 1) if whole else None


# --- budget positions ------------------------------------------------------------------------------------------
class BudgetPositionsIn(ToolInput):
    fiscal_year: int | None = Field(default=None, ge=2000, le=2100, description="Fiscal year; defaults to the current year.")


def budget_positions(ctx: ToolContext, data: BudgetPositionsIn) -> ToolResult:
    from app.modules.finance.service import FinanceService

    year = data.fiscal_year or date.today().year
    s = FinanceService(ctx.session).summary(ctx.principal, year)  # type: ignore[arg-type]
    departments = [
        {
            "department": d.department.name,
            "allocated_sar": str(d.allocated),
            "committed_and_spent_sar": str(d.committed),
            "available_sar": str(d.available),
            "utilisation_pct": _pct(Decimal(d.committed), Decimal(d.allocated)),
        }
        for d in s.by_department
    ]
    departments.sort(key=lambda d: d["utilisation_pct"] if d["utilisation_pct"] is not None else -1, reverse=True)
    data_out = {
        "fiscal_year": year,
        "currency": "SAR",
        "totals": {
            "allocated_sar": str(s.allocated),
            "committed_sar": str(s.committed),
            "actual_sar": str(s.actual),
            "available_sar": str(s.available),
            "utilisation_pct": float(s.utilisation_pct),
            "budgets_at_or_over_80_pct": s.over_threshold_count,
        },
        "departments_by_utilisation": departments,
        "note": "utilisation_pct = (committed + spent) / allocated for the department's active budgets.",
    }
    return ToolResult(
        data_out,
        f"FY{year} · {len(departments)} departments",
        [
            {
                "kind": "table",
                "title": f"Budget positions FY{year}",
                "columns": ["department", "allocated_sar", "committed_and_spent_sar", "available_sar", "utilisation_pct"],
                "rows": departments,
            }
        ],
    )


# --- approvals backlog -----------------------------------------------------------------------------------------
class NoInput(ToolInput):
    pass


def approvals_backlog(ctx: ToolContext, data: NoInput) -> ToolResult:
    from app.modules.approvals.models import ApprovalRequest, ApprovalStep

    now = datetime.now(UTC)
    rows = ctx.session.execute(
        select(
            ApprovalRequest.entity_type,
            func.count(),
            func.coalesce(func.sum(ApprovalRequest.amount), 0),
            func.min(ApprovalRequest.created_at),
        )
        .where(ApprovalRequest.status == "pending")
        .group_by(ApprovalRequest.entity_type)
    ).all()
    by_type = [
        {
            "document_type": t,
            "pending": int(n),
            "amount_sar": str(Decimal(a)),
            "oldest_waiting_days": round((now - oldest).total_seconds() / 86400, 1),
        }
        for t, n, a, oldest in rows
    ]
    oldest = ctx.session.execute(
        select(ApprovalRequest.entity_code, ApprovalRequest.title, ApprovalRequest.amount, ApprovalRequest.created_at, ApprovalStep.label)
        .join(ApprovalStep, (ApprovalStep.request_id == ApprovalRequest.id) & (ApprovalStep.status == "pending"), isouter=True)
        .where(ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at)
        .limit(5)
    ).all()
    items = [
        {
            "code": c,
            "title": t,
            "amount_sar": str(a),
            "waiting_days": round((now - created).total_seconds() / 86400, 1),
            "waiting_for": label,
        }
        for c, t, a, created, label in oldest
    ]
    total = sum(x["pending"] for x in by_type)
    return ToolResult({"pending_total": total, "by_document_type": by_type, "oldest_pending": items}, f"{total} pending approvals")


# --- purchase order commitments ------------------------------------------------------------------------------
def po_commitments(ctx: ToolContext, data: NoInput) -> ToolResult:
    from app.modules.procurement.models import PurchaseOrder

    rows = ctx.session.execute(
        select(PurchaseOrder.status, func.count(), func.coalesce(func.sum(PurchaseOrder.total_amount), 0)).group_by(PurchaseOrder.status)
    ).all()
    by_status = {s: {"orders": int(n), "total_sar": str(Decimal(t))} for s, n, t in rows}
    open_value = sum((Decimal(by_status[s]["total_sar"]) for s in ("draft", "issued") if s in by_status), ZERO)
    data_out = {
        "by_status": by_status,
        "open_orders_value_sar": str(open_value),
        "note": "Budget commitment happens at purchase-request approval; orders themselves write nothing to the ledger.",
    }
    return ToolResult(data_out, f"{sum(v['orders'] for v in by_status.values())} purchase orders")


# --- lead funnel -----------------------------------------------------------------------------------------------
def lead_funnel(ctx: ToolContext, data: NoInput) -> ToolResult:
    from app.modules.crm.service import CRMService

    s = CRMService(ctx.session).stats(ctx.principal, scope="all")  # type: ignore[arg-type]
    stages = {k: getattr(s, k) for k in ("new", "contacted", "qualified", "viewing", "negotiation", "won", "lost")}
    closed = s.won + s.lost
    data_out = {
        "stages": stages,
        "open": s.open,
        "follow_ups_overdue": s.overdue,
        "unassigned_open": s.unassigned,
        "win_rate_of_closed_pct": _pct(Decimal(s.won), Decimal(closed)),
    }
    return ToolResult(data_out, f"{sum(stages.values())} leads · {s.open} open")


# --- unit inventory -------------------------------------------------------------------------------------------
def unit_inventory(ctx: ToolContext, data: NoInput) -> ToolResult:
    from app.modules.realestate.models import ReProject, ReUnit

    rows = ctx.session.execute(
        select(ReProject.code, ReProject.name, ReUnit.status, func.count(), func.coalesce(func.sum(ReUnit.list_price), 0))
        .join(ReProject, ReProject.id == ReUnit.project_id)
        .group_by(ReProject.code, ReProject.name, ReUnit.status)
        .order_by(ReProject.code)
    ).all()
    projects: dict[str, dict] = {}
    for code, name, status, n, value in rows:
        p = projects.setdefault(code, {"project": name, "code": code, "units": {}, "list_value_sar": {}})
        p["units"][status] = int(n)
        p["list_value_sar"][status] = str(Decimal(value))
    total = sum(sum(p["units"].values()) for p in projects.values())
    return ToolResult({"projects": list(projects.values())}, f"{total} units in {len(projects)} projects")


# --- workflow failures ----------------------------------------------------------------------------------------
class WorkflowFailuresIn(ToolInput):
    hours: int = Field(default=24, ge=1, le=720, description="Look-back window in hours (default 24).")


def workflow_failures(ctx: ToolContext, data: WorkflowFailuresIn) -> ToolResult:
    from app.automation.models import WorkflowExecution

    since = datetime.now(UTC) - timedelta(hours=data.hours)
    counts = dict(
        ctx.session.execute(
            select(WorkflowExecution.status, func.count()).where(WorkflowExecution.created_at >= since).group_by(WorkflowExecution.status)
        ).all()
    )
    failed = ctx.session.scalars(
        select(WorkflowExecution)
        .where(WorkflowExecution.status == "failed", WorkflowExecution.created_at >= since)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(10)
    ).all()
    items = [
        {
            "workflow": e.workflow_key,
            "failed_at": e.finished_at.isoformat() if e.finished_at else None,
            "error_code": e.error_code,
            "attempts": e.attempt,
        }
        for e in failed
    ]
    return ToolResult(
        {"window_hours": data.hours, "executions_by_status": {k: int(v) for k, v in counts.items()}, "recent_failures": items},
        f"{counts.get('failed', 0)} failed in {data.hours} h",
    )


INTERNAL_TOOLS = [
    Tool(
        "get_budget_positions",
        "Checked budget positions",
        "Budget allocation, commitments, spend, availability and utilisation % per department for a fiscal year (SAR).",
        BudgetPositionsIn,
        "internal",
        budget_positions,
        Perm.FINANCE_BUDGETS_READ.value,
    ),
    Tool(
        "get_approvals_backlog",
        "Checked the approvals backlog",
        "Pending approval requests by document type with amounts and waiting time, plus the oldest pending items.",
        NoInput,
        "internal",
        approvals_backlog,
        Perm.APPROVALS_READ_ALL.value,
    ),
    Tool(
        "get_purchase_order_commitments",
        "Checked purchase orders",
        "Purchase order counts and totals (SAR) by status.",
        NoInput,
        "internal",
        po_commitments,
        Perm.PROCUREMENT_REQUESTS_READ_ALL.value,
    ),
    Tool(
        "get_lead_funnel",
        "Checked the lead funnel",
        "CRM lead counts by pipeline stage, open leads, overdue follow-ups, unassigned leads and win rate.",
        NoInput,
        "internal",
        lead_funnel,
        Perm.CRM_LEADS_READ_ALL.value,
    ),
    Tool(
        "get_unit_inventory",
        "Checked unit inventory",
        "Real-estate unit counts and list value (SAR) by project and status (available, reserved, sold, blocked).",
        NoInput,
        "internal",
        unit_inventory,
        Perm.REALESTATE_INVENTORY_READ.value,
    ),
    Tool(
        "get_workflow_failures",
        "Checked workflow failures",
        "Automation workflow executions by status in a time window, with the most recent failures.",
        WorkflowFailuresIn,
        "internal",
        workflow_failures,
        Perm.AUTOMATION_WORKFLOWS_READ.value,
    ),
]
