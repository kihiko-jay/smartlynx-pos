import os
os.environ.setdefault('DATABASE_URL', 'postgresql://root:smartlynx@dukapos_db:5432/smartlynx')
from app.database import SessionLocal
from app.models.product import Supplier
from datetime import datetime

db = SessionLocal()
store_id = 1

# Additional suppliers to create
new_suppliers = [
    'Eastern Hardware Depot',
    'Kisumu Fresh Hub',
    'Rift Valley Grain Supply',
]

print('\n🏢 Creating Additional Suppliers...\n')
created = 0
for sup_name in new_suppliers:
    existing = db.query(Supplier).filter_by(store_id=store_id, name=sup_name).first()
    if existing:
        print(f'  → {sup_name} (already exists)')
    else:
        sup = Supplier(store_id=store_id, name=sup_name, created_at=datetime.utcnow())
        db.add(sup)
        created += 1
        print(f'  ✓ Created: {sup_name}')

db.commit()
print(f'\n✅ Additional suppliers created: {created}\n')
db.close()
