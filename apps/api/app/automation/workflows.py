"""Workflows (four from Phase 3, two from Phase 5). Each composes registered actions; thresholds come from editable parameters."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.automation.conditions import entity_status_in, parameter_enabled, step_output_truthy
from app.automation.contracts import (
    Condition,
    ConditionResult,
    EventTrigger,
    ExecutionContext,
    ParamSpec,
    ScheduleTrigger,
    Step,
    Workflow,
)
from app.automation.registry import register_workflow
from app.modules.crm.models import Lead
from app.modules.procurement.models import PurchaseRequest


def _pr_status(session: Session, entity_id: str) -> str | None:
    pr = session.get(PurchaseRequest, entity_id)
    return pr.status if pr else None


def _lead_stage(session: Session, entity_id: str) -> str | None:
    lead = session.get(Lead, entity_id)
    return lead.stage if lead else None


def trigger_is(kind: str) -> Condition:
    def check(_: Session, ctx: ExecutionContext) -> ConditionResult:
        return ConditionResult(
            ctx.trigger_type in ((kind, "manual") if kind == "schedule" else (kind,)), f"Triggered by {ctx.trigger_type}"
        )

    return Condition(name=f"trigger_is_{kind}", check=check, description=f"Runs on {kind} triggers")


def payload_has(field: str) -> Condition:
    def check(_: Session, ctx: ExecutionContext) -> ConditionResult:
        value = ctx.payload.get(field)
        return ConditionResult(bool(value) and value != "None", f"{field} = {value!r}")

    return Condition(name=f"has_{field}", check=check, description=f"The event carries a {field.replace('_', ' ')}")


@register_workflow
class PurchaseRequestApproval(Workflow):
    key = "procurement.purchase_request_approval"
    name = "Purchase Request Approval"
    description = (
        "Checks every new approval route can actually be decided, reminds approvers of waiting requests and escalates "
        "overdue steps up the approver's reporting line. Decisions themselves are always made by people."
    )
    category = "Procurement"
    entity_type = "purchase_request"
    triggers = (EventTrigger(("purchase_request.sent_for_approval",)), ScheduleTrigger(every_minutes=15))
    parameters = {
        "remind_after_hours": ParamSpec("int", 24, "Remind after", "Send a reminder once a step has waited this long.", 1, 336, "hours"),
        "escalate_after_hours": ParamSpec(
            "int", 48, "Escalate after", "Escalate a personally assigned step after this long.", 1, 720, "hours"
        ),
        "escalation_enabled": ParamSpec("bool", True, "Escalation enabled", "Turn off to send reminders only."),
    }
    steps = (
        Step(
            "verify_route",
            "approvals.verify_route",
            "Verify the approval route",
            lambda c: {"subject_type": "purchase_request", "subject_id": c.entity_id},
            when=trigger_is("event"),
        ),
        Step(
            "remind",
            "approvals.send_reminders",
            "Remind waiting approvers",
            lambda c: {"remind_after_hours": c.parameters["remind_after_hours"]},
            when=trigger_is("schedule"),
        ),
        Step(
            "escalate",
            "approvals.escalate_overdue",
            "Escalate overdue steps",
            lambda c: {"escalate_after_hours": c.parameters["escalate_after_hours"]},
            when=Condition(
                "schedule_and_enabled",
                lambda s, c: ConditionResult(
                    c.trigger_type in ("schedule", "manual") and bool(c.parameters["escalation_enabled"]),
                    f"trigger={c.trigger_type}, escalation {'on' if c.parameters['escalation_enabled'] else 'off'}",
                ),
                description="Scheduled or manual run with escalation enabled",
            ),
        ),
    )


@register_workflow
class BudgetValidation(Workflow):
    key = "finance.budget_validation"
    name = "Budget Validation"
    description = (
        "Re-validates the budget whenever a request is submitted or sent for approval and whenever the ledger changes. "
        "Alerts finance at the warning and critical thresholds and flags over-budget requests early. It never blocks or approves."
    )
    category = "Finance"
    entity_type = "budget"
    triggers = (EventTrigger(("purchase_request.submitted", "purchase_request.sent_for_approval", "budget.ledger_changed")),)
    conditions = (payload_has("budget_id"),)
    parameters = {
        "warning_pct": ParamSpec("number", 80, "Warning threshold", "Alert when utilisation reaches this share.", 1, 100, "%"),
        "critical_pct": ParamSpec("number", 100, "Critical threshold", "Alert again when utilisation reaches this share.", 1, 200, "%"),
        "flag_over_budget_requests": ParamSpec(
            "bool", True, "Flag over-budget requests", "Tell finance when a request exceeds its budget."
        ),
    }
    steps = (
        Step(
            "evaluate",
            "finance.evaluate_budget",
            "Evaluate the budget position",
            lambda c: {
                "budget_id": c.payload["budget_id"],
                "warning_pct": c.parameters["warning_pct"],
                "critical_pct": c.parameters["critical_pct"],
                "document_code": c.payload.get("code") if c.trigger.get("event_type", "").startswith("purchase_request") else None,
                "document_over_budget": bool(c.payload.get("over_budget")),
            },
        ),
        Step(
            "alert_threshold",
            "finance.alert_threshold",
            "Alert finance about utilisation",
            lambda c: {k: c.data["evaluate"][k] for k in ("budget_id", "label", "threshold", "utilisation_pct", "available")},
            when=step_output_truthy("evaluate", "threshold", "A utilisation threshold was reached"),
        ),
        Step(
            "alert_over_budget",
            "finance.alert_over_budget_document",
            "Flag the over-budget request",
            lambda c: {
                "entity_id": c.entity_id,
                "document_code": c.payload.get("code"),
                "event_type": c.trigger.get("event_type"),
                "label": c.data["evaluate"]["label"],
                "available": c.data["evaluate"]["available"],
            },
            when=Condition(
                "over_budget_flag",
                lambda s, c: ConditionResult(
                    bool(c.data["evaluate"].get("over_budget_document")) and bool(c.parameters["flag_over_budget_requests"]),
                    f"over budget = {c.data['evaluate'].get('over_budget_document')}",
                ),
                description="The request is over budget and flagging is on",
            ),
        ),
    )


@register_workflow
class SupplierAnalysis(Workflow):
    key = "procurement.supplier_analysis"
    name = "Supplier Analysis"
    description = (
        "Scores supplier quotations on price, delivery time and supplier rating each time a quotation is recorded, flags risks "
        "(single quote, expiring quotes, wide price spread) and shares a recommendation. Advisory: buyers still choose."
    )
    category = "Procurement"
    entity_type = "purchase_request"
    triggers = (EventTrigger(("purchase_request.quotation_added",)),)
    conditions = (entity_status_in("purchase request", _pr_status, ("sourcing",)),)
    parameters = {
        "min_quotations": ParamSpec("int", 2, "Share from", "Notify procurement once this many quotations exist.", 1, 10, "quotations"),
        "weight_price": ParamSpec("number", 0.6, "Price weight", "Share of the score from price.", 0, 1),
        "weight_delivery": ParamSpec("number", 0.25, "Delivery weight", "Share of the score from delivery time.", 0, 1),
        "weight_rating": ParamSpec("number", 0.15, "Rating weight", "Share of the score from supplier rating.", 0, 1),
        "expiry_warning_days": ParamSpec("int", 3, "Expiry warning", "Warn when a quotation expires within this many days.", 0, 60, "days"),
    }
    steps = (
        Step(
            "analyse",
            "procurement.analyse_quotations",
            "Score the quotations",
            lambda c: {
                "request_id": c.entity_id,
                "weight_price": c.parameters["weight_price"],
                "weight_delivery": c.parameters["weight_delivery"],
                "weight_rating": c.parameters["weight_rating"],
                "expiry_warning_days": c.parameters["expiry_warning_days"],
            },
        ),
        Step(
            "share",
            "procurement.share_supplier_analysis",
            "Share the recommendation",
            lambda c: {
                "request_id": c.entity_id,
                "request_code": c.data["analyse"]["request_code"],
                "quotations": c.data["analyse"]["quotations"],
                "recommendation": c.data["analyse"]["recommendation"],
            },
            when=Condition(
                "enough_quotations",
                lambda s, c: ConditionResult(
                    (c.data.get("analyse") or {}).get("quotations", 0) >= c.parameters["min_quotations"],
                    f"{(c.data.get('analyse') or {}).get('quotations', 0)} quotation(s), sharing from {c.parameters['min_quotations']}",
                ),
                description="Enough quotations have been recorded to share",
            ),
        ),
    )


@register_workflow
class LeadRegistration(Workflow):
    key = "crm.lead_registration"
    name = "Lead Registration"
    description = (
        "Scores every new lead with transparent rules (incl. timeline and budget fit against available units), assigns it "
        "round-robin to the sales team (one rotation per project), sets a follow-up deadline and notifies the new owner. "
        "Implements the roadmap's crm.new_lead workflow (key kept for execution history, decision C1)."
    )
    category = "CRM"
    entity_type = "lead"
    triggers = (EventTrigger(("lead.created",)),)
    conditions = (entity_status_in("lead", _lead_stage, ("new",)),)
    parameters = {
        "hot_score": ParamSpec("int", 70, "Hot from", "Score at which a lead is graded hot.", 1, 100, "points"),
        "warm_score": ParamSpec("int", 40, "Warm from", "Score at which a lead is graded warm.", 1, 100, "points"),
        "follow_up_hours": ParamSpec("int", 48, "Follow-up deadline", "Time the owner has for the first contact.", 1, 720, "hours"),
        "auto_assign": ParamSpec("bool", True, "Auto-assign", "Turn off to score leads without assigning them."),
    }
    steps = (
        Step(
            "score",
            "crm.score_lead",
            "Score the lead",
            lambda c: {"lead_id": c.entity_id, "hot_score": c.parameters["hot_score"], "warm_score": c.parameters["warm_score"]},
        ),
        Step(
            "assign",
            "crm.assign_lead",
            "Assign to the sales team",
            lambda c: {"lead_id": c.entity_id, "follow_up_hours": c.parameters["follow_up_hours"]},
            when=parameter_enabled("auto_assign", "Auto-assignment is enabled"),
        ),
        Step(
            "notify",
            "crm.notify_lead_owner",
            "Notify the owner",
            lambda c: {"lead_id": c.entity_id},
            when=step_output_truthy("assign", "newly_assigned", "The lead was just assigned"),
            on_error="continue",
        ),
    )


@register_workflow
class FollowUpSLA(Workflow):
    key = "crm.follow_up_sla"
    name = "Lead Follow-up SLA"
    description = (
        "Every 15 minutes, finds open leads whose follow-up date has passed (48 h after assignment by default) and escalates "
        "them to the sales managers, with a reminder to the owner. Each lead is escalated at most once per day."
    )
    category = "CRM"
    entity_type = "lead"
    triggers = (ScheduleTrigger(every_minutes=15),)
    parameters = {
        "max_leads": ParamSpec("int", 200, "Leads per run", "Upper bound of escalations in one run.", 1, 1000, "leads"),
    }
    steps = (Step("escalate", "crm.escalate_overdue", "Escalate overdue follow-ups", lambda c: {"max_leads": c.parameters["max_leads"]}),)


@register_workflow
class ReservationExpiry(Workflow):
    key = "crm.reservation_expiry"
    name = "Reservation Expiry"
    description = (
        "Every 15 minutes, expires reservations that are still active after their expiry time, releases the unit back to "
        "available in the same transaction and notifies the lead owner. Converted or cancelled reservations are never touched."
    )
    category = "CRM"
    entity_type = "unit_reservation"
    triggers = (ScheduleTrigger(every_minutes=15),)
    parameters = {
        "batch_size": ParamSpec("int", 200, "Reservations per run", "Upper bound of expiries in one run.", 1, 1000, "reservations"),
    }
    steps = (
        Step("expire", "crm.expire_reservations", "Expire overdue reservations", lambda c: {"batch_size": c.parameters["batch_size"]}),
    )
