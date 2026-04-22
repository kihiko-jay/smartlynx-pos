from alembic import op
import sqlalchemy as sa
revision="0024_customer_store_credit"
down_revision="0023_perf_indexes"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("customers", sa.Column("store_credit_balance", sa.Numeric(12,2), nullable=True, server_default="0.00"))
def downgrade():
    op.drop_column("customers", "store_credit_balance")
