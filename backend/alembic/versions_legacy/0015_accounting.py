"""Add accounting module — chart of accounts, journal entries, journal lines

Revision ID: 0015_accounting
Revises:     0013_sync_log_store_id
Create Date: 2026-04-08

What this creates:
  accounts          — chart of accounts per store (seeded with Kenyan SMB defaults)
  journal_entries   — one balanced entry per financial event (transaction / GRN / manual)
  journal_lines     — debit/credit lines; SUM(debit) must equal SUM(credit) per entry

Design rules:
  - Every store gets its own isolated chart of accounts (store_id FK on accounts).
  - journal_entries reference a source via (ref_type, ref_id):
      ref_type = 'transaction'  →  ref_id = txn_number
      ref_type = 'grn'          →  ref_id = grn_number
      ref_type = 'manual'       →  ref_id = free text
  - Double-entry integrity is enforced at the application layer (accounting service),
    not in the DB, to avoid constraint complexity across partial flushes.
  - is_system on accounts: True = auto-created defaults, cannot be deleted via UI.
  - posted_by FK to employees is nullable (system-posted entries have NULL).
"""

from alembic import op
import sqlalchemy as sa

revision      = "0015_accounting"
down_revision = "0014_registration_system"
branch_labels = None
depends_on    = None


def upgrade():
    # ── accounts ─────────────────────────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id",          sa.Integer(),     primary_key=True),
        sa.Column("store_id",    sa.Integer(),     sa.ForeignKey("stores.id"),    nullable=False),
        sa.Column("code",        sa.String(20),    nullable=False),
        sa.Column("name",        sa.String(120),   nullable=False),
        sa.Column("account_type", sa.String(20),   nullable=False),
        # ASSET | LIABILITY | EQUITY | REVENUE | EXPENSE | COGS
        sa.Column("sub_type",    sa.String(40),    nullable=True),
        # e.g. "current_asset", "accounts_payable", "cost_of_goods_sold"
        sa.Column("description", sa.Text(),        nullable=True),
        sa.Column("is_active",   sa.Boolean(),     server_default="true", nullable=False),
        sa.Column("is_system",   sa.Boolean(),     server_default="false", nullable=False),
        # system accounts cannot be deleted via the UI
        sa.Column("normal_balance", sa.String(6),  nullable=False, server_default="debit"),
        # "debit" | "credit" — determines how the account grows
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_accounts_store_id",   "accounts", ["store_id"])
    op.create_index("ix_accounts_code_store",  "accounts", ["store_id", "code"], unique=True)
    op.create_index("ix_accounts_type",        "accounts", ["store_id", "account_type"])

    # ── journal_entries ───────────────────────────────────────────────────────
    op.create_table(
        "journal_entries",
        sa.Column("id",          sa.Integer(),     primary_key=True),
        sa.Column("store_id",    sa.Integer(),     sa.ForeignKey("stores.id"),      nullable=False),
        sa.Column("ref_type",    sa.String(30),    nullable=False),   # transaction|grn|manual|void
        sa.Column("ref_id",      sa.String(50),    nullable=False),   # txn_number / grn_number / free
        sa.Column("description", sa.String(250),   nullable=True),
        sa.Column("entry_date",  sa.Date(),        nullable=False),
        sa.Column("is_void",     sa.Boolean(),     server_default="false", nullable=False),
        sa.Column("void_reason", sa.Text(),        nullable=True),
        sa.Column("posted_by",   sa.Integer(),     sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_je_store_id",    "journal_entries", ["store_id"])
    op.create_index("ix_je_ref",         "journal_entries", ["store_id", "ref_type", "ref_id"])
    op.create_index("ix_je_entry_date",  "journal_entries", ["store_id", "entry_date"])
    op.create_index("ix_je_ref_id",      "journal_entries", ["ref_id"])

    # ── journal_lines ─────────────────────────────────────────────────────────
    op.create_table(
        "journal_lines",
        sa.Column("id",         sa.Integer(),      primary_key=True),
        sa.Column("entry_id",   sa.Integer(),      sa.ForeignKey("journal_entries.id"), nullable=False),
        sa.Column("account_id", sa.Integer(),      sa.ForeignKey("accounts.id"),        nullable=False),
        sa.Column("debit",      sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("credit",     sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("memo",       sa.String(200),    nullable=True),
    )
    op.create_index("ix_jl_entry_id",   "journal_lines", ["entry_id"])
    op.create_index("ix_jl_account_id", "journal_lines", ["account_id"])


def downgrade():
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_table("accounts")
