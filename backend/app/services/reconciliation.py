"""
Reconciliation service — inventory truth and accounting integrity.

Responsibilities:
  1. detect_oversells()          — finds negative stock after sync, creates OversellEvents
  2. assert_period_open()        — raises if trying to post into a closed period
  3. get_inventory_ledger_diff() — compares physical stock value to account 1200 balance
  4. run_full_reconciliation()   — runs all checks for a store (called by background job)

This service is called:
  - After every sync batch (detect_oversells)
  - Before every journal post (assert_period_open)
  - By the /reconciliation/run API endpoint (run_full_reconciliation)
  - By the scheduled background job every 5 minutes
"""

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session
from app.models.accounting import JournalEntry
from sqlalchemy import func, text

from app.models.inventory import OversellEvent, OversellResolution, AccountingPeriod, PeriodStatus
from app.models.product import Product
from app.models.transaction import Transaction, TransactionItem, TransactionStatus
from app.models.accounting import Account, JournalLine, JournalEntry

logger = logging.getLogger("dukapos.reconciliation")

TWO_PLACES = Decimal("0.01")


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# ── Period guard ──────────────────────────────────────────────────────────────

def assert_period_open(db: Session, store_id: int, entry_date: date) -> None:
    """
    Raise ValueError if a journal entry cannot be posted for entry_date
    because the period is CLOSED or LOCKED.

    Called by AccountingService before posting ANY journal entry.
    This is the gatekeeper for period immutability.

    Rules:
      - OPEN periods:   always writable
      - CLOSED periods: read-only. Post corrections in the current open period instead.
      - LOCKED periods: permanently read-only (used for audited financial statements)
      - No period row for date: assume OPEN (before period close feature was active)
    """
    period = (
        db.query(AccountingPeriod)
        .filter(
            AccountingPeriod.store_id   == store_id,
            AccountingPeriod.start_date <= entry_date,
            AccountingPeriod.end_date   >= entry_date,
        )
        .first()
    )

    if period is None:
        return  # No period defined → implicitly open

    if period.status == PeriodStatus.OPEN:
        return  # Fine

    if period.status == PeriodStatus.CLOSED:
        raise ValueError(
            f"Cannot post to {entry_date}: period '{period.period_name}' is CLOSED. "
            f"Post your correction in the current open period with a memo referencing "
            f"the original transaction."
        )

    if period.status == PeriodStatus.LOCKED:
        raise ValueError(
            f"Cannot post to {entry_date}: period '{period.period_name}' is LOCKED. "
            f"Locked periods are permanently immutable and cannot accept any entries."
        )


def get_current_open_period(db: Session, store_id: int) -> Optional[AccountingPeriod]:
    """Return the current OPEN period for a store, or None if none exists."""
    today = date.today()
    return (
        db.query(AccountingPeriod)
        .filter(
            AccountingPeriod.store_id   == store_id,
            AccountingPeriod.status     == PeriodStatus.OPEN,
            AccountingPeriod.start_date <= today,
            AccountingPeriod.end_date   >= today,
        )
        .first()
    )


# ── Oversell detection ────────────────────────────────────────────────────────

