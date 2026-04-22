"""Add store_id to sync_log for tenant isolation

Revision ID: 0013_sync_log_store_id
Revises:     0012_procurement
Create Date: 2025-08-01

Rationale:
    Without store_id, /audit/sync-log returns rows from all stores to any
    authenticated manager — a cross-tenant data leak. This migration adds a
    nullable store_id FK so existing rows are preserved and the router can
    filter by current.store_id.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0013_sync_log_store_id"
down_revision = "0012_procurement"
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column(
        "sync_log",
        sa.Column("store_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sync_log_store_id",
        "sync_log", "stores",
        ["store_id"], ["id"],
    )
    op.create_index("ix_sync_log_store_id", "sync_log", ["store_id"])


def downgrade():
    op.drop_index("ix_sync_log_store_id", table_name="sync_log")
    op.drop_constraint("fk_sync_log_store_id", "sync_log", type_="foreignkey")
    op.drop_column("sync_log", "store_id")
