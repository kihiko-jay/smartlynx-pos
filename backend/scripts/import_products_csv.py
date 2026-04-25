#!/usr/bin/env python3
"""
import_products_csv.py — Import inventory products from a CSV file into SmartLynx POS.

CSV Format:
  Required columns:
    - sku: Unique product code (e.g., "PRD-001")
    - name: Product name (e.g., "Milk 1L")
    - selling_price: Retail price in KES (e.g., "125.00")

  Optional columns:
    - barcode: EAN/UPC code (e.g., "5901234123457")
    - itemcode: Numeric item code for fast POS lookup (e.g., "1001")
    - description: Product description or notes
    - category: Category name — auto-creates if doesn't exist (e.g., "Dairy")
    - supplier: Supplier name — auto-creates if doesn't exist (e.g., "Fresh Dairy Ltd")
    - cost_price: Product cost in KES (e.g., "85.00")
    - vat_exempt: Exempt from VAT (yes/no/true/false, default: no)
    - tax_code: Tax classification — A=exempt, B=standard 16% (default: B)
    - stock_quantity: Initial stock level (default: 0)
    - reorder_level: Low stock alert threshold (default: 10)
    - unit: Unit of measure (e.g., piece, kg, liter, pack, default: piece)
    - is_active: Product active status (yes/no/true/false, default: yes)

Usage:
  python -m scripts.import_products_csv --csv-file products.csv --store-id 1
  python -m scripts.import_products_csv --csv-file products.csv --store-id 1 --dry-run
  python -m scripts.import_products_csv --csv-file products.csv --store-id 1 --skip-errors

Options:
  --csv-file        PATH   Path to the CSV file (required)
  --store-id        INT    Store ID to import into (required)
  --dry-run                Show what would be imported without writing
  --skip-errors            Continue importing even if individual products fail
  --update-existing        Update existing products (by SKU) instead of skipping
  --mapping-file    PATH   JSON file with category/supplier name mappings

Example CSV (comma-separated):
  sku,name,selling_price,cost_price,category,supplier,stock_quantity,reorder_level
  MILK-001,Fresh Milk 1L,150.00,95.00,Dairy,Fresh Dairy Ltd,100,20
  BREAD-001,Wheat Bread 800g,80.00,45.00,Bakery,Local Bakery,50,15
  RICE-001,Jasmine Rice 2kg,350.00,280.00,Grains,Agro Supplies,200,50
"""

import argparse
import csv
import sys
import os
import json
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.product import Product, Category, Supplier
from app.models.subscription import Store


# ============================================================================
# CONFIGURATION
# ============================================================================

BOOL_VALUES = {
    'yes': True, 'y': True, '1': True, 'true': True, 'TRUE': True, 'True': True,
    'no': False, 'n': False, '0': False, 'false': False, 'FALSE': False, 'False': False,
}

UNIT_MAPPING = {
    'pcs': 'piece',
    'pc': 'piece',
    'pieces': 'piece',
    'kg': 'kilogram',
    'kilograms': 'kilogram',
    'g': 'gram',
    'grams': 'gram',
    'l': 'liter',
    'liter': 'liter',
    'liters': 'liter',
    'ml': 'milliliter',
    'milliliters': 'milliliter',
    'pack': 'pack',
    'packs': 'pack',
    'box': 'box',
    'boxes': 'box',
    'bottle': 'bottle',
    'bottles': 'bottle',
    'can': 'can',
    'cans': 'can',
    'carton': 'carton',
    'cartons': 'carton',
    'dozen': 'dozen',
    'bundle': 'bundle',
}


# ============================================================================
# VALIDATION & PARSING
# ============================================================================

class CSVImportError(Exception):
    """Base exception for CSV import errors."""
    pass


class RowParseError(CSVImportError):
    """Error parsing a single CSV row."""
    def __init__(self, row_num: int, message: str):
        self.row_num = row_num
        self.message = message
        super().__init__(f"Row {row_num}: {message}")


