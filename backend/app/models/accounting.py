"""
Accounting models — double-entry bookkeeping engine for Smartlynx.

Architecture:
  Account        — chart of accounts (one set per store, seeded with Kenyan defaults)
  JournalEntry   — one balanced financial event (sale, purchase receipt, void, manual)
  JournalLine    — individual debit/credit lines on an entry

Double-entry rules enforced at the service layer:
  SUM(debit lines) == SUM(credit lines) for every JournalEntry.
  Normal balance:
    ASSET / EXPENSE / COGS → increases with DEBIT
    LIABILITY / EQUITY / REVENUE → increases with CREDIT

Kenyan SMB default chart of accounts (seeded per store on registration):

  ASSETS
    1000  Cash in Hand
    1010  M-PESA Float
    1020  Bank Account
    1100  Accounts Receivable
    1200  Inventory / Stock
    1300  Prepaid Expenses

  LIABILITIES
    2000  Accounts Payable
    2100  VAT Payable
    2200  Credit Sales Payable

  EQUITY
    3000  Owner's Capital
    3100  Retained Earnings

  REVENUE
    4000  Sales Revenue
    4100  Other Income

  COST OF GOODS SOLD
    5000  Cost of Goods Sold

  EXPENSES
    6000  Salaries & Wages
    6100  Rent
    6200  Utilities
    6300  Transport & Delivery
    6400  Marketing & Advertising
    6500  Bank Charges
    6600  Miscellaneous Expenses
"""

import enum
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean,
    DateTime, Date, Text, ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class AccountType(str, enum.Enum):
    ASSET     = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY    = "EQUITY"
    REVENUE   = "REVENUE"
    COGS      = "COGS"       # Cost of Goods Sold — treated separately for Gross Profit
    EXPENSE   = "EXPENSE"


class NormalBalance(str, enum.Enum):
    DEBIT  = "debit"
    CREDIT = "credit"


# Normal balance by account type — used by the reporting engine
NORMAL_BALANCE_MAP: dict[AccountType, NormalBalance] = {
    AccountType.ASSET:     NormalBalance.DEBIT,
    AccountType.EXPENSE:   NormalBalance.DEBIT,
    AccountType.COGS:      NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY:    NormalBalance.CREDIT,
    AccountType.REVENUE:   NormalBalance.CREDIT,
}


# ── Account ───────────────────────────────────────────────────────────────────

class Account(Base):
    """
    One row per account in the chart of accounts.
    Scoped to a store — store A's accounts are invisible to store B.
    """
    __tablename__ = "accounts"

    id             = Column(Integer, primary_key=True, index=True)
    store_id       = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)

    code           = Column(String(20),  nullable=False)
    # e.g. "1000", "4000-SALES" — unique per store (enforced by migration index)

    name           = Column(String(120), nullable=False)
    account_type   = Column(String(20),  nullable=False)  # AccountType value
    sub_type       = Column(String(40),  nullable=True)
    # e.g. "current_asset", "accounts_payable", "cost_of_goods_sold"

    description    = Column(Text,        nullable=True)
    normal_balance = Column(String(6),   nullable=False, default="debit")
    # "debit" | "credit"

    is_active      = Column(Boolean, default=True,  nullable=False)
    is_system      = Column(Boolean, default=False, nullable=False)
    # system=True accounts are auto-seeded and cannot be deleted via UI

    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    journal_lines  = relationship("JournalLine", back_populates="account")

    def __repr__(self):
        return f"<Account {self.code} {self.name} ({self.account_type})>"

    @property
    def type_enum(self) -> AccountType:
        return AccountType(self.account_type)

    @property
    def normal_balance_enum(self) -> NormalBalance:
        return NormalBalance(self.normal_balance)


# ── JournalEntry ──────────────────────────────────────────────────────────────

class JournalEntry(Base):
    """
    One balanced journal entry per financial event.

    ref_type / ref_id links back to the source:
      "transaction" / "TXN-XXXXXXXX"  — a completed sale
      "grn"         / "GRN-XXXXXXXX"  — a posted goods receipt
      "void"        / "TXN-XXXXXXXX"  — reversal of a sale
      "manual"      / free text       — accountant adjustment

    Invariant: SUM(lines.debit) == SUM(lines.credit)
    Enforced in AccountingService.post_entry().
    """
    __tablename__ = "journal_entries"

    id          = Column(Integer, primary_key=True, index=True)
    store_id    = Column(Integer, ForeignKey("stores.id"),    nullable=False, index=True)

    ref_type    = Column(String(30),  nullable=False)
    ref_id      = Column(String(50),  nullable=False)
    description = Column(String(250), nullable=True)
    entry_date  = Column(Date,        nullable=False)

    is_void     = Column(Boolean, default=False, nullable=False)
    void_reason = Column(Text,    nullable=True)

    posted_by   = Column(Integer, ForeignKey("employees.id"), nullable=True)
    # NULL = system-posted (auto from transaction / GRN)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    lines       = relationship(
        "JournalLine",
        back_populates="entry",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<JournalEntry {self.ref_type}:{self.ref_id} {self.entry_date}>"

    @property
    def total_debits(self) -> Decimal:
        return sum(line.debit for line in self.lines)

    @property
    def total_credits(self) -> Decimal:
        return sum(line.credit for line in self.lines)

    @property
    def is_balanced(self) -> bool:
        return self.total_debits == self.total_credits


