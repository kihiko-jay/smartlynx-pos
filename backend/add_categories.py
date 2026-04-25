import os
os.environ.setdefault('DATABASE_URL', 'postgresql://root:smartlynx@dukapos_db:5432/smartlynx')
from app.database import SessionLocal
from app.models.product import Category
from datetime import datetime

db = SessionLocal()
store_id = 1

# Additional categories to create
new_categories = ['Snacks']

print('\n📁 Creating Additional Categories...\n')
created = 0
for cat_name in new_categories:
    existing = db.query(Category).filter_by(store_id=store_id, name=cat_name).first()
    if existing:
        print(f'  → {cat_name} (already exists)')
    else:
        cat = Category(store_id=store_id, name=cat_name, created_at=datetime.utcnow())
        db.add(cat)
        created += 1
        print(f'  ✓ Created: {cat_name}')

db.commit()
print(f'\n✅ Additional categories created: {created}\n')
db.close()
