"""Fix account 2300 Cash Over/Short from LIABILITY to EXPENSE

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa

revision = '0030_cash_variance_account'
down_revision = '0029_store_credit_method'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE accounts
        SET account_type   = 'EXPENSE',
            sub_type       = 'operating_expense',
            normal_balance = 'debit'
        WHERE code = '2300'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE accounts
        SET account_type   = 'LIABILITY',
            sub_type       = 'current_liability',
            normal_balance = 'credit'
        WHERE code = '2300'
    """)
