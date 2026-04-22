"""
Returns & Refunds ORM models — SmartlynX POS v4.6

Design rules
------------
- ReturnTransaction: one per return event (can span multiple items)
- ReturnItem: one per line item being returned (per-line granularity)
- Original transactions are NEVER modified — they stay COMPLETED
- All amounts are snapshots from the original transaction at the time of sale
- is_restorable drives both stock restoration and COGS accounting reversal
- Accounting ref_type = "return", ref_id = return_number
"""

import enum
import uuid as _uuid
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean,
    DateTime, Text, ForeignKey, Index, CheckConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class ReturnStatus(str, enum.Enum):
    PENDING   = "pending"     # awaiting supervisor approval
    COMPLETED = "completed"   # refund issued, stock/accounting settled
    REJECTED  = "rejected"    # supervisor rejected — no refund, no restock


class ReturnReason(str, enum.Enum):
    CHANGE_OF_MIND     = "change_of_mind"
    DEFECTIVE          = "defective"
    WRONG_ITEM         = "wrong_item"
    DAMAGED_IN_TRANSIT = "damaged_in_transit"
    EXPIRED            = "expired"
    QUALITY_ISSUE      = "quality_issue"
    OTHER              = "other"


class RefundMethod(str, enum.Enum):
    CASH           = "cash"
    MPESA          = "mpesa"
    CARD           = "card"
    CREDIT_NOTE    = "credit_note"    # paper document — no system payment
    STORE_CREDIT   = "store_credit"   # added to customer.credit_balance


# ── ReturnTransaction ─────────────────────────────────────────────────────────

