"""
Financial aggregation for reports — Decimal throughout; JSON floats only at boundaries.

Uses stored transaction header fields (total, subtotal, vat_amount, discount_amount).
Net ex-VAT is sum(subtotal), not (gross − VAT), to match persisted accounting rows.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.money import quantize_money


def quantize_txn_field(value) -> Decimal:
    """Normalize a DB/API money field to quantized Decimal."""
    return quantize_money(value if value is not None else 0)


def aggregate_completed_txn_financials(transactions: list) -> dict[str, Decimal]:
    """
    Sum authoritative stored totals for a list of transactions (e.g. COMPLETED filter applied by caller).

    Returns:
        gross_sales:      sum(total)
        vat_collected:    sum(vat_amount)
        total_discounts:  sum(discount_amount)
        net_sales_ex_vat: sum(subtotal)  — persisted ex-VAT revenue, not recomputed from VAT rate
    """
    gross = Decimal("0")
    vat = Decimal("0")
    disc = Decimal("0")
    sub = Decimal("0")
    for t in transactions:
        gross += quantize_txn_field(getattr(t, "total", None))
        vat += quantize_txn_field(getattr(t, "vat_amount", None))
        disc += quantize_txn_field(getattr(t, "discount_amount", None))
        sub += quantize_txn_field(getattr(t, "subtotal", None))
    return {
        "gross_sales": quantize_money(gross),
        "vat_collected": quantize_money(vat),
        "total_discounts": quantize_money(disc),
        "net_sales_ex_vat": quantize_money(sub),
    }


def money_json(d: Decimal) -> float:
    """Serialize quantized Decimal to JSON number at API boundary."""
    return float(d)
