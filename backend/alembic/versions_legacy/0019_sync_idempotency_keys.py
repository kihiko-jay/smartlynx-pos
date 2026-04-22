"""Add sync idempotency key ledger.

Revision ID: 0019_sync_idempotency_keys
Revises:     0018_refresh_sessions
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_sync_idempotency_keys"
down_revision = "0018_refresh_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "endpoint",
            "store_id",
            "idempotency_key",
            name="uq_sync_idempotency_endpoint_store_key",
        ),
    )
    op.create_index("ix_sync_idempotency_keys_endpoint", "sync_idempotency_keys", ["endpoint"])
    op.create_index("ix_sync_idempotency_keys_store_id", "sync_idempotency_keys", ["store_id"])
    op.create_index("ix_sync_idempotency_keys_idempotency_key", "sync_idempotency_keys", ["idempotency_key"])
    op.create_index("ix_sync_idempotency_keys_created_at", "sync_idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_idempotency_keys_created_at", table_name="sync_idempotency_keys")
    op.drop_index("ix_sync_idempotency_keys_idempotency_key", table_name="sync_idempotency_keys")
    op.drop_index("ix_sync_idempotency_keys_store_id", table_name="sync_idempotency_keys")
    op.drop_index("ix_sync_idempotency_keys_endpoint", table_name="sync_idempotency_keys")
    op.drop_table("sync_idempotency_keys")
