"""
Pre-migration safety checks for store ownership assumptions.

Run before applying schema migrations in production:
  python backend/scripts/migration_preflight.py
"""

from sqlalchemy import text

from app.database import SessionLocal


CHECKS = [
    (
        "products_without_store_id",
        "SELECT COUNT(*) FROM products WHERE store_id IS NULL",
    ),
    (
        "transactions_without_store_id",
        "SELECT COUNT(*) FROM transactions WHERE store_id IS NULL",
    ),
    (
        "customers_without_store_id",
        "SELECT COUNT(*) FROM customers WHERE store_id IS NULL",
    ),
]


def main() -> int:
    db = SessionLocal()
    try:
        failures = []
        for name, sql in CHECKS:
            count = db.execute(text(sql)).scalar() or 0
            print(f"{name}: {count}")
            if count > 0:
                failures.append((name, count))
        if failures:
            print("Preflight FAILED: resolve ownership gaps before migration.")
            return 1
        print("Preflight PASSED.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
