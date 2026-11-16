from __future__ import annotations

from decimal import Decimal

import pytest

from app.common.money import line_total, q2, total
from app.modules.finance.service import BudgetCheck, BudgetPosition

D = Decimal


def test_money_rounding_is_half_up_and_exact():
    assert q2("0.005") == D("0.01")
    assert q2("2.675") == D("2.68")  # float would give 2.67
    assert line_total(D("3.333"), D("0.15")) == D("0.50")
    assert total([D("0.10")] * 3) == D("0.30")


def test_budget_position_math():
    p = BudgetPosition(allocated=D("1000.00"), adjustments=D("-100.00"), committed=D("500.00"), actual=D("150.00"))
    assert p.capacity == D("900.00") and p.available == D("250.00") and p.used == D("650.00")
    assert p.utilisation_pct == D("72.2")
    assert BudgetPosition(D("0"), D("0"), D("0"), D("0")).utilisation_pct == D("0.0")
    assert BudgetPosition(D("0"), D("0"), D("5"), D("0")).utilisation_pct == D("100.0")


def test_budget_check_flags():
    pos = BudgetPosition(D("100.00"), D("0"), D("40.00"), D("0"))
    assert not BudgetCheck(None, pos, D("60.00")).over_budget
    assert BudgetCheck(None, pos, D("60.01")).over_budget
    assert BudgetCheck(None, pos, D("60.01")).available_after == D("-0.01")
    assert BudgetCheck(None, None, D("1.00")).over_budget  # no budget at all


# --- Phase 5: payment-plan maths ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("price", "down", "n", "handover", "expected"),
    [
        ("900000.00", "10", 36, "0", ("90000.00", "22500.00", "22500.00", "0.00")),
        ("1000000.00", "10", 3, "0", ("100000.00", "300000.00", "300000.00", "0.00")),
        ("100000.00", "10", 7, "0", ("10000.00", "12857.14", "12857.16", "0.00")),  # rounding cent lands on the last installment
        ("333333.33", "20", 0, "80", ("66666.67", None, None, "266666.66")),
        ("750000.00", "20", 8, "30", ("150000.00", "46875.00", "46875.00", "225000.00")),
    ],
)
def test_payment_plan_breakdown_is_exact(price, down, n, handover, expected):
    from app.modules.realestate.plans import breakdown

    b = breakdown(Decimal(price), Decimal(down), n, Decimal(handover))
    got = (b.down_payment, b.installment_amount, b.last_installment_amount, b.handover_payment)
    assert tuple(None if v is None else str(v) for v in got) == expected
    paid = b.down_payment + b.handover_payment + ((b.installment_amount or 0) * (n - 1) + (b.last_installment_amount or 0) if n else 0)
    assert paid == Decimal(price) == b.total


def test_payment_plan_breakdown_rejects_bad_shares():
    from app.modules.realestate.plans import breakdown

    with pytest.raises(ValueError):
        breakdown(Decimal("100"), Decimal("60"), 2, Decimal("50"))
    with pytest.raises(ValueError):
        breakdown(Decimal("0"), Decimal("10"), 2, Decimal("0"))
