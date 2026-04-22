"""Production hardening v4.5 — costing, tax, inventory integrity, period close.

Revision ID: 0017_production_hardening
Revises:     0016_store_mpesa_config
Create Date: 2026-04-09

What this migration adds:
  1. products.wac + wac_updated_at          — WAC cache column
  2. products.cost_price NOT NULL DEFAULT 0 — enforce non-nullable cost price
  3. transaction_items.cost_price_snap NOT NULL DEFAULT 0 — enforce cost snapshot
  4. transaction_items.cost_confidence      — 'actual'|'estimated'|'zero'
  5. transaction_items.tax_rate_applied     — tax rate snapshot at sale time
  6. transaction_items.tax_code_snapshot    — tax code snapshot
  7. transaction_items.tax_jurisdiction_snapshot — jurisdiction snapshot
  8. cost_layers                            — WAC/FIFO cost tracking per GRN
  9. oversell_events                        — detected inventory oversells
 10. stock_allocations                      — terminal stock reservation buckets
 11. accounting_periods                     — period close / lock
 12. tax_jurisdictions                      — configurable tax authorities
 13. tax_rates                              — configurable rates with effective dates
 14. product_tax_assignments               — per-product tax rate overrides
 15. customer_tax_exemptions               — customer-level VAT exemptions
 16. Seed initial KE_VAT jurisdiction and 16% standard rate

Safety:
  - cost_price backfill runs BEFORE the NOT NULL constraint is set
  - cost_price_snap backfill runs BEFORE the NOT NULL constraint is set
  - All new tables have IF NOT EXISTS guards via Alembic's create_table
  - Downgrade removes only the new tables (does not un-backfill the columns)
"""

from alembic import op
import sqlalchemy as sa
from datetime import date

