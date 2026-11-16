"""Automation engine on PostgreSQL: triggers, conditions, execution, retries, timeouts, leases, idempotency,
integrations with procurement / finance / approvals / CRM, and the management API (RBAC + audit)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.automation import events
from app.automation.engine import Engine
from app.automation.manager import sync_definitions
from app.automation.models import AutomationEvent, WorkflowDefinition, WorkflowExecution, WorkflowExecutionLog, WorkflowStepExecution
from app.modules.approvals.models import ApprovalStep
from app.modules.audit.models import AuditLog
from app.modules.crm.models import Lead
from app.modules.notifications.models import Notification
from tests import automation_test_workflows as tw
from tests.business_fixtures import Actor, quotation_body, request_body, to_approval

pytestmark = pytest.mark.db


@pytest.fixture
def factory(connection):
    return lambda: Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def wf_engine(db, factory, roles):
    sync_definitions(db)
    db.commit()
    return Engine(factory, "worker-a")


def run(engine: Engine, db: Session) -> int:
    n = engine.run_until_idle()
    db.expire_all()
    return n


def executions(db: Session, key: str) -> list[WorkflowExecution]:
    db.expire_all()
    return list(db.scalars(select(WorkflowExecution).where(WorkflowExecution.workflow_key == key).order_by(WorkflowExecution.created_at)))


def emit_test(db: Session, key: str, user) -> AutomationEvent:
    e = events.emit(db, key, entity_type="test", entity_id=user.id, payload={"user_id": str(user.id)})
    db.commit()
    return e


def make_due(db: Session) -> None:
    db.execute(
        update(WorkflowExecution)
        .where(WorkflowExecution.status == "pending")
        .values(available_at=func.clock_timestamp() - text("interval '1 second'"))
    )
    db.commit()


# ============================================================================= registry & manager
def test_definitions_are_synced(db, wf_engine):
    defs = {d.key: d for d in db.scalars(select(WorkflowDefinition))}
    for key in (
        "procurement.purchase_request_approval",
        "finance.budget_validation",
        "procurement.supplier_analysis",
        "crm.lead_registration",
    ):
        assert defs[key].is_enabled and defs[key].is_registered
    assert defs["procurement.purchase_request_approval"].schedule_minutes == 15
    assert defs["crm.lead_registration"].event_types == ["lead.created"]
    assert defs["finance.budget_validation"].parameters["warning_pct"] == 80


# ============================================================================= execution, retries, idempotency
def test_transient_failure_retries_and_resumes_without_repeating_steps(db, wf_engine, make_user):
    user = make_user()
    emit_test(db, "test.flaky", user)
    run(wf_engine, db)
    (e,) = executions(db, "test.flaky")
    assert (e.status, e.attempt, e.error_code) == ("pending", 1, "transient_error")
    assert e.available_at > datetime.now(UTC)  # backoff
    steps = db.scalars(select(WorkflowStepExecution).where(WorkflowStepExecution.execution_id == e.id)).all()
    assert sorted((s.step_key, s.status) for s in steps) == [("before", "succeeded"), ("flaky", "failed")]
    # the failed step's notification was rolled back; the committed one stays
    assert {n.title.split()[0] for n in db.scalars(select(Notification).where(Notification.user_id == user.id))} == {"before"}

    make_due(db)
    run(wf_engine, db)
    (e,) = executions(db, "test.flaky")
    assert (e.status, e.attempt) == ("succeeded", 2)
    assert tw.CALLS[f"record:{e.id}:before"] == 1  # completed step not repeated on retry
    assert {n.title.split()[0] for n in db.scalars(select(Notification).where(Notification.user_id == user.id))} == {
        "before",
        "flaky",
        "after",
    }
    logs = [
        entry.message
        for entry in db.scalars(
            select(WorkflowExecutionLog).where(WorkflowExecutionLog.execution_id == e.id).order_by(WorkflowExecutionLog.seq)
        )
    ]
    assert any("retry 2 scheduled" in m for m in logs) and any("resuming after 1 completed step" in m for m in logs)


def test_attempts_exhaust_then_fail(db, wf_engine, make_user):
    emit_test(db, "test.exhaust", make_user())
    run(wf_engine, db)
    make_due(db)
    run(wf_engine, db)
    (e,) = executions(db, "test.exhaust")
    assert (e.status, e.attempt, e.error_code) == ("failed", 2, "transient_error")


def test_permanent_failure_is_not_retried(db, wf_engine, make_user):
    emit_test(db, "test.permanent", make_user())
    run(wf_engine, db)
    (e,) = executions(db, "test.permanent")
    assert (e.status, e.attempt, e.error_code, e.error_message) == ("failed", 1, "bad_data", "Bad data")


def test_optional_step_failure_does_not_fail_execution(db, wf_engine, make_user):
    emit_test(db, "test.optional", make_user())
    run(wf_engine, db)
    (e,) = executions(db, "test.optional")
    assert e.status == "succeeded" and e.result["x"]["failed"] is True and e.result["y"] == {"recorded": "y"}


def test_event_dispatch_is_idempotent(db, wf_engine, make_user):
    ev = emit_test(db, "test.noop", make_user())
    run(wf_engine, db)
    db.execute(update(AutomationEvent).where(AutomationEvent.id == ev.id).values(status="pending"))  # simulate a re-delivered event
    db.commit()
    run(wf_engine, db)
    (e,) = executions(db, "test.noop")
    assert e.status == "succeeded" and tw.CALLS[f"noop:{e.id}"] == 1


def test_disabled_workflow_receives_no_executions(db, wf_engine, make_user):
    db.execute(update(WorkflowDefinition).where(WorkflowDefinition.key == "test.noop").values(is_enabled=False))
    db.commit()
    ev = emit_test(db, "test.noop", make_user())
    run(wf_engine, db)
    assert executions(db, "test.noop") == []
    db.refresh(ev)
    assert ev.status == "dispatched" and ev.executions_created == 0


# ============================================================================= timeouts & leases
def test_step_timeout_rolls_back_and_retries(db, wf_engine, make_user):
    user = make_user()
    emit_test(db, "test.slow", user)
    run(wf_engine, db)
    (e,) = executions(db, "test.slow")
    assert (e.status, e.error_code) == ("pending", "timeout")
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id)) == 0  # rolled back


def test_long_database_statement_is_cancelled(db, wf_engine, make_user):
    emit_test(db, "test.pg_sleep", make_user())
    t0 = datetime.now(UTC)
    run(wf_engine, db)
    (e,) = executions(db, "test.pg_sleep")
    assert (e.status, e.error_code) == ("pending", "timeout")
    assert (datetime.now(UTC) - t0).total_seconds() < 4  # pg_sleep(5) was cancelled by statement_timeout


def test_abandoned_execution_is_recovered_and_stale_worker_is_fenced(db, factory, wf_engine, make_user):
    user = make_user()
    emit_test(db, "test.noop", user)
    a, b = Engine(factory, "worker-a"), Engine(factory, "worker-b")
    a.dispatch_events()
    [(eid, attempt_a)] = a.claim()
    # worker A "crashes": its lease expires
    db.execute(
        update(WorkflowExecution)
        .where(WorkflowExecution.id == eid)
        .values(lease_expires_at=func.clock_timestamp() - text("interval '1 minute'"))
    )
    db.commit()
    assert b.recover_abandoned() == 1
    db.expire_all()
    e = db.get(WorkflowExecution, eid)
    assert (e.status, e.error_code, e.lease_owner) == ("pending", "abandoned", None)
    make_due(db)
    [(eid_b, attempt_b)] = b.claim()
    assert (eid_b, attempt_b) == (eid, 2)
    assert a.execute(eid, attempt_a) == "lease_lost"  # the stale worker can't write anything
    assert b.execute(eid, attempt_b) == "succeeded"
    assert tw.CALLS[f"noop:{eid}"] == 1


def test_recovery_fails_execution_after_last_attempt(db, factory, wf_engine, make_user):
    emit_test(db, "test.exhaust", make_user())  # max_attempts = 2
    eng = Engine(factory, "w")
    eng.dispatch_events()
    for _ in range(2):
        make_due(db)
        [(eid, _)] = eng.claim()
        db.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == eid)
            .values(lease_expires_at=func.clock_timestamp() - text("interval '1 minute'"))
        )
        db.commit()
        eng.recover_abandoned()
    db.expire_all()
    assert (db.get(WorkflowExecution, eid).status, db.get(WorkflowExecution, eid).error_code) == ("failed", "abandoned")


def test_schedule_fires_once_per_slot(db, wf_engine):
    # Isolate one scheduled workflow (Phase 5 added more schedules): the others' next slot is in the future.
    db.execute(
        update(WorkflowDefinition)
        .where(WorkflowDefinition.key != "procurement.purchase_request_approval")
        .values(next_run_at=func.now() + text("interval '1 hour'"))
    )
    db.execute(update(WorkflowDefinition).where(WorkflowDefinition.key == "procurement.purchase_request_approval").values(next_run_at=None))
    db.commit()
    assert wf_engine.fire_schedules() == 1
    assert wf_engine.fire_schedules() == 0  # next_run_at moved to the next slot
    db.execute(update(WorkflowDefinition).where(WorkflowDefinition.key == "procurement.purchase_request_approval").values(next_run_at=None))
    db.commit()
    assert wf_engine.fire_schedules() == 0  # same slot again → idempotency key prevents a duplicate
    assert len(executions(db, "procurement.purchase_request_approval")) == 1


# ============================================================================= integrations
def _lead_body(**kw):
    return {
        "full_name": "Maha Al-Saud",
        "phone": "+966 50 000 0000",
        "email": "maha@example.com",
        "source": "referral",
        "budget_min": "900000",
        "budget_max": "1500000",
        "bedrooms_wanted": 3,
        "interest": "3-bedroom, NOVA Residences",
        "consent": True,
        **kw,
    }


def test_lead_registration_scores_assigns_round_robin_and_notifies(db, wf_engine, make_user, app):
    agents = [make_user("sales_agent", name=f"Agent {i}") for i in range(2)]
    manager = Actor(app, make_user("sales_manager"))
    first = manager.post("/crm/leads", _lead_body())
    second = manager.post(
        "/crm/leads",
        _lead_body(
            full_name="Omar B",
            email=None,
            source="website",
            budget_min=None,
            budget_max=None,
            bedrooms_wanted=None,
            interest=None,
            consent=False,
        ),
    )
    assert first.status_code == 201, first.text
    run(wf_engine, db)
    l1, l2 = db.get(Lead, first.json()["id"]), db.get(Lead, second.json()["id"])
    assert (l1.score, l1.grade) == (100, "hot") and l1.score_reasons
    assert (l2.score, l2.grade) == (20, "cold")
    assert {l1.owner_user_id, l2.owner_user_id} == {a.id for a in agents}  # round-robin
    assert l1.next_follow_up_at is not None
    assert db.scalar(select(Notification).where(Notification.user_id == l1.owner_user_id, Notification.type == "crm.lead_assigned"))
    assert db.scalar(select(AuditLog).where(AuditLog.action == "crm.lead_assigned", AuditLog.entity_id == str(l1.id)))
    ex = [x for x in executions(db, "crm.lead_registration") if x.entity_id == str(l1.id)][0]
    assert ex.status == "succeeded" and ex.result["assign"]["newly_assigned"] is True


def test_lead_condition_skips_when_lead_already_progressed(db, wf_engine, make_user, app):
    make_user("sales_agent")
    r = Actor(app, make_user("sales_manager")).post("/crm/leads", _lead_body())
    db.execute(update(Lead).where(Lead.id == r.json()["id"]).values(stage="contacted"))
    db.commit()
    run(wf_engine, db)
    (ex,) = executions(db, "crm.lead_registration")
    assert ex.status == "skipped" and "contacted" in ex.result["skipped_because"]


def test_budget_validation_flags_over_budget_and_thresholds(db, wf_engine, as_, org):
    detail, approval = to_approval(as_, org, unit_price="11000.00")  # 110,000 > 100,000 budget
    run(wf_engine, db)
    cfo = org.users["cfo"].id
    types = {n.type for n in db.scalars(select(Notification).where(Notification.user_id == cfo))}
    assert "finance.over_budget_request" in types
    # approve all steps → ledger commitment → critical threshold crossed
    as_("head").post(f"/approvals/{approval}/approve", {})
    as_("cfo").post(f"/approvals/{approval}/approve", {})
    as_("ceo").post(f"/approvals/{approval}/approve", {})
    run(wf_engine, db)
    alert = db.scalar(select(Notification).where(Notification.user_id == cfo, Notification.type == "finance.budget_threshold"))
    assert alert is not None and "fully used" in alert.title
    runs = executions(db, "finance.budget_validation")
    assert {r.status for r in runs} == {"succeeded"} and len(runs) >= 3  # submitted, sent_for_approval, ledger_changed


def test_supplier_analysis_recommends_after_second_quotation(db, wf_engine, as_, org):
    pr = as_("eng").post("/procurement/requests", request_body(org, items=(("Item A", "10", "unit", "100.00"),))).json()
    as_("eng").post(f"/procurement/requests/{pr['id']}/submit")
    as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[0], ["95.00"], days=20))
    run(wf_engine, db)
    first = next(x for x in executions(db, "procurement.supplier_analysis") if x.result and x.result["analyse"]["quotations"] == 1)
    assert first.result["analyse"]["quotations"] == 1 and first.result["share"]["skipped"] is True
    assert "Only one quotation" in first.result["analyse"]["warnings"][0]
    as_("buyer").post(f"/procurement/requests/{pr['id']}/quotations", quotation_body(pr, org.suppliers[1], ["99.00"], days=2))
    run(wf_engine, db)
    second = next(x for x in executions(db, "procurement.supplier_analysis") if x.result and x.result["analyse"]["quotations"] == 2)
    analysis = second.result["analyse"]
    assert analysis["advisory"] is True and analysis["ranking"][0]["supplier"] == "Supplier 2"  # faster delivery outweighs a 4% price gap
    assert "above the lowest price" in analysis["recommendation"]
    assert db.scalar(
        select(Notification).where(Notification.user_id == org.users["buyer"].id, Notification.type == "procurement.supplier_analysis")
    )
    db.expire_all()
    pr_row = as_("buyer").get(f"/procurement/requests/{pr['id']}").json()
    assert pr_row["selected_quotation_id"] is None  # advisory only: nothing selected automatically


def test_purchase_request_approval_verifies_route_reminds_and_escalates(db, wf_engine, as_, org, factory):
    detail, approval = to_approval(as_, org)
    run(wf_engine, db)
    route = [x for x in executions(db, "procurement.purchase_request_approval") if x.trigger_type == "event"][0]
    assert route.status == "succeeded" and route.result["verify_route"]["status"] == "ok"
    # the department step has waited 50 hours
    db.execute(
        update(ApprovalStep)
        .where(ApprovalStep.status == "pending")
        .values(activated_at=func.clock_timestamp() - text("interval '50 hours'"))
    )
    db.commit()
    eid = wf_engine.run_now(db, "procurement.purchase_request_approval", None)
    db.commit()
    run(wf_engine, db)
    sla = db.get(WorkflowExecution, eid)
    assert sla.status == "succeeded"
    assert sla.result["remind"]["overdue_steps"] == 1 and sla.result["escalate"]["escalated"] == 1
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.status == "pending"))
    assert step.assigned_user_id == org.users["ceo"].id and "Escalated after 48 h" in step.escalation_reason
    assert db.scalar(select(AuditLog).where(AuditLog.action == "approval.escalated"))
    assert as_("head").post(f"/approvals/{approval}/approve", {}).status_code in (403, 404)
    assert as_("ceo").post(f"/approvals/{approval}/approve", {}).status_code == 200
    # a second sweep finds nothing new (SLA restarted / decided)
    eid2 = wf_engine.run_now(db, "procurement.purchase_request_approval", None)
    db.commit()
    run(wf_engine, db)
    assert db.get(WorkflowExecution, eid2).result["escalate"]["escalated"] == 0


# ============================================================================= management API: RBAC + audit
def test_management_api_permissions_retry_cancel_and_audit(db, wf_engine, make_user, app):
    admin, executive, employee = Actor(app, make_user("super_admin")), Actor(app, make_user("executive")), Actor(app, make_user("employee"))
    user = make_user()
    emit_test(db, "test.permanent", user)
    run(wf_engine, db)
    (failed,) = executions(db, "test.permanent")

    assert employee.get("/automation/workflows").status_code == 403
    assert executive.get("/automation/workflows").status_code == 200
    detail = executive.get(f"/automation/executions/{failed.id}").json()
    assert detail["status"] == "failed" and detail["allowed_actions"] == [] and detail["logs"]
    assert executive.post(f"/automation/executions/{failed.id}/retry").status_code == 403

    r = admin.post(f"/automation/executions/{failed.id}/retry")
    assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["max_attempts"] == 2
    assert admin.post(f"/automation/executions/{failed.id}/retry").status_code == 409  # already queued
    assert admin.post(f"/automation/executions/{failed.id}/cancel").json()["status"] == "cancelled"
    actions = {a.action for a in db.scalars(select(AuditLog).where(AuditLog.entity_id == str(failed.id)))}
    assert {"automation.execution_retried", "automation.execution_cancelled"} <= actions

    assert admin.post("/automation/workflows/crm.lead_registration/run").status_code == 422  # event workflows can't be run on demand
    run_r = admin.post("/automation/workflows/procurement.purchase_request_approval/run")
    assert (
        run_r.status_code == 202 and admin.get(f"/automation/executions/{run_r.json()['execution_id']}").json()["trigger_type"] == "manual"
    )

    bad = admin.patch("/automation/workflows/finance.budget_validation", {"parameters": {"warning_pct": 500}})
    assert bad.status_code == 422 and bad.json()["error"]["details"]["fields"][0]["field"] == "parameters.warning_pct"
    assert (
        admin.patch("/automation/workflows/finance.budget_validation", {"parameters": {"warning_pct": 90, "critical_pct": 85}}).status_code
        == 422
    )
    ok = admin.patch("/automation/workflows/finance.budget_validation", {"parameters": {"warning_pct": 75}, "max_attempts": 4})
    assert ok.status_code == 200 and {p["name"]: p["value"] for p in ok.json()["parameters"]}["warning_pct"] == 75
    assert executive.patch("/automation/workflows/finance.budget_validation", {"is_enabled": False}).status_code == 403
    assert db.scalar(select(AuditLog).where(AuditLog.action == "automation.workflow_updated"))

    listing = executive.get("/automation/executions", params={"status": "failed"}).json()
    assert all(i["status"] == "failed" for i in listing["items"])
    overview = executive.get("/automation/overview").json()
    assert overview["executions"] >= 1 and "workers" in overview
