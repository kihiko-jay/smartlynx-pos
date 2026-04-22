"""Add refresh session tracking for secure token rotation.

Revision ID: 0018_refresh_sessions
Revises:     0017_production_hardening
Create Date: 2026-04-10

Adds:
  - refresh_sessions table for persistent server-side refresh-token rotation
  - indexes on employee_id, token_family, and expires_at for cleanup and audits
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_refresh_sessions"
down_revision = "0017_production_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=200), nullable=False),
        sa.Column("token_family", sa.String(length=64), nullable=False),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", name="uq_refresh_sessions_session_id"),
    )
    op.create_index("ix_refresh_sessions_employee_id", "refresh_sessions", ["employee_id"])
    op.create_index("ix_refresh_sessions_token_family", "refresh_sessions", ["token_family"])
    op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_expires_at", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_token_family", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_employee_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
