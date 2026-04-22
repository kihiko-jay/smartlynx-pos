"""
Accounting service — double-entry auto-posting engine.

Responsibilities:
  1. seed_chart_of_accounts(store_id)  — called once when a store registers
  2. post_transaction(txn)             — auto-posts a completed sale
  3. post_grn(grn)                     — auto-posts a posted GRN (stock received)
  4. post_transaction_void(txn)        — reverses a sale's journal entry
  5. get_trial_balance(store_id, ...)  — trial balance report
  6. get_pl(store_id, ...)             — Profit & Loss statement
  7. get_balance_sheet(store_id, ...)  — Balance Sheet
  8. get_vat_summary(store_id, ...)    — VAT input / output reconciliation

Journal entry patterns:

  CASH SALE (payment_method = cash):
    DR  Cash in Hand (1000)           total
      CR  Sales Revenue (4000)              subtotal (excl. VAT)
      CR  VAT Payable (2100)                vat_amount

  M-PESA SALE (payment_method = mpesa):
    DR  M-PESA Float (1010)           total
      CR  Sales Revenue (4000)              subtotal (excl. VAT)
      CR  VAT Payable (2100)                vat_amount

  CREDIT SALE (payment_method = credit):
    DR  Accounts Receivable (1100)    total
      CR  Sales Revenue (4000)              subtotal (excl. VAT)
      CR  VAT Payable (2100)                vat_amount

  GRN POSTED (goods received from supplier):
    DR  Inventory / Stock (1200)      total_received_cost
      CR  Accounts Payable (2000)           total_received_cost

  CASH SALE WITH COGS (full 5-leg entry — REQUIRED):
    DR  Cash in Hand (1000)           total
      CR  Sales Revenue (4000)              subtotal (excl. VAT)
      CR  VAT Payable (2100)                vat_amount
    DR  Cost of Goods Sold (5000)     cogs_amount
      CR  Inventory / Stock (1200)          cogs_amount

  SALE VOID (reversal):
    Mirror-image of the original sale entry (DR/CR swapped).
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from sqlalchemy.exc import SQLAlchemyError

from app.models.accounting import (
    Account, JournalEntry, JournalLine,
    AccountType, DEFAULT_ACCOUNTS,
)
from app.models.transaction import Transaction, TransactionItem, PaymentMethod, TransactionStatus
from app.models.procurement import GoodsReceivedNote, GoodsReceivedItem, GRNStatus
from app.models.product import Product, Supplier, StockMovement
from app.models.customer import Customer, CustomerPayment
from app.models.procurement import SupplierPayment
from app.models.expenses import ExpenseVoucher
from app.models.cash_session import CashSession
from app.models.returns import ReturnTransaction, ReturnStatus, RefundMethod
from app.database import business_date

logger = logging.getLogger("dukapos.accounting")

TWO_PLACES = Decimal("0.01")


# Lazy import to avoid circular dependency (reconciliation imports accounting)
def _check_period(db: Session, store_id: int, entry_date) -> None:
    """Guard: raises ValueError if entry_date is in a closed/locked period."""
    try:
        from app.services.reconciliation import assert_period_open
        assert_period_open(db, store_id, entry_date)
    except ImportError:
        pass  # reconciliation service not available (e.g. test environment)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _q(amount) -> Decimal:
    """Quantize to 2 decimal places."""
    return Decimal(str(amount)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _get_account(db: Session, store_id: int, code: str) -> Account:
    acc = db.query(Account).filter(
        Account.store_id == store_id,
        Account.code == code,
        Account.is_active == True,
    ).first()
    if not acc:
        raise ValueError(
            f"Account code '{code}' not found for store {store_id}. "
            f"Run seed_chart_of_accounts() first."
        )
    return acc


def _post_entry(
    db: Session,
    store_id: int,
    ref_type: str,
    ref_id: str,
    description: str,
    entry_date: date,
    lines: list[tuple[Account, Decimal, Decimal, str]],
    # (account, debit, credit, memo)
    posted_by: Optional[int] = None,
) -> JournalEntry:
    """
    Create and persist a balanced journal entry.
    Raises ValueError if debits != credits.
    """
    total_dr = sum(dr for _, dr, _, _ in lines)
    total_cr = sum(cr for _, _, cr, _ in lines)

    if _q(total_dr) != _q(total_cr):
        raise ValueError(
            f"Unbalanced journal entry for {ref_type}:{ref_id} — "
            f"DR={total_dr} CR={total_cr}"
        )

    # Period guard — raises ValueError if entry_date falls in a closed/locked period
    _check_period(db, store_id, entry_date)

    entry = JournalEntry(
        store_id    = store_id,
        ref_type    = ref_type,
        ref_id      = ref_id,
        description = description,
        entry_date  = entry_date,
        posted_by   = posted_by,
    )
    db.add(entry)
    db.flush()  # get entry.id

    for account, debit, credit, memo in lines:
        db.add(JournalLine(
            entry_id   = entry.id,
            account_id = account.id,
            debit      = _q(debit),
            credit     = _q(credit),
            memo       = memo,
        ))

    logger.info(
        "Journal entry posted: %s:%s  DR=%.2f  CR=%.2f",
        ref_type, ref_id, total_dr, total_cr,
    )
    return entry


def _debit_account_for_payment(
    payment_method: PaymentMethod,
    db: Session,
    store_id: int,
) -> Account:
    """
    Return the correct asset account for a payment method.
    
    P1-D: SPLIT is no longer supported — validation at router level rejects it.
    This function raises an error if SPLIT somehow makes it through.
    """
    code_map = {
        PaymentMethod.CASH:         "1000",  # Cash in Hand
        PaymentMethod.MPESA:        "1010",  # M-PESA Float
        PaymentMethod.CARD:         "1020",  # Bank Account (card settles to bank)
        PaymentMethod.CREDIT:       "1100",  # Accounts Receivable
        PaymentMethod.STORE_CREDIT: "1400",  # Store Credit Liability
    }
    
    if payment_method == PaymentMethod.SPLIT:
        raise ValueError(
            "SPLIT payment method is not supported. "
            "Transactions should be rejected at API validation level."
        )
    
    code = code_map.get(payment_method, "1000")
    return _get_account(db, store_id, code)


# ── Public API ────────────────────────────────────────────────────────────────

def seed_chart_of_accounts(db: Session, store_id: int) -> int:
    """
    Insert the default Kenyan SMB chart of accounts for a new store.
    Idempotent — skips codes that already exist.
    Returns the number of accounts created.
    """
    existing_codes = {
        row.code
        for row in db.query(Account.code).filter(Account.store_id == store_id).all()
    }

    created = 0
    for code, name, acct_type, sub_type, normal_bal, is_system in DEFAULT_ACCOUNTS:
        if code in existing_codes:
            continue
        db.add(Account(
            store_id       = store_id,
            code           = code,
            name           = name,
            account_type   = acct_type,
            sub_type       = sub_type,
            normal_balance = normal_bal,
            is_system      = is_system,
        ))
        created += 1

    if created:
        db.flush()
        logger.info("Seeded %d accounts for store %d", created, store_id)

    return created


def post_transaction(
    db: Session,
    txn: Transaction,
    items: Optional[list] = None,  # list[TransactionItem]; loaded from DB if None
) -> Optional[JournalEntry]:
    """
    Auto-post a completed sale as a FULL double-entry journal entry.

    Posts ALL five accounting legs:
      DR  Cash / M-PESA / AR       total_received
      CR  Sales Revenue             subtotal (excl. VAT)
      CR  VAT Payable               vat_amount
      DR  Cost of Goods Sold        cogs_amount  ← NEW
      CR  Inventory / Stock         cogs_amount  ← NEW

    Called from:
      - transactions.py create_transaction()       (online POS sales)
      - sync.py sync_transactions()                (offline sync ingest) ← CRITICAL

    COGS calculation uses cost_price_snap on TransactionItem.
    If cost_price_snap is 0 or NULL the entry is still posted with COGS=0
    and a 'zero_cost_sale' flag is logged for ops review.

    Returns the JournalEntry, or None if:
      - transaction is not COMPLETED
      - journal entry already exists for this txn (idempotency)
    """
    if txn.status != TransactionStatus.COMPLETED:
        return None

    # Idempotency guard — never double-post
    existing = db.query(JournalEntry).filter(
        JournalEntry.store_id == txn.store_id,
        JournalEntry.ref_type == "transaction",
        JournalEntry.ref_id   == txn.txn_number,
        JournalEntry.is_void  == False,
    ).first()
    if existing:
        logger.debug("Journal entry already exists for txn %s — skipping", txn.txn_number)
        return existing

    # Load items if not supplied
    if items is None:
        items = db.query(TransactionItem).filter(
            TransactionItem.transaction_id == txn.id
        ).all()

    # Calculate COGS from cost_price_snap (never from product.cost_price at posting time)
    cogs = Decimal("0.00")
    zero_cost_items = []
    for item in items:
        snap = item.cost_price_snap if item.cost_price_snap is not None else Decimal("0.00")
        item_cogs = _q(Decimal(str(snap)) * Decimal(str(item.qty)))
        cogs += item_cogs
        if snap == Decimal("0.00"):
            zero_cost_items.append(getattr(item, 'sku', str(item.product_id)))

    if zero_cost_items:
        logger.warning(
            "ZERO COST SALE — txn %s has items with no cost snapshot: %s. "
            "COGS will be understated. Check product cost prices.",
            txn.txn_number, zero_cost_items
        )

    try:
        # Resolve accounts
        debit_acc = _debit_account_for_payment(txn.payment_method, db, txn.store_id)
        rev_acc   = _get_account(db, txn.store_id, "4000")   # Sales Revenue
        vat_acc   = _get_account(db, txn.store_id, "2100")   # VAT Payable
        cogs_acc  = _get_account(db, txn.store_id, "5000")   # Cost of Goods Sold
        inv_acc   = _get_account(db, txn.store_id, "1200")   # Inventory / Stock

        total   = _q(txn.total)
        vat     = _q(txn.vat_amount or 0)
        revenue = _q(total - vat)
        cogs    = _q(cogs)

        entry_date = txn.completed_at.date() if txn.completed_at else (
            txn.created_at.date() if txn.created_at else business_date()
        )

        # Build the 5-leg entry
        lines = [
            (debit_acc, total,          Decimal(0), f"{txn.payment_method.value.upper()} receipt — {txn.txn_number}"),
            (rev_acc,   Decimal(0),     revenue,    f"Sales revenue — {txn.txn_number}"),
            (vat_acc,   Decimal(0),     vat,        "VAT Payable 16%"),
        ]
        if cogs > Decimal("0.00"):
            lines.append((cogs_acc, cogs, Decimal(0), f"COGS — {txn.txn_number}"))
            lines.append((inv_acc,  Decimal(0), cogs, f"Inventory reduction — {txn.txn_number}"))
        # Note: if COGS = 0, we skip COGS/Inventory legs to keep entry balanced.
        # A zero-cost alert is logged above. This is a data quality issue, not an
        # accounting error — the 3-leg entry (cash/revenue/VAT) still balances.

        entry = _post_entry(
            db          = db,
            store_id    = txn.store_id,
            ref_type    = "transaction",
            ref_id      = txn.txn_number,
            description = f"Sale {txn.txn_number} — {txn.payment_method.value} | COGS={float(cogs):.2f}",
            entry_date  = entry_date,
            lines       = lines,
            posted_by   = None,  # system-posted
        )
        return entry

    except ValueError as exc:
        logger.error("Accounting post FAILED for txn %s: %s", txn.txn_number, exc)
        raise  # Re-raise so the caller can roll back the entire transaction


def post_transaction_void(
    db: Session,
    txn: Transaction,
    voided_by: int,
) -> Optional[JournalEntry]:
    """
    Post a reversal entry when a transaction is voided.
    Mirrors the original entry with DR/CR swapped.
    """
    # Find original entry
    original = db.query(JournalEntry).filter(
        JournalEntry.store_id == txn.store_id,
        JournalEntry.ref_type == "transaction",
        JournalEntry.ref_id   == txn.txn_number,
        JournalEntry.is_void  == False,
    ).first()

    if not original:
        logger.warning("No original journal entry to reverse for txn %s", txn.txn_number)
        return None

    # Idempotency — don't post void twice
    void_exists = db.query(JournalEntry).filter(
        JournalEntry.store_id == txn.store_id,
        JournalEntry.ref_type == "void",
        JournalEntry.ref_id   == txn.txn_number,
    ).first()
    if void_exists:
        return void_exists

    # Explicitly load lines — flush first so any pending inserts are visible
    db.flush()
    from app.models.accounting import JournalLine as _JournalLine
    original_lines = db.query(_JournalLine).filter(
        _JournalLine.entry_id == original.id
    ).all()

    if not original_lines:
        logger.warning("No lines found on original entry %d for txn %s — void skipped",
                       original.id, txn.txn_number)
        return None

    try:
        # Reverse each line (swap debit/credit)
        reversal_lines = []
        for line in original_lines:
            acc = db.query(Account).get(line.account_id)
            reversal_lines.append((
                acc,
                line.credit,   # original credit becomes debit
                line.debit,    # original debit becomes credit
                f"VOID: {line.memo or ''}",
            ))

        entry = _post_entry(
            db          = db,
            store_id    = txn.store_id,
            ref_type    = "void",
            ref_id      = txn.txn_number,
            description = f"VOID of sale {txn.txn_number}",
            entry_date  = business_date(),
            lines       = reversal_lines,
            posted_by   = voided_by,
        )
        return entry

    except ValueError as exc:
        logger.error("Void reversal failed for txn %s: %s", txn.txn_number, exc)
        return None


def post_grn(
    db: Session,
    grn: GoodsReceivedNote,
    posted_by: int,
) -> Optional[JournalEntry]:
    """
    Auto-post a GRN as:
      DR  Inventory / Stock (1200)   total cost received
        CR  Accounts Payable (2000)     total cost received

    Called from procurement service after GRN is posted.
    Only posts if grn.status == POSTED.
    """
    if grn.status != GRNStatus.POSTED:
        return None

    # Idempotency
    existing = db.query(JournalEntry).filter(
        JournalEntry.store_id == grn.store_id,
        JournalEntry.ref_type == "grn",
        JournalEntry.ref_id   == grn.grn_number,
        JournalEntry.is_void  == False,
    ).first()
    if existing:
        return existing

    # Calculate total received cost from GRN items
    total_cost = Decimal("0.00")
    for item in grn.items:
        accepted = item.received_qty_base - (item.damaged_qty_base or 0) - (item.rejected_qty_base or 0)
        if accepted > 0 and item.cost_per_base_unit:
            total_cost += _q(Decimal(str(accepted)) * Decimal(str(item.cost_per_base_unit)))

    if total_cost <= 0:
        logger.info("GRN %s has zero cost — skipping journal entry", grn.grn_number)
        return None

    inv_acc = _get_account(db, grn.store_id, "1200")  # Inventory / Stock
    ap_acc  = _get_account(db, grn.store_id, "2000")  # Accounts Payable

    lines = [
        (inv_acc, total_cost, Decimal(0), f"Stock received — {grn.grn_number}"),
        (ap_acc,  Decimal(0), total_cost, f"Payable to supplier — {grn.grn_number}"),
    ]

    entry = _post_entry(
        db          = db,
        store_id    = grn.store_id,
        ref_type    = "grn",
        ref_id      = grn.grn_number,
        description = f"GRN {grn.grn_number} — stock received from supplier",
        entry_date  = grn.received_date or business_date(),
        lines       = lines,
        posted_by   = posted_by,
    )
    return entry


# ── Reporting queries ──────────────────────────────────────────────────────────

def get_trial_balance(
    db: Session,
    store_id: int,
    as_of_date: Optional[date] = None,
) -> dict:
    """
    Trial balance: all account codes with their net debit/credit balance.
    as_of_date defaults to today — filters journal entries up to and including that date.
    """
    as_of = as_of_date or business_date()

    rows = (
        db.query(
            Account.id,
            Account.code,
            Account.name,
            Account.account_type,
            Account.normal_balance,
            func.coalesce(func.sum(JournalLine.debit),  Decimal(0)).label("total_dr"),
            func.coalesce(func.sum(JournalLine.credit), Decimal(0)).label("total_cr"),
        )
        .outerjoin(JournalLine, JournalLine.account_id == Account.id)
        .outerjoin(
            JournalEntry,
            and_(
                JournalEntry.id       == JournalLine.entry_id,
                JournalEntry.is_void  == False,
                JournalEntry.entry_date <= as_of,
            )
        )
        .filter(
            Account.store_id  == store_id,
            Account.is_active == True,
        )
        .group_by(Account.id, Account.code, Account.name, Account.account_type, Account.normal_balance)
        .order_by(Account.code)
        .all()
    )

    accounts = []
    total_debits  = Decimal(0)
    total_credits = Decimal(0)

    for row in rows:
        dr = _q(row.total_dr)
        cr = _q(row.total_cr)

        # Net balance: positive = account has a balance on its normal side
        if row.normal_balance == "debit":
            net = _q(dr - cr)
            debit_bal  = max(net,  Decimal(0))
            credit_bal = max(-net, Decimal(0))
        else:
            net = _q(cr - dr)
            credit_bal = max(net,  Decimal(0))
            debit_bal  = max(-net, Decimal(0))

        total_debits  += debit_bal
        total_credits += credit_bal

        accounts.append({
            "code":           row.code,
            "name":           row.name,
            "account_type":   row.account_type,
            "normal_balance": row.normal_balance,
            "debit_balance":  float(debit_bal),
            "credit_balance": float(credit_bal),
        })

    return {
        "as_of_date":     str(as_of),
        "accounts":       accounts,
        "total_debits":   float(total_debits),
        "total_credits":  float(total_credits),
        "is_balanced":    _q(total_debits) == _q(total_credits),
    }


def get_pl(
    db: Session,
    store_id: int,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
) -> dict:
    """
    Profit & Loss statement for a date range.
    Defaults to current month if no dates supplied.
    """
    from datetime import date as _date
    today = business_date()

    if not date_from:
        date_from = today.replace(day=1)   # first of current month
    if not date_to:
        date_to = today

    try:
        def _sum_type(acct_type: str) -> Decimal:
            row = (
                db.query(
                    func.coalesce(
                        func.sum(
                            case(
                                (Account.normal_balance == "credit",
                                JournalLine.credit - JournalLine.debit),
                                else_=JournalLine.debit - JournalLine.credit,
                            )
                        ),
                        Decimal(0)
                    ).label("net")
                )
                .select_from(Account)
                .join(JournalLine, JournalLine.account_id == Account.id)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .filter(
                    JournalEntry.is_void == False,
                    JournalEntry.entry_date >= date_from,
                    JournalEntry.entry_date <= date_to,
                    Account.store_id == store_id,
                    Account.account_type == acct_type,
                    Account.is_active == True,
                )
                .first()
            )
            return _q(row.net if row and row.net else Decimal(0))

        revenue  = _sum_type("REVENUE")
        cogs     = _sum_type("COGS")
        expenses = _sum_type("EXPENSE")

        gross_profit = _q(revenue - cogs)
        net_profit   = _q(gross_profit - expenses)

        # Breakdown by account
        def _breakdown(acct_type: str) -> list[dict]:
            rows = (
                db.query(
                    Account.code,
                    Account.name,
                    func.coalesce(
                        func.sum(
                            case(
                                (Account.normal_balance == "credit",
                                JournalLine.credit - JournalLine.debit),
                                else_=JournalLine.debit - JournalLine.credit,
                            )
                        ),
                        Decimal(0)
                    ).label("net"),
                )
                .select_from(Account)
                .join(JournalLine, JournalLine.account_id == Account.id)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .filter(
                    JournalEntry.is_void == False,
                    JournalEntry.entry_date >= date_from,
                    JournalEntry.entry_date <= date_to,
                    Account.store_id == store_id,
                    Account.account_type == acct_type,
                    Account.is_active == True,
                )
                .group_by(Account.code, Account.name, Account.normal_balance)
                .order_by(Account.code)
                .all()
            )
            return [
                {"code": r.code, "name": r.name, "amount": float(_q(r.net))}
                for r in rows if _q(r.net) != 0
            ]

        return {
            "date_from":     str(date_from),
            "date_to":       str(date_to),
            "revenue":       float(revenue),
            "cogs":          float(cogs),
            "gross_profit":  float(gross_profit),
            "expenses":      float(expenses),
            "net_profit":    float(net_profit),
            "breakdown": {
                "revenue":   _breakdown("REVENUE"),
                "cogs":      _breakdown("COGS"),
                "expenses":  _breakdown("EXPENSE"),
            },
        }
    except SQLAlchemyError as exc:
        logger.exception(
            "P&L query failed for store_id=%s range=%s..%s",
            store_id,
            date_from,
            date_to,
        )
        raise HTTPException(
            status_code=503,
            detail="Accounting data is unavailable. Run database migrations and retry.",
        ) from exc


def get_balance_sheet(
    db: Session,
    store_id: int,
    as_of_date: Optional[date] = None,
) -> dict:
    """
    Balance Sheet: Assets = Liabilities + Equity
    as_of_date defaults to today.

    P1-D Fix: Retain historical retained earnings (3100) balance (from prior periods),
    plus current month's unallocated profit, without double-counting.
    """
    as_of = as_of_date or business_date()

    def _net_balance(acct_type: str, exclude_code: Optional[str] = None) -> tuple[Decimal, list[dict]]:
        query = (
            db.query(
                Account.code,
                Account.name,
                Account.normal_balance,
                func.coalesce(func.sum(JournalLine.debit),  Decimal(0)).label("dr"),
                func.coalesce(func.sum(JournalLine.credit), Decimal(0)).label("cr"),
            )
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(JournalEntry, and_(
                JournalEntry.id          == JournalLine.entry_id,
                JournalEntry.is_void     == False,
                JournalEntry.entry_date  <= as_of,
            ))
            .filter(
                Account.store_id     == store_id,
                Account.account_type == acct_type,
                Account.is_active    == True,
            )
        )
        
        if exclude_code:
            query = query.filter(Account.code != exclude_code)
        
        rows = query.group_by(Account.code, Account.name, Account.normal_balance).order_by(Account.code).all()
        
        total = Decimal(0)
        items = []
        for r in rows:
            if r.normal_balance == "debit":
                net = _q(r.dr - r.cr)
            else:
                net = _q(r.cr - r.dr)
            total += net
            if net != 0:
                items.append({"code": r.code, "name": r.name, "amount": float(net)})
        return total, items

    asset_total,   assets      = _net_balance("ASSET")
    liab_total,    liabilities = _net_balance("LIABILITY")
    # P1-D: Exclude 3100 (Retained Earnings) from equity sum to avoid double-counting current period
    equity_total,  equities    = _net_balance("EQUITY", exclude_code="3100")

    # Cumulative P&L from inception through the day BEFORE the current period starts.
    # This correctly accumulates all historical profit without relying on manual closing entries.
    # When a formal year-end close workflow is added later, this can be replaced with
    # the 3100 journal balance, and this block updated to only run as a fallback.
    from datetime import timedelta
    INCEPTION_DATE = date(2020, 1, 1)  # floor date — adjust to actual go-live date if known
    as_of_month_start = as_of.replace(day=1)
    prior_period_end = as_of_month_start - timedelta(days=1)

    if prior_period_end >= INCEPTION_DATE:
        prior_pl = get_pl(db, store_id, date_from=INCEPTION_DATE, date_to=prior_period_end)
        retained_hist = _q(Decimal(str(prior_pl["net_profit"])))
    else:
        retained_hist = Decimal(0)
    pl = get_pl(db, store_id, date_from=as_of_month_start, date_to=as_of)
    current_profit = _q(Decimal(str(pl["net_profit"])))
    
    # Total retained = historical balance from 3100 account + current period unallocated profit
    total_retained = _q(retained_hist + current_profit)
    equity_total += total_retained
    
    if retained_hist != 0 or current_profit != 0:
        equities.append({"code": "3100", "name": "Retained Earnings", "amount": float(retained_hist)})
        if current_profit != 0:
            equities.append({"code": "RE", "name": "Current Period Profit (Unallocated)", "amount": float(current_profit)})

    return {
        "as_of_date":       str(as_of),
        "total_assets":     float(asset_total),
        "total_liabilities": float(liab_total),
        "total_equity":     float(equity_total),
        "is_balanced":      _q(asset_total) == _q(liab_total + equity_total),
        "assets":           assets,
        "liabilities":      liabilities,
        "equity":           equities,
    }


def get_vat_summary(
    db: Session,
    store_id: int,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
) -> dict:
    """
    VAT reconciliation report.
    Output VAT = VAT collected on sales (CR balance on VAT Payable 2100).
    Input VAT  = VAT paid on purchases — not yet modelled (Phase 2 with supplier invoices).
    Net VAT payable = Output - Input.
    """
    today = business_date()
    if not date_from:
        date_from = today.replace(day=1)
    if not date_to:
        date_to = today

    vat_acc = db.query(Account).filter(
        Account.store_id     == store_id,
        Account.code         == "2100",
        Account.is_active    == True,
    ).first()

    if not vat_acc:
        return {"error": "VAT Payable account (2100) not found. Run account seeding first."}

    row = (
        db.query(
            func.coalesce(func.sum(JournalLine.credit), Decimal(0)).label("output_vat"),
            func.coalesce(func.sum(JournalLine.debit),  Decimal(0)).label("input_vat"),
        )
        .join(JournalEntry, and_(
            JournalEntry.id         == JournalLine.entry_id,
            JournalEntry.is_void    == False,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
        ))
        .filter(JournalLine.account_id == vat_acc.id)
        .first()
    )

    output_vat = _q(row.output_vat or Decimal(0))
    input_vat  = _q(row.input_vat  or Decimal(0))
    net_vat    = _q(output_vat - input_vat)

    return {
        "date_from":    str(date_from),
        "date_to":      str(date_to),
        "output_vat":   float(output_vat),   # collected from customers
        "input_vat":    float(input_vat),    # paid to suppliers (Phase 2)
        "net_payable":  float(net_vat),      # owed to KRA
        "vat_rate":     "16%",
        "note": "Input VAT from supplier invoices will be included in Phase 2.",
    }


def get_account_ledger(
    db: Session,
    store_id: int,
    account_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 100,
) -> dict:
    """
    General ledger for a single account — all transactions affecting it.
    """
    today = business_date()
    if not date_from:
        date_from = today.replace(day=1)
    if not date_to:
        date_to = today

    account = db.query(Account).filter(
        Account.id       == account_id,
        Account.store_id == store_id,
    ).first()

    if not account:
        raise HTTPException(404, "Account not found")

    lines = (
        db.query(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(
            JournalLine.account_id  == account_id,
            JournalEntry.is_void    == False,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
        )
        .order_by(JournalEntry.entry_date, JournalEntry.id)
        .limit(limit)
        .all()
    )

    running_balance = Decimal(0)
    entries_out = []

    for line, entry in lines:
        dr = _q(line.debit)
        cr = _q(line.credit)

        if account.normal_balance == "debit":
            running_balance += dr - cr
        else:
            running_balance += cr - dr

        entries_out.append({
            "date":        str(entry.entry_date),
            "ref_type":    entry.ref_type,
            "ref_id":      entry.ref_id,
            "description": entry.description,
            "memo":        line.memo,
            "debit":       float(dr),
            "credit":      float(cr),
            "balance":     float(_q(running_balance)),
        })

    return {
        "account":    {"code": account.code, "name": account.name, "type": account.account_type},
        "date_from":  str(date_from),
        "date_to":    str(date_to),
        "entries":    entries_out,
        "closing_balance": float(_q(running_balance)),
    }


# ── Returns accounting ────────────────────────────────────────────────────────

def post_return(
    db:       "Session",
    ret_txn:  "Any",           # ReturnTransaction — avoid circular import
    items:    list,            # list[ReturnItem]
) -> Optional[JournalEntry]:
    """
    Post a double-entry journal reversal for a completed return.

    Journal pattern
    ───────────────
    For ALL return items (restorable + damaged):
        CR  Payment account (1000/1010/1020/1100)  total_refund_amount
        DR  Sales Revenue (4000)                   Σ line_totals (ex-VAT)
        DR  VAT Payable (2100)                     Σ vat_amounts

    For RESTORABLE items only:
        DR  Inventory / Stock (1200)               Σ cost × qty
        CR  Cost of Goods Sold (5000)              Σ cost × qty

    For DAMAGED (non-restorable) items:
        No Inventory / COGS legs — cost is a sunk loss.

    Idempotent: if a journal entry already exists for this return_number
    the existing entry is returned without creating a duplicate.

    Called exclusively from returns_service.approve_and_complete() within
    the same DB transaction — do not call independently.
    """
    from app.models.returns import RefundMethod as _RefundMethod

    # ── Idempotency guard ─────────────────────────────────────────────────────
    existing = db.query(JournalEntry).filter(
        JournalEntry.store_id == ret_txn.store_id,
        JournalEntry.ref_type == "return",
        JournalEntry.ref_id   == ret_txn.return_number,
        JournalEntry.is_void  == False,
    ).first()
    if existing:
        logger.debug(
            "Journal entry already exists for return %s — skipping",
            ret_txn.return_number,
        )
        return existing

    # ── Aggregate amounts from items ──────────────────────────────────────────
    total_revenue_reversal = Decimal("0.00")
    total_vat_reversal     = Decimal("0.00")
    total_cogs_reversal    = Decimal("0.00")

    for item in items:
        total_revenue_reversal += _q(Decimal(str(item.line_total)))
        total_vat_reversal     += _q(Decimal(str(item.vat_amount)))
        if item.is_restorable:
            total_cogs_reversal += _q(
                Decimal(str(item.cost_price_snap)) * Decimal(str(item.qty_returned))
            )

    total_revenue_reversal = _q(total_revenue_reversal)
    total_vat_reversal     = _q(total_vat_reversal)
    total_cogs_reversal    = _q(total_cogs_reversal)

    # Total cash out = revenue_reversal (ex-VAT) + vat_reversal
    total_cash_out = _q(total_revenue_reversal + total_vat_reversal)

    if total_cash_out <= Decimal("0.00"):
        logger.warning(
            "Return %s has zero total — skipping journal entry",
            ret_txn.return_number,
        )
        return None

    try:
        # Resolve the payment asset account for the refund (CR side)
        refund_method = ret_txn.refund_method
        _method_to_code = {
            _RefundMethod.CASH:         "1000",  # Cash in Hand
            _RefundMethod.MPESA:        "1010",  # M-PESA Float
            _RefundMethod.CARD:         "1020",  # Bank Account
            _RefundMethod.STORE_CREDIT: "1400",  # Store Credit Liability
            _RefundMethod.CREDIT_NOTE:  "1100",  # Treated as AR / payable to customer
        }
        asset_code = _method_to_code.get(refund_method, "1000")
        asset_acc = _get_account(db, ret_txn.store_id, asset_code)
        rev_acc   = _get_account(db, ret_txn.store_id, "4000")   # Sales Revenue
        vat_acc   = _get_account(db, ret_txn.store_id, "2100")   # VAT Payable

        # Base 3-leg entry (applies to ALL returns — restorable and damaged)
        lines = [
            # CR asset account — we are paying the customer back
            (asset_acc, Decimal(0), total_cash_out,
             f"Refund payment — {ret_txn.return_number}"),
            # DR Sales Revenue — reverse the revenue
            (rev_acc, total_revenue_reversal, Decimal(0),
             f"Revenue reversal — {ret_txn.return_number}"),
            # DR VAT Payable — reverse the VAT that was collected
            (vat_acc, total_vat_reversal, Decimal(0),
             f"VAT reversal — {ret_txn.return_number}"),
        ]

        # 5-leg extension for restorable items only
        if total_cogs_reversal > Decimal("0.00"):
            inv_acc  = _get_account(db, ret_txn.store_id, "1200")  # Inventory / Stock
            cogs_acc = _get_account(db, ret_txn.store_id, "5000")  # COGS
            lines.append(
                # DR Inventory — stock is coming back in
                (inv_acc, total_cogs_reversal, Decimal(0),
                 f"Inventory restore — {ret_txn.return_number}")
            )
            lines.append(
                # CR COGS — reverse the cost we recognised on the original sale
                (cogs_acc, Decimal(0), total_cogs_reversal,
                 f"COGS reversal — {ret_txn.return_number}")
            )

        entry_date = (
            ret_txn.completed_at.date()
            if ret_txn.completed_at
            else business_date()
        )

        entry = _post_entry(
            db          = db,
            store_id    = ret_txn.store_id,
            ref_type    = "return",
            ref_id      = ret_txn.return_number,
            description = (
                f"Return {ret_txn.return_number} — "
                f"orig {ret_txn.original_txn_number} | "
                f"method={refund_method}"
            ),
            entry_date  = entry_date,
            lines       = lines,
            posted_by   = ret_txn.approved_by,
        )
        return entry

    except ValueError as exc:
        logger.error(
            "Accounting post FAILED for return %s: %s",
            ret_txn.return_number, exc,
        )
        raise



def _payment_method_to_account(db: Session, store_id: int, payment_method: str) -> Account:
    method = (payment_method or "cash").lower()
    code = {"cash": "1000", "mpesa": "1010", "card": "1020", "bank": "1020", "bank_clearing": "1050"}.get(method, "1000")
    return _get_account(db, store_id, code)


def post_supplier_payment(db: Session, payment: SupplierPayment) -> JournalEntry:
    amount = _q(payment.amount)
    if amount <= Decimal("0.00"):
        raise ValueError("Supplier payment amount must be greater than zero")
    ap = _get_account(db, payment.store_id, "2000")
    cash = _payment_method_to_account(db, payment.store_id, payment.payment_method)
    return _post_entry(
        db, payment.store_id, "supplier_payment", payment.payment_number,
        f"Supplier payment {payment.payment_number}", payment.payment_date,
        [
            (ap, amount, Decimal("0.00"), f"Supplier payment {payment.payment_number}"),
            (cash, Decimal("0.00"), amount, f"Supplier payment {payment.payment_number}"),
        ],
        posted_by=payment.created_by,
    )


def post_expense_voucher(db: Session, voucher: ExpenseVoucher) -> JournalEntry:
    amount = _q(voucher.amount)
    if amount <= Decimal("0.00"):
        raise ValueError("Expense amount must be greater than zero")
    expense_account = db.query(Account).filter(Account.id == voucher.account_id, Account.store_id == voucher.store_id).first()
    if not expense_account:
        raise ValueError("Expense account not found")
    if expense_account.account_type not in (AccountType.EXPENSE.value, AccountType.COGS.value):
        raise ValueError("Expense voucher must post to an expense or COGS account")
    credit_account = _payment_method_to_account(db, voucher.store_id, voucher.payment_method)
    return _post_entry(
        db, voucher.store_id, "expense_voucher", voucher.voucher_number,
        f"Expense voucher {voucher.voucher_number}", voucher.expense_date,
        [
            (expense_account, amount, Decimal("0.00"), voucher.payee or "Expense voucher"),
            (credit_account, Decimal("0.00"), amount, voucher.reference or voucher.voucher_number),
        ],
        posted_by=voucher.created_by,
    )


def post_expense_voucher_void(db: Session, voucher: ExpenseVoucher) -> Optional[JournalEntry]:
    """
    Post a reversal entry when an expense voucher is voided.
    Mirrors post_expense_voucher() with DR/CR swapped:

    Original:  DR Expense Account    amount
               CR Cash/Bank Account  amount

    Reversal:  CR Expense Account    amount   ← this function
               DR Cash/Bank Account  amount
    """
    # Idempotency guard — do not post void reversal twice
    existing = db.query(JournalEntry).filter(
        JournalEntry.store_id == voucher.store_id,
        JournalEntry.ref_type == "expense_void",
        JournalEntry.ref_id   == voucher.voucher_number,
        JournalEntry.is_void  == False,
    ).first()
    if existing:
        logger.debug(
            "Void reversal already exists for expense voucher %s — skipping",
            voucher.voucher_number,
        )
        return existing

    amount = _q(voucher.amount)
    if amount <= Decimal("0.00"):
        raise ValueError("Expense voucher amount must be greater than zero")

    # Resolve the original expense account
    expense_account = db.query(Account).filter(
        Account.id       == voucher.account_id,
        Account.store_id == voucher.store_id,
    ).first()
    if not expense_account:
        raise ValueError(
            f"Expense account (id={voucher.account_id}) not found for store {voucher.store_id}"
        )

    # Resolve the cash/bank account that was originally credited
    credit_account = _payment_method_to_account(db, voucher.store_id, voucher.payment_method)

    # Reversed lines: CR expense, DR cash (mirror of original)
    lines = [
        (credit_account,  amount,         Decimal("0.00"), f"Void of expense {voucher.voucher_number}"),
        (expense_account, Decimal("0.00"), amount,         f"Void reversal — {voucher.voucher_number}"),
    ]

    return _post_entry(
        db          = db,
        store_id    = voucher.store_id,
        ref_type    = "expense_void",
        ref_id      = voucher.voucher_number,
        description = f"VOID of expense voucher {voucher.voucher_number}",
        entry_date  = business_date(),
        lines       = lines,
        posted_by   = voucher.voided_by,
    )


def post_customer_payment(db: Session, store_id: int, customer: Customer, amount, payment_date, payment_method: str, reference: str, actor_id: int | None = None) -> JournalEntry:
    amount = _q(amount)
    if amount <= Decimal("0.00"):
        raise ValueError("Customer payment amount must be greater than zero")
    ar = _get_account(db, store_id, "1100")
    cash = _payment_method_to_account(db, store_id, payment_method)
    return _post_entry(
        db, store_id, "customer_payment", reference,
        f"Customer payment {reference} — {customer.name}", payment_date,
        [
            (cash, amount, Decimal("0.00"), f"Customer payment {reference}"),
            (ar, Decimal("0.00"), amount, f"Customer payment {reference}"),
        ],
        posted_by=actor_id,
    )


def _stock_adjustment_reason_account(db: Session, store_id: int, reason: str, qty_change: int):
    reason = (reason or "adjustment").lower()
    if reason in {"damage", "damaged", "expiry", "expired"}:
        return _get_account(db, store_id, "6800")
    if reason in {"shrinkage", "stock_loss", "write_off", "theft"}:
        return _get_account(db, store_id, "6700")
    if qty_change > 0:
        return _get_account(db, store_id, "4100")
    return _get_account(db, store_id, "6700")


def post_stock_adjustment(db: Session, store_id: int, product: Product, quantity_change: int, reason: str, notes: str | None, actor_id: int | None = None) -> JournalEntry | None:
    if quantity_change == 0:
        return None
    unit_cost = Decimal(str(product.cost_price or product.wac or product.selling_price or 0))
    value = _q(unit_cost * Decimal(str(abs(quantity_change))))
    if value <= Decimal("0.00"):
        return None
    inventory = _get_account(db, store_id, "1200")
    offset = _stock_adjustment_reason_account(db, store_id, reason, quantity_change)
    ref_id = f"ADJ-{product.id}-{int(datetime.now().timestamp())}"
    if quantity_change < 0:
        lines = [
            (offset, value, Decimal("0.00"), notes or reason),
            (inventory, Decimal("0.00"), value, notes or reason),
        ]
    else:
        lines = [
            (inventory, value, Decimal("0.00"), notes or reason),
            (offset, Decimal("0.00"), value, notes or reason),
        ]
    return _post_entry(db, store_id, "stock_adjustment", ref_id, f"Stock adjustment {reason} — {product.sku}", business_date(), lines, posted_by=actor_id)


def post_cash_session_open(db: Session, cash_session: CashSession) -> JournalEntry | None:
    amount = _q(cash_session.opening_float)
    if amount <= Decimal("0.00"):
        return None
    till = _get_account(db, cash_session.store_id, "1040")
    cash = _get_account(db, cash_session.store_id, "1000")
    return _post_entry(db, cash_session.store_id, "cash_session_open", cash_session.session_number, f"Cash session open {cash_session.session_number}", business_date(), [(till, amount, Decimal("0.00"), "Opening float"), (cash, Decimal("0.00"), amount, "Opening float")], posted_by=cash_session.opened_by)


def post_cash_session_close(db: Session, cash_session: CashSession) -> JournalEntry | None:
    variance = _q(cash_session.variance or 0)
    if variance == Decimal("0.00"):
        return None
    till = _get_account(db, cash_session.store_id, "1040")
    variance_acc = _get_account(db, cash_session.store_id, "2300")
    if variance > Decimal("0.00"):
        lines = [(till, variance, Decimal("0.00"), "Till overage"), (variance_acc, Decimal("0.00"), variance, "Till overage")]
    else:
        v = abs(variance)
        lines = [(variance_acc, v, Decimal("0.00"), "Till shortage"), (till, Decimal("0.00"), v, "Till shortage")]
    return _post_entry(db, cash_session.store_id, "cash_session_close", cash_session.session_number, f"Cash session close {cash_session.session_number}", business_date(), lines, posted_by=cash_session.closed_by)


def get_ap_aging(db: Session, store_id: int) -> dict:
    from sqlalchemy import text
    today = business_date()

    # ── Single query: outstanding GRN invoices per supplier with age ──────────
    grn_sql = text("""
        SELECT
            s.id        AS supplier_id,
            s.name      AS supplier_name,
            g.id        AS grn_id,
            COALESCE(g.total_received_cost, 0) AS invoice_amount,
            COALESCE(DATE(g.posted_at), g.received_date) AS invoice_date
        FROM suppliers s
        JOIN goods_received_notes g
          ON g.supplier_id = s.id AND g.store_id = :store_id AND g.status = 'posted'
        WHERE s.store_id = :store_id
        ORDER BY s.id, invoice_date
    """)

    pay_sql = text("""
        SELECT
            supplier_id,
            SUM(COALESCE(amount, 0)) AS total_paid
        FROM supplier_payments
        WHERE store_id = :store_id AND is_void = false
        GROUP BY supplier_id
    """)

    grn_rows = db.execute(grn_sql, {"store_id": store_id}).mappings().all()
    pay_rows = db.execute(pay_sql, {"store_id": store_id}).mappings().all()

    # Index payments by supplier
    payments_by_supplier: dict[int, Decimal] = {
        r["supplier_id"]: _q(r["total_paid"]) for r in pay_rows
    }

    # Group GRNs by supplier
    from collections import defaultdict
    from datetime import date as _date
    supplier_grns: dict[int, list] = defaultdict(list)
    supplier_names: dict[int, str] = {}
    for r in grn_rows:
        supplier_grns[r["supplier_id"]].append(r)
        supplier_names[r["supplier_id"]] = r["supplier_name"]

    def _bucket(age: int) -> str:
        if age <= 0:  return "current"
        if age <= 30: return "1_30"
        if age <= 60: return "31_60"
        if age <= 90: return "61_90"
        return "90_plus"

    rows = []
    totals = {k: Decimal("0.00") for k in ["current", "1_30", "31_60", "61_90", "90_plus", "total"]}

    for sup_id, grns in supplier_grns.items():
        remaining_credit = payments_by_supplier.get(sup_id, Decimal("0.00"))
        buckets = {k: Decimal("0.00") for k in ["current", "1_30", "31_60", "61_90", "90_plus"]}
        total = Decimal("0.00")

        for grn in sorted(grns, key=lambda g: g["invoice_date"]):
            amt = _q(grn["invoice_amount"])
            if amt <= 0:
                continue
            # Apply payment credits FIFO
            applied = min(amt, remaining_credit)
            remaining_credit = _q(remaining_credit - applied)
            outstanding = _q(amt - applied)
            if outstanding <= 0:
                continue
            invoice_date = grn["invoice_date"]
            if isinstance(invoice_date, str):
                from datetime import date as _date
                invoice_date = _date.fromisoformat(invoice_date)
            age = (today - invoice_date).days
            buckets[_bucket(age)] += outstanding
            total += outstanding

        total = _q(total)
        if total <= 0:
            continue
        for k in buckets:
            buckets[k] = _q(buckets[k])
            totals[k] += buckets[k]
        totals["total"] += total
        rows.append({
            "supplier_id":   sup_id,
            "supplier_name": supplier_names[sup_id],
            **{k: float(v) for k, v in buckets.items()},
            "total": float(total),
        })

    return {"rows": rows, "totals": {k: float(_q(v)) for k, v in totals.items()}}

    return {"rows": rows, "totals": {k: float(_q(v)) for k, v in totals.items()}}


def get_ar_aging(db: Session, store_id: int) -> dict:
    from sqlalchemy import text
    from collections import defaultdict
    today = business_date()

    # ── Single query: outstanding credit-sale transactions per customer ────────
    txn_sql = text("""
        SELECT
            c.id         AS customer_id,
            c.name       AS customer_name,
            t.id         AS txn_id,
            COALESCE(t.total, 0) AS invoice_amount,
            COALESCE(DATE(t.completed_at), DATE(t.created_at)) AS invoice_date
        FROM customers c
        JOIN transactions t
          ON t.customer_id = c.id
          AND t.store_id = :store_id
          AND t.payment_method = 'credit'
          AND t.status = 'completed'
        WHERE c.store_id = :store_id
        ORDER BY c.id, invoice_date
    """)

    pay_sql = text("""
        SELECT
            customer_id,
            SUM(COALESCE(amount, 0)) AS total_paid
        FROM customer_payments
        WHERE store_id = :store_id
        GROUP BY customer_id
    """)

    txn_rows = db.execute(txn_sql, {"store_id": store_id}).mappings().all()
    pay_rows = db.execute(pay_sql, {"store_id": store_id}).mappings().all()

    payments_by_customer: dict[int, Decimal] = {
        r["customer_id"]: _q(r["total_paid"]) for r in pay_rows
    }

    customer_txns: dict[int, list] = defaultdict(list)
    customer_names: dict[int, str] = {}
    for r in txn_rows:
        customer_txns[r["customer_id"]].append(r)
        customer_names[r["customer_id"]] = r["customer_name"]

    def _bucket(age: int) -> str:
        if age <= 0:  return "current"
        if age <= 30: return "1_30"
        if age <= 60: return "31_60"
        if age <= 90: return "61_90"
        return "90_plus"

    rows = []
    totals = {k: Decimal("0.00") for k in ["current", "1_30", "31_60", "61_90", "90_plus", "total"]}

    for cust_id, txns in customer_txns.items():
        remaining_credit = payments_by_customer.get(cust_id, Decimal("0.00"))
        buckets = {k: Decimal("0.00") for k in ["current", "1_30", "31_60", "61_90", "90_plus"]}
        total = Decimal("0.00")

        for txn in sorted(txns, key=lambda t: t["invoice_date"]):
            amt = _q(txn["invoice_amount"])
            if amt <= 0:
                continue
            applied = min(amt, remaining_credit)
            remaining_credit = _q(remaining_credit - applied)
            outstanding = _q(amt - applied)
            if outstanding <= 0:
                continue
            invoice_date = txn["invoice_date"]
            if isinstance(invoice_date, str):
                from datetime import date as _date
                invoice_date = _date.fromisoformat(invoice_date)
            age = (today - invoice_date).days
            buckets[_bucket(age)] += outstanding
            total += outstanding

        total = _q(total)
        if total <= 0:
            continue
        for k in buckets:
            buckets[k] = _q(buckets[k])
            totals[k] += buckets[k]
        totals["total"] += total
        rows.append({
            "customer_id":   cust_id,
            "customer_name": customer_names[cust_id],
            **{k: float(v) for k, v in buckets.items()},
            "total": float(total),
        })

    return {"rows": rows, "totals": {k: float(_q(v)) for k, v in totals.items()}}


def get_supplier_statement(db: Session, store_id: int, supplier_id: int) -> dict:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.store_id == store_id).first()
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    rows = []
    running = Decimal('0.00')
    invoices = [
        ((g.posted_at.date() if g.posted_at else g.received_date), 'grn', g.grn_number, _q(g.total_received_cost or 0), Decimal('0.00'))
        for g in db.query(GoodsReceivedNote).filter(
            GoodsReceivedNote.store_id == store_id,
            GoodsReceivedNote.supplier_id == supplier_id,
            GoodsReceivedNote.status == GRNStatus.POSTED,
        ).all()
    ]
    pays = [
        (p.payment_date, 'payment', p.payment_number, Decimal('0.00'), _q(p.amount or 0))
        for p in db.query(SupplierPayment).filter(
            SupplierPayment.store_id == store_id,
            SupplierPayment.supplier_id == supplier_id,
            SupplierPayment.is_void == False,
        ).all()
    ]
    for dt, typ, ref, debit, credit in sorted(invoices + pays, key=lambda x: (x[0], x[2])):
        running = _q(running + debit - credit)
        rows.append({"date": str(dt), "type": typ, "reference": ref, "debit": float(debit), "credit": float(credit), "running_balance": float(running)})
    return {"supplier_id": supplier.id, "supplier_name": supplier.name, "rows": rows, "balance": float(_q(running))}


def get_customer_statement(db: Session, store_id: int, customer_id: int) -> dict:
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == store_id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")
    rows = []
    running = Decimal('0.00')
    wallet_running = Decimal('0.00')
    entries = []

    txns = db.query(Transaction).filter(
        Transaction.store_id == store_id,
        Transaction.customer_id == customer_id,
        Transaction.payment_method == PaymentMethod.CREDIT,
        Transaction.status == TransactionStatus.COMPLETED,
    ).all()
    for t in txns:
        entries.append({
            "date": t.completed_at.date() if t.completed_at else t.created_at.date(),
            "type": 'credit_sale',
            "reference": t.txn_number,
            "debit": _q(t.total),
            "credit": Decimal('0.00'),
            "wallet_delta": Decimal('0.00'),
        })

    payments = db.query(CustomerPayment).filter(
        CustomerPayment.store_id == store_id,
        CustomerPayment.customer_id == customer_id,
    ).all()
    for p in payments:
        p_date = p.payment_date.date() if hasattr(p.payment_date, 'date') else p.payment_date
        entries.append({
            "date": p_date,
            "type": 'payment',
            "reference": p.payment_number,
            "debit": Decimal('0.00'),
            "credit": _q(p.amount or 0),
            "wallet_delta": Decimal('0.00'),
        })

    # STORE_CREDIT usage: customer spent their wallet on goods
    wallet_usage_txns = db.query(Transaction).filter(
        Transaction.store_id    == store_id,
        Transaction.customer_id == customer_id,
        Transaction.payment_method == PaymentMethod.STORE_CREDIT,
        Transaction.status      == TransactionStatus.COMPLETED,
    ).all()
    for t in wallet_usage_txns:
        t_date = t.completed_at.date() if t.completed_at else t.created_at.date()
        entries.append({
            "date":         t_date,
            "type":         "wallet_usage",
            "reference":    t.txn_number,
            "debit":        Decimal("0.00"),
            "credit":       Decimal("0.00"),
            "wallet_delta": -_q(t.total),   # negative: wallet balance decreases
        })

    wallet_returns = db.query(ReturnTransaction).filter(
        ReturnTransaction.store_id == store_id,
        ReturnTransaction.status == ReturnStatus.COMPLETED,
        ReturnTransaction.refund_method == RefundMethod.STORE_CREDIT,
    ).all()
    for ret in wallet_returns:
        original_txn = db.query(Transaction).filter(
            Transaction.id == ret.original_txn_id,
            Transaction.customer_id == customer_id,
        ).first()
        if not original_txn:
            continue
        ret_date = ret.completed_at.date() if ret.completed_at else ret.created_at.date()
        entries.append({
            "date": ret_date,
            "type": 'store_credit',
            "reference": ret.return_number,
            "debit": Decimal('0.00'),
            "credit": Decimal('0.00'),
            "wallet_delta": _q(ret.refund_amount or 0),
        })

    for entry in sorted(entries, key=lambda x: (x["date"], x["reference"], x["type"])):
        running = _q(running + entry["debit"] - entry["credit"])
        wallet_running = _q(wallet_running + entry["wallet_delta"])
        rows.append({
            "date": str(entry["date"]),
            "type": entry["type"],
            "reference": entry["reference"],
            "debit": float(entry["debit"]),
            "credit": float(entry["credit"]),
            "wallet_delta": float(entry["wallet_delta"]),
            "wallet_running_balance": float(wallet_running),
            "running_balance": float(running),
        })

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "store_credit_balance": float(_q(customer.store_credit_balance or 0)),
        "rows": rows,
        "balance": float(_q(running)),
    }


def get_consolidated_pl(db: Session, store_ids: list[int] | None = None, date_from=None, date_to=None) -> dict:
    if not store_ids:
        store_ids = [sid for (sid,) in db.query(Transaction.store_id).distinct().all()]
    stores = []
    total = {"revenue": Decimal('0.00'), "cogs": Decimal('0.00'), "gross_profit": Decimal('0.00'), "expenses": Decimal('0.00'), "net_profit": Decimal('0.00')}
    for sid in store_ids:
        pl = get_pl(db, sid, date_from, date_to)
        stores.append({"store_id": sid, **{k: pl[k] for k in ['revenue','cogs','gross_profit','expenses','net_profit']}})
        for k in total:
            total[k] += _q(pl.get(k, 0))
    return {"stores": stores, **{k: float(v) for k,v in total.items()}}


def get_branch_comparison(db: Session, store_ids: list[int] | None = None, date_from=None, date_to=None) -> dict:
    data = get_consolidated_pl(db, store_ids, date_from, date_to)
    return {"rows": data['stores']}
