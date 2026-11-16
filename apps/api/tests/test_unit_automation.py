from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError

from app.automation.actions.procurement import rank_quotations
from app.automation.errors import PermanentError, StepTimeout, TransientError, backoff_seconds, classify
from app.automation.manager import validate_parameters
from app.automation.registry import ACTIONS, load_catalog
from app.core.errors import BusinessRuleViolation, ExternalServiceUnavailable, ValidationFailed
from app.modules.crm.scoring import LeadFacts, score

D = Decimal


def test_backoff_grows_and_is_capped():
    first, third = backoff_seconds(1, jitter=0), backoff_seconds(3, jitter=0)
    assert (first, third) == (30, 120)
    assert backoff_seconds(20, jitter=0) == 900
    assert all(24 <= backoff_seconds(1) <= 36 for _ in range(50))


def test_error_classification():
    assert classify(TransientError("x"))[:2] == (True, "transient_error")
    assert classify(StepTimeout("x"))[:2] == (True, "timeout")
    assert classify(PermanentError("x", code="bad"))[:2] == (False, "bad")
    assert classify(ExternalServiceUnavailable())[0] is True
    assert classify(BusinessRuleViolation("no"))[:2] == (False, "business_rule_violation")
    assert classify(OperationalError("SELECT 1", {}, Exception("conn lost")))[0] is True
    assert classify(RuntimeError("boom"))[:2] == (False, "unexpected_error")


def test_catalog_registers_core_workflows_with_known_actions():
    workflows = load_catalog()
    core = {k: w for k, w in workflows.items() if not k.startswith("test.")}
    assert set(core) == {
        "procurement.purchase_request_approval",
        "finance.budget_validation",
        "procurement.supplier_analysis",
        "crm.lead_registration",
        "crm.follow_up_sla",  # Phase 5
        "crm.reservation_expiry",  # Phase 5
    }
    assert all(step.action in ACTIONS for w in core.values() for step in w.steps)
    assert ACTIONS["procurement.analyse_quotations"].advisory is True
    # deterministic control: no advisory action changes approvals, budgets or assignments
    assert {k for k, a in ACTIONS.items() if a.advisory} == {"procurement.analyse_quotations"}


def test_parameter_validation():
    wf = load_catalog()["finance.budget_validation"]
    assert validate_parameters(wf, {"warning_pct": 75, "flag_over_budget_requests": False}) == {
        "warning_pct": 75.0,
        "flag_over_budget_requests": False,
    }
    for bad in ({"warning_pct": 0}, {"warning_pct": "80"}, {"flag_over_budget_requests": 1}, {"nope": 1}):
        with pytest.raises(ValidationFailed):
            validate_parameters(wf, bad)
    lead = load_catalog()["crm.lead_registration"]
    with pytest.raises(ValidationFailed):
        validate_parameters(lead, {"follow_up_hours": 2.5})


def test_supplier_ranking_balances_price_delivery_and_rating():
    quotes = [
        {"quotation_id": "a", "supplier": "Cheap but slow", "total": D("1000"), "delivery_days": 30, "rating": D("3.0")},
        {"quotation_id": "b", "supplier": "Slightly dearer, fast", "total": D("1040"), "delivery_days": 3, "rating": D("4.5")},
    ]
    price_only = rank_quotations(quotes, (1, 0, 0))
    assert price_only[0]["quotation_id"] == "a" and price_only[0]["score"] == 100.0
    balanced = rank_quotations(quotes, (0.6, 0.25, 0.15))
    assert balanced[0]["quotation_id"] == "b"
    assert rank_quotations([{**quotes[0], "delivery_days": 0}], (0.6, 0.25, 0.15))[0]["delivery_score"] == 100.0


def test_lead_scoring_is_transparent():
    total, grade, reasons = score(
        LeadFacts(
            source="referral",
            has_email=True,
            has_phone=True,
            budget_min=D("900000"),
            budget_max=D("1500000"),
            bedrooms_wanted=3,
            consent=True,
            interest=True,
        )
    )
    assert (total, grade) == (100, "hot") and sum(int(r["points"]) for r in reasons) >= 100
    total, grade, _ = score(
        LeadFacts(
            source="social",
            has_email=False,
            has_phone=True,
            budget_min=None,
            budget_max=None,
            bedrooms_wanted=None,
            consent=False,
            interest=False,
        )
    )
    assert (total, grade) == (10, "cold")
