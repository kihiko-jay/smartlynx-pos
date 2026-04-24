"""Add payment method count columns to cash_sessions

Revision ID: 0033_add_payment_method_counts
Revises: 0032_cashier_open_session_unique
Create Date: 2026-04-24 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0033_add_payment_method_counts'
down_revision = '0032_cashier_open_session_unique'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns for payment method counts
    op.add_column('cash_sessions', sa.Column('counted_mpesa', sa.Numeric(12, 2), nullable=True, default=0))
    op.add_column('cash_sessions', sa.Column('counted_card', sa.Numeric(12, 2), nullable=True, default=0))
    op.add_column('cash_sessions', sa.Column('counted_credit', sa.Numeric(12, 2), nullable=True, default=0))
    op.add_column('cash_sessions', sa.Column('counted_store_credit', sa.Numeric(12, 2), nullable=True, default=0))
    op.add_column('cash_sessions', sa.Column('total_counted', sa.Numeric(12, 2), nullable=True))


def downgrade():
    # Remove the added columns
    op.drop_column('cash_sessions', 'total_counted')
    op.drop_column('cash_sessions', 'counted_store_credit')
    op.drop_column('cash_sessions', 'counted_credit')
    op.drop_column('cash_sessions', 'counted_card')
    op.drop_column('cash_sessions', 'counted_mpesa')