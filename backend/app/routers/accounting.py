"""
Accounting router — financial reports and chart of accounts management.

Access: MANAGER and ADMIN (and PLATFORM_OWNER).
Cashiers and Supervisors cannot view accounting data.

Endpoints:
  GET  /accounting/accounts              — list chart of accounts
  POST /accounting/accounts              — create custom account
  GET  /accounting/trial-balance         — trial balance as of date
  GET  /accounting/pl                    — P&L for date range
  GET  /accounting/balance-sheet         — balance sheet as of date
  GET  /accounting/vat-summary           — VAT reconciliation
  GET  /accounting/ledger/{account_id}   — general ledger for one account
  POST /accounting/seed                  — seed default COA (idempotent)
  GET  /accounting/journal               — list recent journal entries
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_employee, require_manager
from app.models.employee import Employee, Role
from app.models.accounting import Account, JournalEntry, AccountType
from app.services.accounting import (
    seed_chart_of_accounts,
    get_trial_balance,
    get_pl,
    get_balance_sheet,
    get_vat_summary,
    get_account_ledger,
    get_ap_aging, get_ar_aging, get_supplier_statement, get_customer_statement,
    get_consolidated_pl, get_branch_comparison,
)

logger = logging.getLogger("dukapos.accounting")
router = APIRouter(prefix="/accounting", tags=["Accounting"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    code:          str              = Field(..., min_length=1, max_length=20)
    name:          str              = Field(..., min_length=1, max_length=120)
    account_type:  str              = Field(..., description="ASSET|LIABILITY|EQUITY|REVENUE|COGS|EXPENSE")
    sub_type:      Optional[str]    = None
    description:   Optional[str]   = None
    normal_balance: Optional[str]  = Field(None, description="debit|credit — auto-derived if omitted")


class AccountOut(BaseModel):
    id:             int
    code:           str
    name:           str
    account_type:   str
    sub_type:       Optional[str]
    description:    Optional[str]
    normal_balance: str
    is_active:      bool
    is_system:      bool

    class Config:
        from_attributes = True


# ── Helper: resolve store ─────────────────────────────────────────────────────

def _resolve_store_id(current: Employee, store_id_param: Optional[int] = None) -> int:
    if current.role == Role.PLATFORM_OWNER:
        sid = store_id_param or current.store_id
        if not sid:
            raise HTTPException(400, "PLATFORM_OWNER must supply ?store_id=")
        return sid
    return current.store_id


# ── Chart of accounts ─────────────────────────────────────────────────────────

@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    account_type:   Optional[str] = Query(None, description="Filter by type"),
    store_id_param: Optional[int] = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """List all accounts in the chart of accounts for this store."""
    sid = _resolve_store_id(current, store_id_param)
    q = db.query(Account).filter(
        Account.store_id == sid,
        Account.is_active == True,
    )
    if account_type:
        q = q.filter(Account.account_type == account_type.upper())
    return q.order_by(Account.code).all()


@router.post("/accounts", response_model=AccountOut)
def create_account(
    payload: AccountCreate,
    store_id_param: Optional[int] = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """Create a custom account. Code must be unique within the store."""
    sid = _resolve_store_id(current, store_id_param)

    # Validate account type
    valid_types = {t.value for t in AccountType}
    if payload.account_type.upper() not in valid_types:
        raise HTTPException(422, f"account_type must be one of: {valid_types}")

    # Check code uniqueness
    existing = db.query(Account).filter(
        Account.store_id == sid,
        Account.code     == payload.code,
    ).first()
    if existing:
        raise HTTPException(400, f"Account code '{payload.code}' already exists")

    # Derive normal balance from type if not provided
    normal_balance = payload.normal_balance
    if not normal_balance:
        debit_types = {"ASSET", "EXPENSE", "COGS"}
        normal_balance = "debit" if payload.account_type.upper() in debit_types else "credit"

    account = Account(
        store_id       = sid,
        code           = payload.code,
        name           = payload.name,
        account_type   = payload.account_type.upper(),
        sub_type       = payload.sub_type,
        description    = payload.description,
        normal_balance = normal_balance,
        is_system      = False,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/accounts/{account_id}")
def deactivate_account(
    account_id: int,
    store_id_param: Optional[int] = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """Deactivate a custom account (soft delete). System accounts cannot be removed."""
    sid     = _resolve_store_id(current, store_id_param)
    account = db.query(Account).filter(
        Account.id       == account_id,
        Account.store_id == sid,
    ).first()
    if not account:
        raise HTTPException(404, "Account not found")
    if account.is_system:
        raise HTTPException(400, "System accounts cannot be deactivated")

    # Check for existing journal lines
    has_lines = db.query(Account).join(
        Account.journal_lines
    ).filter(Account.id == account_id).first()
    if has_lines:
        raise HTTPException(
            400,
            "Cannot deactivate account with existing transactions. "
            "Consider renaming it instead."
        )

    account.is_active = False
    db.commit()
    return {"message": f"Account '{account.name}' deactivated"}


# ── Seed ──────────────────────────────────────────────────────────────────────

@router.post("/seed")
def seed_accounts(
    store_id_param: Optional[int] = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    Seed the default Kenyan SMB chart of accounts for this store.
    Idempotent — safe to call multiple times.
    """
    sid     = _resolve_store_id(current, store_id_param)
    created = seed_chart_of_accounts(db, sid)
    db.commit()
    return {
        "message": f"Seeded {created} new accounts (skipped existing).",
        "created": created,
    }


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/trial-balance")
def trial_balance(
    as_of_date:     Optional[date] = Query(None, description="Defaults to today"),
    store_id_param: Optional[int]  = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    Trial balance — all account balances as of a given date.
    Confirms the books are balanced: total debits == total credits.
    """
    sid = _resolve_store_id(current, store_id_param)
    return get_trial_balance(db, sid, as_of_date)


@router.get("/pl")
def profit_and_loss(
    date_from:      Optional[date] = Query(None, description="Defaults to first of current month"),
    date_to:        Optional[date] = Query(None, description="Defaults to today"),
    store_id_param: Optional[int]  = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    Profit & Loss statement.
    Revenue - COGS = Gross Profit. Gross Profit - Expenses = Net Profit.
    """
    sid = _resolve_store_id(current, store_id_param)
    return get_pl(db, sid, date_from, date_to)


@router.get("/balance-sheet")
def balance_sheet(
    as_of_date:     Optional[date] = Query(None, description="Defaults to today"),
    store_id_param: Optional[int]  = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    Balance Sheet: Assets = Liabilities + Equity.
    Includes current period retained earnings (net profit).
    """
    sid = _resolve_store_id(current, store_id_param)
    return get_balance_sheet(db, sid, as_of_date)


@router.get("/vat-summary")
def vat_summary(
    date_from:      Optional[date] = Query(None),
    date_to:        Optional[date] = Query(None),
    store_id_param: Optional[int]  = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    VAT reconciliation — output VAT (from sales) vs input VAT (from purchases).
    Net payable = what is owed to KRA for the period.
    """
    sid = _resolve_store_id(current, store_id_param)
    return get_vat_summary(db, sid, date_from, date_to)


@router.get("/ledger/{account_id}")
def account_ledger(
    account_id:     int,
    date_from:      Optional[date] = Query(None),
    date_to:        Optional[date] = Query(None),
    limit:          int            = Query(default=100, le=500),
    store_id_param: Optional[int]  = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    General ledger for a single account — all journal lines affecting it
    with a running balance.
    """
    sid = _resolve_store_id(current, store_id_param)
    return get_account_ledger(db, sid, account_id, date_from, date_to, limit)


@router.get("/journal")
def list_journal_entries(
    date_from:      Optional[date] = Query(None),
    date_to:        Optional[date] = Query(None),
    ref_type:       Optional[str]  = Query(None, description="transaction|grn|manual|void"),
    skip:           int            = 0,
    limit:          int            = Query(default=50, le=200),
    store_id_param: Optional[int]  = Query(None, alias="store_id"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """List journal entries with their lines — for auditing and debugging."""
    sid = _resolve_store_id(current, store_id_param)

    q = db.query(JournalEntry).filter(
        JournalEntry.store_id == sid,
        JournalEntry.is_void  == False,
    )
    if date_from:
        q = q.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.filter(JournalEntry.entry_date <= date_to)
    if ref_type:
        q = q.filter(JournalEntry.ref_type == ref_type)

    entries = q.order_by(
        JournalEntry.entry_date.desc(), JournalEntry.id.desc()
    ).offset(skip).limit(limit).all()

    result = []
    for entry in entries:
        result.append({
            "id":          entry.id,
            "ref_type":    entry.ref_type,
            "ref_id":      entry.ref_id,
            "description": entry.description,
            "entry_date":  str(entry.entry_date),
            "is_balanced": entry.is_balanced,
            "lines": [
                {
                    "account_code": line.account.code,
                    "account_name": line.account.name,
                    "debit":        float(line.debit),
                    "credit":       float(line.credit),
                    "memo":         line.memo,
                }
                for line in entry.lines
            ],
        })
    return result



@router.get("/ap-aging")
def ap_aging(store_id_param: Optional[int] = Query(None, alias="store_id"), db: Session = Depends(get_db), current: Employee = Depends(require_manager)):
    sid = _resolve_store_id(current, store_id_param)
    return get_ap_aging(db, sid)


@router.get("/ar-aging")
def ar_aging(store_id_param: Optional[int] = Query(None, alias="store_id"), db: Session = Depends(get_db), current: Employee = Depends(require_manager)):
    sid = _resolve_store_id(current, store_id_param)
    return get_ar_aging(db, sid)


@router.get("/suppliers/{supplier_id}/statement")
def supplier_statement_accounting(supplier_id: int, store_id_param: Optional[int] = Query(None, alias="store_id"), db: Session = Depends(get_db), current: Employee = Depends(require_manager)):
    sid = _resolve_store_id(current, store_id_param)
    return get_supplier_statement(db, sid, supplier_id)


@router.get("/customers/{customer_id}/statement")
def customer_statement_accounting(customer_id: int, store_id_param: Optional[int] = Query(None, alias="store_id"), db: Session = Depends(get_db), current: Employee = Depends(require_manager)):
    sid = _resolve_store_id(current, store_id_param)
    return get_customer_statement(db, sid, customer_id)


@router.get("/consolidated/pl")
def consolidated_pl(store_ids: Optional[str] = Query(None), date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None), db: Session = Depends(get_db), current: Employee = Depends(require_manager)):
    ids = [int(x) for x in store_ids.split(',')] if store_ids else None
    return get_consolidated_pl(db, ids, date_from, date_to)


@router.get("/branch-comparison")
def branch_comparison(store_ids: Optional[str] = Query(None), date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None), db: Session = Depends(get_db), current: Employee = Depends(require_manager)):
    ids = [int(x) for x in store_ids.split(',')] if store_ids else None
    return get_branch_comparison(db, ids, date_from, date_to)
