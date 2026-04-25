# scripts/import_products.py
"""
Complete product import script for DukaPOS
Run: python -m scripts.import_products
"""

import sys
import os
import re
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.product import Product, Category, Supplier
from app.models.subscription import Store
from app.models.employee import Employee, Role


# Tax mapping: SQL tax_id -> (tax_code, description)
TAX_MAPPING = {
    1: {"code": "B", "description": "Standard VAT 16%"},      # Standard VAT
    2: {"code": "A", "description": "Zero-rated"},            # Zero-rated
    3: {"code": "A", "description": "Exempt"},                # Exempt
}

# Default unit mapping
UNIT_MAPPING = {
    'pcs': 'piece',
    'kg': 'kilogram',
    'g': 'gram',
    'L': 'liter',
    'ml': 'milliliter',
    'pack': 'pack',
}


def parse_sql_row(row_text: str) -> List[str]:
    """Parse a SQL row string into individual values, handling quoted strings."""
    values = []
    current = ""
    in_quotes = False
    quote_char = None
    
    for char in row_text:
        if char in ("'", '"') and not in_quotes:
            in_quotes = True
            quote_char = char
            current += char
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
            current += char
        elif char == ',' and not in_quotes:
            values.append(current.strip())
            current = ""
        else:
            current += char
    
    values.append(current.strip())
    return values


def extract_products_from_sql(sql_file: str) -> List[Dict]:
    """Extract product data from SQL INSERT statements."""
    with open(sql_file, 'r') as f:
        content = f.read()
    
    # Find the product INSERT block
    insert_match = re.search(r"INSERT INTO products\s*\((.*?)\)\s*VALUES\s*(.*?);", 
                             content, re.DOTALL | re.IGNORECASE)
    
    if not insert_match:
        print("Could not find product INSERT statement")
        return []
    
    columns_str = insert_match.group(1)
    values_str = insert_match.group(2)
    
    # Parse column names
    columns = [col.strip().lower() for col in columns_str.split(',')]
    
    # Parse rows - find each VALUES tuple
    rows = []
    depth = 0
    current_row = ""
    
    for char in values_str:
        if char == '(':
            depth += 1
            if depth == 1:
                current_row = ""
            current_row += char
        elif char == ')':
            depth -= 1
            current_row += char
            if depth == 0 and current_row.strip():
                rows.append(current_row.strip('()'))
        elif depth > 0:
            current_row += char
    
    products = []
    for row in rows:
        raw_values = parse_sql_row(row)
        
        # Map values to columns
        product = {}
        for i, col in enumerate(columns):
            if i < len(raw_values):
                val = raw_values[i]
                # Remove quotes
                if val.startswith("'") and val.endswith("'"):
                    val = val[1:-1]
                elif val.upper() == 'NULL' or val == '':
                    val = None
                elif val.upper() == 'TRUE':
                    val = True
                elif val.upper() == 'FALSE':
                    val = False
                elif col in ('id', 'category_id', 'supplier_id', 'reorder_level', 'current_stock'):
                    if val is not None:
                        try:
                            val = int(val)
                        except (ValueError, TypeError):
                            val = None
                elif col in ('cost_price', 'selling_price'):
                    if val is not None:
                        try:
                            val = Decimal(str(val)).quantize(Decimal('0.01'))
                        except (ValueError, TypeError):
                            val = Decimal('0')
                
                product[col] = val
        
        products.append(product)
    
    return products