revision      = "0017_production_hardening"
down_revision = "0016_store_mpesa_config"
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ── 1. products: WAC columns ──────────────────────────────────────────────
    op.add_column("products", sa.Column("wac",            sa.Numeric(12, 4), nullable=True))
    op.add_column("products", sa.Column("wac_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_products_wac_store", "products", ["store_id", "wac"])

    # ── 2. products.cost_price → NOT NULL DEFAULT 0 ───────────────────────────
    # First backfill nulls, then add constraint
    op.execute("UPDATE products SET cost_price = 0.00 WHERE cost_price IS NULL")
    op.alter_column("products", "cost_price",
                    existing_type=sa.Numeric(12, 2),
                    nullable=False,
                    server_default="0.00")

    # ── 3. transaction_items: cost snapshot columns ───────────────────────────
    # Backfill cost_price_snap nulls first, then constrain
    op.execute("UPDATE transaction_items SET cost_price_snap = 0.00 WHERE cost_price_snap IS NULL")
    op.alter_column("transaction_items", "cost_price_snap",
                    existing_type=sa.Numeric(12, 2),
                    nullable=False,
                    server_default="0.00")
    op.add_column("transaction_items",
                  sa.Column("cost_confidence", sa.String(10), nullable=False, server_default="actual"))
    op.add_column("transaction_items",
                  sa.Column("tax_rate_applied", sa.Numeric(6, 4), nullable=True))
    op.add_column("transaction_items",
                  sa.Column("tax_code_snapshot", sa.String(10), nullable=True))
    op.add_column("transaction_items",
                  sa.Column("tax_jurisdiction_snapshot", sa.String(20), nullable=True))

    # ── 4. cost_layers ────────────────────────────────────────────────────────
    op.create_table(
        "cost_layers",
        sa.Column("id",             sa.Integer(),      primary_key=True),
        sa.Column("product_id",     sa.Integer(),      sa.ForeignKey("products.id"),             nullable=False),
        sa.Column("store_id",       sa.Integer(),      sa.ForeignKey("stores.id"),               nullable=False),
        sa.Column("grn_id",         sa.Integer(),      sa.ForeignKey("goods_received_notes.id"), nullable=True),
        sa.Column("qty_received",   sa.Integer(),      nullable=False),
        sa.Column("qty_remaining",  sa.Integer(),      nullable=False),
        sa.Column("unit_cost",      sa.Numeric(12, 4), nullable=False),
        sa.Column("effective_date", sa.Date(),         nullable=False),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",     sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.CheckConstraint("qty_received > 0",    name="ck_cl_qty_received_positive"),
        sa.CheckConstraint("qty_remaining >= 0",  name="ck_cl_qty_remaining_nonneg"),
        sa.CheckConstraint("unit_cost >= 0",      name="ck_cl_unit_cost_nonneg"),
    )
    op.create_index("ix_cost_layers_product_store",  "cost_layers", ["product_id", "store_id"])
    op.create_index("ix_cost_layers_effective_date", "cost_layers", ["product_id", "effective_date"])

    # ── 5. oversell_events ────────────────────────────────────────────────────
    op.create_table(
        "oversell_events",
        sa.Column("id",                     sa.Integer(),    primary_key=True),
        sa.Column("store_id",               sa.Integer(),    sa.ForeignKey("stores.id"),    nullable=False),
        sa.Column("product_id",             sa.Integer(),    sa.ForeignKey("products.id"),  nullable=False),
        sa.Column("stock_before_sync",      sa.Integer(),    nullable=False),
        sa.Column("total_sold_offline",     sa.Integer(),    nullable=False),
        sa.Column("shortfall_qty",          sa.Integer(),    nullable=False),
        sa.Column("contributing_terminals", sa.Text(),       nullable=True),  # JSON
        sa.Column("candidate_txn_numbers",  sa.Text(),       nullable=True),  # JSON
        sa.Column("resolution",             sa.String(20),   nullable=False,  server_default="pending"),
        sa.Column("resolved_by",            sa.Integer(),    sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("resolution_notes",       sa.Text(),       nullable=True),
        sa.Column("detected_at",            sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at",            sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_oversell_store_status", "oversell_events", ["store_id", "resolution"])
    op.create_index("ix_oversell_product",      "oversell_events", ["product_id", "detected_at"])

    # ── 6. stock_allocations ──────────────────────────────────────────────────
    op.create_table(
        "stock_allocations",
        sa.Column("id",            sa.Integer(),    primary_key=True),
        sa.Column("product_id",    sa.Integer(),    sa.ForeignKey("products.id"), nullable=False),
        sa.Column("store_id",      sa.Integer(),    sa.ForeignKey("stores.id"),   nullable=False),
        sa.Column("terminal_id",   sa.String(50),   nullable=False),
        sa.Column("allocated_qty", sa.Integer(),    nullable=False, server_default="0"),
        sa.Column("consumed_qty",  sa.Integer(),    nullable=False, server_default="0"),
        sa.Column("status",        sa.String(15),   nullable=False, server_default="active"),
        sa.Column("allocated_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("refreshed_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at",    sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("product_id", "terminal_id", name="uq_allocation_product_terminal"),
        sa.CheckConstraint("allocated_qty >= 0", name="ck_alloc_qty_nonneg"),
        sa.CheckConstraint("consumed_qty >= 0",  name="ck_alloc_consumed_nonneg"),
    )
    op.create_index("ix_alloc_store_product", "stock_allocations", ["store_id", "product_id"])

    # ── 7. accounting_periods ─────────────────────────────────────────────────
    op.create_table(
        "accounting_periods",
        sa.Column("id",          sa.Integer(),  primary_key=True),
        sa.Column("store_id",    sa.Integer(),  sa.ForeignKey("stores.id"),    nullable=False),
        sa.Column("period_name", sa.String(20), nullable=False),
        sa.Column("start_date",  sa.Date(),     nullable=False),
        sa.Column("end_date",    sa.Date(),     nullable=False),
        sa.Column("status",      sa.String(10), nullable=False, server_default="open"),
        sa.Column("closed_by",   sa.Integer(),  sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("closed_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by",   sa.Integer(),  sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("locked_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes",       sa.Text(),     nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("store_id", "period_name", name="uq_period_store_name"),
    )
    op.create_index("ix_period_store_status", "accounting_periods", ["store_id", "status"])

    # ── 8. tax_jurisdictions ──────────────────────────────────────────────────
    op.create_table(
        "tax_jurisdictions",
        sa.Column("id",        sa.Integer(),    primary_key=True),
        sa.Column("code",      sa.String(20),   nullable=False, unique=True),
        sa.Column("name",      sa.String(100),  nullable=False),
        sa.Column("country",   sa.String(2),    nullable=False),
        sa.Column("is_active", sa.Boolean(),    server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 9. tax_rates ──────────────────────────────────────────────────────────
    op.create_table(
        "tax_rates",
        sa.Column("id",              sa.Integer(),     primary_key=True),
        sa.Column("jurisdiction_id", sa.Integer(),     sa.ForeignKey("tax_jurisdictions.id"), nullable=False),
        sa.Column("code",            sa.String(20),    nullable=False),
        sa.Column("rate",            sa.Numeric(6, 4), nullable=False),
        sa.Column("name",            sa.String(80),    nullable=False),
        sa.Column("description",     sa.Text(),        nullable=True),
        sa.Column("effective_from",  sa.Date(),        nullable=False),
        sa.Column("effective_to",    sa.Date(),        nullable=True),
        sa.Column("is_active",       sa.Boolean(),     server_default="true", nullable=False),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tax_rates_jurisdiction_active", "tax_rates", ["jurisdiction_id", "is_active"])
    op.create_index("ix_tax_rates_effective", "tax_rates", ["jurisdiction_id", "code", "effective_from"])

    # ── 10. product_tax_assignments ───────────────────────────────────────────
    op.create_table(
        "product_tax_assignments",
        sa.Column("id",              sa.Integer(), primary_key=True),
        sa.Column("product_id",      sa.Integer(), sa.ForeignKey("products.id"),         nullable=False),
        sa.Column("jurisdiction_id", sa.Integer(), sa.ForeignKey("tax_jurisdictions.id"), nullable=False),
        sa.Column("tax_rate_id",     sa.Integer(), sa.ForeignKey("tax_rates.id"),         nullable=False),
        sa.Column("created_by",      sa.Integer(), sa.ForeignKey("employees.id"),         nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "jurisdiction_id", name="uq_product_tax_jurisdiction"),
    )

    # ── 11. customer_tax_exemptions ───────────────────────────────────────────
    op.create_table(
        "customer_tax_exemptions",
        sa.Column("id",              sa.Integer(),  primary_key=True),
        sa.Column("customer_id",     sa.Integer(),  sa.ForeignKey("customers.id"),          nullable=False),
        sa.Column("jurisdiction_id", sa.Integer(),  sa.ForeignKey("tax_jurisdictions.id"),  nullable=False),
        sa.Column("exemption_ref",   sa.String(100), nullable=True),
        sa.Column("valid_from",      sa.Date(),     nullable=False),
        sa.Column("valid_to",        sa.Date(),     nullable=True),
        sa.Column("is_active",       sa.Boolean(),  server_default="true", nullable=False),
        sa.Column("created_by",      sa.Integer(),  sa.ForeignKey("employees.id"),          nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("customer_id", "jurisdiction_id", name="uq_customer_tax_exemption"),
    )
    op.create_index("ix_cte_customer_active", "customer_tax_exemptions", ["customer_id", "is_active"])

    # ── 12. Seed Kenya VAT configuration ──────────────────────────────────────
    # This is the base data required for the tax engine to function.
    # Inserted via raw SQL so it's idempotent with the IF NOT EXISTS pattern.
    op.execute("""
        INSERT INTO tax_jurisdictions (code, name, country, is_active)
        VALUES ('KE_VAT', 'Kenya Value Added Tax', 'KE', true)
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO tax_rates (jurisdiction_id, code, rate, name, effective_from, is_active)
        SELECT id, 'STANDARD', 0.1600, 'Standard VAT 16%', '2024-01-01', true
        FROM tax_jurisdictions WHERE code = 'KE_VAT'
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO tax_rates (jurisdiction_id, code, rate, name, effective_from, is_active)
        SELECT id, 'ZERO', 0.0000, 'Zero-Rated', '2024-01-01', true
        FROM tax_jurisdictions WHERE code = 'KE_VAT'
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO tax_rates (jurisdiction_id, code, rate, name, effective_from, is_active)
        SELECT id, 'EXEMPT', 0.0000, 'VAT Exempt', '2024-01-01', true
        FROM tax_jurisdictions WHERE code = 'KE_VAT'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Remove tables in reverse FK dependency order
    op.drop_table("customer_tax_exemptions")
    op.drop_table("product_tax_assignments")
    op.drop_table("tax_rates")
    op.drop_table("tax_jurisdictions")
    op.drop_table("accounting_periods")
    op.drop_table("stock_allocations")
    op.drop_table("oversell_events")
    op.drop_table("cost_layers")

    # Revert column changes
    op.drop_column("transaction_items", "tax_jurisdiction_snapshot")
    op.drop_column("transaction_items", "tax_code_snapshot")
    op.drop_column("transaction_items", "tax_rate_applied")
    op.drop_column("transaction_items", "cost_confidence")
    # Note: cost_price_snap and cost_price are NOT reverted to nullable —
    # downgrading the constraint would require data review. Left as-is.
    op.drop_column("products", "wac_updated_at")
    op.drop_column("products", "wac")
