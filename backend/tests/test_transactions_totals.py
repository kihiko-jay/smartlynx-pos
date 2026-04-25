"""
Totals / VAT consistency for transaction creation (no HTTP — avoids DB fixture drift).

Asserts the same rounding policy as app.core.money (ROUND_HALF_UP, 2 dp).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routers.transactions import _line_net_and_vat


def _product_std():
    return SimpleNamespace(vat_exempt=False, tax_code="B")


def _product_exempt():
    return SimpleNamespace(vat_exempt=True, tax_code="B")


@pytest.mark.parametrize(
    "gross,forbidden",
    [
        ("500.00", {Decimal("499.99"), Decimal("500.48"), Decimal("499.98"), Decimal("500.01")}),
        ("500", {Decimal("499.99"), Decimal("500.48")}),
    ],
)
def test_kes_500_vat_inclusive_single_line_no_total_drift(gross, forbidden):
    """KES 500 sticker (VAT-in) must not collapse to common rounding bugs."""
    net, vat = _line_net_and_vat(Decimal(gross), _product_std(), prices_include_vat=True)
    total = net + vat
    assert total == Decimal("500.00")
    assert total not in forbidden
    assert net == Decimal("431.03")
    assert vat == Decimal("68.97")
    assert net + vat == total


def test_vat_inclusive_subtotal_plus_vat_equals_payable():
    net, vat = _line_net_and_vat(Decimal("116.00"), _product_std(), prices_include_vat=True)
    assert net == Decimal("100.00")
    assert vat == Decimal("16.00")
    assert net + vat == Decimal("116.00")


def test_vat_exclusive_no_double_vat():
    net, vat = _line_net_and_vat(Decimal("100.00"), _product_std(), prices_include_vat=False)
    assert net == Decimal("100.00")
    assert vat == Decimal("16.00")
    assert net + vat == Decimal("116.00")


def test_vat_inclusive_exempt_all_net():
    net, vat = _line_net_and_vat(Decimal("500.00"), _product_exempt(), prices_include_vat=True)
    assert net == Decimal("500.00")
    assert vat == Decimal("0.00")


def test_multi_line_inclusive_sums_to_header_components():
    """Header-style aggregation: sum(line nets) + sum(line vats) == sum(implied gross)."""
    p = _product_std()
    lines = [Decimal("250.00"), Decimal("250.00")]
    nets, vats = [], []
    for g in lines:
        n, v = _line_net_and_vat(g, p, prices_include_vat=True)
        nets.append(n)
        vats.append(v)
    subtotal = sum(nets)
    tax = sum(vats)
    assert subtotal + tax == Decimal("500.00")
    assert subtotal == Decimal("431.04")  # 215.52 * 2
    assert tax == Decimal("68.96")
