"""Exact six-place money and explicitly rounded ratios, without ambient context."""

from decimal import Decimal
from fractions import Fraction

SCALE = 1_000_000
ZERO = Decimal("0.000000")


def _units(value: Decimal) -> int:
    scaled = Fraction(value) * SCALE
    if scaled.denominator != 1:
        raise ValueError("Canonical monetary aggregates must have at most six decimal places")
    return scaled.numerator


def _decimal(units: int) -> Decimal:
    whole, fraction = divmod(abs(units), SCALE)
    sign = "-" if units < 0 else ""
    return Decimal(f"{sign}{whole}.{fraction:06d}")


def _rounded_ratio(numerator: int, denominator: int) -> Decimal:
    """Round an exact ratio of micro-units once, using ROUND_HALF_EVEN."""
    if denominator <= 0:
        raise ValueError("A ratio requires a positive denominator")
    quotient, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 > denominator or (remainder * 2 == denominator and quotient % 2):
        quotient += 1
    return _decimal(-quotient if numerator < 0 else quotient)


def difference(current: Decimal, comparison: Decimal) -> Decimal:
    return _decimal(_units(current) - _units(comparison))


def average(total: Decimal, count: int) -> Decimal | None:
    return _rounded_ratio(_units(total), count) if count else None


def percentage(amount: Decimal | None, total: Decimal | None) -> Decimal | None:
    if amount is None or total is None or total == 0:
        return None
    return _rounded_ratio(_units(amount) * 100 * SCALE, _units(total))
