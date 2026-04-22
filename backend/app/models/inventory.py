"""
Inventory integrity models — Production Hardening v4.5

New tables:
  CostLayer         — WAC/FIFO cost tracking per GRN receipt
  OversellEvent     — detected oversells requiring manager resolution
  StockAllocation   — terminal stock reservation buckets (Option B offline safety)
  AccountingPeriod  — period close / locked periods for immutability
"""

import enum
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean,
    DateTime, Date, Text, ForeignKey, Index,
    CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class OversellResolution(str, enum.Enum):
    PENDING     = "pending"
    WRITTEN_OFF = "written_off"     # accept stock loss
    REVERSED    = "reversed"        # void one of the overselling transactions
    SOURCED     = "sourced"         # found replacement product urgently
    IGNORED     = "ignored"         # low-value, manager chose to ignore


class PeriodStatus(str, enum.Enum):
    OPEN   = "open"
    CLOSED = "closed"
    LOCKED = "locked"               # fully immutable, cannot be reopened


class AllocationStatus(str, enum.Enum):
    ACTIVE    = "active"
    EXHAUSTED = "exhausted"
    RETURNED  = "returned"
    EXPIRED   = "expired"


# ── CostLayer ─────────────────────────────────────────────────────────────────

class CostLayer(Base):
    """
    One row per goods receipt batch for a product.

    Used to:
      1. Track WAC (Weighted Average Cost) — each layer contributes to the
         running WAC on products.wac
      2. Enable FIFO in future — qty_remaining decremented oldest-first on sale

    Only POSTED GRNs create cost layers. Draft GRNs and cancelled GRNs do not.

    Invariants:
      0 <= qty_remaining <= qty_received
      unit_cost >= 0
    """
    __tablename__ = "cost_layers"
    __table_args__ = (
        CheckConstraint("qty_received > 0",       name="ck_cl_qty_received_positive"),
        CheckConstraint("qty_remaining >= 0",      name="ck_cl_qty_remaining_nonneg"),
        CheckConstraint("unit_cost >= 0",          name="ck_cl_unit_cost_nonneg"),
        Index("ix_cost_layers_product_store", "product_id", "store_id"),
        Index("ix_cost_layers_effective_date", "product_id", "effective_date"),
    )

    id             = Column(Integer, primary_key=True, index=True)
    product_id     = Column(Integer, ForeignKey("products.id"),             nullable=False, index=True)
    store_id       = Column(Integer, ForeignKey("stores.id"),               nullable=False, index=True)
    grn_id         = Column(Integer, ForeignKey("goods_received_notes.id"), nullable=True)
    # NULL grn_id = opening balance / manual adjustment

    qty_received   = Column(Integer,       nullable=False)
    qty_remaining  = Column(Integer,       nullable=False)  # decremented as items are sold (FIFO)
    unit_cost      = Column(Numeric(12, 4), nullable=False)  # 4 decimal places for KES accuracy
    effective_date = Column(Date,          nullable=False)

    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), onupdate=func.now())

    product = relationship("Product")

    @property
    def layer_value(self) -> Decimal:
        return Decimal(str(self.qty_remaining)) * Decimal(str(self.unit_cost))

    def __repr__(self):
        return (
            f"<CostLayer product_id={self.product_id} "
            f"qty={self.qty_remaining}/{self.qty_received} "
            f"cost={self.unit_cost} date={self.effective_date}>"
        )


# ── OversellEvent ─────────────────────────────────────────────────────────────

