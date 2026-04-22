"""Add registration and password reset support

Revision ID: 0014_registration_system
Revises:     0013_sync_log_store_id
Create Date: 2026-04-07

Rationale:
    Adds self-service store registration and password reset functionality.
    
    New tables:
    - password_reset_tokens: Secure, one-time-use password reset tokens
    - store_invitations: Track employee invitations (optional)
    
    Modified tables:
    - employees: Add last_login_at, password_changed_at, is_password_reset_required
"""

from alembic import op
import sqlalchemy as sa


revision      = "0014_registration_system"
down_revision = "0013_sync_log_store_id"
branch_labels = None
depends_on    = None


def upgrade():
    # Create password_reset_tokens table
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), default=False, nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_password_reset_tokens_employee_id', 'password_reset_tokens', ['employee_id'])
    op.create_index('ix_password_reset_tokens_token_hash', 'password_reset_tokens', ['token_hash'])
    op.create_index('ix_password_reset_tokens_is_used', 'password_reset_tokens', ['is_used'])
    op.create_index('ix_password_reset_tokens_expires_at', 'password_reset_tokens', ['expires_at'])

    # Create store_invitations table (optional, for tracking)
    op.create_table(
        'store_invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(200), nullable=False),
        sa.Column('invited_by', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_accepted', sa.Boolean(), default=False, nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['employees.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_store_invitations_store_id', 'store_invitations', ['store_id'])
    op.create_index('ix_store_invitations_email', 'store_invitations', ['email'])
    op.create_index('ix_store_invitations_token_hash', 'store_invitations', ['token_hash'])
    op.create_index('ix_store_invitations_is_accepted', 'store_invitations', ['is_accepted'])

    # Add columns to employees table
    op.add_column('employees', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('employees', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('employees', sa.Column('is_password_reset_required', sa.Boolean(), nullable=True))
    
    # Set default value for existing rows
    op.execute("UPDATE employees SET is_password_reset_required = FALSE WHERE is_password_reset_required IS NULL")
    
    # Make the column NOT NULL
    op.alter_column('employees', 'is_password_reset_required', nullable=False, existing_type=sa.Boolean())


def downgrade():
    # Drop new tables
    op.drop_table('store_invitations')
    op.drop_table('password_reset_tokens')

    # Drop new columns
    op.drop_column('employees', 'is_password_reset_required')
    op.drop_column('employees', 'password_changed_at')
    op.drop_column('employees', 'last_login_at')
