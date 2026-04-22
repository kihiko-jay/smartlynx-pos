from alembic import op
import sqlalchemy as sa
revision="0027_expense_vouchers"
down_revision="0026_supplier_payments"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("expense_vouchers", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False), sa.Column("voucher_number", sa.String(30), nullable=False), sa.Column("expense_date", sa.Date(), nullable=False), sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False), sa.Column("amount", sa.Numeric(12,2), nullable=False), sa.Column("payment_method", sa.String(20), nullable=False), sa.Column("payee", sa.String(200), nullable=True), sa.Column("reference", sa.String(100), nullable=True), sa.Column("notes", sa.Text(), nullable=True), sa.Column("created_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("is_void", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("void_reason", sa.Text(), nullable=True), sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True), sa.Column("voided_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True))
    op.create_index("ix_expense_vouchers_voucher_number", "expense_vouchers", ["voucher_number"], unique=True)
def downgrade():
    op.drop_index("ix_expense_vouchers_voucher_number", table_name="expense_vouchers")
    op.drop_table("expense_vouchers")
