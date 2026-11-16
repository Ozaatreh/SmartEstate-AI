"""Deterministic lead scoring (no AI). Every point carries a reason that is stored with the lead."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

SOURCE_POINTS = {"referral": 25, "walk_in": 20, "property_assistant": 15, "website": 15, "campaign": 10, "phone": 10, "social": 5}
HIGH_BUDGET = Decimal("1000000")


@dataclass(frozen=True)
class LeadFacts:
    source: str
    has_email: bool
    has_phone: bool
    budget_min: Decimal | None
    budget_max: Decimal | None
    bedrooms_wanted: int | None
    consent: bool
    interest: bool


def score(facts: LeadFacts, *, hot_threshold: int = 70, warm_threshold: int = 40) -> tuple[int, str, list[dict[str, object]]]:
    reasons: list[dict[str, object]] = []

    def add(points: int, reason: str) -> None:
        reasons.append({"points": points, "reason": reason})

    add(SOURCE_POINTS.get(facts.source, 5), f"Source: {facts.source.replace('_', ' ')}")
    if facts.has_email and facts.has_phone:
        add(15, "Both phone and email provided")
    elif facts.has_phone or facts.has_email:
        add(5, "One contact channel provided")
    if facts.budget_min is not None or facts.budget_max is not None:
        add(15, "Budget range shared")
        if (facts.budget_max or facts.budget_min or Decimal(0)) >= HIGH_BUDGET:
            add(15, "Budget at or above SAR 1,000,000")
    if facts.bedrooms_wanted:
        add(10, "Unit size specified")
    if facts.interest:
        add(10, "Specific interest described")
    if facts.consent:
        add(10, "Consent to be contacted")
    total = min(100, sum(int(r["points"]) for r in reasons))
    grade = "hot" if total >= hot_threshold else "warm" if total >= warm_threshold else "cold"
    return total, grade, reasons
