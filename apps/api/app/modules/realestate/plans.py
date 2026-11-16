"""Payment-plan maths (pure, exact Decimal). The parts always add up to the list price exactly:
rounding differences go into the last installment (or the handover payment when there are no installments)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.common.money import ZERO, q2

HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Breakdown:
    down_payment: Decimal
    installments: int
    installment_amount: Decimal | None
    last_installment_amount: Decimal | None
    handover_payment: Decimal
    total: Decimal


def breakdown(price: Decimal, down_pct: Decimal, installments: int, handover_pct: Decimal) -> Breakdown:
    if price <= 0:
        raise ValueError("price must be positive")
    if not (ZERO <= down_pct <= HUNDRED and ZERO <= handover_pct <= HUNDRED) or down_pct + handover_pct > HUNDRED:
        raise ValueError("invalid shares")
    down = q2(price * down_pct / HUNDRED)
    handover = q2(price * handover_pct / HUNDRED)
    rest = price - down - handover
    if installments <= 0:
        # Down payment + handover cover everything; any rounding cent goes to the handover payment.
        return Breakdown(down, 0, None, None, handover + rest, price)
    each = q2(rest / installments)
    last = rest - each * (installments - 1)
    return Breakdown(down, installments, each, last, handover, price)