class ReturnTransaction(Base):
    """
    One record per return/refund event.

    Invariants:
      - original_txn must have status = COMPLETED
      - store_id must match original_txn.store_id (enforced in service)
      - status machine: PENDING → COMPLETED | REJECTED (irreversible)
      - SUM(qty_returned per original_txn_item_id, COMPLETED) ≤ original qty
    """
    __tablename__ = "return_transactions"
    __table_args__ = (
        Index("idx_ret_store_status",  "store_id", "status"),
        Index("idx_ret_original_txn",  "original_txn_id"),
        Index("idx_ret_store_created", "store_id", "created_at"),
        CheckConstraint(
            "status IN ('pending','approved','completed','rejected')",
            name="ck_ret_status",
        ),
        CheckConstraint(
            "refund_amount IS NULL OR refund_amount >= 0",
            name="ck_ret_refund_nonneg",
        ),
    )

    id            = Column(Integer, primary_key=True, index=True)
    uuid          = Column(String(36), nullable=False, unique=True, index=True,
                           default=lambda: str(_uuid.uuid4()))
    return_number = Column(String(30), nullable=False, unique=True, index=True)
    # Format: RET-XXXXXXXX  (generated in service layer)

    # ── Tenant + original txn linkage ─────────────────────────────────────────
    store_id             = Column(Integer, ForeignKey("stores.id"),        nullable=False, index=True)
    original_txn_id      = Column(Integer, ForeignKey("transactions.id"),  nullable=False, index=True)
    original_txn_number  = Column(String(30), nullable=False)  # immutable snapshot

    # ── State ─────────────────────────────────────────────────────────────────
    status        = Column(String(15), nullable=False, default=ReturnStatus.PENDING)

    # ── Reason ────────────────────────────────────────────────────────────────
    return_reason = Column(String(30), nullable=False)
    reason_notes  = Column(Text, nullable=True)

    # ── Refund payment (populated when completed) ─────────────────────────────
    refund_method = Column(String(20), nullable=True)
    refund_amount = Column(Numeric(12, 2), nullable=True)
    refund_ref    = Column(String(100), nullable=True)
    # e.g. M-PESA confirmation code for the outgoing refund payment

    # ── Summary flags + snapshot totals ──────────────────────────────────────
    is_partial           = Column(Boolean, nullable=False, default=False)
    total_refund_gross   = Column(Numeric(12, 2), nullable=True)  # sum of line_totals
    total_vat_reversed   = Column(Numeric(12, 2), nullable=True)
    total_cogs_reversed  = Column(Numeric(12, 2), nullable=True)  # 0 for non-restorable

    # ── Personnel ─────────────────────────────────────────────────────────────
    requested_by   = Column(Integer, ForeignKey("employees.id"), nullable=False)
    approved_by    = Column(Integer, ForeignKey("employees.id"), nullable=True)
    approved_at    = Column(DateTime(timezone=True), nullable=True)
    rejected_by    = Column(Integer, ForeignKey("employees.id"), nullable=True)
    rejected_at    = Column(DateTime(timezone=True), nullable=True)
    rejection_notes = Column(Text, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    items        = relationship("ReturnItem", back_populates="return_transaction",
                                cascade="all, delete-orphan")
    original_txn = relationship("Transaction", foreign_keys=[original_txn_id])
    requester    = relationship("Employee", foreign_keys=[requested_by])
    approver     = relationship("Employee", foreign_keys=[approved_by])
    rejector     = relationship("Employee", foreign_keys=[rejected_by])

    def __repr__(self):
        return (
            f"<ReturnTransaction {self.return_number} "
            f"orig={self.original_txn_number} status={self.status}>"
        )

    @property
    def is_pending(self) -> bool:
        return self.status == ReturnStatus.PENDING

    @property
    def is_completed(self) -> bool:
        return self.status == ReturnStatus.COMPLETED

    @property
    def is_rejected(self) -> bool:
        return self.status == ReturnStatus.REJECTED


# ── ReturnItem ────────────────────────────────────────────────────────────────

class ReturnItem(Base):
    """
    One record per line item returned.

    Financial snapshots are copied from the original TransactionItem at the
    time of return creation — they NEVER change after that. This preserves
    auditability even if product pricing changes later.

    is_restorable drives two independent decisions:
      1. Whether stock_quantity is incremented (stock restoration)
      2. Whether a COGS/Inventory accounting reversal is posted
    """
    __tablename__ = "return_items"
    __table_args__ = (
        Index("idx_ri_return_txn", "return_txn_id"),
        Index("idx_ri_orig_item",  "original_txn_item_id"),
        Index("idx_ri_product",    "product_id"),
        CheckConstraint("qty_returned > 0",     name="ck_ri_qty_positive"),
        CheckConstraint("line_total >= 0",      name="ck_ri_line_nonneg"),
        CheckConstraint("cost_price_snap >= 0", name="ck_ri_cost_nonneg"),
    )

    id                  = Column(Integer, primary_key=True, index=True)
    return_txn_id       = Column(Integer, ForeignKey("return_transactions.id"), nullable=False)

    # Immutable FK to the original line item
    original_txn_item_id = Column(Integer, ForeignKey("transaction_items.id"), nullable=False)
    product_id           = Column(Integer, ForeignKey("products.id"),           nullable=False)

    # Snapshots from original transaction (never recalculate from live data)
    product_name        = Column(String(200),    nullable=False)
    sku                 = Column(String(50),     nullable=False)
    qty_returned        = Column(Integer,        nullable=False)
    unit_price_at_sale  = Column(Numeric(12, 2), nullable=False)
    cost_price_snap     = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_proportion = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    # discount_proportion = original_item.discount * (qty_returned / original_item.qty)
    vat_amount          = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    line_total          = Column(Numeric(12, 2), nullable=False)
    # line_total = (unit_price * qty_returned) - discount_proportion
    # (ex-VAT — matches how original transaction_items.line_total is computed)

    # Restockability — drives stock and COGS accounting decisions
    is_restorable  = Column(Boolean, nullable=False, default=True)
    damaged_notes  = Column(Text, nullable=True)

    # Relationships
    return_transaction    = relationship("ReturnTransaction", back_populates="items")
    original_txn_item     = relationship("TransactionItem",  foreign_keys=[original_txn_item_id])
    product               = relationship("Product",          foreign_keys=[product_id])

    def __repr__(self):
        return (
            f"<ReturnItem sku={self.sku} qty={self.qty_returned} "
            f"restorable={self.is_restorable}>"
        )

    @property
    def cogs_amount(self) -> Decimal:
        """COGS to reverse — only meaningful if is_restorable."""
        return (
            Decimal(str(self.cost_price_snap)) * Decimal(str(self.qty_returned))
        ).quantize(Decimal("0.01"))
