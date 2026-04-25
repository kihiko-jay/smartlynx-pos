import os
os.environ.setdefault('DATABASE_URL', 'postgresql://root:smartlynx@dukapos_db:5432/smartlynx')
from app.database import SessionLocal
from app.models.product import Category, Supplier
from datetime import datetime

db = SessionLocal()
store_id = 1

# Categories to create
categories_to_create = [
    'Bakery',
    'Baking Supplies',
    'Beverages',
    'Cooking Essentials',
    'Dairy',
    'Fruits',
    'Grains',
    'Household',
    'Personal Care',
    'Poultry',
    'Vegetables',
]

# Suppliers to create
suppliers_to_create = [
    ('Agro Supplies', None, None),
    ('Coffee Imports', None, None),
    ('Detergent Factory', None, None),
    ('Farm Direct', None, None),
    ('Fresh Dairy Ltd', None, None),
    ('Fruit Imports', None, None),
    ('Grain Millers', None, None),
    ('Health & Beauty', None, None),
    ('Local Bakery', None, None),
    ('Metro Pharma Supply', None, None),
    ('Mount Kenya Dairy Supply', None, None),
    ('Nairobi Wholesale Traders Ltd', None, None),
    ('Oil Distributors', None, None),
    ('Paper Mills', None, None),
    ('Poultry Farm Ltd', None, None),
    ('Salt Works', None, None),
    ('Soap Manufacturers', None, None),
    ('Sugar Mills', None, None),
    ('Tea Gardens', None, None),
]

print('\n📁 Creating Categories...\n')
created_cats = 0
for cat_name in categories_to_create:
    existing = db.query(Category).filter_by(store_id=store_id, name=cat_name).first()
    if existing:
        print(f'  → {cat_name} (already exists)')
    else:
        cat = Category(store_id=store_id, name=cat_name, created_at=datetime.utcnow())
        db.add(cat)
        created_cats += 1
        print(f'  ✓ Created: {cat_name}')

print(f'\n🏢 Creating Suppliers...\n')
created_sups = 0
for sup_name, phone, email in suppliers_to_create:
    existing = db.query(Supplier).filter_by(store_id=store_id, name=sup_name).first()
    if existing:
        print(f'  → {sup_name} (already exists)')
    else:
        sup = Supplier(store_id=store_id, name=sup_name, phone=phone, email=email, created_at=datetime.utcnow())
        db.add(sup)
        created_sups += 1
        print(f'  ✓ Created: {sup_name}')

db.commit()
print(f'\n✅ Summary:')
print(f'  Categories created: {created_cats}')
print(f'  Suppliers created: {created_sups}')
print()

db.close()
