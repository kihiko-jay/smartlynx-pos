from alembic import op
import sqlalchemy as sa
revision="0026_supplier_payments"
down_revision="0025_accounting_chart"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("supplier_payments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False), sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False), sa.Column("payment_number", sa.String(30), nullable=False), sa.Column("payment_date", sa.Date(), nullable=False), sa.Column("amount", sa.Numeric(12,2), nullable=False), sa.Column("payment_method", sa.String(20), nullable=False), sa.Column("reference", sa.String(100), nullable=True), sa.Column("notes", sa.Text(), nullable=True), sa.Column("created_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("is_void", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("void_reason", sa.Text(), nullable=True), sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True), sa.Column("voided_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True))
    op.create_index("ix_supplier_payments_payment_number", "supplier_payments", ["payment_number"], unique=True)
    op.create_index("ix_supplier_payments_store_supplier", "supplier_payments", ["store_id", "supplier_id"], unique=False)
def downgrade():
    op.drop_index("ix_supplier_payments_store_supplier", table_name="supplier_payments")
    op.drop_index("ix_supplier_payments_payment_number", table_name="supplier_payments")
    op.drop_table("supplier_payments")
