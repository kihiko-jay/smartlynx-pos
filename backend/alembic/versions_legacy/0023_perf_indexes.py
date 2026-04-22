"""0023 — performance indexes for reporting and returns query paths

Revision ID: 0023_perf_indexes
Revises: 0022_returns
Create Date: 2025-04-22

Adds composite indexes on the three hottest query patterns:
  1. journal_entries(store_id, entry_date)     — all accounting report queries
  2. journal_entries(store_id, ref_type, is_void) — journal list filters
  3. return_transactions(store_id, status, created_at) — returns list view
  4. transactions(store_id, status, completed_at)  — Z-tape / reporting truth
  5. transaction_items(transaction_id, product_id) — COGS aggregation
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_perf_indexes"
down_revision = "0022_returns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── journal_entries ────────────────────────────────────────────────────────
    op.create_index(
        "idx_je_store_date",
        "journal_entries",
        ["store_id", "entry_date"],
        unique=False,
        postgresql_where=sa.text("is_void = false"),
    )
    op.create_index(
        "idx_je_store_reftype_void",
        "journal_entries",
        ["store_id", "ref_type", "is_void"],
        unique=False,
    )
    op.create_index(
        "idx_je_store_refid",
        "journal_entries",
        ["store_id", "ref_id"],
        unique=False,
    )

    # ── journal_lines ──────────────────────────────────────────────────────────
    op.create_index(
        "idx_jl_account_entry",
        "journal_lines",
        ["account_id", "entry_id"],
        unique=False,
    )

    # ── return_transactions ────────────────────────────────────────────────────
    op.create_index(
        "idx_ret_store_status_created",
        "return_transactions",
        ["store_id", "status", "created_at"],
        unique=False,
    )

    # ── transactions ───────────────────────────────────────────────────────────
    op.create_index(
        "idx_txn_store_status_completed",
        "transactions",
        ["store_id", "status", "completed_at"],
        unique=False,
    )

    # ── transaction_items ──────────────────────────────────────────────────────
    op.create_index(
        "idx_ti_txn_product",
        "transaction_items",
        ["transaction_id", "product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_ti_txn_product",         table_name="transaction_items")
    op.drop_index("idx_txn_store_status_completed", table_name="transactions")
    op.drop_index("idx_ret_store_status_created", table_name="return_transactions")
    op.drop_index("idx_jl_account_entry",        table_name="journal_lines")
    op.drop_index("idx_je_store_refid",          table_name="journal_entries")
    op.drop_index("idx_je_store_reftype_void",   table_name="journal_entries")
    op.drop_index("idx_je_store_date",           table_name="journal_entries")
