"""
Tax engine — configuration-driven, jurisdiction-aware tax calculation.

Replaces the hardcoded 16% VAT approach with a rules engine backed by
the tax_jurisdictions, tax_rates, product_tax_assignments, and
customer_tax_exemptions tables.

Design:
  - Tax rates come from the DB — a rate change is a config change, not a deploy
  - Line-level calculation (not basket-level)
  - Customer exemptions override product rates
  - Tax snapshots (rate, code, jurisdiction) are stored on TransactionItem at
    sale time and are IMMUTABLE after the sale is completed
  - Kenya (KE_VAT) is the default jurisdiction for backwards compatibility

Usage at POS sale time:
    engine = TaxEngine(db)
    for item in cart:
        result = engine.calculate_line_tax(
            product=item.product,
            customer=cart.customer,
            qty=item.qty,
            unit_price=item.unit_price,
            jurisdiction_code="KE_VAT",
            sale_date=today,
        )
        item.vat_amount = result.tax_amount
        item.tax_rate_applied = result.rate
        item.tax_code_snapshot = result.code
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tax import (
    TaxJurisdiction, TaxRate,
    ProductTaxAssignment, CustomerTaxExemption,
)
from app.models.product import Product
from app.models.customer import Customer

logger = logging.getLogger("dukapos.tax")

TWO_PLACES = Decimal("0.01")


@dataclass
class TaxResult:
    """Result of a single tax calculation for one line item."""
    tax_amount:          Decimal    # absolute KES amount for this line
    rate:                Decimal    # e.g. Decimal("0.1600")
    code:                str        # STANDARD | ZERO | EXEMPT | REDUCED
    jurisdiction_code:   str        # e.g. KE_VAT
    is_exempt:           bool
    exemption_reason:    Optional[str]  # None | 'customer_exemption' | 'product_exempt'
    tax_inclusive:       bool = False   # True if unit_price already includes tax


class TaxEngine:
    """
    Stateless tax calculator. Instantiate per-request with the DB session.
    """

    def __init__(self, db: Session, default_jurisdiction: str = "KE_VAT"):
        self.db = db
        self.default_jurisdiction = default_jurisdiction
        self._jurisdiction_cache: dict[str, TaxJurisdiction] = {}
        self._rate_cache: dict[tuple, Optional[TaxRate]] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def calculate_line_tax(
        self,
        product: Product,
        qty: int,
        unit_price: Decimal,
        customer: Optional[Customer] = None,
        jurisdiction_code: Optional[str] = None,
        sale_date: Optional[date] = None,
        tax_inclusive: bool = False,
    ) -> TaxResult:
        """
        Calculate tax for one line item.

        Priority order:
          1. Customer exemption → EXEMPT (0%)
          2. Product tax assignment for jurisdiction
          3. Product.vat_exempt flag (backwards compatibility)
          4. Default STANDARD rate for jurisdiction

        Args:
            product:           The product being sold
            qty:               Quantity sold
            unit_price:        Price per unit (tax-exclusive unless tax_inclusive=True)
            customer:          Optional — if provided, checked for exemption
            jurisdiction_code: Override jurisdiction (defaults to store's default)
            sale_date:         Date of sale (for rate effective-date lookup; defaults to today)
            tax_inclusive:     If True, unit_price already includes tax (reverse-calculate)

        Returns:
            TaxResult with tax_amount, rate, code, and audit snapshot fields
        """
        from datetime import date as _date
        jcode     = jurisdiction_code or self.default_jurisdiction
        calc_date = sale_date or _date.today()

        # 1. Customer exemption check
        if customer:
            exemption = self._get_customer_exemption(customer.id, jcode, calc_date)
            if exemption:
                return TaxResult(
                    tax_amount        = Decimal("0.00"),
                    rate              = Decimal("0"),
                    code              = "EXEMPT",
                    jurisdiction_code = jcode,
                    is_exempt         = True,
                    exemption_reason  = "customer_exemption",
                    tax_inclusive     = tax_inclusive,
                )

        # 2. Product exemption (backwards-compat: vat_exempt boolean)
        if getattr(product, "vat_exempt", False):
            return TaxResult(
                tax_amount        = Decimal("0.00"),
                rate              = Decimal("0"),
                code              = "EXEMPT",
                jurisdiction_code = jcode,
                is_exempt         = True,
                exemption_reason  = "product_exempt",
                tax_inclusive     = tax_inclusive,
            )

        # 3. Get applicable rate for product + jurisdiction + date
        rate_row = self._get_product_rate(product.id, jcode, calc_date)

        if rate_row is None:
            # No rate configured — fallback to backwards-compat logic
            rate_row = self._get_default_rate(jcode, calc_date)

        if rate_row is None or rate_row.code == "EXEMPT" or rate_row.rate == Decimal("0"):
            return TaxResult(
                tax_amount        = Decimal("0.00"),
                rate              = Decimal("0"),
                code              = rate_row.code if rate_row else "EXEMPT",
                jurisdiction_code = jcode,
                is_exempt         = True,
                exemption_reason  = "zero_rate",
                tax_inclusive     = tax_inclusive,
            )

        # 4. Calculate tax amount
        rate = rate_row.rate
        line_value = Decimal(str(unit_price)) * Decimal(str(qty))

        if tax_inclusive:
            # Reverse-calculate: tax = price * rate / (1 + rate)
            tax_amount = (line_value * rate / (Decimal("1") + rate)).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
        else:
            tax_amount = (line_value * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return TaxResult(
            tax_amount        = tax_amount,
            rate              = rate,
            code              = rate_row.code,
            jurisdiction_code = jcode,
            is_exempt         = False,
            exemption_reason  = None,
            tax_inclusive     = tax_inclusive,
        )

    def calculate_basket_tax(
        self,
        items: list[dict],  # [{"product": Product, "qty": int, "unit_price": Decimal}]
        customer: Optional[Customer] = None,
        jurisdiction_code: Optional[str] = None,
        sale_date: Optional[date] = None,
        tax_inclusive: bool = False,
    ) -> dict:
        """
        Calculate tax for a full basket. Returns per-line results and totals.

        Returns:
            {
                "lines": [TaxResult, ...],
                "total_tax": Decimal,
                "total_taxable": Decimal,
                "total_exempt": Decimal,
            }
        """
        results = []
        total_tax     = Decimal("0.00")
        total_taxable = Decimal("0.00")
        total_exempt  = Decimal("0.00")

        for item in items:
            result = self.calculate_line_tax(
                product            = item["product"],
                qty                = item["qty"],
                unit_price         = item["unit_price"],
                customer           = customer,
                jurisdiction_code  = jurisdiction_code,
                sale_date          = sale_date,
                tax_inclusive      = tax_inclusive,
            )
            results.append(result)
            total_tax += result.tax_amount
            line_val   = Decimal(str(item["unit_price"])) * Decimal(str(item["qty"]))
            if result.is_exempt:
                total_exempt += line_val
            else:
                total_taxable += line_val

        return {
            "lines":         results,
            "total_tax":     total_tax,
            "total_taxable": total_taxable,
            "total_exempt":  total_exempt,
        }

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_jurisdiction(self, code: str) -> Optional[TaxJurisdiction]:
        if code not in self._jurisdiction_cache:
            j = self.db.query(TaxJurisdiction).filter(
                TaxJurisdiction.code == code,
                TaxJurisdiction.is_active == True,
            ).first()
            self._jurisdiction_cache[code] = j
        return self._jurisdiction_cache[code]

    def _get_product_rate(
        self, product_id: int, jurisdiction_code: str, calc_date: date
    ) -> Optional[TaxRate]:
        """Get product-specific tax rate assignment for a jurisdiction and date."""
        cache_key = (product_id, jurisdiction_code, calc_date)
        if cache_key in self._rate_cache:
            return self._rate_cache[cache_key]

        jurisdiction = self._get_jurisdiction(jurisdiction_code)
        if not jurisdiction:
            return None

        assignment = (
            self.db.query(ProductTaxAssignment)
            .filter(ProductTaxAssignment.product_id      == product_id,
                    ProductTaxAssignment.jurisdiction_id == jurisdiction.id)
            .first()
        )

        if not assignment:
            result = None
        else:
            result = self._rate_effective_on(assignment.tax_rate_id, calc_date)

        self._rate_cache[cache_key] = result
        return result

    def _get_default_rate(self, jurisdiction_code: str, calc_date: date) -> Optional[TaxRate]:
        """Get the STANDARD rate for a jurisdiction on a given date."""
        jurisdiction = self._get_jurisdiction(jurisdiction_code)
        if not jurisdiction:
            logger.warning("Tax jurisdiction '%s' not found — no tax will be applied", jurisdiction_code)
            return None

        return (
            self.db.query(TaxRate)
            .filter(
                TaxRate.jurisdiction_id == jurisdiction.id,
                TaxRate.code            == "STANDARD",
                TaxRate.is_active       == True,
                TaxRate.effective_from  <= calc_date,
            )
            .filter(
                (TaxRate.effective_to == None) | (TaxRate.effective_to >= calc_date)
            )
            .order_by(TaxRate.effective_from.desc())
            .first()
        )

    def _rate_effective_on(self, tax_rate_id: int, calc_date: date) -> Optional[TaxRate]:
        """Get a specific tax rate row, verifying it's effective on calc_date."""
        row = self.db.query(TaxRate).filter(TaxRate.id == tax_rate_id).first()
        if not row or not row.is_active:
            return None
        if row.effective_from > calc_date:
            return None
        if row.effective_to and row.effective_to < calc_date:
            return None
        return row

    def _get_customer_exemption(
        self, customer_id: int, jurisdiction_code: str, calc_date: date
    ) -> Optional[CustomerTaxExemption]:
        """Check if a customer has a valid exemption for the jurisdiction on the sale date."""
        jurisdiction = self._get_jurisdiction(jurisdiction_code)
        if not jurisdiction:
            return None

        return (
            self.db.query(CustomerTaxExemption)
            .filter(
                CustomerTaxExemption.customer_id     == customer_id,
                CustomerTaxExemption.jurisdiction_id == jurisdiction.id,
                CustomerTaxExemption.is_active       == True,
                CustomerTaxExemption.valid_from      <= calc_date,
            )
            .filter(
                (CustomerTaxExemption.valid_to == None) |
                (CustomerTaxExemption.valid_to >= calc_date)
            )
            .first()
        )
