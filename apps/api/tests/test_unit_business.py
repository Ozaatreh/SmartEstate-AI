from __future__ import annotations

from decimal import Decimal

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