def parse_decimal(value: Optional[str], field_name: str) -> Optional[Decimal]:
    """Parse string to Decimal with 2 decimal places."""
    if not value or str(value).strip() == '':
        return None
    try:
        return Decimal(str(value).strip()).quantize(Decimal('0.01'))
    except Exception as e:
        raise ValueError(f"{field_name} must be a decimal number (got '{value}')")


def parse_bool(value: Optional[str]) -> bool:
    """Parse string to boolean."""
    if not value or str(value).strip() == '':
        return False
    val_str = str(value).strip().lower()
    if val_str in BOOL_VALUES:
        return BOOL_VALUES[val_str]
    raise ValueError(f"Boolean value must be yes/no or true/false (got '{value}')")


def parse_int(value: Optional[str], field_name: str) -> Optional[int]:
    """Parse string to integer."""
    if not value or str(value).strip() == '':
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        raise ValueError(f"{field_name} must be an integer (got '{value}')")


def normalize_unit(unit: Optional[str]) -> str:
    """Normalize unit name using mapping table."""
    if not unit:
        return 'piece'
    normalized = unit.strip().lower()
    return UNIT_MAPPING.get(normalized, normalized)


def validate_tax_code(code: Optional[str]) -> str:
    """Validate tax code (A or B)."""
    if not code:
        return 'B'
    code_str = str(code).strip().upper()
    if code_str not in ('A', 'B'):
        raise ValueError(f"Tax code must be A or B (got '{code}')")
    return code_str


# ============================================================================
# ROW PARSING
# ============================================================================

def parse_csv_row(
    row: Dict[str, str],
    row_num: int,
    store_id: int,
    category_cache: Dict[str, int],
    supplier_cache: Dict[str, int],
) -> Dict:
    """Parse and validate a CSV row into a product dict."""
    try:
        # Required fields
        sku = str(row.get('sku', '').strip())
        if not sku:
            raise RowParseError(row_num, "SKU is required")

        name = str(row.get('name', '').strip())
        if not name:
            raise RowParseError(row_num, "Product name is required")

        selling_price_str = row.get('selling_price', '').strip()
        if not selling_price_str:
            raise RowParseError(row_num, "Selling price is required")

        try:
            selling_price = parse_decimal(selling_price_str, "selling_price")
        except ValueError as e:
            raise RowParseError(row_num, str(e))

        # Optional fields
        barcode = row.get('barcode', '').strip() or None
        itemcode = None
        try:
            itemcode = parse_int(row.get('itemcode', ''), "itemcode")
        except ValueError as e:
            raise RowParseError(row_num, str(e))

        description = row.get('description', '').strip() or None

        # Prices
        cost_price = None
        try:
            cost_price = parse_decimal(row.get('cost_price', ''), "cost_price")
        except ValueError as e:
            raise RowParseError(row_num, str(e))

        # Category (by name, with caching)
        category_id = None
        category_name = row.get('category', '').strip()
        if category_name:
            category_id = category_cache.get(category_name.lower())
            if category_id is None:
                raise RowParseError(row_num, f"Category '{category_name}' not found")

        # Supplier (by name, with caching)
        supplier_id = None
        supplier_name = row.get('supplier', '').strip()
        if supplier_name:
            supplier_id = supplier_cache.get(supplier_name.lower())
            if supplier_id is None:
                raise RowParseError(row_num, f"Supplier '{supplier_name}' not found")

        # VAT & tax
        vat_exempt = False
        try:
            vat_exempt = parse_bool(row.get('vat_exempt', ''))
        except ValueError as e:
            raise RowParseError(row_num, f"vat_exempt: {e}")

        tax_code = 'B'
        try:
            tax_code = validate_tax_code(row.get('tax_code', ''))
        except ValueError as e:
            raise RowParseError(row_num, str(e))

        # Stock
        stock_quantity = 0
        try:
            sq = parse_int(row.get('stock_quantity', ''), "stock_quantity")
            if sq is not None:
                stock_quantity = sq
        except ValueError as e:
            raise RowParseError(row_num, str(e))

        reorder_level = 10
        try:
            rl = parse_int(row.get('reorder_level', ''), "reorder_level")
            if rl is not None:
                reorder_level = rl
        except ValueError as e:
            raise RowParseError(row_num, str(e))

        # Unit
        unit = normalize_unit(row.get('unit', ''))

        # Active status
        is_active = True
        try:
            is_active = parse_bool(row.get('is_active', 'yes'))
        except ValueError as e:
            raise RowParseError(row_num, f"is_active: {e}")

        return {
            'sku': sku,
            'barcode': barcode,
            'itemcode': itemcode,
            'name': name,
            'description': description,
            'category_id': category_id,
            'supplier_id': supplier_id,
            'selling_price': selling_price,
            'cost_price': cost_price,
            'vat_exempt': vat_exempt,
            'tax_code': tax_code,
            'stock_quantity': stock_quantity,
            'reorder_level': reorder_level,
            'unit': unit,
            'is_active': is_active,
        }

    except RowParseError:
        raise
    except Exception as e:
        raise RowParseError(row_num, str(e))


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def build_category_cache(db: Session, store_id: int) -> Dict[str, int]:
    """Build cache of category names -> IDs for the store."""
    categories = db.query(Category).filter(Category.store_id == store_id).all()
    return {cat.name.lower(): cat.id for cat in categories}