def detect_oversells(
    db: Session,
    store_id: int,
    terminal_id: Optional[str] = None,
) -> list[OversellEvent]:
    """
    Scan for products with negative stock_quantity and create OversellEvent records.

    Called after every sync batch commit. Each negative-stock product gets one
    pending OversellEvent (unless one already exists for that product).

    For each oversell:
      1. Identify which transactions drove the product negative
      2. Record contributing terminal_ids
      3. Calculate shortfall quantity
      4. Create OversellEvent with resolution=PENDING

    Returns the list of new OversellEvent rows created.
    """
    # Find all products with negative stock in this store
    negative_products = (
        db.query(Product)
        .filter(
            Product.store_id       == store_id,
            Product.stock_quantity < 0,
            Product.is_active      == True,
        )
        .all()
    )

    if not negative_products:
        return []

    new_events = []

    for product in negative_products:
        # Skip if already has a pending oversell event for this product
        existing_pending = (
            db.query(OversellEvent)
            .filter(
                OversellEvent.product_id == product.id,
                OversellEvent.store_id   == store_id,
                OversellEvent.resolution == OversellResolution.PENDING,
            )
            .first()
        )
        if existing_pending:
            logger.debug("Oversell already tracked for product %d — skipping", product.id)
            continue

        # Find recent transactions that sold this product (contributors to the oversell)
        # Look at transactions since stock was last reconciled / last 7 days
        from datetime import timedelta
        lookback = datetime.now(timezone.utc) - timedelta(days=7)

        contributors = (
            db.query(Transaction.terminal_id, Transaction.txn_number, TransactionItem.qty)
            .join(TransactionItem, TransactionItem.transaction_id == Transaction.id)
            .filter(
                Transaction.store_id       == store_id,
                Transaction.status         == TransactionStatus.COMPLETED,
                Transaction.created_at     >= lookback,
                TransactionItem.product_id == product.id,
            )
            .all()
        )

        contributing_terminals = list({c.terminal_id for c in contributors if c.terminal_id})
        candidate_txns         = [c.txn_number for c in contributors]
        total_sold_in_window   = sum(c.qty for c in contributors)

        # stock_before_sync: what stock would have been if all sales are counted
        # = current stock + total_sold = the pre-sell quantity
        stock_before = product.stock_quantity + total_sold_in_window
        shortfall    = abs(product.stock_quantity)

        event = OversellEvent(
            store_id                = store_id,
            product_id              = product.id,
            stock_before_sync       = stock_before,
            total_sold_offline      = total_sold_in_window,
            shortfall_qty           = shortfall,
            contributing_terminals  = json.dumps(contributing_terminals),
            candidate_txn_numbers   = json.dumps(candidate_txns[:20]),  # cap at 20
            resolution              = OversellResolution.PENDING,
        )
        db.add(event)
        new_events.append(event)

        logger.warning(
            "OVERSELL DETECTED: product_id=%d store_id=%d shortfall=%d "
            "terminals=%s candidate_txns=%d",
            product.id, store_id, shortfall,
            contributing_terminals, len(candidate_txns),
        )

    if new_events:
        db.flush()
        logger.warning(
            "Reconciliation: %d new oversell events for store %d",
            len(new_events), store_id,
        )

    return new_events


# ── Inventory-to-ledger reconciliation ───────────────────────────────────────

def get_inventory_ledger_diff(
    db: Session,
    store_id: int,
    as_of_date: Optional[date] = None,
) -> dict:
    """
    Compare physical inventory value (stock_quantity * wac) against
    the balance of account 1200 (Inventory / Stock) in the ledger.

    A non-zero difference indicates:
      - Unposted stock movements (sync lag)
      - Accounting errors
      - Manual stock adjustments without journal entries
      - WAC drift from retroactive cost changes

    Returns:
      {
        "physical_inventory_value": Decimal,   # SUM(stock_quantity * wac)
        "ledger_inventory_balance": Decimal,   # Account 1200 net balance
        "variance": Decimal,                   # difference (should be near 0)
        "variance_pct": float,                 # % of physical value
        "products_without_wac": int,           # products with wac=NULL (data quality)
        "as_of_date": str,
      }
    """
    as_of = as_of_date or date.today()

    # Physical inventory value
    physical = (
        db.query(
            func.coalesce(
                func.sum(Product.stock_quantity * func.coalesce(Product.wac, Product.cost_price, 0)),
                Decimal("0")
            ).label("value"),
            func.count().filter(Product.wac == None).label("no_wac_count"),
        )
        .filter(
            Product.store_id   == store_id,
            Product.is_active  == True,
            Product.stock_quantity > 0,
        )
        .first()
    )

    physical_value = _q(physical.value or Decimal("0"))
    no_wac_count   = physical.no_wac_count or 0

    # Ledger balance for account 1200 (Inventory / Stock)
    inv_account = (
        db.query(Account)
        .filter(Account.store_id == store_id, Account.code == "1200")
        .first()
    )

    ledger_balance = Decimal("0.00")
    if inv_account:
        row = (
            db.query(
                func.coalesce(func.sum(JournalLine.debit),  Decimal("0")).label("dr"),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0")).label("cr"),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(
                JournalLine.account_id  == inv_account.id,
                JournalEntry.is_void    == False,
                JournalEntry.entry_date <= as_of,
            )
            .first()
        )
        if row:
            # Account 1200 is a DEBIT-normal account: balance = DR - CR
            ledger_balance = _q(row.dr - row.cr)

    variance = _q(physical_value - ledger_balance)
    variance_pct = (
        float(abs(variance) / physical_value * 100)
        if physical_value > Decimal("0") else 0.0
    )

    return {
        "physical_inventory_value": float(physical_value),
        "ledger_inventory_balance": float(ledger_balance),
        "variance":                 float(variance),
        "variance_pct":             round(variance_pct, 2),
        "products_without_wac":     no_wac_count,
        "as_of_date":               str(as_of),
        "status":                   "ok" if abs(variance) < Decimal("1.00") else "needs_investigation",
    }


