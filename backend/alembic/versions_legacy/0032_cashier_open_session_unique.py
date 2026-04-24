"""Add partial unique index: one open session per cashier

Revision ID: 0032_cashier_open_session_unique
Revises: 0031_stock_movement_types
Create Date: 2026-04-22
"""

from alembic import op

revision = '0032_cashier_open_session_unique'
down_revision = '0031_stock_movement_types'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial unique index: only one 'open' session per cashier at the DB level.
    # Supervisors/managers can still close sessions they don't own (no cashier_id restriction at DB).
    op.execute("""
        CREATE UNIQUE INDEX uix_cashier_one_open_session
        ON cash_sessions (cashier_id)
        WHERE status = 'open'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uix_cashier_one_open_session")
