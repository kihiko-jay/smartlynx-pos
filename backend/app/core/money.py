"""
Central money helpers — Decimal only, bank-style rounding.

Policy:
  - Quantization uses ROUND_HALF_UP to two decimal places (minor units).
  - Float is not accepted for money inputs (use str/int/Decimal from DB/API).
  - This module does not perform I/O or persistence; callers quantize at boundaries.

VAT helpers assume ``rate`` is a decimal fraction (e.g. 0.16 for 16% Kenya standard).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Union

MoneyInput = Union[Decimal, int, str, None]

MONEY_QUANTUM = Decimal("0.01")
_ONE = Decimal("1")


class MoneyTypeError(TypeError):
    """Raised when a value type cannot be safely interpreted as money."""


def to_decimal_money(value: MoneyInput) -> Decimal:
    """
    Convert a money-like value to Decimal without applying quantum rounding.

    Accepts: None (→ 0), int, str (stripped), Decimal.
    Rejects: float (binary representation is not suitable as a money source).
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, float):
        raise MoneyTypeError(
            "float is not accepted for money; use str, int, or Decimal (e.g. from DB NUMERIC)."
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return Decimal("0")
        try:
            return Decimal(s)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid money string: {value!r}") from exc
    raise MoneyTypeError(f"Unsupported money type: {type(value).__name__}")


def quantize_money(value: MoneyInput) -> Decimal:
    """Quantize to two decimal places using ROUND_HALF_UP."""
    d = to_decimal_money(value)
    return d.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_vat_inclusive(amount_ex_vat: MoneyInput, rate: MoneyInput) -> Decimal:
    """
    VAT-inclusive total from a VAT-exclusive amount:
        amount_ex_vat * (1 + rate)
    """
    base = to_decimal_money(amount_ex_vat)
    r = to_decimal_money(rate)
    return (base * (_ONE + r)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_vat_exclusive(amount_ex_vat: MoneyInput, rate: MoneyInput) -> Decimal:
    """
    VAT amount on a VAT-exclusive base:
        amount_ex_vat * rate
    """
    base = to_decimal_money(amount_ex_vat)
    r = to_decimal_money(rate)
    return (base * r).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def split_inclusive_price(gross_inclusive: MoneyInput, rate: MoneyInput) -> tuple[Decimal, Decimal]:
    """
    Split a VAT-inclusive gross into (exclusive_net, vat_amount).

        net = gross / (1 + rate)
        vat = gross - net

    Both results are quantized to MONEY_QUANTUM so net + vat == gross after rounding
    where possible; any remainder-of-a-cent stays on the VAT leg via subtraction.
    """
    gross = quantize_money(gross_inclusive)
    r = to_decimal_money(rate)
    divisor = _ONE + r
    if divisor == 0:
        raise ValueError("VAT rate cannot be -100% (1 + rate == 0)")
    net = (gross / divisor).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    vat = (gross - net).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return net, vat