# ── Full reconciliation run ───────────────────────────────────────────────────

def run_full_reconciliation(db: Session, store_id: int) -> dict:
    """
    Run all reconciliation checks for a store and return a summary report.

    Called by:
      - POST /api/v1/reconciliation/run   (manual trigger by ops)
      - Background scheduler (every 5 minutes)

    Returns a summary dict suitable for the reconciliation dashboard.
    """
    oversell_events = detect_oversells(db, store_id)
    ledger_diff     = get_inventory_ledger_diff(db, store_id)

    # Pending oversell count (including previously unresolved ones)
    pending_oversells = (
        db.query(func.count(OversellEvent.id))
        .filter(
            OversellEvent.store_id   == store_id,
            OversellEvent.resolution == OversellResolution.PENDING,
        )
        .scalar()
    ) or 0

    # Products with negative stock (even without an oversell event yet)
    negative_stock_count = (
        db.query(func.count(Product.id))
        .filter(Product.store_id == store_id, Product.stock_quantity < 0)
        .scalar()
    ) or 0

    db.commit()

    result = {
        "store_id":            store_id,
        "run_at":              datetime.now(timezone.utc).isoformat(),
        "new_oversell_events": len(oversell_events),
        "pending_oversells":   pending_oversells,
        "negative_stock_products": negative_stock_count,
        "inventory_ledger":    ledger_diff,
        "health": {
            "oversell_ok":  pending_oversells == 0,
            "inventory_ok": ledger_diff["status"] == "ok",
            "stock_ok":     negative_stock_count == 0,
        },
    }

    if pending_oversells > 0 or negative_stock_count > 0:
        logger.warning(
            "Reconciliation WARNINGS for store %d: oversells=%d negative_stock=%d",
            store_id, pending_oversells, negative_stock_count,
        )

    return result



def check_finance_control_integrity(db: Session, store_id: int) -> dict:
    from app.models.expenses import ExpenseVoucher
    from app.models.procurement import SupplierPayment
    from app.models.customer import CustomerPayment
    from app.models.cash_session import CashSession
    missing = {
        "expense_vouchers_missing_journals": 0,
        "supplier_payments_missing_journals": 0,
        "customer_payments_missing_journals": 0,
        "cash_session_variance_missing_journals": 0,
    }
    missing["expense_vouchers_missing_journals"] = sum(1 for v in db.query(ExpenseVoucher).filter(ExpenseVoucher.store_id == store_id, ExpenseVoucher.is_void == False).all() if not db.query(JournalEntry).filter(JournalEntry.store_id == store_id, JournalEntry.ref_type == 'expense_voucher', JournalEntry.ref_id == v.voucher_number).first())
    missing["supplier_payments_missing_journals"] = sum(1 for v in db.query(SupplierPayment).filter(SupplierPayment.store_id == store_id, SupplierPayment.is_void == False).all() if not db.query(JournalEntry).filter(JournalEntry.store_id == store_id, JournalEntry.ref_type == 'supplier_payment', JournalEntry.ref_id == v.payment_number).first())
    missing["customer_payments_missing_journals"] = sum(1 for v in db.query(CustomerPayment).filter(CustomerPayment.store_id == store_id).all() if not db.query(JournalEntry).filter(JournalEntry.store_id == store_id, JournalEntry.ref_type == 'customer_payment', JournalEntry.ref_id == (v.reference or v.payment_number)).first())
    missing["cash_session_variance_missing_journals"] = sum(1 for v in db.query(CashSession).filter(CashSession.store_id == store_id, CashSession.status == 'closed').all() if (v.variance or 0) != 0 and not db.query(JournalEntry).filter(JournalEntry.store_id == store_id, JournalEntry.ref_type == 'cash_session_close', JournalEntry.ref_id == v.session_number).first())
    return missing
