"""
Tax engine models — Production Hardening v4.5

Replaces the hardcoded 16% VAT single-boolean approach with a configuration-
driven tax rules engine. All tax rates, jurisdictions, and exemptions are stored
in the database — rate changes require a config update with an effective date,
NOT a code deployment.

Design principles:
  1. Tax rates have effective dates — historical accuracy is preserved
  2. Line-level tax snapshots on TransactionItem are always stored
  3. Customer exemptions are first-class entities (KRA exemption certificates)
  4. Multi-jurisdiction: adding Uganda/Tanzania = adding rows, not code
"""

import enum
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean,
    DateTime, Date, Text, ForeignKey, Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ── TaxJurisdiction ───────────────────────────────────────────────────────────

class TaxJurisdiction(Base):
    """
    A tax authority / region. One row per country + tax type.

    Examples:
      code='KE_VAT'  name='Kenya VAT'       country='KE'
      code='UG_VAT'  name='Uganda VAT'      country='UG'
      code='TZ_VAT'  name='Tanzania VAT'    country='TZ'
    """
    __tablename__ = "tax_jurisdictions"

    id         = Column(Integer, primary_key=True, index=True)
    code       = Column(String(20),  nullable=False, unique=True)  # 'KE_VAT', 'UG_VAT'
    name       = Column(String(100), nullable=False)
    country    = Column(String(2),   nullable=False)               # ISO 3166-1 alpha-2
    is_active  = Column(Boolean,     default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    rates = relationship("TaxRate", back_populates="jurisdiction")

    def __repr__(self):
        return f"<TaxJurisdiction {self.code} ({self.country})>"


# ── TaxRate ───────────────────────────────────────────────────────────────────

class TaxRate(Base):
    """
    A specific tax rate within a jurisdiction, with effective date range.

    The effective_to=NULL means "currently active."
    When a rate changes, the old row gets effective_to set and a new row
    is created with the new rate and the new effective_from date.

    Codes:
      STANDARD  — standard rate (e.g. 16% KE VAT)
      ZERO      — zero-rated (0% VAT but still VAT-registered goods)
      EXEMPT    — entirely exempt (no VAT)
      REDUCED   — reduced rate (future use, e.g. certain food items)
    """
    __tablename__ = "tax_rates"
    __table_args__ = (
        Index("ix_tax_rates_jurisdiction_active", "jurisdiction_id", "is_active"),
        Index("ix_tax_rates_effective", "jurisdiction_id", "code", "effective_from"),
    )

    id              = Column(Integer, primary_key=True, index=True)
    jurisdiction_id = Column(Integer, ForeignKey("tax_jurisdictions.id"), nullable=False, index=True)

    code            = Column(String(20),  nullable=False)          # STANDARD, ZERO, EXEMPT, REDUCED
    rate            = Column(Numeric(6, 4), nullable=False)        # 0.1600 = 16%
    name            = Column(String(80),  nullable=False)          # "Standard VAT 16%"
    description     = Column(Text,        nullable=True)

    effective_from  = Column(Date, nullable=False)
    effective_to    = Column(Date, nullable=True)                  # NULL = still active

    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    jurisdiction = relationship("TaxJurisdiction", back_populates="rates")
    product_assignments = relationship("ProductTaxAssignment", back_populates="tax_rate")

    def __repr__(self):
        return f"<TaxRate {self.code} {float(self.rate)*100:.2f}% from={self.effective_from}>"


# ── ProductTaxAssignment ──────────────────────────────────────────────────────

class ProductTaxAssignment(Base):
    """
    Links a product to a tax rate for a specific jurisdiction.

    A product can have different tax treatment in different jurisdictions.
    For example, baby formula might be zero-rated in Kenya but standard-rated
    in Uganda.

    If no assignment exists for a product+jurisdiction, the system defaults
    to the STANDARD rate for that jurisdiction.
    """
    __tablename__ = "product_tax_assignments"
    __table_args__ = (
        UniqueConstraint("product_id", "jurisdiction_id", name="uq_product_tax_jurisdiction"),
    )

    id              = Column(Integer, primary_key=True, index=True)
    product_id      = Column(Integer, ForeignKey("products.id"),       nullable=False, index=True)
    jurisdiction_id = Column(Integer, ForeignKey("tax_jurisdictions.id"), nullable=False)
    tax_rate_id     = Column(Integer, ForeignKey("tax_rates.id"),      nullable=False)

    created_by  = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    product      = relationship("Product")
    tax_rate     = relationship("TaxRate", back_populates="product_assignments")
    jurisdiction = relationship("TaxJurisdiction")

    def __repr__(self):
        return f"<ProductTaxAssignment product={self.product_id} rate={self.tax_rate_id}>"


# ── CustomerTaxExemption ──────────────────────────────────────────────────────

class CustomerTaxExemption(Base):
    """
    Records a customer's tax exemption for a specific jurisdiction.

    Example: Nairobi City Council has a KRA exemption certificate.
    When they purchase, no VAT is charged on any line item regardless of
    the product's default tax assignment.

    The exemption_ref stores the KRA exemption certificate number for audit.
    """
    __tablename__ = "customer_tax_exemptions"
    __table_args__ = (
        UniqueConstraint("customer_id", "jurisdiction_id", name="uq_customer_tax_exemption"),
        Index("ix_cte_customer_active", "customer_id", "is_active"),
    )

    id              = Column(Integer, primary_key=True, index=True)
    customer_id     = Column(Integer, ForeignKey("customers.id"),          nullable=False, index=True)
    jurisdiction_id = Column(Integer, ForeignKey("tax_jurisdictions.id"),  nullable=False)

    exemption_ref   = Column(String(100), nullable=True)   # KRA certificate number
    valid_from      = Column(Date, nullable=False)
    valid_to        = Column(Date, nullable=True)          # NULL = indefinite

    is_active       = Column(Boolean, default=True, nullable=False)
    created_by      = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    customer     = relationship("Customer")
    jurisdiction = relationship("TaxJurisdiction")
    creator      = relationship("Employee", foreign_keys=[created_by])

    def __repr__(self):
        return (
            f"<CustomerTaxExemption customer={self.customer_id} "
            f"jurisdiction={self.jurisdiction_id} ref={self.exemption_ref}>"
        )
