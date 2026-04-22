#!/usr/bin/env python3
"""
import_products.py — Load the Kenyan 1000-product dataset into SmartDukaPOS.

What this script does:
  1. Creates a temporary PostgreSQL schema ("import_staging") and loads the
     SQL file's standalone tables into it — no risk to your live data.
  2. Reads the staged categories, suppliers, and products.
  3. Upserts them into the real DukaPOS tables (categories, suppliers, products,
     stock_movements) scoped to YOUR store_id.
  4. Maps the SQL file's tax_type → DukaPOS vat_exempt + tax_code correctly.
  5. Skips duplicates by SKU (safe to run more than once).
  6. Prints a summary at the end.

Usage:
  1. Copy this file into your backend/ directory.
  2. Make sure your .env is present (or set DATABASE_URL in the environment).
  3. Run:
       cd backend
       python import_products.py --store-id 1
     Replace 1 with your actual store ID.

Options:
  --store-id    INT    Required. The store to import products into.
  --sql-file    PATH   Path to the SQL file (default: ./dukapos_kenyan_ready_1000_items_postgres.sql)
  --dry-run            Print what would be inserted without writing anything.
  --wipe-staging       Drop the staging schema when done (default: True).
"""

import argparse
import os
import sys
import re
from decimal import Decimal
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Import Kenyan 1000-product dataset into DukaPOS.")
parser.add_argument("--store-id",     type=int,  required=True, help="DukaPOS store ID to import into")
parser.add_argument("--sql-file",     type=str,  default="dukapos_kenyan_ready_1000_items_postgres.sql")
parser.add_argument("--dry-run",      action="store_true", help="Show what would be inserted, don't write")
parser.add_argument("--wipe-staging", action="store_true", default=True, help="Drop staging schema after import")
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Database connection — reuses your .env / environment
# ---------------------------------------------------------------------------

from dotenv import load_dotenv
load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set. Make sure backend/.env exists.")
    sys.exit(1)

import psycopg2
import psycopg2.extras

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(sql, params=None):
    cur.execute(sql, params)

