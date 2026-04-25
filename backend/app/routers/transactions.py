"""
Transactions router (v4.1 - Phase P1-B: Reporting Truth & Timezone Safety)

Changes:
  - create_transaction and void_transaction wrapped in explicit try/except
    that rolls back on any failure — no partial writes
  - Idempotency-Key header checked on create: if the same key has already
    been processed, return the existing transaction (safe retries)
  - Logging added at key decision points
  - PHASE P1-B: today_summary now uses merchant_today() to ensure sales for
    current business day in merchant's timezone (Africa/Nairobi), not UTC

PHASE P1-B: Reporting Truth & Timezone Safety
──────────────────────────────────────────────
today_summary() endpoint now reflects:
  - COMPLETED transactions for the current business day in merchant's timezone
  - Prevents midnight-edge transactions from appearing in wrong day
  - M-PESA delayed completions attributed to correct business day
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, case
from typing import List, Optional
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
import uuid

from app.core.deps import get_db, require_cashier, require_manager, get_current_employee, require_role
from app.core.money import (
    calculate_vat_exclusive,
    quantize_money,
    split_inclusive_price,
    to_decimal_money,
)
from app.models.employee import Role
from app.core.datetime_utils import merchant_today, ensure_utc_datetime, utc_to_merchant_date
from app.models.transaction import Transaction, TransactionItem, TransactionStatus, PaymentMethod, SyncStatus
from app.models.product import Product, StockMovement
from app.models.employee import Employee
from app.models.customer import Customer
from app.models.cash_session import CashSession
from app.models.audit import AuditTrail
from app.schemas.transaction import TransactionCreate, TransactionOut, TransactionSummary
from app.core.config import settings
from app.core.stock_movements import StockMovementType
from app.services.reconciliation import assert_period_open
from app.services.accounting import (
    post_transaction as _accounting_post_transaction,
    post_transaction_void as _accounting_post_transaction_void,
)

logger = logging.getLogger("dukapos.transactions")
router = APIRouter(prefix="/transactions", tags=["Transactions"])


def generate_txn_number() -> str:
    return f"TXN-{uuid.uuid4().hex[:8].upper()}"


def _allocate_order_discount(items_data, subtotal_before_discount: Decimal, order_discount: Decimal):
    """Allocate header discount proportionally and force remainder on last line."""
    allocations = []
    running = Decimal("0.00")
    for idx, (_, _, raw_line_total) in enumerate(items_data):
        if order_discount <= Decimal("0.00") or subtotal_before_discount <= Decimal("0.00"):
            share = Decimal("0.00")
        elif idx == len(items_data) - 1:
            share = quantize_money(order_discount - running)
        else:
            share = quantize_money(raw_line_total / subtotal_before_discount * order_discount)
            remaining = quantize_money(order_discount - running)
            if share > remaining:
                share = remaining
        allocations.append(share)
        running += share
    return allocations


def _write_audit(db, actor_id: int, actor_name: str, action: str, txn_number: str,
                 store_id: int = None, before=None, after=None, notes: str = None):
    db.add(AuditTrail(
        store_id   = store_id,
        actor_id   = actor_id,
        actor_name = actor_name,
        action     = action,
        entity     = "transaction",
        entity_id  = txn_number,
        before_val = before,
        after_val  = after,
        notes      = notes,
    ))


def _tax_rate_for_product(product: Product) -> Decimal:
    """
    Determine the applicable VAT rate for a product.

    VAT LOGIC (Phase P0-C):
    ─────────────────────────────────────────────────────────────
    Kenya's tax treatment is:
      - Standard rate: 16% VAT (KRA category "B")
      - Zero-rated: 0% VAT (KRA category "Z", "A", "E")
      - Exempt: 0% VAT (administrative flag)

    RULES (in order of precedence):
      1. If product.vat_exempt == True:
         → 0% VAT (exempt goods: education, medical, etc.)
      2. Else if product.tax_code in ("Z", "A", "E"):
         → 0% VAT (zero-rated goods: food, exports, etc.)
      3. Else (default to category "B"):
         → 16% VAT (standard rate, most goods)

    Args:
        product: Product model instance

    Returns:
        Decimal: VAT rate as decimal (0.00 or 0.16 for Kenya)

    Note:
        The rate is read from settings.VAT_RATE at posting time.
        To support multiple tax regimes, extend this function:
          - Check product.category_id + store tax ruleset
          - Return rate from lookup table
    """
    if product.vat_exempt:
        return Decimal("0.00")
    code = (product.tax_code or "B").upper()
    if code in ("E", "A", "Z"):
        return Decimal("0.00")
    return Decimal(str(settings.VAT_RATE))




def _enforce_discount_controls(current: Employee, subtotal_before_discount: Decimal, order_discount: Decimal, items_data):
    """Basic fraud/approval guardrails for discounts."""
    subtotal_before_discount = Decimal(str(subtotal_before_discount or 0))
    order_discount = Decimal(str(order_discount or 0))
    if subtotal_before_discount <= Decimal("0.00"):
        return

    order_pct = (order_discount / subtotal_before_discount) if subtotal_before_discount else Decimal("0.00")
    line_pcts = []
    for _, item, raw_line_total in items_data:
        gross_line = Decimal(str(item.unit_price)) * Decimal(str(item.qty))
        line_discount = Decimal(str(item.discount or 0))
        pct = (line_discount / gross_line) if gross_line > Decimal("0.00") else Decimal("0.00")
        line_pcts.append((pct, raw_line_total))

    max_line_pct = max((pct for pct, _ in line_pcts), default=Decimal("0.00"))

    if current.role == Role.CASHIER:
        if order_pct > Decimal("0.10") or max_line_pct > Decimal("0.15"):
            raise HTTPException(403, "Discount exceeds cashier approval limit. Supervisor approval required.")
    elif current.role == Role.SUPERVISOR:
        if order_pct > Decimal("0.20") or max_line_pct > Decimal("0.25"):
            raise HTTPException(403, "Discount exceeds supervisor approval limit. Manager approval required.")


def _enforce_credit_sale_controls(current: Employee):
    if current.role == Role.CASHIER:
        raise HTTPException(403, "Cashiers cannot post credit sales without supervisor approval.")

def _line_net_and_vat(
    line_money: Decimal,
    product: Product,
    *,
    prices_include_vat: bool,
) -> tuple[Decimal, Decimal]:
    """
    Derive stored line net (ex-VAT) and VAT from one post-discount line amount.

    ``line_money`` is always the line total after line + allocated order discounts,
    in the same semantic as ``unit_price`` on the request: gross if
    ``prices_include_vat`` else exclusive net. VAT is never stacked twice.
    """
    line_money = quantize_money(line_money)
    rate = _tax_rate_for_product(product)
    if prices_include_vat:
        net, vat = split_inclusive_price(line_money, rate)
        return net, vat
    net = line_money
    vat = calculate_vat_exclusive(net, rate)
    return net, vat


@router.post("", response_model=TransactionOut)
def create_transaction(
    payload:          TransactionCreate,
    db:               Session  = Depends(get_db),
    current:          Employee = Depends(require_role(Role.CASHIER)),
    idempotency_key:  Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Create a completed transaction.

    Idempotency: pass Idempotency-Key header (e.g. the offline txn_number).
    If a transaction with this key was already processed, returns the existing
    record instead of creating a duplicate. Safe for retries.
    """

    # ── Idempotency check ──────────────────────────────────────────────────────
    if idempotency_key:
        existing = (
            db.query(Transaction)
            .filter(
                Transaction.txn_number == idempotency_key,
                Transaction.store_id == current.store_id,
            )
            .first()
        )
        if existing:
            logger.info("Idempotent request — returning existing txn", extra={
                "idempotency_key": idempotency_key, "txn_id": existing.id,
            })
            return existing

    try:
        # ── 1. Validate items and verify stock ─────────────────────────────────
        items_data = []
        subtotal   = Decimal("0.00")
        subtotal_before_discount = Decimal("0.00")

        for item in payload.items:
            product = db.query(Product).filter(
                Product.id == item.product_id,
                Product.store_id == current.store_id,
            ).with_for_update().first()
            if not product:
                raise HTTPException(404, f"Product ID {item.product_id} not found")
            if product.stock_quantity < item.qty:
                raise HTTPException(
                    400,
                    f"Insufficient stock for '{product.name}': "
                    f"requested {item.qty}, available {product.stock_quantity}",
                )
            raw_line_total = (
                to_decimal_money(item.unit_price) * item.qty
                - to_decimal_money(item.discount)
            )
            if raw_line_total < Decimal("0.00"):
                raise HTTPException(400, f"Negative line total for product '{product.name}'")
            subtotal_before_discount += raw_line_total
            items_data.append((product, item, raw_line_total))

        if payload.discount_amount is None:
            payload.discount_amount = Decimal("0.00")
        if payload.discount_amount < Decimal("0.00"):
            raise HTTPException(400, "Discount amount cannot be negative")
        if payload.discount_amount > subtotal_before_discount:
            raise HTTPException(
                400,
                f"Discount amount ({payload.discount_amount}) cannot exceed subtotal ({subtotal_before_discount})",
            )

        _enforce_discount_controls(current, subtotal_before_discount, payload.discount_amount, items_data)

        # ── 2. Calculate totals (PHASE P0-C: Per-Line VAT) ────────────────────
        # VAT is calculated per line item, not as a flat subtotal * rate.
        # This respects product tax status and creates mixed-basket integrity.
        item_snapshots = []
        discount_allocations = _allocate_order_discount(items_data, subtotal_before_discount, payload.discount_amount)
        prices_include_vat = bool(getattr(payload, "prices_include_vat", False))
        for (product, item, raw_line_total), order_discount_share in zip(items_data, discount_allocations):
            line_after_header_disc = quantize_money(raw_line_total - order_discount_share)
            line_total, line_vat = _line_net_and_vat(
                line_after_header_disc,
                product,
                prices_include_vat=prices_include_vat,
            )
            item_snapshots.append((product, item, line_total, line_vat))

        subtotal = quantize_money(sum(t[2] for t in item_snapshots))
        vat_amount = quantize_money(sum(t[3] for t in item_snapshots))
        total = quantize_money(subtotal + vat_amount)
        change_given = None

        # ── P1-D: Reject unsupported SPLIT payment method ─────────────────────
        if payload.payment_method == PaymentMethod.SPLIT:
            raise HTTPException(
                400,
                "SPLIT payment method is not currently supported. "
                "Please use CASH, MPESA, CARD, or CREDIT.",
            )

        if payload.payment_method == PaymentMethod.CASH:
            if payload.cash_tendered is None or payload.cash_tendered < total:
                raise HTTPException(
                    400,
                    f"Cash tendered ({payload.cash_tendered}) is less than total ({total:.2f})",
                )
            if not payload.cash_session_id:
                raise HTTPException(400, "Cash sales require an open cash session")
            change_given = quantize_money(to_decimal_money(payload.cash_tendered) - total)

        customer = None
        next_balance = None
        next_wallet_balance = None
        if payload.payment_method in (PaymentMethod.CREDIT, PaymentMethod.STORE_CREDIT):
            if not payload.customer_id:
                raise HTTPException(400, f"{payload.payment_method.value} sales require customer_id")
            customer = db.query(Customer).filter(Customer.id == payload.customer_id, Customer.store_id == current.store_id).with_for_update().first()
            if not customer:
                raise HTTPException(404, "Customer not found")
        if payload.payment_method == PaymentMethod.CREDIT:
            _enforce_credit_sale_controls(current)
            next_balance = Decimal(str(customer.credit_balance or 0)) + total
            if Decimal(str(customer.credit_limit or 0)) > Decimal("0.00") and next_balance > Decimal(str(customer.credit_limit)):
                raise HTTPException(400, "Credit sale exceeds customer credit limit")
        if payload.payment_method == PaymentMethod.STORE_CREDIT:
            wallet_balance = Decimal(str(customer.store_credit_balance or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if wallet_balance < total:
                raise HTTPException(400, f"Insufficient store credit balance ({wallet_balance}) for total ({total})")
            next_wallet_balance = (wallet_balance - total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if payload.payment_method == PaymentMethod.CASH and getattr(payload, "cash_session_id", None):
            cash_session = db.query(CashSession).filter(CashSession.id == payload.cash_session_id, CashSession.store_id == current.store_id, CashSession.status == "open").first()
            if not cash_session:
                raise HTTPException(400, "Selected cash session is not open")

        # ── 3. Create transaction ──────────────────────────────────────────────
        txn_number = idempotency_key or generate_txn_number()
        txn = Transaction(
            txn_number      = txn_number,
            store_id        = current.store_id,
            terminal_id     = payload.terminal_id,
            subtotal        = subtotal,
            discount_amount = quantize_money(payload.discount_amount),
            vat_amount      = vat_amount,
            total           = total,
            payment_method  = payload.payment_method,
            cash_tendered   = payload.cash_tendered,
            change_given    = change_given,
            status          = TransactionStatus.PENDING,
            sync_status     = SyncStatus.PENDING,
            cashier_id      = current.id,
            customer_id     = payload.customer_id,
            cash_session_id = getattr(payload, "cash_session_id", None),
        )
        db.add(txn)
        db.flush()

        # ── 4. Line items + stock ledger ───────────────────────────────────────
        # Each TransactionItem snapshots:
        #   - line_total: subtotal after discount
        #   - vat_amount: per-line VAT based on product tax status
        #   - tax_code, vat_exempt: tax classification at time of sale
        # This enables:
        #   - Receipt display: breakdown per item
        #   - Accounting: correct journal posting per tax class
        #   - Compliance: vat_amount visible for KRA eTIMS
        #   - Audit: original tax status preserved
        txn_items = []
        for product, item, line_total, line_vat in item_snapshots:
            txn_item = TransactionItem(
                transaction_id  = txn.id,
                product_id      = product.id,
                product_name    = product.name,
                sku             = product.sku,
                qty             = item.qty,
                unit_price      = item.unit_price,
                cost_price_snap = product.cost_price,
                discount        = item.discount,
                vat_amount      = line_vat,              # Per-line VAT
                line_total      = line_total,           # Subtotal after discount (before VAT)
                tax_code        = product.tax_code,     # Snapshot: tax classification
                vat_exempt      = product.vat_exempt,   # Snapshot: exempt flag
            )
            db.add(txn_item)
            txn_items.append(txn_item)
            qty_before = product.stock_quantity
            product.stock_quantity -= item.qty
            db.add(StockMovement(
                product_id    = product.id,
                store_id      = current.store_id,
                movement_type = StockMovementType.SALE.value,
                qty_delta     = -item.qty,
                qty_before    = qty_before,
                qty_after     = product.stock_quantity,
                ref_id        = txn.txn_number,
                performed_by  = current.id,
            ))

        # ── 5. Final status ────────────────────────────────────────────────────
        if payload.payment_method == PaymentMethod.MPESA:
            txn.status = TransactionStatus.PENDING
        else:
            txn.status       = TransactionStatus.COMPLETED
            txn.completed_at = datetime.now(timezone.utc)


        if payload.payment_method == PaymentMethod.CREDIT and customer is not None and next_balance is not None:
            customer.credit_balance = next_balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if payload.payment_method == PaymentMethod.STORE_CREDIT and customer is not None and next_wallet_balance is not None:
            customer.store_credit_balance = next_wallet_balance
        if payload.payment_method == PaymentMethod.CASH and getattr(txn, "cash_session_id", None):
            cash_session = db.query(CashSession).filter(CashSession.id == txn.cash_session_id).with_for_update().first()
            if cash_session:
                cash_session.expected_cash = (Decimal(str(cash_session.expected_cash or 0)) + txn.total - Decimal(str(txn.change_given or 0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        discount_pct = Decimal("0.00")
        if subtotal_before_discount > Decimal("0.00"):
            discount_pct = (payload.discount_amount / subtotal_before_discount * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        _write_audit(
            db, current.id, current.full_name, "create", txn.txn_number,
            store_id=current.store_id,
            after={
                "total": str(txn.total),
                "payment_method": txn.payment_method.value,
                "discount_amount": str(payload.discount_amount),
                "discount_pct": str(discount_pct),
                "customer_id": txn.customer_id,
                "cash_session_id": txn.cash_session_id,
            },
            notes=(
                "high_risk_sale" if txn.payment_method in (PaymentMethod.CREDIT, PaymentMethod.STORE_CREDIT) or payload.discount_amount > Decimal("0.00") else None
            ),
        )
        # ── Auto-post to accounting ledger (atomic with sale commit) ─────────
        _accounting_post_transaction(db, txn, txn_items)
        db.commit()
        db.refresh(txn)

        logger.info("Transaction created", extra={
            "txn_number": txn.txn_number,
            "total":      str(txn.total),
            "method":     txn.payment_method.value,
            "cashier_id": current.id,
        })
        return txn

    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        msg = str(exc)
        if "Run seed_chart_of_accounts() first." in msg:
            logger.warning(
                "Transaction blocked due to incomplete accounting setup",
                extra={"store_id": current.store_id, "reason": msg},
            )
            raise HTTPException(
                503,
                "Accounting setup incomplete for this store. "
                "Run POST /api/v1/accounting/seed and retry.",
            ) from exc
        logger.error("Transaction creation failed — rolled back", exc_info=True)
        raise HTTPException(500, "Transaction failed. No charge was made.") from exc
    except Exception as exc:
        db.rollback()
        logger.error("Transaction creation failed — rolled back", exc_info=True)
        raise HTTPException(500, "Transaction failed. No charge was made.") from exc


@router.get("", response_model=List[TransactionSummary])
def list_transactions(
    date_from:      Optional[date]              = Query(None),
    date_to:        Optional[date]              = Query(None),
    cashier_id:     Optional[int]               = None,
    payment_method: Optional[PaymentMethod]     = None,
    status:         Optional[TransactionStatus] = None,
    sync_status:    Optional[SyncStatus]        = None,
    search:         Optional[str]               = Query(None, description="Filter by txn_number prefix"),
    skip:  int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    q = db.query(Transaction).filter(
        Transaction.store_id == current.store_id
    )
    # Use completed_at as the canonical business date; fall back to created_at for pending txns
    _date_col = func.coalesce(Transaction.completed_at, Transaction.created_at)
    if date_from:       q = q.filter(cast(_date_col, Date) >= date_from)
    if date_to:         q = q.filter(cast(_date_col, Date) <= date_to)
    if cashier_id:      q = q.filter(Transaction.cashier_id     == cashier_id)
    if payment_method:  q = q.filter(Transaction.payment_method == payment_method)
    if status:          q = q.filter(Transaction.status         == status)
    if sync_status:     q = q.filter(Transaction.sync_status    == sync_status)
    if search:          q = q.filter(Transaction.txn_number.ilike(f"%{search}%"))
    return q.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/summary/today")
def today_summary(db: Session = Depends(get_db), current: Employee = Depends(require_cashier)):
    """
    Summary of COMPLETED transactions for today.
    
    PHASE P1-B: Uses merchant_today() to ensure the date reflects the merchant's
    timezone (Africa/Nairobi), not UTC. Prevents midnight-edge transactions from
    appearing in wrong day's report.
    """
    today = merchant_today()

    # Fetch today's completed transactions with date buffer
    buffer_start = today - timedelta(days=1)
    buffer_end = today + timedelta(days=1)

    txns = (
        db.query(Transaction)
        .filter(Transaction.store_id == current.store_id)
        .filter(Transaction.status == TransactionStatus.COMPLETED)
        .filter(
            (Transaction.completed_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
        )
        .filter(
            (Transaction.completed_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
        )
        .all()
    )

    # Filter to today in merchant timezone
    def get_merchant_date(txn: Transaction) -> date:
        ts = ensure_utc_datetime(txn.completed_at or txn.created_at)
        return utc_to_merchant_date(ts)

    today_txns = [t for t in txns if get_merchant_date(t) == today]

    total_sales = sum(Decimal(str(t.total or 0)) for t in today_txns)
    total_vat   = sum(Decimal(str(t.vat_amount or 0)) for t in today_txns)
    unsynced_count = sum(1 for t in today_txns if t.sync_status != SyncStatus.SYNCED)

    # Group by payment method
    by_method: dict[str, Decimal] = {}
    for txn in today_txns:
        method_key = txn.payment_method.value
        if method_key not in by_method:
            by_method[method_key] = Decimal("0.00")
        by_method[method_key] += Decimal(str(txn.total or 0))

    return {
        "date":               str(today),
        "transaction_count":  len(today_txns),
        "total_sales":        float(total_sales.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total_vat":          float(total_vat.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "net_sales":          float((total_sales - total_vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "by_payment_method":  {k: float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) for k, v in by_method.items()},
        "unsynced_count":     unsynced_count,
        "currency":           settings.CURRENCY,
    }


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(txn_id: int, db: Session = Depends(get_db), current: Employee = Depends(require_cashier)):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.store_id != current.store_id:
        raise HTTPException(403, "Access denied")
    return txn


@router.post("/{txn_id}/void", dependencies=[Depends(require_manager)])
def void_transaction(
    txn_id: int,
    db:     Session  = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.store_id != current.store_id:
        raise HTTPException(403, "Cannot void a transaction from another store")
    if txn.status == TransactionStatus.VOIDED:
        raise HTTPException(400, "Transaction already voided")

    try:
        for item in txn.items:
            product = db.query(Product).filter(Product.id == item.product_id).with_for_update().first()
            if product:
                qty_before             = product.stock_quantity
                product.stock_quantity += item.qty
                db.add(StockMovement(
                    product_id    = product.id,
                    store_id      = txn.store_id,
                    movement_type = StockMovementType.VOID_RESTORE.value,
                    qty_delta     = item.qty,
                    qty_before    = qty_before,
                    qty_after     = product.stock_quantity,
                    ref_id        = txn.txn_number,
                    performed_by  = current.id,
                ))

        txn.status = TransactionStatus.VOIDED

        if txn.payment_method == PaymentMethod.CREDIT and txn.customer_id:
            customer = db.query(Customer).filter(
                Customer.id == txn.customer_id,
                Customer.store_id == txn.store_id,
            ).with_for_update().first()
            if customer:
                current_balance = Decimal(str(customer.credit_balance or 0))
                customer.credit_balance = max(Decimal("0.00"), current_balance - Decimal(str(txn.total or 0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if txn.payment_method == PaymentMethod.STORE_CREDIT and txn.customer_id:
            sc_customer = db.query(Customer).filter(
                Customer.id       == txn.customer_id,
                Customer.store_id == txn.store_id,
            ).with_for_update().first()
            if sc_customer:
                sc_customer.store_credit_balance = (
                    Decimal(str(sc_customer.store_credit_balance or 0)) + Decimal(str(txn.total or 0))
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if txn.payment_method == PaymentMethod.CASH and getattr(txn, "cash_session_id", None):
            cash_session = db.query(CashSession).filter(CashSession.id == txn.cash_session_id).with_for_update().first()
            if cash_session:
                net_cash = (Decimal(str(txn.total or 0)) - Decimal(str(txn.change_given or 0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                cash_session.expected_cash = (Decimal(str(cash_session.expected_cash or 0)) - net_cash).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        _write_audit(
            db, current.id, current.full_name, "void", txn.txn_number,
            store_id=txn.store_id,
            before={"status": "completed"},
            after={"status": "voided"},
        )

        void_entry = _accounting_post_transaction_void(db=db, txn=txn, voided_by=current.id)
        if void_entry is None:
            logger.warning(
                "Transaction %s voided without an accounting reversal entry."
                " Ensure a prior journal entry exists.",
                txn.txn_number,
            )

        db.commit()
        logger.info("Transaction voided", extra={"txn_number": txn.txn_number, "by": current.id})
        return {"message": f"Transaction {txn.txn_number} voided. Stock restored."}

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("Void failed — rolled back", extra={"txn_id": txn_id}, exc_info=True)
        raise HTTPException(500, "Void failed. No changes were made.") from exc


@router.post("/{txn_id}/mpesa-confirm", dependencies=[Depends(require_manager)])
def mpesa_confirm(
    txn_id:    int,
    mpesa_ref: str = Query(...),
    db:        Session  = Depends(get_db),
    current:   Employee = Depends(get_current_employee),
):
    """
    Manager-only manual M-PESA confirmation for exception handling.

    Use only when the Daraja callback has not arrived and the cashier
    has confirmed the M-PESA receipt verbally with the customer.
    Every use is recorded in the audit trail.
    """
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.store_id != current.store_id:
        raise HTTPException(403, "Transaction belongs to a different store")
    if txn.status == TransactionStatus.COMPLETED:
        raise HTTPException(400, "Transaction already completed")
    if txn.status == TransactionStatus.VOIDED:
        raise HTTPException(400, "Cannot confirm a voided transaction")

    try:
        txn.mpesa_ref    = mpesa_ref
        txn.status       = TransactionStatus.COMPLETED
        txn.completed_at = datetime.now(timezone.utc)

        db.add(AuditTrail(
            store_id   = txn.store_id,
            actor_id   = current.id,
            actor_name = current.full_name,
            action     = "manual_mpesa_confirm",
            entity     = "transaction",
            entity_id  = txn.txn_number,
            before_val = {"status": "pending"},
            after_val  = {"status": "completed", "mpesa_ref": mpesa_ref,
                          "confirmed_by": current.full_name, "method": "manual"},
            notes      = "Manual M-PESA confirmation by manager",
        ))

        _accounting_post_transaction(db, txn, txn.items)
        db.commit()

    except Exception as exc:
        db.rollback()
        logger.error(
            "Manual M-PESA confirmation failed for txn %s: %s",
            txn.txn_number, exc,
            exc_info=True,
        )
        raise HTTPException(500, "Manual M-PESA confirmation failed. No changes were made.") from exc

    logger.warning(
        "Manual M-PESA confirmation by employee %s for txn %s",
        current.id, txn.txn_number,
    )
    return {"message": "Payment confirmed", "txn_number": txn.txn_number}


@router.post("/sync/mark-synced", dependencies=[Depends(require_cashier)])
def mark_synced(txn_numbers: List[str], db: Session = Depends(get_db)):
    """Deprecated: sync agent now uses confirmed_txn_numbers + local DB ACK."""
    raise HTTPException(410, "Deprecated endpoint. Use /sync/transactions confirmed_txn_numbers ACK flow.")
