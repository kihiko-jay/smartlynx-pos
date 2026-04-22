"""Initial bootstrap schema for fresh SmartLynX installs.

Revision ID: 1000
Revises:
Create Date: 2026-04-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

from app.database import Base
import app.models  # noqa: F401


revision = "1000"
down_revision = None
branch_labels = ("bootstrap",)
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Bootstrap creates the schema in one pass from the current model snapshot.
    # This is the fresh-install path; legacy upgrades continue via versions_legacy.
    for table in Base.metadata.sorted_tables:
        table.create(bind=bind, checkfirst=True)

    # Critical operational indexes/guards expected in production.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_txn_mpesa_ref
        ON transactions (mpesa_ref)
        WHERE mpesa_ref IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_txn_sync_pending
        ON transactions (created_at ASC)
        WHERE sync_status IN ('PENDING', 'FAILED') AND status = 'COMPLETED'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_txn_etims_pending
        ON transactions (created_at ASC)
        WHERE etims_synced = FALSE AND status = 'COMPLETED'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_prod_active_sku
        ON products (sku)
        WHERE is_active = TRUE
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_txn_etims_invoice
        ON transactions (etims_invoice_no)
        WHERE etims_invoice_no IS NOT NULL
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        table.drop(bind=bind, checkfirst=True)