# ── JournalLine ───────────────────────────────────────────────────────────────

class JournalLine(Base):
    """
    One debit or credit line on a journal entry.
    A line has either a debit OR a credit (the other is 0.00).
    """
    __tablename__ = "journal_lines"

    id         = Column(Integer, primary_key=True, index=True)
    entry_id   = Column(Integer, ForeignKey("journal_entries.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"),        nullable=False, index=True)

    debit      = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    credit     = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    memo       = Column(String(200), nullable=True)

    # Relationships
    entry      = relationship("JournalEntry", back_populates="lines")
    account    = relationship("Account",      back_populates="journal_lines")

    def __repr__(self):
        side = f"DR {self.debit}" if self.debit else f"CR {self.credit}"
        return f"<JournalLine {side} → account_id={self.account_id}>"


# ── Default chart of accounts seed data ──────────────────────────────────────
# Used by AccountingService.seed_chart_of_accounts(store_id)

DEFAULT_ACCOUNTS = [
    # code   name                          type         sub_type               normal   system
    ("1000", "Cash in Hand",               "ASSET",     "current_asset",       "debit",  True),
    ("1010", "M-PESA Float",               "ASSET",     "current_asset",       "debit",  True),
    ("1020", "Bank Account",               "ASSET",     "current_asset",       "debit",  True),
    ("1100", "Accounts Receivable",        "ASSET",     "current_asset",       "debit",  True),
    ("1200", "Inventory / Stock",          "ASSET",     "current_asset",       "debit",  True),
    ("1300", "Prepaid Expenses",           "ASSET",     "current_asset",       "debit",  False),
    ("1030", "Petty Cash",                  "ASSET",     "current_asset",       "debit",  False),
    ("1040", "Till Float",                  "ASSET",     "current_asset",       "debit",  False),
    ("1050", "Bank Clearing",               "ASSET",     "current_asset",       "debit",  False),

    ("2000", "Accounts Payable",           "LIABILITY", "accounts_payable",    "credit", True),
    ("2100", "VAT Payable",                "LIABILITY", "tax_payable",         "credit", True),
    ("2200", "Credit Sales Payable",       "LIABILITY", "current_liability",   "credit", False),
    ("2300", "Cash Over / Short",          "EXPENSE",   "operating_expense",    "debit",  False),
    ("1400", "Store Credit Liability",     "LIABILITY", "current_liability",   "credit", False),

    ("3000", "Owner's Capital",            "EQUITY",    "owners_equity",       "credit", True),
    ("3100", "Retained Earnings",          "EQUITY",    "retained_earnings",   "credit", True),

    ("4000", "Sales Revenue",              "REVENUE",   "operating_revenue",   "credit", True),
    ("4100", "Other Income",               "REVENUE",   "other_income",        "credit", False),

    ("5000", "Cost of Goods Sold",         "COGS",      "cost_of_goods_sold",  "debit",  True),

    ("6000", "Salaries & Wages",           "EXPENSE",   "payroll",             "debit",  False),
    ("6100", "Rent",                       "EXPENSE",   "occupancy",           "debit",  False),
    ("6200", "Utilities",                  "EXPENSE",   "occupancy",           "debit",  False),
    ("6300", "Transport & Delivery",       "EXPENSE",   "operations",          "debit",  False),
    ("6400", "Marketing & Advertising",    "EXPENSE",   "marketing",           "debit",  False),
    ("6500", "Bank Charges",               "EXPENSE",   "financial",           "debit",  False),
    ("6600", "Miscellaneous Expenses",     "EXPENSE",   "general",             "debit",  False),
    ("6700", "Shrinkage / Stock Loss",     "EXPENSE",   "inventory_loss",      "debit",  False),
    ("6800", "Damages / Expiry Loss",      "EXPENSE",   "inventory_loss",      "debit",  False),
    ("6900", "General Operating Expense",  "EXPENSE",   "general",             "debit",  False),
]
