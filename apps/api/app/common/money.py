"""Exact money arithmetic. Amounts are ``Decimal`` in Python and NUMERIC in PostgreSQL — never float."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_AMOUNT = Decimal("9999999999999999.99")  # NUMERIC(18,2)


def q2(value: Decimal | int | str) -> Decimal:
    """Quantise to 2 decimals, half-up (matches PostgreSQL ``round(numeric, 2)`` for these values)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return q2(quantity * unit_price)


def total(values: Iterable[Decimal]) -> Decimal:
    return q2(sum(values, ZERO))
