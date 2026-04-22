"""add store_credit payment method

Revision ID: 0029_payment_method_store_credit
Revises: 0028_cash_sessions_customer_pay
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_store_credit_method"
down_revision = "0028_cash_sessions"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'store_credit'")
    # SQLite tests don't require enum alteration because SQLAlchemy emulates enums there.


def downgrade():
    # PostgreSQL enum value removal is not straightforward/safe in-place.
    # Intentionally left as no-op.
    pass