def build_supplier_cache(db: Session, store_id: int) -> Dict[str, int]:
    """Build cache of supplier names -> IDs for the store."""
    suppliers = db.query(Supplier).filter(Supplier.store_id == store_id).all()
    return {sup.name.lower(): sup.id for sup in suppliers}


def check_store_exists(db: Session, store_id: int) -> bool:
    """Verify store exists."""
    store = db.query(Store).filter(Store.id == store_id).first()
    return store is not None


def check_product_exists(db: Session, store_id: int, sku: str) -> Optional[Product]:
    """Check if product with given SKU already exists."""
    return db.query(Product).filter(
        Product.store_id == store_id,
        Product.sku == sku
    ).first()


def create_or_update_product(
    db: Session,
    store_id: int,
    product_data: Dict,
    update_existing: bool = False,
) -> Tuple[Product, bool]:
    """
    Create or update a product.
    Returns (product, is_new).
    """
    existing = check_product_exists(db, store_id, product_data['sku'])

    if existing:
        if not update_existing:
            return existing, False

        # Update existing product
        for key, value in product_data.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        existing.updated_at = datetime.utcnow()
        db.add(existing)
        return existing, False

    # Create new product
    product = Product(
        store_id=store_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        **product_data
    )
    db.add(product)
    return product, True


# ============================================================================
# IMPORT LOGIC
# ============================================================================

def read_csv_file(csv_file: str) -> List[Dict[str, str]]:
    """Read CSV file and convert to list of dicts."""
    rows = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        # Try to detect dialect
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = 'excel'

        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)

        if not reader.fieldnames:
            raise CSVImportError("CSV file is empty or has no header row")

        for i, row in enumerate(reader, start=2):  # Start at 2 because row 1 is header
            rows.append((i, row))

    return rows


