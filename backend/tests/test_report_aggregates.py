"""Report financial aggregation — Decimal sums match stored transaction fields."""

from decimal import Decimal
from types import SimpleNamespace

from app.core.report_aggregates import aggregate_completed_txn_financials, money_json, quantize_txn_field


def test_aggregate_sums_stored_headers_kes_500_and_mixed():
    txns = [
        SimpleNamespace(
            total=Decimal("500.00"),
            subtotal=Decimal("431.03"),
            vat_amount=Decimal("68.97"),
            discount_amount=Decimal("0.00"),
        ),
        SimpleNamespace(
            total=Decimal("229.65"),
            subtotal=Decimal("197.97"),
            vat_amount=Decimal("31.68"),
            discount_amount=Decimal("0.00"),
        ),
    ]
    agg = aggregate_completed_txn_financials(txns)
    assert agg["gross_sales"] == Decimal("729.65")
    assert agg["vat_collected"] == Decimal("100.65")
    assert agg["net_sales_ex_vat"] == Decimal("629.00")
    assert agg["total_discounts"] == Decimal("0.00")
    # Net is sum(subtotal), not gross − VAT recomputed from floats
    assert agg["net_sales_ex_vat"] == quantize_txn_field(txns[0].subtotal) + quantize_txn_field(
        txns[1].subtotal
    )


def test_net_ex_vat_prefers_subtotal_not_gross_minus_vat_when_misaligned():
    """If legacy row were inconsistent, report still uses stored subtotal sum."""
    txns = [
        SimpleNamespace(
            total=Decimal("100.00"),
            subtotal=Decimal("90.00"),
            vat_amount=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
        ),
    ]
    agg = aggregate_completed_txn_financials(txns)
    assert agg["gross_sales"] == Decimal("100.00")
    assert agg["net_sales_ex_vat"] == Decimal("90.00")
    assert agg["gross_sales"] - agg["vat_collected"] == Decimal("90.00")
    # If subtotal were wrong vs total-vat, we still expose subtotal sum:
    bad = [
        SimpleNamespace(
            total=Decimal("100.00"),
            subtotal=Decimal("85.00"),
            vat_amount=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
        ),
    ]
    agg_bad = aggregate_completed_txn_financials(bad)
    assert agg_bad["net_sales_ex_vat"] == Decimal("85.00")


def test_money_json_boundary():
    assert money_json(Decimal("500.00")) == 500.0
    assert isinstance(money_json(Decimal("431.03")), float)


def test_daily_breakdown_totals_equal_z_tape_style_pool():
    """Same transaction set: sum of per-day gross equals pooled gross (merchant-day split omitted)."""
    pool = [
        SimpleNamespace(
            total="100.00",
            subtotal="86.21",
            vat_amount="13.79",
            discount_amount="0.00",
        ),
        SimpleNamespace(
            total="200.50",
            subtotal="172.84",
            vat_amount="27.66",
            discount_amount="0.50",
        ),
    ]
    whole = aggregate_completed_txn_financials(pool)
    day_a = aggregate_completed_txn_financials([pool[0]])
    day_b = aggregate_completed_txn_financials([pool[1]])
    assert day_a["gross_sales"] + day_b["gross_sales"] == whole["gross_sales"]
    assert day_a["vat_collected"] + day_b["vat_collected"] == whole["vat_collected"]
    assert day_a["net_sales_ex_vat"] + day_b["net_sales_ex_vat"] == whole["net_sales_ex_vat"]
