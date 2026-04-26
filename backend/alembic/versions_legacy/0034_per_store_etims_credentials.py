"""Add per-store eTIMS credentials to stores table

Revision ID: 0034_per_store_etims
Revises: 0033_add_payment_method_counts
Create Date: 2026-04-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0034_per_store_etims'
down_revision = '0033_add_payment_method_counts'
branch_labels = None
depends_on = None


def upgrade():
    # Add eTIMS per-store configuration columns
    op.add_column('stores', sa.Column('etims_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('stores', sa.Column('etims_pin', sa.String(length=200), nullable=True))
    op.add_column('stores', sa.Column('etims_branch_id', sa.String(length=10), nullable=True))
    op.add_column('stores', sa.Column('etims_device_serial', sa.String(length=200), nullable=True))


def downgrade():
    # Remove the added columns
    op.drop_column('stores', 'etims_device_serial')
    op.drop_column('stores', 'etims_branch_id')
    op.drop_column('stores', 'etims_pin')
    op.drop_column('stores', 'etims_enabled')
