from alembic import op
import sqlalchemy as sa
revision="0028_cash_sessions"
down_revision="0027_expense_vouchers"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("cash_sessions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False), sa.Column("cashier_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("terminal_id", sa.String(50), nullable=True), sa.Column("session_number", sa.String(30), nullable=False), sa.Column("opening_float", sa.Numeric(12,2), nullable=False, server_default="0.00"), sa.Column("expected_cash", sa.Numeric(12,2), nullable=False, server_default="0.00"), sa.Column("counted_cash", sa.Numeric(12,2), nullable=True), sa.Column("variance", sa.Numeric(12,2), nullable=True), sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("status", sa.String(20), nullable=False, server_default="open"), sa.Column("opened_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True), sa.Column("closed_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True), sa.Column("notes", sa.Text(), nullable=True))
    op.create_index("ix_cash_sessions_session_number", "cash_sessions", ["session_number"], unique=True)
    op.create_table("customer_payments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False), sa.Column("payment_number", sa.String(30), nullable=False), sa.Column("payment_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("amount", sa.Numeric(12,2), nullable=False), sa.Column("payment_method", sa.String(20), nullable=False), sa.Column("reference", sa.String(100), nullable=True), sa.Column("notes", sa.Text(), nullable=True), sa.Column("created_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_customer_payments_payment_number", "customer_payments", ["payment_number"], unique=True)
    op.add_column("transactions", sa.Column("cash_session_id", sa.Integer(), sa.ForeignKey("cash_sessions.id"), nullable=True))
def downgrade():
    op.drop_column("transactions", "cash_session_id")
    op.drop_index("ix_customer_payments_payment_number", table_name="customer_payments")
    op.drop_table("customer_payments")
    op.drop_index("ix_cash_sessions_session_number", table_name="cash_sessions")
    op.drop_table("cash_sessions")