def import_products_from_csv(
    csv_file: str,
    store_id: int,
    dry_run: bool = False,
    skip_errors: bool = False,
    update_existing: bool = False,
) -> Dict:
    """
    Import products from CSV file.

    Returns dict with:
      - success: bool
      - total_rows: int
      - created: int
      - updated: int
      - errors: List[str]
      - summary: str
    """
    result = {
        'success': False,
        'total_rows': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': [],
        'summary': '',
    }

    db = SessionLocal()
    try:
        # Validate store exists
        if not check_store_exists(db, store_id):
            raise CSVImportError(f"Store with ID {store_id} does not exist")

        # Validate CSV file
        if not os.path.exists(csv_file):
            raise CSVImportError(f"CSV file not found: {csv_file}")

        print(f"\n{'=' * 70}")
        print(f"  PRODUCT CSV IMPORT")
        print(f"{'=' * 70}")
        print(f"  CSV File:      {csv_file}")
        print(f"  Store ID:      {store_id}")
        print(f"  Dry Run:       {dry_run}")
        print(f"  Update Mode:   {update_existing}")
        print(f"  Skip Errors:   {skip_errors}")
        print(f"{'=' * 70}\n")

        # Read CSV
        print("📖 Reading CSV file...")
        rows = read_csv_file(csv_file)
        result['total_rows'] = len(rows)
        print(f"   ✓ Found {len(rows)} data rows\n")

        if not rows:
            raise CSVImportError("CSV file contains no data rows")

        # Build caches
        print("📦 Building category & supplier caches...")
        category_cache = build_category_cache(db, store_id)
        supplier_cache = build_supplier_cache(db, store_id)
        print(f"   ✓ {len(category_cache)} categories, {len(supplier_cache)} suppliers\n")

        # Track for duplicate detection
        seen_skus: Set[str] = set()

        # Process rows
        print("⏳ Processing rows...\n")
        for row_num, row in rows:
            try:
                # Parse row
                product_data = parse_csv_row(row, row_num, store_id, category_cache, supplier_cache)

                # Check for duplicates within CSV
                if product_data['sku'] in seen_skus:
                    result['errors'].append(f"Row {row_num}: Duplicate SKU '{product_data['sku']}' in CSV")
                    if not skip_errors:
                        raise CSVImportError(f"Row {row_num}: Duplicate SKU")
                    result['skipped'] += 1
                    continue

                seen_skus.add(product_data['sku'])

                # Create/update product
                product, is_new = create_or_update_product(
                    db,
                    store_id,
                    product_data,
                    update_existing=update_existing,
                )

                if is_new:
                    result['created'] += 1
                    status = "✓ CREATE"
                else:
                    result['updated'] += 1
                    status = "↻ UPDATE"

                print(f"   {status}  {product_data['sku']}: {product_data['name']}")

            except RowParseError as e:
                result['errors'].append(str(e))
                if not skip_errors:
                    raise
                result['skipped'] += 1
                print(f"   ✗ SKIP   Row {row_num}: {e.message}")

            except Exception as e:
                msg = f"Row {row_num}: {str(e)}"
                result['errors'].append(msg)
                if not skip_errors:
                    raise CSVImportError(msg)
                result['skipped'] += 1
                print(f"   ✗ SKIP   {msg}")

        # Commit or rollback
        print(f"\n{'=' * 70}")

        if dry_run:
            db.rollback()
            print("  🔄 DRY RUN: Rolling back changes")
            result['success'] = True
        else:
            db.commit()
            print("  ✓ Committing changes to database")
            result['success'] = True

        # Print summary
        summary_lines = [
            f"Total Rows:    {result['total_rows']}",
            f"Created:       {result['created']}",
            f"Updated:       {result['updated']}",
            f"Skipped:       {result['skipped']}",
            f"Errors:        {len(result['errors'])}",
        ]

        for line in summary_lines:
            print(f"  {line}")

        if result['errors']:
            print(f"\n  ⚠️  ERRORS:")
            for error in result['errors'][:10]:  # Show first 10 errors
                print(f"     - {error}")
            if len(result['errors']) > 10:
                print(f"     ... and {len(result['errors']) - 10} more")

        print(f"{'=' * 70}\n")

        result['summary'] = (
            f"Imported {result['created']} products "
            f"({result['updated']} updated, {result['skipped']} skipped)"
        )

        return result

    except CSVImportError as e:
        print(f"\n❌ ERROR: {e}\n")
        result['errors'].append(str(e))
        db.rollback()
        return result

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        result['errors'].append(f"Unexpected error: {str(e)}")
        db.rollback()
        return result

    finally:
        db.close()


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Import inventory products from CSV file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        '--csv-file',
        type=str,
        required=True,
        help='Path to CSV file to import',
    )

    parser.add_argument(
        '--store-id',
        type=int,
        required=True,
        help='Store ID to import into',
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be imported without writing',
    )

    parser.add_argument(
        '--skip-errors',
        action='store_true',
        help='Continue importing even if individual products fail',
    )

    parser.add_argument(
        '--update-existing',
        action='store_true',
        help='Update existing products (by SKU) instead of skipping',
    )

    args = parser.parse_args()

    result = import_products_from_csv(
        csv_file=args.csv_file,
        store_id=args.store_id,
        dry_run=args.dry_run,
        skip_errors=args.skip_errors,
        update_existing=args.update_existing,
    )

    sys.exit(0 if result['success'] else 1)
