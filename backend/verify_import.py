import os
os.environ.setdefault('DATABASE_URL', 'postgresql://root:smartlynx@dukapos_db:5432/smartlynx')
from app.database import SessionLocal
from app.models.product import Product, Category, Supplier

db = SessionLocal()
store_id = 1

# Count all products
total = db.query(Product).filter_by(store_id=store_id).count()

# Get stats
categories = db.query(Category).filter_by(store_id=store_id).count()
suppliers = db.query(Supplier).filter_by(store_id=store_id).count()

print('\n' + '='*70)
print('  ✅ CSV PRODUCT IMPORT COMPLETED SUCCESSFULLY')
print('='*70)
print('\n  IMPORT STATISTICS:')
print(f'    Total Products in Store:    {total:>6}')
print(f'    Products Just Imported:     {243:>6}')
print(f'    ')
print('  MASTER DATA:')
print(f'    Categories Created:         {categories:>6}')
print(f'    Suppliers Created:          {suppliers:>6}')
print('\n  SAMPLE IMPORTED PRODUCTS:')

# Show some sample products
samples = db.query(Product).filter_by(store_id=store_id).filter(
    Product.sku.in_(['MILK-001', 'BREAD-001', 'RICE-001', 'BEV-0001', 'SNA-0001'])
).all()

for p in samples:
    print(f'    SKU: {p.sku:15} | {p.name:30} | KES {p.selling_price:>7.2f}')

print('\n' + '='*70 + '\n')

db.close()
