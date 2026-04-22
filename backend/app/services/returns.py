"""
Returns & Refunds service — SmartlynX POS v4.6

Public API
──────────
  create_return(db, current_employee, payload)  →  ReturnTransaction
  get_return(db, current_employee, return_id)   →  ReturnTransaction
  list_returns(db, current_employee, ...)       →  list[ReturnTransaction]
  approve_and_complete(db, approver, return_id, payload)  →  ReturnTransaction
  reject_return(db, rejector, return_id, payload)         →  ReturnTransaction

Design invariants enforced here
────────────────────────────────
1. Original transaction MUST be COMPLETED and belong to the same store.
2. Qty ceiling: SUM(returned_qty for item, COMPLETED returns) ≤ original qty.
   Uses SELECT FOR UPDATE to prevent race conditions.
3. store_id of return == store_id of original txn == store_id of current employee.
4. Accounting, stock restoration, and status update are committed atomically.
5. cost_price_snap comes from the ORIGINAL transaction_item — never recalculated.
6. CASHIER role cannot approve or reject — only SUPERVISOR/MANAGER/ADMIN.
7. A return cannot target a VOIDED or already-VOIDED transaction.
8. Completed and rejected returns are permanently immutable.
"""

from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.audit import AuditTrail
from app.models.employee import Employee, Role
from app.models.product import Product, StockMovement
from app.core.stock_movements import StockMovementType
from app.models.returns import (
    RefundMethod, ReturnItem, ReturnReason, ReturnStatus, ReturnTransaction,
)
from app.models.transaction import Transaction, TransactionItem, TransactionStatus
from app.models.customer import Customer
from app.models.cash_session import CashSession
from app.schemas.returns import ReturnApproveRequest, ReturnCreate, ReturnRejectRequest
from app.services.accounting import post_return as _post_accounting_entry

logger = logging.getLogger("smartlynx.returns")

TWO = Decimal("0.01")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _q(v) -> Decimal:
    return Decimal(str(v)).quantize(TWO, rounding=ROUND_HALF_UP)


