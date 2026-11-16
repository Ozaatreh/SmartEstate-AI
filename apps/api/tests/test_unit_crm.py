"""Phase 5B — pure CRM rules: scoring table (incl. timeline and budget fit) and stage transitions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.crm.scoring import LeadFacts, score
from app.modules.crm.service import allowed_stage_targets

D = Decimal
BASE = dict(
    source="phone", has_email=False, has_phone=True, budget_min=None, budget_max=None, bedrooms_wanted=None, consent=False, interest=False
)


def facts(**kw) -> LeadFacts:
    return LeadFacts(**{**BASE, **kw})


@pytest.mark.parametrize(
    ("kw", "expected_total", "expected_grade", "reason"),
    [
        ({}, 15, "cold", "Source: phone"),  # 10 source + 5 one channel
        ({"source": "referral"}, 30, "cold", "Source: referral"),
        ({"source": "unknown_source"}, 10, "cold", "Source: unknown source"),  # fallback 5 points
        ({"has_email": True}, 25, "cold", "Both phone and email provided"),
        ({"budget_min": D("500000")}, 30, "cold", "Budget range shared"),
        ({"budget_max": D("1200000")}, 45, "warm", "Budget at or above SAR 1,000,000"),
        ({"bedrooms_wanted": 2}, 25, "cold", "Unit size specified"),
        ({"interest": True}, 25, "cold", "Specific interest described"),
        ({"consent": True}, 25, "cold", "Consent to be contacted"),
        ({"timeline": "immediate"}, 30, "cold", "Timeline: ready to buy now"),
        ({"timeline": "within_3_months"}, 25, "cold", "Timeline: within 3 months"),
        ({"timeline": "within_6_months"}, 20, "cold", "Timeline: within 6 months"),
        ({"timeline": "over_6_months"}, 15, "cold", "Timeline: more than 6 months away"),
        ({"budget_min": D("500000"), "fitting_units": 0}, 30, "cold", "No available units within budget"),
        ({"budget_min": D("500000"), "fitting_units": 1}, 40, "warm", "Budget fits 1 available unit"),
        ({"budget_min": D("500000"), "fitting_units": 2}, 40, "warm", "Budget fits 2 available units"),
        ({"budget_min": D("500000"), "fitting_units": 7}, 45, "warm", "Budget fits 7 available units"),
    ],
)
def test_scoring_table(kw, expected_total, expected_grade, reason):
    total, grade, reasons = score(facts(**kw))
    assert (total, grade) == (expected_total, expected_grade)
    assert reason in [r["reason"] for r in reasons]
    assert total == min(100, sum(int(r["points"]) for r in reasons))  # every point is explained


def test_scoring_caps_at_100_and_respects_thresholds():
    full = facts(
        source="referral",
        has_email=True,
        budget_min=D("900000"),
        budget_max=D("1500000"),
        bedrooms_wanted=3,
        consent=True,
        interest=True,
        timeline="immediate",
        fitting_units=5,
    )
    total, grade, reasons = score(full)
    assert (total, grade) == (100, "hot") and sum(int(r["points"]) for r in reasons) > 100
    assert score(facts(timeline="immediate"), hot_threshold=30, warm_threshold=20)[1] == "hot"
    assert score(facts(), warm_threshold=15)[1] == "warm"


def test_scoring_is_deterministic_and_ignores_unknown_timeline():
    f = facts(timeline="someday", budget_max=D("800000"), fitting_units=None)
    assert score(f) == score(f)
    assert not any(r["reason"].startswith("Timeline") for r in score(f)[2])
    assert not any("units" in r["reason"] for r in score(f)[2])  # no inventory comparison without a count


@pytest.mark.parametrize(
    ("stage", "targets"),
    [
        ("new", ["contacted", "qualified", "viewing", "negotiation", "won", "lost"]),
        ("qualified", ["viewing", "negotiation", "won", "lost"]),
        ("negotiation", ["won", "lost"]),
        ("won", []),
        ("lost", ["new", "contacted", "qualified", "viewing", "negotiation"]),
    ],
)
def test_stage_transitions(stage, targets):
    assert allowed_stage_targets(stage) == targets
