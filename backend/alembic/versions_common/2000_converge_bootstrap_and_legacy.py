"""Converge legacy and bootstrap migration branches.

Revision ID: 2000
Revises: 0032, 1000
Create Date: 2026-04-22 00:05:00.000000
"""

from alembic import op


revision = "2000"
down_revision = ("0032_cashier_open_session_unique", "1000")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge point only. Future migrations should depend on 2000.
    pass


def downgrade() -> None:
    pass
