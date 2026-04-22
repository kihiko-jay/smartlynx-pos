"""Add per-store M-PESA configuration

Revision ID: 0016_store_mpesa_config
Revises: 0015_accounting
Create Date: 2026-04-07 00:00:00.000000

Each store now can configure its own M-PESA paybill (shortcode), consumer key/secret,
passkey, and callback URL. This enables multi-tenant M-PESA settlements where each store
receives payments to its own paybill.

Changes:
  - mpesa_enabled: Boolean flag to enable/disable M-PESA for this store
  - mpesa_consumer_key: Safaricom Daraja app consumer key (per-store)
  - mpesa_consumer_secret: Safaricom Daraja app consumer secret (per-store)
  - mpesa_shortcode: Business shortcode/Paybill (per-store)
  - mpesa_passkey: M-Pesa Online passkey (per-store)
  - mpesa_callback_url: Store-specific callback URL (per-store)
  - mpesa_till_number: Optional till number (if using Till instead of Paybill)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016_store_mpesa_config"
down_revision = "0015_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add M-PESA per-store configuration columns
    op.add_column(
        "stores",
        sa.Column("mpesa_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "stores",
        sa.Column("mpesa_consumer_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "stores",
        sa.Column("mpesa_consumer_secret", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "stores",
        sa.Column("mpesa_shortcode", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "stores",
        sa.Column("mpesa_passkey", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "stores",
        sa.Column("mpesa_callback_url", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "stores",
        sa.Column("mpesa_till_number", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    # Remove M-PESA columns
    op.drop_column("stores", "mpesa_till_number")
    op.drop_column("stores", "mpesa_callback_url")
    op.drop_column("stores", "mpesa_passkey")
    op.drop_column("stores", "mpesa_shortcode")
    op.drop_column("stores", "mpesa_consumer_secret")
    op.drop_column("stores", "mpesa_consumer_key")
    op.drop_column("stores", "mpesa_enabled")
