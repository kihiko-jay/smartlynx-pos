"""Add CHECK constraint for stock_movements.movement_type (Phase P0-D)

This migration enforces the canonical list of movement types:
- sale, return, void_restore
- purchase_receive, purchase_receive_damaged, purchase_reject
- mpesa_failed_restore, mpesa_timeout_restore
- adjustment, sync

Revision ID: 0031_stock_movement_types
Revises: 0030
Create Date: 2025-01-01 00:00:00.000000


"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '0031_stock_movement_types'
down_revision = '0030_cash_variance_account'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add CHECK constraint to stock_movements.movement_type
    to enforce canonical values defined in app.core.stock_movements
    """
    
    # Existing databases can contain legacy values like 'purchase'.
    # Keep this as a superset to avoid failing upgrades on valid historic data.
    op.execute(
        "ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS ck_stock_movements_type"
    )
    op.execute(
        "ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS chk_sm_movement_type"
    )
    op.create_check_constraint(
        "ck_stock_movements_type",
        "stock_movements",
        (
            "movement_type IN ("
            "'sale', 'return', 'void_restore', "
            "'purchase', 'purchase_receive', 'purchase_receive_damaged', 'purchase_reject', "
            "'mpesa_failed_restore', 'mpesa_timeout_restore', "
            "'adjustment', 'write_off', 'opening', 'sync'"
            ")"
        ),
    )


def downgrade() -> None:
    """Remove the CHECK constraint."""
    op.drop_constraint("ck_stock_movements_type", "stock_movements")