def _generate_return_number() -> str:
    """RET-XXXXXXXX — 8 random uppercase alphanumeric characters."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=8))
    return f"RET-{suffix}"


def _assert_store_access(employee: Employee, store_id: int) -> None:
    """Raise 403 if this employee cannot operate on the given store."""
    if employee.role == Role.PLATFORM_OWNER:
        return  # platform owner has global access
    if employee.store_id != store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied — cross-store operation rejected.",
        )


def _qty_already_returned(
    db: Session,
    original_txn_item_id: int,
    lock_item: bool = False,
) -> tuple[int, Optional[TransactionItem]]:
    """
    Sum of qty_returned across ALL COMPLETED returns for this transaction item.
    Used to enforce the qty ceiling invariant.
    
    Returns: (already_returned_qty, original_txn_item_or_none)
    
    If lock_item=True:
      - Locks the TransactionItem row for UPDATE
      - Used during approve_and_complete() to ensure atomic validation
      - Returned item is the locked row (or None if not found)
    """
    rows = (
        db.query(ReturnItem)
        .join(ReturnTransaction, ReturnTransaction.id == ReturnItem.return_txn_id)
        .filter(
            ReturnItem.original_txn_item_id == original_txn_item_id,
            ReturnTransaction.status == ReturnStatus.COMPLETED,
        )
        .all()
    )
    qty_returned = sum(r.qty_returned for r in rows)
    
    if lock_item:
        # Lock the item row and return it
        orig_item = (
            db.query(TransactionItem)
            .filter(TransactionItem.id == original_txn_item_id)
            .with_for_update()
            .first()
        )
        return (qty_returned, orig_item)
    else:
        return (qty_returned, None)


def _write_audit(
    db:        Session,
    store_id:  int,
    actor:     Employee,
    action:    str,
    entity_id: str,
    before:    Optional[dict],
    after:     Optional[dict],
) -> None:
    db.add(AuditTrail(
        store_id   = store_id,
        actor_id   = actor.id,
        actor_name = actor.full_name,
        action     = action,
        entity     = "return",
        entity_id  = entity_id,
        before_val = before,
        after_val  = after,
    ))


# ── Public service functions ──────────────────────────────────────────────────

def create_return(
    db:       Session,
    employee: Employee,
    payload:  ReturnCreate,
) -> ReturnTransaction:
    """
    Step 1 — cashier creates a return request (PENDING).

    Validates:
      - original transaction exists, is COMPLETED, belongs to same store
      - each item belongs to that transaction
      - qty_returned ≤ (original qty − already COMPLETED returns)
      - at least one item is being returned
    """
    # ── Load and validate original transaction ────────────────────────────────
    orig_txn = db.query(Transaction).filter(
        Transaction.id == payload.original_txn_id,
    ).first()

    if not orig_txn:
        raise HTTPException(status_code=404, detail="Original transaction not found.")

    _assert_store_access(employee, orig_txn.store_id)

    if orig_txn.status != TransactionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot return against a transaction with status '{orig_txn.status}'. "
                f"Only COMPLETED transactions can be returned."
            ),
        )

    # ── Validate each item ────────────────────────────────────────────────────
    return_items: list[ReturnItem] = []

    for item_req in payload.items:
        orig_item = db.query(TransactionItem).filter(
            TransactionItem.id             == item_req.original_txn_item_id,
            TransactionItem.transaction_id == orig_txn.id,
        ).first()

        if not orig_item:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Transaction item {item_req.original_txn_item_id} "
                    f"does not belong to transaction {orig_txn.txn_number}."
                ),
            )

        already_returned, _ = _qty_already_returned(db, orig_item.id, lock_item=False)
        returnable       = orig_item.qty - already_returned

        if item_req.qty_returned > returnable:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot return {item_req.qty_returned} × {orig_item.sku}. "
                    f"Original qty: {orig_item.qty}, already returned: {already_returned}, "
                    f"remaining returnable: {returnable}."
                ),
            )

        # Compute proportional financials for the returned qty
        ratio     = Decimal(str(item_req.qty_returned)) / Decimal(str(orig_item.qty))
        orig_disc = Decimal(str(orig_item.discount or 0))
        orig_vat  = Decimal(str(orig_item.vat_amount or 0))

        discount_proportion = _q(orig_disc * ratio)
        vat_amount          = _q(orig_vat  * ratio)

        # line_total = (unit_price × qty_returned) − discount_proportion
        # This matches how TransactionItem.line_total is originally computed.
        unit_price_at_sale = _q(orig_item.unit_price)
        line_total         = _q(
            unit_price_at_sale * item_req.qty_returned - discount_proportion
        )
        cost_price_snap = _q(orig_item.cost_price_snap or Decimal("0"))

        return_items.append(ReturnItem(
            original_txn_item_id = orig_item.id,
            product_id           = orig_item.product_id,
            product_name         = orig_item.product_name,
            sku                  = orig_item.sku,
            qty_returned         = item_req.qty_returned,
            unit_price_at_sale   = unit_price_at_sale,
            cost_price_snap      = cost_price_snap,
            discount_proportion  = discount_proportion,
            vat_amount           = vat_amount,
            line_total           = line_total,
            is_restorable        = item_req.is_restorable,
            damaged_notes        = item_req.damaged_notes,
        ))

    # ── Determine is_partial ──────────────────────────────────────────────────
    all_orig_items = db.query(TransactionItem).filter(
        TransactionItem.transaction_id == orig_txn.id
    ).all()

    # is_partial = True if the return doesn't cover every item at its full original qty
    full_return = all(
        any(
            ri.original_txn_item_id == oi.id and ri.qty_returned == oi.qty
            for ri in return_items  # type: ignore[attr-defined]
        )
        for oi in all_orig_items
    )
    is_partial = not full_return

    # ── Persist ───────────────────────────────────────────────────────────────
    # Ensure unique return_number (retry up to 5×)
    for _ in range(5):
        return_number = _generate_return_number()
        if not db.query(ReturnTransaction).filter(
            ReturnTransaction.return_number == return_number
        ).first():
            break

    ret_txn = ReturnTransaction(
        return_number        = return_number,
        store_id             = orig_txn.store_id,
        original_txn_id      = orig_txn.id,
        original_txn_number  = orig_txn.txn_number,
        status               = ReturnStatus.PENDING,
        return_reason        = payload.return_reason,
        reason_notes         = payload.reason_notes,
        is_partial           = is_partial,
        requested_by         = employee.id,
    )

    for ri in return_items:
        ri.return_transaction = ret_txn

    db.add(ret_txn)
    db.flush()  # get ret_txn.id before audit

    _write_audit(
        db        = db,
        store_id  = orig_txn.store_id,
        actor     = employee,
        action    = "return_created",
        entity_id = ret_txn.return_number,
        before    = None,
        after     = {
            "return_number":    ret_txn.return_number,
            "original_txn":     orig_txn.txn_number,
            "reason":           payload.return_reason,
            "items":            [
                {"sku": ri.sku, "qty": ri.qty_returned, "restorable": ri.is_restorable}
                for ri in return_items
            ],
        },
    )

    db.commit()
    db.refresh(ret_txn)
    logger.info(
        "Return %s created for txn %s by employee %d (store %d)",
        ret_txn.return_number, orig_txn.txn_number, employee.id, orig_txn.store_id,
    )
    return ret_txn


def approve_and_complete(
    db:        Session,
    approver:  Employee,
    return_id: int,
    payload:   ReturnApproveRequest,
) -> ReturnTransaction:
    """
    Step 2 — supervisor/manager approves and atomically executes the return.

    Executes in this exact order (all inside one DB transaction):
      1. Re-validate qty ceilings (race-condition guard, with FOR UPDATE)
      2. Restore stock for restorable items
      3. Create StockMovement records
      4. Post accounting reversal journal entry
      5. Update return_transaction status → COMPLETED
      6. Write audit trail

    Any exception rolls back the entire operation.
    """
    if approver.role == Role.CASHIER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cashiers cannot approve return requests. Supervisor approval required.",
        )

    ret_txn = db.query(ReturnTransaction).filter(
        ReturnTransaction.id == return_id,
    ).first()

    if not ret_txn:
        raise HTTPException(status_code=404, detail="Return not found.")

    _assert_store_access(approver, ret_txn.store_id)

    if ret_txn.status != ReturnStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Return is already '{ret_txn.status}' — cannot approve.",
        )

    items: list[ReturnItem] = ret_txn.items
    if not items:
        raise HTTPException(status_code=400, detail="Return has no items.")

    # ── Refund method vs original payment method validation ───────────────────
    # Prevents cash extraction fraud on MPESA/card sales.
    orig_txn = db.query(Transaction).filter(
        Transaction.id == ret_txn.original_txn_id,
    ).first()
    if not orig_txn:
        raise HTTPException(status_code=404, detail="Original transaction not found.")

    _ALLOWED_REFUND_METHODS: dict = {
        "cash":         {RefundMethod.CASH,         RefundMethod.STORE_CREDIT},
        "mpesa":        {RefundMethod.MPESA,         RefundMethod.STORE_CREDIT, RefundMethod.CREDIT_NOTE},
        "card":         {RefundMethod.CARD,          RefundMethod.STORE_CREDIT, RefundMethod.CREDIT_NOTE},
        "credit":       {RefundMethod.STORE_CREDIT,  RefundMethod.CREDIT_NOTE},
        "store_credit": {RefundMethod.STORE_CREDIT},
    }
    orig_payment = orig_txn.payment_method.value.lower()
    allowed_methods = _ALLOWED_REFUND_METHODS.get(orig_payment, set(RefundMethod))

    if payload.refund_method not in allowed_methods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Refund method '{payload.refund_method.value}' is not permitted for a "
                f"'{orig_txn.payment_method.value}' sale. "
                f"Allowed methods: {[m.value for m in allowed_methods]}."
            ),
        )

    now = datetime.now(timezone.utc)

    # ── 1. Race-condition qty guard (FOR UPDATE with locked re-check) ────────
    # CRITICAL: Lock items FIRST, then recompute qty_already_returned while locked
    # This prevents concurrent approvals from both seeing stale "already_returned" values
    
    locked_items: dict[int, TransactionItem] = {}  # return_item_id -> locked TransactionItem
    for ri in items:
        already, orig_item = _qty_already_returned(db, ri.original_txn_item_id, lock_item=True)
        if not orig_item:
            raise HTTPException(status_code=400, detail="Original item no longer found.")
        
        locked_items[ri.id] = orig_item
        
        # Check qty ceiling WHILE HOLDING LOCK
        if already + ri.qty_returned > orig_item.qty:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Concurrent return conflict on item {ri.sku}: "
                    f"only {orig_item.qty - already} units are still returnable."
                ),
            )

    # ── 2 + 3. Stock restoration + StockMovement records ─────────────────────
    for ri in items:
        if not ri.is_restorable:
            logger.info(
                "Return %s: item %s is non-restorable (damaged) — no stock change",
                ret_txn.return_number, ri.sku,
            )
            continue

        product = (
            db.query(Product)
            .filter(Product.id == ri.product_id)
            .with_for_update()
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Product {ri.sku} (id={ri.product_id}) not found.",
            )

        qty_before             = product.stock_quantity
        product.stock_quantity += ri.qty_returned
        db.add(product)

        db.add(StockMovement(
            product_id    = product.id,
            store_id      = ret_txn.store_id,
            movement_type=StockMovementType.RETURN.value,
            qty_delta     = ri.qty_returned,
            qty_before    = qty_before,
            qty_after     = product.stock_quantity,
            ref_id        = ret_txn.return_number,
            notes         = (
                f"Return {ret_txn.return_number} — "
                f"orig txn {ret_txn.original_txn_number}"
            ),
            performed_by  = approver.id,
        ))

        logger.info(
            "Stock restored: product %d (%s) qty %d → %d (return %s)",
            product.id, product.sku,
            qty_before, product.stock_quantity,
            ret_txn.return_number,
        )


    # Store-credit wallet is separate from receivable debt.
    if payload.refund_method == RefundMethod.STORE_CREDIT:
        original_txn = db.query(Transaction).filter(Transaction.id == ret_txn.original_txn_id).first()
        if not original_txn or not original_txn.customer_id:
            raise HTTPException(status_code=400, detail="Store credit returns require an identified customer.")
        customer = db.query(Customer).filter(Customer.id == original_txn.customer_id, Customer.store_id == ret_txn.store_id).with_for_update().first()
        if not customer:
            raise HTTPException(status_code=400, detail="Customer for store credit return was not found.")
        wallet_increment = _q(sum(Decimal(str(ri.line_total)) for ri in items) + sum(Decimal(str(ri.vat_amount)) for ri in items))
        customer.store_credit_balance = _q(Decimal(str(customer.store_credit_balance or 0)) + wallet_increment)

    # ── 4. Till impact for cash refunds ───────────────────────────────────────
    if payload.refund_method == RefundMethod.CASH:
        original_txn = db.query(Transaction).filter(Transaction.id == ret_txn.original_txn_id).first()
        if original_txn and getattr(original_txn, "cash_session_id", None):
            cash_session = db.query(CashSession).filter(
                CashSession.id == original_txn.cash_session_id,
                CashSession.store_id == ret_txn.store_id,
                CashSession.status == "open",
            ).with_for_update().first()
            if cash_session:
                refund_cash = _q(sum(Decimal(str(ri.line_total)) for ri in items) + sum(Decimal(str(ri.vat_amount)) for ri in items))
                cash_session.expected_cash = _q(Decimal(str(cash_session.expected_cash or 0)) - refund_cash)

    # ── 5. Post accounting entry ──────────────────────────────────────────────
    # Set completion timestamp NOW so post_return() can use it for entry_date
    ret_txn.refund_method = payload.refund_method
    ret_txn.refund_ref    = payload.refund_ref
    ret_txn.completed_at  = now
    ret_txn.approved_by   = approver.id
    ret_txn.approved_at   = now
    db.flush()

    journal_entry = _post_accounting_entry(db, ret_txn, items)
    if journal_entry:
        logger.info(
            "Return %s — journal entry %d posted",
            ret_txn.return_number, journal_entry.id,
        )

    # ── 5. Compute and store snapshot totals ──────────────────────────────────
    total_refund_gross  = _q(sum(Decimal(str(ri.line_total)) for ri in items))
    total_vat_reversed  = _q(sum(Decimal(str(ri.vat_amount)) for ri in items))
    total_cogs_reversed = _q(sum(
        Decimal(str(ri.cost_price_snap)) * ri.qty_returned
        for ri in items if ri.is_restorable
    ))

    ret_txn.status              = ReturnStatus.COMPLETED
    ret_txn.total_refund_gross  = total_refund_gross
    ret_txn.total_vat_reversed  = total_vat_reversed
    ret_txn.total_cogs_reversed = total_cogs_reversed
    ret_txn.refund_amount       = _q(total_refund_gross + total_vat_reversed)

    _write_audit(
        db        = db,
        store_id  = ret_txn.store_id,
        actor     = approver,
        action    = "return_completed",
        entity_id = ret_txn.return_number,
        before    = {"status": ReturnStatus.PENDING},
        after     = {
            "status":         ReturnStatus.COMPLETED,
            "refund_method":  payload.refund_method,
            "refund_amount":  float(ret_txn.refund_amount),
            "total_vat":      float(total_vat_reversed),
            "total_cogs":     float(total_cogs_reversed),
            "approved_by":    approver.id,
        },
    )

    db.commit()
    db.refresh(ret_txn)
    logger.info(
        "Return %s COMPLETED by approver %d — refund %.2f via %s",
        ret_txn.return_number, approver.id,
        float(ret_txn.refund_amount or 0), payload.refund_method,
    )
    return ret_txn


def reject_return(
    db:        Session,
    rejector:  Employee,
    return_id: int,
    payload:   ReturnRejectRequest,
) -> ReturnTransaction:
    """
    Supervisor/manager rejects a pending return.
    No stock or accounting changes — purely a status update.
    Rejection is permanent.
    """
    if rejector.role == Role.CASHIER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cashiers cannot reject return requests.",
        )

    ret_txn = db.query(ReturnTransaction).filter(
        ReturnTransaction.id == return_id,
    ).first()

    if not ret_txn:
        raise HTTPException(status_code=404, detail="Return not found.")

    _assert_store_access(rejector, ret_txn.store_id)

    if ret_txn.status != ReturnStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Return is already '{ret_txn.status}' — cannot reject.",
        )

    now = datetime.now(timezone.utc)
    ret_txn.status          = ReturnStatus.REJECTED
    ret_txn.rejected_by     = rejector.id
    ret_txn.rejected_at     = now
    ret_txn.rejection_notes = payload.rejection_notes

    _write_audit(
        db        = db,
        store_id  = ret_txn.store_id,
        actor     = rejector,
        action    = "return_rejected",
        entity_id = ret_txn.return_number,
        before    = {"status": ReturnStatus.PENDING},
        after     = {
            "status":           ReturnStatus.REJECTED,
            "rejected_by":      rejector.id,
            "rejection_notes":  payload.rejection_notes,
        },
    )

    db.commit()
    db.refresh(ret_txn)
    logger.info(
        "Return %s REJECTED by employee %d — reason: %s",
        ret_txn.return_number, rejector.id, payload.rejection_notes[:80],
    )
    return ret_txn


def get_return(
    db:        Session,
    employee:  Employee,
    return_id: int,
) -> ReturnTransaction:
    """Fetch a single return by ID.  Enforces store access."""
    ret_txn = db.query(ReturnTransaction).filter(
        ReturnTransaction.id == return_id,
    ).first()

    if not ret_txn:
        raise HTTPException(status_code=404, detail="Return not found.")

    _assert_store_access(employee, ret_txn.store_id)
    return ret_txn


def list_returns(
    db:               Session,
    employee:         Employee,
    status_filter:    Optional[str]  = None,
    original_txn_id:  Optional[int]  = None,
    limit:            int             = 50,
    offset:           int             = 0,
) -> list[ReturnTransaction]:
    """List returns for the employee's store with optional filters."""
    q = db.query(ReturnTransaction)

    # Tenant scope
    if employee.role != Role.PLATFORM_OWNER:
        q = q.filter(ReturnTransaction.store_id == employee.store_id)

    if status_filter:
        try:
            status_enum = ReturnStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid return status '{status_filter}'. "
                       f"Valid values: {[s.value for s in ReturnStatus]}",
            )
        q = q.filter(ReturnTransaction.status == status_enum)

    if original_txn_id:
        q = q.filter(ReturnTransaction.original_txn_id == original_txn_id)

    try:
        return (
            q.order_by(ReturnTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
    except SQLAlchemyError as exc:
        logger.exception(
            "Failed to list returns for store_id=%s employee_id=%s",
            employee.store_id,
            employee.id,
        )
        raise HTTPException(
            status_code=503,
            detail="Returns data is unavailable. Run database migrations and retry.",
        ) from exc
