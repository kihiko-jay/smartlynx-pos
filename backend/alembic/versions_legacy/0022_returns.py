"""Returns & Refunds — DB migration

Revision ID: 0022_returns
Revises:     0021_gap_indexes
Create Date: 2026-04-15

What this migration adds
-------------------------
1.  return_transactions  — one record per return/refund event.
    Links back to the original transaction (immutable FK).
    Tracks status, return reason, refund method, amounts, who approved.

2.  return_items  — one record per line item being returned.
    Links to the original transaction_items row (immutable FK).
    Captures all per-line financial snapshots needed for accounting reversal.
    CHECK: qty_returned > 0  (DB-level guard).
    CHECK: line_total >= 0.

3.  stock_movements.chk_sm_movement_type  — extended to include 'return'.
    The existing check only covers sale|purchase|adjustment|write_off|
    void_restore|sync|opening|mpesa_timeout_restore.  Returns need their own
    movement type for audit and reconciliation.

4.  Indexes
    idx_ret_store_status    (return_transactions: store_id, status)
    idx_ret_original_txn    (return_transactions: original_txn_id)
    idx_ri_return_txn       (return_items: return_txn_id)
    idx_ri_orig_item        (return_items: original_txn_item_id)

Constraint update safety
------------------------
PostgreSQL requires DROP + recreate to change a CHECK constraint body.
The drop is safe because the new constraint is a SUPERSET of the old one
(adds 'return' and 'mpesa_timeout_restore' which startup code already writes).

Migration is idempotent when run twice — IF NOT EXISTS on table creation,
IF EXISTS on drops.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0022_returns"
down_revision = "0019_sync_idempotency_keys"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── 1. return_transactions ────────────────────────────────────────────────
    op.create_table(
        "return_transactions",
        sa.Column("id",           sa.Integer(),     primary_key=True),
        sa.Column("uuid",         sa.String(36),    nullable=False, unique=True),
        sa.Column("return_number",sa.String(30),    nullable=False, unique=True),

        # Tenant isolation — must match original txn's store_id
        sa.Column("store_id",     sa.Integer(),
                  sa.ForeignKey("stores.id"),        nullable=False),

        # Immutable link to the original completed transaction
        sa.Column("original_txn_id",     sa.Integer(),
                  sa.ForeignKey("transactions.id"),  nullable=False),
        sa.Column("original_txn_number", sa.String(30), nullable=False),
        # ↑ snapshot: survives if the txn row is ever archived

        # Workflow state
        sa.Column("status",        sa.String(15),   nullable=False,
                  server_default="pending"),
        # pending | approved | completed | rejected

        # Return reason
        sa.Column("return_reason", sa.String(30),   nullable=False),
        sa.Column("reason_notes",  sa.Text(),        nullable=True),

        # Refund payment details (set when completed)
        sa.Column("refund_method", sa.String(20),   nullable=True),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("refund_ref",    sa.String(100),  nullable=True),
        # e.g. M-PESA confirmation code for the outgoing refund

        # Granularity flag
        sa.Column("is_partial",    sa.Boolean(),    nullable=False,
                  server_default=sa.false()),

        # Snapshot totals (populated when completed)
        sa.Column("total_refund_gross",  sa.Numeric(12, 2), nullable=True),
        sa.Column("total_vat_reversed",  sa.Numeric(12, 2), nullable=True),
        sa.Column("total_cogs_reversed", sa.Numeric(12, 2), nullable=True),

        # Who did what
        sa.Column("requested_by", sa.Integer(),
                  sa.ForeignKey("employees.id"),     nullable=False),
        sa.Column("approved_by",  sa.Integer(),
                  sa.ForeignKey("employees.id"),     nullable=True),
        sa.Column("approved_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by",  sa.Integer(),
                  sa.ForeignKey("employees.id"),     nullable=True),
        sa.Column("rejected_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_notes", sa.Text(),     nullable=True),

        # Timestamps
        sa.Column("created_at",   sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),

        # Constraints
        sa.CheckConstraint(
            "status IN ('pending','approved','completed','rejected')",
            name="ck_ret_status",
        ),
        sa.CheckConstraint(
            "refund_amount IS NULL OR refund_amount >= 0",
            name="ck_ret_refund_nonneg",
        ),
    )

    op.create_index("idx_ret_store_status",  "return_transactions", ["store_id", "status"])
    op.create_index("idx_ret_original_txn",  "return_transactions", ["original_txn_id"])
    op.create_index("idx_ret_store_created", "return_transactions", ["store_id", "created_at"])

    # ── 2. return_items ───────────────────────────────────────────────────────
    op.create_table(
        "return_items",
        sa.Column("id",                  sa.Integer(), primary_key=True),
        sa.Column("return_txn_id",       sa.Integer(),
                  sa.ForeignKey("return_transactions.id"), nullable=False),

        # Immutable link to the specific line item that is being returned
        sa.Column("original_txn_item_id", sa.Integer(),
                  sa.ForeignKey("transaction_items.id"), nullable=False),
        sa.Column("product_id",           sa.Integer(),
                  sa.ForeignKey("products.id"),           nullable=False),

        # Snapshots — never recalculate from live product data
        sa.Column("product_name",       sa.String(200),    nullable=False),
        sa.Column("sku",                sa.String(50),     nullable=False),
        sa.Column("qty_returned",       sa.Integer(),      nullable=False),
        sa.Column("unit_price_at_sale", sa.Numeric(12, 2), nullable=False),
        sa.Column("cost_price_snap",    sa.Numeric(12, 2), nullable=False,
                  server_default="0.00"),
        # proportion of original discount applied to the returned units
        sa.Column("discount_proportion",sa.Numeric(12, 2), nullable=False,
                  server_default="0.00"),
        sa.Column("vat_amount",         sa.Numeric(12, 2), nullable=False,
                  server_default="0.00"),
        # Total refund value for this line (ex-VAT, after discount)
        sa.Column("line_total",         sa.Numeric(12, 2), nullable=False),

        # Restockability
        sa.Column("is_restorable",  sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("damaged_notes",  sa.Text(),    nullable=True),

        # Constraints
        sa.CheckConstraint("qty_returned > 0",  name="ck_ri_qty_positive"),
        sa.CheckConstraint("line_total >= 0",   name="ck_ri_line_nonneg"),
        sa.CheckConstraint("cost_price_snap >= 0", name="ck_ri_cost_nonneg"),
    )

    op.create_index("idx_ri_return_txn",  "return_items", ["return_txn_id"])
    op.create_index("idx_ri_orig_item",   "return_items", ["original_txn_item_id"])
    op.create_index("idx_ri_product",     "return_items", ["product_id"])

    # ── 3. Extend stock_movements movement_type check ─────────────────────────
    # DROP old constraint then recreate with 'return' added.
    # Both 'return' (from this migration) and 'mpesa_timeout_restore' (already
    # written by startup cleanup code) are included.
    op.execute("""
        ALTER TABLE stock_movements
        DROP CONSTRAINT IF EXISTS chk_sm_movement_type
    """)
    op.execute("""
        ALTER TABLE stock_movements
        ADD CONSTRAINT chk_sm_movement_type
        CHECK (movement_type IN (
            'sale', 'purchase', 'adjustment', 'write_off',
            'void_restore', 'sync', 'opening',
            'mpesa_timeout_restore',
            'return'
        ))
    """)


def downgrade() -> None:
    # Restore original stock_movements check (remove 'return' and 'mpesa_timeout_restore')
    op.execute("""
        ALTER TABLE stock_movements
        DROP CONSTRAINT IF EXISTS chk_sm_movement_type
    """)
    op.execute("""
        ALTER TABLE stock_movements
        ADD CONSTRAINT chk_sm_movement_type
        CHECK (movement_type IN (
            'sale','purchase','adjustment','write_off','void_restore','sync','opening'
        ))
    """)

    # Drop indexes then tables (FK dependency order: items before header)
    op.drop_index("idx_ri_product",    table_name="return_items")
    op.drop_index("idx_ri_orig_item",  table_name="return_items")
    op.drop_index("idx_ri_return_txn", table_name="return_items")
    op.drop_table("return_items")

    op.drop_index("idx_ret_store_created", table_name="return_transactions")
    op.drop_index("idx_ret_original_txn",  table_name="return_transactions")
    op.drop_index("idx_ret_store_status",  table_name="return_transactions")
    op.drop_table("return_transactions")