def create_or_get_categories(db: Session, store_id: int, sql_file: str) -> Dict[int, int]:
    """Create categories from SQL file if they don't exist, return mapping SQL_id -> DB_id."""
    
    # First, extract categories from SQL
    category_data = {}
    with open(sql_file, 'r') as f:
        content = f.read()
    
    # Find category INSERT
    cat_match = re.search(r"INSERT INTO categories\s*\((.*?)\)\s*VALUES\s*(.*?);", 
                          content, re.DOTALL | re.IGNORECASE)
    
    if cat_match:
        values_str = cat_match.group(2)
        depth = 0
        current_row = ""
        rows = []
        
        for char in values_str:
            if char == '(':
                depth += 1
                if depth == 1:
                    current_row = ""
                current_row += char
            elif char == ')':
                depth -= 1
                current_row += char
                if depth == 0 and current_row.strip():
                    rows.append(current_row.strip('()'))
            elif depth > 0:
                current_row += char
        
        for row in rows:
            values = parse_sql_row(row)
            if len(values) >= 2:
                try:
                    cat_id = int(values[0])
                    cat_name = values[1].strip("'")
                    default_tax = values[2].strip("'") if len(values) > 2 else 'standard'
                    category_data[cat_id] = {
                        'name': cat_name,
                        'default_tax_type': default_tax
                    }
                except (ValueError, IndexError):
                    continue
    
    # Create categories in DB
    mapping = {}
    for sql_id, cat_info in category_data.items():
        # Check if category exists in this store
        existing = db.query(Category).filter(
            Category.store_id == store_id,
            Category.name == cat_info['name']
        ).first()
        
        if existing:
            mapping[sql_id] = existing.id
            print(f"  → Category '{cat_info['name']}' already exists (ID: {existing.id})")
        else:
            category = Category(
                store_id=store_id,
                name=cat_info['name'],
                description=f"Auto-imported from seed data - {cat_info['default_tax_type']}",
                created_at=datetime.utcnow()
            )
            db.add(category)
            db.flush()
            mapping[sql_id] = category.id
            print(f"  ✓ Created category: {cat_info['name']} (ID: {category.id})")
    
    return mapping


def create_or_get_suppliers(db: Session, store_id: int, sql_file: str) -> Dict[int, int]:
    """Create suppliers from SQL file if they don't exist, return mapping SQL_id -> DB_id."""
    
    # Extract suppliers from SQL
    supplier_data = {}
    with open(sql_file, 'r') as f:
        content = f.read()
    
    # Find supplier INSERT
    sup_match = re.search(r"INSERT INTO suppliers\s*\((.*?)\)\s*VALUES\s*(.*?);", 
                          content, re.DOTALL | re.IGNORECASE)
    
    if sup_match:
        values_str = sup_match.group(2)
        depth = 0
        current_row = ""
        rows = []
        
        for char in values_str:
            if char == '(':
                depth += 1
                if depth == 1:
                    current_row = ""
                current_row += char
            elif char == ')':
                depth -= 1
                current_row += char
                if depth == 0 and current_row.strip():
                    rows.append(current_row.strip('()'))
            elif depth > 0:
                current_row += char
        
        for row in rows:
            values = parse_sql_row(row)
            if len(values) >= 3:
                try:
                    sup_id = int(values[0])
                    sup_name = values[1].strip("'") if values[1] else None
                    sup_phone = values[2].strip("'") if len(values) > 2 and values[2] else None
                    sup_address = values[3].strip("'") if len(values) > 3 and values[3] else None
                    is_active = values[4].strip("'").upper() == 'TRUE' if len(values) > 4 else True
                    
                    if sup_name:
                        supplier_data[sup_id] = {
                            'name': sup_name,
                            'phone': sup_phone,
                            'address': sup_address,
                            'is_active': is_active
                        }
                except (ValueError, IndexError):
                    continue
    
    # Create suppliers in DB
    mapping = {}
    for sql_id, sup_info in supplier_data.items():
        # Check if supplier exists
        existing = db.query(Supplier).filter(
            Supplier.store_id == store_id,
            Supplier.name == sup_info['name']
        ).first()
        
        if existing:
            mapping[sql_id] = existing.id
            print(f"  → Supplier '{sup_info['name']}' already exists (ID: {existing.id})")
        else:
            supplier = Supplier(
                store_id=store_id,
                name=sup_info['name'],
                phone=sup_info.get('phone'),
                address=sup_info.get('address'),
                is_active=sup_info.get('is_active', True),
                created_at=datetime.utcnow()
            )
            db.add(supplier)
            db.flush()
            mapping[sql_id] = supplier.id
            print(f"  ✓ Created supplier: {sup_info['name']} (ID: {supplier.id})")
    
    return mapping


def normalize_unit(unit: str) -> str:
    """Normalize unit names to match Product model."""
    if not unit:
        return 'piece'
    unit_lower = unit.lower()
    for key, value in UNIT_MAPPING.items():
        if key in unit_lower:
            return value
    return 'piece'


