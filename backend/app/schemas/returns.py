"""
Pydantic schemas for the returns/refunds workflow.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.returns import RefundMethod, ReturnReason, ReturnStatus


# ── Request schemas ───────────────────────────────────────────────────────────

class ReturnItemCreate(BaseModel):
    """One line item the customer is returning."""
    original_txn_item_id: int               = Field(..., description="ID of the TransactionItem being returned")
    qty_returned: int                       = Field(..., gt=0, description="Must be > 0 and ≤ original qty sold")
    is_restorable: bool                     = True
    damaged_notes: Optional[str]            = Field(None, max_length=500)


class ReturnCreate(BaseModel):
    """
    Cashier creates a return request.

    The request carries the original transaction ID and the list of items
    (with qty) to return.  At least one item is required.
    The supervisor/manager will approve and select the refund method.
    """
    original_txn_id: int
    return_reason: ReturnReason
    reason_notes: Optional[str] = Field(None, max_length=1000)
    items: List[ReturnItemCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def no_duplicate_items(self) -> "ReturnCreate":
        """Each original_txn_item_id must appear at most once per return."""
        seen: set[int] = set()
        for item in self.items:
            if item.original_txn_item_id in seen:
                raise ValueError(
                    f"Duplicate original_txn_item_id {item.original_txn_item_id} "
                    f"in return request — each item can only appear once."
                )
            seen.add(item.original_txn_item_id)
        return self


class ReturnApproveRequest(BaseModel):
    """
    Supervisor/manager approves a pending return and simultaneously executes it.
    Selecting the refund method here is required — the system posts
    accounting and restores stock atomically on approval.
    """
    refund_method: RefundMethod
    refund_ref: Optional[str]   = Field(None, max_length=100,
                                         description="M-PESA ref, card auth code, etc.")
    notes: Optional[str]        = Field(None, max_length=500)


class ReturnRejectRequest(BaseModel):
    rejection_notes: str = Field(..., min_length=3, max_length=1000)


# ── Response schemas ──────────────────────────────────────────────────────────

class ReturnItemOut(BaseModel):
    id:                   int
    original_txn_item_id: int
    product_id:           int
    product_name:         str
    sku:                  str
    qty_returned:         int
    unit_price_at_sale:   Decimal
    cost_price_snap:      Decimal
    discount_proportion:  Decimal
    vat_amount:           Decimal
    line_total:           Decimal
    is_restorable:        bool
    damaged_notes:        Optional[str]

    class Config:
        from_attributes = True


class ReturnSummary(BaseModel):
    """Lightweight row for list views."""
    id:                  int
    return_number:       str
    original_txn_number: str
    status:              ReturnStatus
    return_reason:       ReturnReason
    refund_method:       Optional[RefundMethod]
    refund_amount:       Optional[Decimal]
    is_partial:          bool
    requested_by:        int
    created_at:          datetime

    class Config:
        from_attributes = True


class ReturnOut(BaseModel):
    """Full detail including line items."""
    id:                   int
    uuid:                 str
    return_number:        str
    store_id:             int
    original_txn_id:      int
    original_txn_number:  str
    status:               ReturnStatus
    return_reason:        ReturnReason
    reason_notes:         Optional[str]
    refund_method:        Optional[RefundMethod]
    refund_amount:        Optional[Decimal]
    refund_ref:           Optional[str]
    is_partial:           bool
    total_refund_gross:   Optional[Decimal]
    total_vat_reversed:   Optional[Decimal]
    total_cogs_reversed:  Optional[Decimal]
    requested_by:         int
    approved_by:          Optional[int]
    approved_at:          Optional[datetime]
    rejected_by:          Optional[int]
    rejected_at:          Optional[datetime]
    rejection_notes:      Optional[str]
    created_at:           datetime
    completed_at:         Optional[datetime]
    items:                List[ReturnItemOut] = []

    class Config:
        from_attributes = True