def fetchall(sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()

def fetchone(sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()

# ---------------------------------------------------------------------------
# Step 0 — Validate store exists
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"SmartDukaPOS Product Import — store_id={args.store_id}")
print(f"SQL file: {args.sql_file}")
print(f"Dry run:  {args.dry_run}")
print(f"{'='*60}\n")

store = fetchone("SELECT id, name FROM stores WHERE id = %s", (args.store_id,))
if not store:
    print(f"ERROR: Store with id={args.store_id} not found in the database.")
    print("Run: SELECT id, name FROM stores;  to see available stores.")
    conn.close()
    sys.exit(1)

print(f"✓ Target store: [{store['id']}] {store['name']}")

# ---------------------------------------------------------------------------
# Step 1 — Load the SQL file into a staging schema
# ---------------------------------------------------------------------------

print("\n── Step 1: Loading SQL file into staging schema ──")

if not os.path.exists(args.sql_file):
    print(f"ERROR: SQL file not found: {args.sql_file}")
    print("Make sure the file is in the same directory as this script.")
    conn.close()
    sys.exit(1)

with open(args.sql_file, "r", encoding="utf-8") as f:
    raw_sql = f.read()

# The SQL file has DROP TABLE / CREATE TABLE / INSERT statements.
# We redirect them into a staging schema so they don't touch real tables.
# Strategy: wrap everything in a schema namespace by replacing table references.

STAGING = "import_staging"

# Drop and recreate the staging schema for a clean slate
run(f"DROP SCHEMA IF EXISTS {STAGING} CASCADE")
run(f"CREATE SCHEMA {STAGING}")
# Set search_path so the file's CREATE TABLE and INSERT statements land there
run(f"SET search_path TO {STAGING}, public")

# Strip the outer BEGIN/COMMIT — we manage the transaction ourselves
sql_body = raw_sql.strip()
sql_body = re.sub(r'^\s*BEGIN\s*;', '', sql_body, flags=re.IGNORECASE)
sql_body = re.sub(r'\s*COMMIT\s*;\s*$', '', sql_body, flags=re.IGNORECASE)

# Remove the CREATE INDEX and CREATE VIEW statements — not needed in staging
sql_body = re.sub(r'CREATE\s+INDEX\s+\S+.*?;', '', sql_body, flags=re.IGNORECASE|re.DOTALL)
sql_body = re.sub(r'CREATE\s+OR\s+REPLACE\s+VIEW\s+.*?;', '', sql_body, flags=re.IGNORECASE|re.DOTALL)

# Execute the staging SQL (creates tables, inserts data)
try:
    cur.execute(sql_body)
    print(f"  ✓ Staging schema populated")
except Exception as e:
    print(f"  ERROR loading SQL file: {e}")
    conn.rollback()
    conn.close()
    sys.exit(1)

# Count what's staged
staged = {
    "categories": fetchone(f"SELECT COUNT(*) AS n FROM {STAGING}.categories")["n"],
    "suppliers":  fetchone(f"SELECT COUNT(*) AS n FROM {STAGING}.suppliers")["n"],
    "products":   fetchone(f"SELECT COUNT(*) AS n FROM {STAGING}.products")["n"],
}
print(f"  ✓ Staged: {staged['categories']} categories, {staged['suppliers']} suppliers, {staged['products']} products")

# Reset search_path back to public for all subsequent queries
run("SET search_path TO public")

# ---------------------------------------------------------------------------
# Step 2 — Tax type mapping
#
# SQL file uses: tax_type = 'standard' | 'zero_rated' | 'exempt'
# DukaPOS uses:  vat_exempt BOOLEAN + tax_code VARCHAR
#   tax_code 'A' = exempt (no VAT)
#   tax_code 'B' = standard 16% VAT
#   zero_rated    = technically not exempt but 0% — map to vat_exempt=False, tax_code='B' with rate 0
#                   In Kenya zero-rated goods (unga, bread, milk) are VAT registered but at 0%
#                   DukaPOS treats these as vat_exempt=True for POS simplicity (no VAT line)
# ---------------------------------------------------------------------------

TAX_MAP = {
    # staging tax_type → (vat_exempt, tax_code)
    "standard":   (False, "B"),   # 16% VAT
    "zero_rated": (True,  "B"),   # 0% VAT — zero-rated, tracked but not charged
    "exempt":     (True,  "A"),   # Exempt — no VAT at all
}

# ---------------------------------------------------------------------------
# Step 3 — Upsert categories into DukaPOS
# ---------------------------------------------------------------------------

print("\n── Step 2: Importing categories ──")

staged_cats = fetchall(f"SELECT * FROM {STAGING}.categories ORDER BY id")

cat_id_map = {}  # staging category id → DukaPOS category id

for sc in staged_cats:
    # Check if this category already exists for this store
    existing = fetchone(
        "SELECT id FROM categories WHERE store_id = %s AND name = %s",
        (args.store_id, sc["name"])
    )
    if existing:
        cat_id_map[sc["id"]] = existing["id"]
        print(f"  ↳ Category exists: [{existing['id']}] {sc['name']}")
    else:
        if not args.dry_run:
            run(
                "INSERT INTO categories (store_id, name) VALUES (%s, %s) RETURNING id",
                (args.store_id, sc["name"])
            )
            new_id = cur.fetchone()["id"]
        else:
            new_id = f"<new:{sc['name']}>"
        cat_id_map[sc["id"]] = new_id
        print(f"  + Category created: {sc['name']} → id={new_id}")

print(f"  ✓ {len(cat_id_map)} categories mapped")

# ---------------------------------------------------------------------------
# Step 4 — Upsert suppliers into DukaPOS
# ---------------------------------------------------------------------------

print("\n── Step 3: Importing suppliers ──")

staged_sups = fetchall(f"SELECT * FROM {STAGING}.suppliers ORDER BY id")

sup_id_map = {}  # staging supplier id → DukaPOS supplier id

for ss in staged_sups:
    existing = fetchone(
        "SELECT id FROM suppliers WHERE store_id = %s AND name = %s",
        (args.store_id, ss["name"])
    )
    if existing:
        sup_id_map[ss["id"]] = existing["id"]
        print(f"  ↳ Supplier exists: [{existing['id']}] {ss['name']}")
    else:
        if not args.dry_run:
            run(
                """INSERT INTO suppliers (store_id, name, phone, address, is_active)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (args.store_id, ss["name"], ss.get("contact_phone"), ss.get("address"), True)
            )
            new_id = cur.fetchone()["id"]
        else:
            new_id = f"<new:{ss['name']}>"
        sup_id_map[ss["id"]] = new_id
        print(f"  + Supplier created: {ss['name']} → id={new_id}")

print(f"  ✓ {len(sup_id_map)} suppliers mapped")

# ---------------------------------------------------------------------------
# Step 5 — Import products
# ---------------------------------------------------------------------------

print("\n── Step 4: Importing products ──")

# Join with tax_codes in staging to get the tax_type
staged_products = fetchall(f"""
    SELECT
        p.*,
        tc.tax_type,
        tc.rate AS tax_rate
    FROM {STAGING}.products p
    JOIN {STAGING}.tax_codes tc ON tc.id = p.tax_id
    ORDER BY p.id
""")

inserted = 0
skipped  = 0
errors   = 0

for sp in staged_products:
    sku = sp["sku"]

    # Skip if this SKU already exists for this store
    existing = fetchone(
        "SELECT id FROM products WHERE store_id = %s AND sku = %s",
        (args.store_id, sku)
    )
    if existing:
        skipped += 1
        continue

    # Map IDs and tax fields
    duka_cat_id = cat_id_map.get(sp["category_id"])
    duka_sup_id = sup_id_map.get(sp["supplier_id"])
    vat_exempt, tax_code = TAX_MAP.get(sp["tax_type"], (False, "B"))

    # Build a sensible description from pack_size
    description = sp.get("pack_size") or None

    # unit_of_measure → unit
    unit = sp.get("unit_of_measure") or "piece"

    try:
        if not args.dry_run:
            run("""
                INSERT INTO products (
                    store_id, sku, barcode, name, description,
                    category_id, supplier_id,
                    selling_price, cost_price,
                    vat_exempt, tax_code,
                    stock_quantity, reorder_level,
                    unit, is_active
                ) VALUES (
                    %(store_id)s, %(sku)s, %(barcode)s, %(name)s, %(description)s,
                    %(category_id)s, %(supplier_id)s,
                    %(selling_price)s, %(cost_price)s,
                    %(vat_exempt)s, %(tax_code)s,
                    %(stock_quantity)s, %(reorder_level)s,
                    %(unit)s, %(is_active)s
                )
            """, {
                "store_id":      args.store_id,
                "sku":           sku,
                "barcode":       sp.get("barcode"),
                "name":          sp["name"],
                "description":   description,
                "category_id":   duka_cat_id if isinstance(duka_cat_id, int) else None,
                "supplier_id":   duka_sup_id if isinstance(duka_sup_id, int) else None,
                "selling_price": Decimal(str(sp["selling_price"])),
                "cost_price":    Decimal(str(sp["cost_price"])),
                "vat_exempt":    vat_exempt,
                "tax_code":      tax_code,
                "stock_quantity": sp["current_stock"],
                "reorder_level": sp["reorder_level"],
                "unit":          unit,
                "is_active":     sp["is_active"],
            })
        inserted += 1
    except Exception as e:
        print(f"  ✗ Error inserting {sku} ({sp['name']}): {e}")
        errors += 1

print(f"  ✓ Inserted:  {inserted}")
print(f"  ↳ Skipped (already exist): {skipped}")
if errors:
    print(f"  ✗ Errors:   {errors}")

# ---------------------------------------------------------------------------
# Step 6 — Stock movements for opening stock
# ---------------------------------------------------------------------------

print("\n── Step 5: Recording opening stock movements ──")

if not args.dry_run:
    run("""
        INSERT INTO stock_movements (
            product_id, store_id, movement_type,
            qty_delta, qty_before, qty_after,
            ref_id, notes
        )
        SELECT
            p.id,
            p.store_id,
            'adjustment',
            p.stock_quantity,
            0,
            p.stock_quantity,
            'OPENING-IMPORT-2026',
            'Opening stock from Kenyan 1000-product import'
        FROM products p
        WHERE p.store_id = %s
          AND p.sku LIKE ANY(ARRAY[
              'BEV-%%','SNK-%%','HH-%%','PC-%%','HW-%%','EL-%%',
              'BAK-%%','DAI-%%','CER-%%','FP-%%','PHR-%%','BOO-%%'
          ])
          AND p.stock_quantity > 0
          AND NOT EXISTS (
              SELECT 1 FROM stock_movements sm
              WHERE sm.product_id = p.id
                AND sm.ref_id = 'OPENING-IMPORT-2026'
          )
    """, (args.store_id,))
    sm_count = cur.rowcount
    print(f"  ✓ Created {sm_count} stock movement records")
else:
    print(f"  (dry run — no stock movements written)")

# ---------------------------------------------------------------------------
# Step 7 — Cleanup staging schema
# ---------------------------------------------------------------------------

if args.wipe_staging and not args.dry_run:
    run(f"DROP SCHEMA IF EXISTS {STAGING} CASCADE")
    print("\n── Staging schema cleaned up ──")

# ---------------------------------------------------------------------------
# Commit or rollback
# ---------------------------------------------------------------------------

if args.dry_run:
    conn.rollback()
    print("\n⚠ DRY RUN — nothing was committed. Run without --dry-run to apply.")
else:
    conn.commit()
    print("\n✓ All changes committed.")

conn.close()

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"""
{'='*60}
Import complete
{'='*60}
  Store:        [{args.store_id}] {store['name']}
  Products:     {inserted} inserted, {skipped} skipped, {errors} errors
  Categories:   {len(cat_id_map)} mapped
  Suppliers:    {len(sup_id_map)} mapped
{'='*60}

Next steps:
  1. Log into the Back Office → Inventory to verify products appear.
  2. Check a few zero-rated items (bread, milk, unga) have VAT shown as exempt.
  3. Use the barcode scanner to confirm barcodes scan correctly.
  4. Adjust any selling prices that don't match your actual pricing.
""")
