"""Reference data every environment needs (idempotent): approval policies and budget categories."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.approvals.models import ApprovalPolicy, ApprovalPolicyStep
from app.modules.finance.models import BudgetCategory

# D-11 (fictional SAR thresholds, editable data): min_amount < amount ≤ max_amount.
PR_POLICIES: tuple[tuple[str, Decimal, Decimal | None, tuple[tuple[str, str], ...]], ...] = (
    ("Up to SAR 50,000", Decimal("0"), Decimal("50000"), (("department", "Department manager"),)),
    ("SAR 50,000 – 250,000", Decimal("50000"), Decimal("250000"), (("department", "Department manager"), ("finance", "Finance"))),
    (
        "Above SAR 250,000",
        Decimal("250000"),
        None,
        (("department", "Department manager"), ("finance", "Finance"), ("executive", "Executive")),
    ),
)

CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("CAPEX-CONSTR", "Construction & site works", "Capital works on development projects"),
    ("EQUIP", "Equipment & tools", "Plant, tools and site equipment"),
    ("IT", "Technology", "Hardware, software and IT services"),
    ("MKT", "Marketing & advertising", "Campaigns, media and sales materials"),
    ("OPEX-ADMIN", "Office & administration", "Office supplies, furniture and running costs"),
    ("PROF", "Professional services", "Consultants, legal, audit and training"),
)


def seed_reference(session: Session) -> tuple[int, int]:
    policies = 0
    for name, low, high, steps in PR_POLICIES:
        exists = session.scalar(
            select(ApprovalPolicy).where(ApprovalPolicy.entity_type == "purchase_request", ApprovalPolicy.min_amount == low)
        )
        if exists is None:
            session.add(
                ApprovalPolicy(
                    entity_type="purchase_request",
                    name=name,
                    min_amount=low,
                    max_amount=high,
                    steps=[ApprovalPolicyStep(step_order=i, level=lv, label=label) for i, (lv, label) in enumerate(steps, 1)],
                )
            )
            policies += 1
    categories = 0
    for code, name, desc in CATEGORIES:
        if session.scalar(select(BudgetCategory).where(BudgetCategory.code == code)) is None:
            session.add(BudgetCategory(code=code, name=name, description=desc))
            categories += 1
    session.flush()
    return policies, categories