def import_products(db: Session, store_id: int, products_data: List[Dict], 
                    category_mapping: Dict[int, int], 
                    supplier_mapping: Dict[int, int]) -> Tuple[int, int]:
    """Import products into the database."""
    
    success_count = 0
    skip_count = 0
    
    for idx, product_data in enumerate(products_data):
        # Skip if no SKU
        sku = product_data.get('sku')
        if not sku:
            print(f"  ✗ Skipping product {idx + 1}: No SKU")
            skip_count += 1
            continue
        
        # Check if product already exists
        existing = db.query(Product).filter(
            Product.store_id == store_id,
            Product.sku == sku
        ).first()
        
        if existing:
            print(f"  → Skipping existing product: {sku} - {product_data.get('name', 'Unknown')}")
            skip_count += 1
            continue
        
        # Map category
        sql_category_id = product_data.get('category_id')
        category_id = category_mapping.get(sql_category_id) if sql_category_id else None
        
        # Map supplier
        sql_supplier_id = product_data.get('supplier_id')
        supplier_id = supplier_mapping.get(sql_supplier_id) if sql_supplier_id else None
        
        # Map tax
        sql_tax_id = product_data.get('tax_id', 1)
        tax_info = TAX_MAPPING.get(sql_tax_id, TAX_MAPPING[1])
        
        # Get values
        name = product_data.get('name', '')
        if not name:
            name = f"Product {sku}"
        
        barcode = product_data.get('barcode')
        if barcode == 'NULL' or barcode == '':
            barcode = None
        
        unit = normalize_unit(product_data.get('unit_of_measure', 'pcs'))
        
        cost_price = product_data.get('cost_price')
        if cost_price is None or cost_price == 0:
            cost_price = product_data.get('selling_price', Decimal('0')) * Decimal('0.7')
        
        selling_price = product_data.get('selling_price', Decimal('0'))
        
        stock_quantity = product_data.get('current_stock', 0)
        if stock_quantity is None:
            stock_quantity = 0
        
        reorder_level = product_data.get('reorder_level', 10)
        if reorder_level is None:
            reorder_level = 10
        
        is_active = product_data.get('is_active', True)
        
        # Create product
        product = Product(
            store_id=store_id,
            sku=sku,
            barcode=barcode,
            name=name,
            category_id=category_id,
            supplier_id=supplier_id,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            stock_quantity=stock_quantity,
            reorder_level=reorder_level,
            tax_code=tax_info['code'],
            is_active=is_active,
            created_at=datetime.utcnow()
        )
        
        db.add(product)
        success_count += 1
        
        if (idx + 1) % 100 == 0:
            print(f"  📦 Processed {idx + 1} products...")
    
    return success_count, skip_count


def main():
    """Main import function."""
    sql_file = "dukapos_kenyan_ready_1000_items_postgres.sql"
    store_id = 1  # Change to your store ID
    
    # Check if file exists
    if not os.path.exists(sql_file):
        print(f"❌ SQL file not found: {sql_file}")
        print("Please ensure the file is in the current directory")
        return
    
    print("=" * 60)
    print("DukaPOS Product Import Tool")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Get or create store
        store = db.query(Store).filter(Store.id == store_id).first()
        if not store:
            print(f"\n❌ Store with ID {store_id} not found!")
            print("Available stores:")
            stores = db.query(Store).all()
            for s in stores:
                print(f"  - ID: {s.id}, Name: {s.name}")
            return
        
        print(f"\n📦 Target Store: {store.name} (ID: {store.id})")
        
        # Extract products
        print("\n📖 Parsing SQL file...")
        products = extract_products_from_sql(sql_file)
        print(f"   Found {len(products)} products to import")
        
        if not products:
            print("❌ No products found in SQL file")
            return
        
        # Create categories
        print("\n🏷️  Importing categories...")
        category_mapping = create_or_get_categories(db, store_id, sql_file)
        print(f"   Mapped {len(category_mapping)} categories")
        
        # Create suppliers
        print("\n🏭 Importing suppliers...")
        supplier_mapping = create_or_get_suppliers(db, store_id, sql_file)
        print(f"   Mapped {len(supplier_mapping)} suppliers")
        
        # Commit categories and suppliers
        db.commit()
        print("\n✓ Categories and suppliers saved")
        
        # Import products
        print("\n📦 Importing products...")
        success, skipped = import_products(
            db, store_id, products, category_mapping, supplier_mapping
        )
        
        # Final commit
        db.commit()
        
        print("\n" + "=" * 60)
        print("✅ IMPORT COMPLETE")
        print("=" * 60)
        print(f"   ✓ Products imported: {success}")
        print(f"   ⏭️  Products skipped: {skipped}")
        print(f"   📊 Total processed: {success + skipped}")
        print(f"   🏷️  Categories created/used: {len(category_mapping)}")
        print(f"   🏭 Suppliers created/used: {len(supplier_mapping)}")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error during import: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()