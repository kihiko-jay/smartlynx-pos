"""Unit tests for app.core.money (Decimal-only helpers)."""

import pytest
from decimal import Decimal

from app.core.money import (
    MoneyTypeError,
    calculate_vat_exclusive,
    calculate_vat_inclusive,
    quantize_money,
    split_inclusive_price,
    to_decimal_money,
)


def test_to_decimal_money_none_and_empty_str():
    assert to_decimal_money(None) == Decimal("0")
    assert to_decimal_money("") == Decimal("0")
    assert to_decimal_money("   ") == Decimal("0")


def test_to_decimal_money_int_str_decimal():
    assert to_decimal_money(100) == Decimal("100")
    assert to_decimal_money("12.345") == Decimal("12.345")
    d = Decimal("9.99")
    assert to_decimal_money(d) is d


def test_to_decimal_money_rejects_float():
    with pytest.raises(MoneyTypeError, match="float"):
        to_decimal_money(1.23)


def test_to_decimal_money_invalid_str():
    with pytest.raises(ValueError, match="Invalid money"):
        to_decimal_money("not-a-number")


def test_quantize_money_half_up():
    assert quantize_money("1.005") == Decimal("1.01")
    assert quantize_money("1.004") == Decimal("1.00")
    assert quantize_money(Decimal("2.345")) == Decimal("2.35")


def test_calculate_vat_inclusive():
    # 100 ex @ 16% → 116.00
    assert calculate_vat_inclusive("100", "0.16") == Decimal("116.00")
    assert calculate_vat_inclusive(100, Decimal("0.16")) == Decimal("116.00")


def test_calculate_vat_exclusive():
    # VAT on 100 ex @ 16% → 16.00
    assert calculate_vat_exclusive("100", "0.16") == Decimal("16.00")


def test_split_inclusive_price():
    net, vat = split_inclusive_price("116", "0.16")
    assert net == Decimal("100.00")
    assert vat == Decimal("16.00")
    assert net + vat == Decimal("116.00")


def test_split_inclusive_price_rounding_remainder_on_vat():
    # Gross that does not divide cleanly; net is half-up, vat is residual
    net, vat = split_inclusive_price("10.00", "0.16")
    assert net + vat == Decimal("10.00")


def test_split_inclusive_price_invalid_rate():
    with pytest.raises(ValueError, match="-100%"):
        split_inclusive_price("100", "-1")