class OversellEvent(Base):
    """
    Detected when synced transactions collectively cause stock_quantity to go
    negative on a product. Created by the reconciliation background job.

    Workflow:
      1. Reconciliation job detects product.stock_quantity < 0 after sync
      2. OversellEvent created with resolution = PENDING
      3. Alert sent to store manager
      4. Manager reviews contributing_terminal_ids and resolves:
         - REVERSED: void the later transaction, restock
         - WRITTEN_OFF: accept the loss, adjust accounting
         - SOURCED: emergency restock found
         - IGNORED: low-value / acceptable overcommit
    """
    __tablename__ = "oversell_events"
    __table_args__ = (
        Index("ix_oversell_store_status", "store_id", "resolution"),
        Index("ix_oversell_product", "product_id", "detected_at"),
    )

    id                      = Column(Integer, primary_key=True, index=True)
    store_id                = Column(Integer, ForeignKey("stores.id"),    nullable=False, index=True)
    product_id              = Column(Integer, ForeignKey("products.id"),  nullable=False, index=True)

    # What the cloud stock was before the oversell was detected
    stock_before_sync       = Column(Integer, nullable=False)
    # Combined units sold across all offline terminals in this batch
    total_sold_offline      = Column(Integer, nullable=False)
    # Net shortfall: total_sold_offline - stock_before_sync (always > 0 here)
    shortfall_qty           = Column(Integer, nullable=False)
    # Which terminals contributed to the oversell (JSON array of terminal_ids)
    contributing_terminals  = Column(Text, nullable=True)  # JSON: ["T-001", "T-002"]
    # Which txn_numbers are candidates for reversal
    candidate_txn_numbers   = Column(Text, nullable=True)  # JSON array

    resolution   = Column(String(20), default=OversellResolution.PENDING, nullable=False, index=True)
    resolved_by  = Column(Integer, ForeignKey("employees.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    detected_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at  = Column(DateTime(timezone=True), nullable=True)

    product  = relationship("Product")
    resolver = relationship("Employee", foreign_keys=[resolved_by])

    def __repr__(self):
        return (
            f"<OversellEvent product_id={self.product_id} "
            f"shortfall={self.shortfall_qty} resolution={self.resolution}>"
        )


# ── StockAllocation ───────────────────────────────────────────────────────────

class StockAllocation(Base):
    """
    Terminal stock reservation buckets (Option B offline safety model).

    When a terminal goes online, the cloud allocates a portion of available
    stock to it. The terminal can sell freely within its allocation while
    offline. On reconnect, consumed_qty is reported and unused qty is returned
    to the cloud reserve.

    This prevents oversell by ensuring no two terminals are allocated more
    units than physically exist in the store.

    Invariants:
      consumed_qty <= allocated_qty
      SUM(allocated_qty for all active allocations) <= products.stock_quantity
    """
    __tablename__ = "stock_allocations"
    __table_args__ = (
        UniqueConstraint("product_id", "terminal_id", name="uq_allocation_product_terminal"),
        Index("ix_alloc_store_product", "store_id", "product_id"),
        CheckConstraint("allocated_qty >= 0", name="ck_alloc_qty_nonneg"),
        CheckConstraint("consumed_qty >= 0",  name="ck_alloc_consumed_nonneg"),
    )

    id             = Column(Integer, primary_key=True, index=True)
    product_id     = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    store_id       = Column(Integer, ForeignKey("stores.id"),   nullable=False, index=True)
    terminal_id    = Column(String(50), nullable=False, index=True)

    allocated_qty  = Column(Integer, nullable=False, default=0)
    consumed_qty   = Column(Integer, nullable=False, default=0)
    status         = Column(String(15), default=AllocationStatus.ACTIVE, nullable=False)

    allocated_at   = Column(DateTime(timezone=True), server_default=func.now())
    refreshed_at   = Column(DateTime(timezone=True), nullable=True)
    expires_at     = Column(DateTime(timezone=True), nullable=True)  # auto-return if not refreshed

    product = relationship("Product")

    @property
    def remaining_qty(self) -> int:
        return max(0, self.allocated_qty - self.consumed_qty)

    @property
    def is_exhausted(self) -> bool:
        return self.consumed_qty >= self.allocated_qty

    def __repr__(self):
        return (
            f"<StockAllocation terminal={self.terminal_id} "
            f"product_id={self.product_id} "
            f"alloc={self.allocated_qty} consumed={self.consumed_qty}>"
        )


# ── AccountingPeriod ──────────────────────────────────────────────────────────

class AccountingPeriod(Base):
    """
    Defines open and closed financial periods per store.

    Rules enforced by the accounting service:
      - OPEN:   journal entries can be posted freely
      - CLOSED: no new entries allowed; reversals must be posted in the current period
      - LOCKED: permanently immutable; cannot be reopened even by ADMIN

    Period close requires ADMIN role. Locking requires PLATFORM_OWNER confirmation.

    A store has exactly one OPEN period at any time. Closing requires
    an open period to exist for the next month before close is allowed.
    """
    __tablename__ = "accounting_periods"
    __table_args__ = (
        UniqueConstraint("store_id", "period_name", name="uq_period_store_name"),
        Index("ix_period_store_status", "store_id", "status"),
    )

    id          = Column(Integer, primary_key=True, index=True)
    store_id    = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)

    period_name = Column(String(20), nullable=False)       # e.g. "APR-2026"
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=False)
    status      = Column(String(10), default=PeriodStatus.OPEN, nullable=False)

    closed_by   = Column(Integer, ForeignKey("employees.id"), nullable=True)
    closed_at   = Column(DateTime(timezone=True), nullable=True)

    locked_by   = Column(Integer, ForeignKey("employees.id"), nullable=True)
    locked_at   = Column(DateTime(timezone=True), nullable=True)

    notes       = Column(Text, nullable=True)   # e.g. "Closed for Q1 audit"

    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    closer  = relationship("Employee", foreign_keys=[closed_by])
    locker  = relationship("Employee", foreign_keys=[locked_by])

    def __repr__(self):
        return f"<AccountingPeriod {self.period_name} store={self.store_id} status={self.status}>"

    @property
    def is_open(self) -> bool:
        return self.status == PeriodStatus.OPEN

    @property
    def is_writable(self) -> bool:
        """True if journal entries can be posted to this period."""
        return self.status == PeriodStatus.OPEN
