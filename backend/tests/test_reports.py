"""
Report endpoint regression tests — v1.0

Covers P0 bug: weekly report used 'COMPLETED' (uppercase) while
TransactionStatus.COMPLETED.value == 'completed' (lowercase).
On PostgreSQL this returned zero rows (and therefore zero revenue).

Tests in this file:
  1. Weekly report returns correct revenue for COMPLETED transactions  ← P0 fix
  2. Weekly report excludes VOIDED / PENDING transactions
  3. Weekly report is isolated to the requesting store
  4. Z-tape returns correct totals for COMPLETED transactions
  5. Z-tape excludes VOIDED / PENDING transactions
  6. Z-tape is isolated to the requesting store
  7. VAT report returns correct totals
  8. VAT report excludes non-COMPLETED transactions
  9. Top-products uses ORM (TransactionStatus.COMPLETED) — won't regress
 10. All status comparisons use the canonical enum value, never a raw uppercase string

No migration needed — this is a query-layer-only fix.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta

from app.models.transaction import Transaction, TransactionItem, TransactionStatus, SyncStatus
from app.models.product import Product
from app.models.employee import Employee, Role
from app.models.subscription import Store, Plan, SubStatus
from app.core.security import create_access_token, hash_password
from app.database import Base

from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.core.deps import get_db


# ── Isolated test DB (SQLite in-memory) ──────────────────────────────────────

_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@sa_event.listens_for(_ENGINE, "connect")
def _fk_on(conn, _):
    conn.cursor().execute("PRAGMA foreign_keys=ON")


_Session = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture
def db():
    conn = _ENGINE.connect()
    txn  = conn.begin()
    sess = _Session(bind=conn)
    yield sess
    sess.close()
    txn.rollback()
    conn.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def store(db):
    s = Store(name="Report Test Store", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture
def store_b(db):
    """A second store for isolation tests."""
    s = Store(name="Report Store B", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture
def admin(db, store):
    emp = Employee(
        store_id=store.id, full_name="Report Admin",
        email="report_admin@test.com",
        password=hash_password("pass123"),
        role=Role.ADMIN, is_active=True,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@pytest.fixture
def admin_b(db, store_b):
    emp = Employee(
        store_id=store_b.id, full_name="Report Admin B",
        email="report_admin_b@test.com",
        password=hash_password("pass123"),
        role=Role.ADMIN, is_active=True,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@pytest.fixture
def auth(admin):
    tok = create_access_token({"sub": str(admin.id), "role": admin.role.value})
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def auth_b(admin_b):
    tok = create_access_token({"sub": str(admin_b.id), "role": admin_b.role.value})
    return {"Authorization": f"Bearer {tok}"}


TODAY = date.today()


def _make_txn(
    db,
    store_id: int,
    status: TransactionStatus,
    total: str,
    vat: str,
    txn_date: date = None,
    payment_method: str = "cash",
    txn_number: str = None,
):
    """
    Helper: create a Transaction directly in DB with a specific status.
    Uses a unique txn_number to avoid UNIQUE constraint violations.
    """
    import uuid
    txn_date = txn_date or TODAY
    txn = Transaction(
        txn_number=txn_number or f"REPORT-{uuid.uuid4().hex[:10].upper()}",
        store_id=store_id,
        subtotal=Decimal(total),
        vat_amount=Decimal(vat),
        total=Decimal(total),
        discount_amount=Decimal("0.00"),
        payment_method=payment_method,
        status=status,
        sync_status=SyncStatus.PENDING,
        # SQLite stores timezone-naive datetimes fine for DATE() comparison
        created_at=__import__("datetime").datetime.combine(txn_date, __import__("datetime").time()),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


# ─────────────────────────────────────────────────────────────────────────────
# 1. ENUM VALUE INVARIANT — foundational test
# ─────────────────────────────────────────────────────────────────────────────

def test_transaction_status_completed_value_is_lowercase():
    """
    P0 root cause: TransactionStatus.COMPLETED.value must be 'completed'
    (lowercase). If this ever changes, all raw SQL queries must be updated.
    This test acts as a canary.
    """
    assert TransactionStatus.COMPLETED.value == "completed", (
        "TransactionStatus.COMPLETED.value changed from 'completed'. "
        "All raw SQL report queries use this value via bind parameter — "
        "they will silently return zero rows if the value is uppercase."
    )
    assert TransactionStatus.VOIDED.value    == "voided"
    assert TransactionStatus.PENDING.value   == "pending"


# ─────────────────────────────────────────────────────────────────────────────
# 2. WEEKLY REPORT — P0 bug regression
# ─────────────────────────────────────────────────────────────────────────────

def test_weekly_report_counts_completed_transactions(client, auth, db, store):
    """
    P0 FIX: weekly report must return correct revenue for COMPLETED transactions.
    Previously used 'COMPLETED' (uppercase) causing PostgreSQL to return 0 rows.
    The fix uses TransactionStatus.COMPLETED.value ('completed') as a bind parameter.
    """
    # Create 2 COMPLETED transactions dated today
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "500.00", "68.97", TODAY)
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "300.00", "41.38", TODAY)

    r = client.get("/api/v1/reports/weekly", headers=auth,
                   params={"week_ending": str(TODAY)})
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["week_total_sales"] > 0, (
        "P0 BUG REGRESSION: weekly report returned 0 total sales despite "
        "COMPLETED transactions existing. The status string comparison is "
        "likely case-mismatched (e.g., 'COMPLETED' vs 'completed')."
    )
    assert data["week_total_sales"] == 800.0, (
        f"Expected week_total_sales=800.0, got {data['week_total_sales']}"
    )
    assert data["week_total_vat"] == pytest.approx(110.35, abs=0.01)


def test_weekly_report_returns_correct_day_breakdown(client, auth, db, store):
    """Daily breakdown must correctly attribute sales to each date."""
    yesterday = TODAY - timedelta(days=1)
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "1000.00", "137.93", TODAY)
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "200.00",  "27.59",  yesterday)

    r = client.get("/api/v1/reports/weekly", headers=auth,
                   params={"week_ending": str(TODAY)})
    assert r.status_code == 200, r.text

    daily = {d["date"]: d for d in r.json()["daily_breakdown"]}

    today_row     = daily.get(str(TODAY), {})
    yesterday_row = daily.get(str(yesterday), {})

    assert today_row.get("total_sales", 0)     == 1000.0
    assert yesterday_row.get("total_sales", 0) == 200.0


def test_weekly_report_excludes_voided_transactions(client, auth, db, store):
    """VOIDED transactions must NOT appear in weekly sales totals."""
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "100.00", "13.79", TODAY)
    _make_txn(db, store.id, TransactionStatus.VOIDED,    "500.00", "68.97", TODAY)

    r = client.get("/api/v1/reports/weekly", headers=auth,
                   params={"week_ending": str(TODAY)})
    assert r.status_code == 200

    # Only the 100.00 COMPLETED sale should appear
    assert r.json()["week_total_sales"] == 100.0, (
        "VOIDED transaction amount is included in weekly total — "
        "the status filter is wrong."
    )


def test_weekly_report_excludes_pending_transactions(client, auth, db, store):
    """PENDING M-PESA transactions must NOT appear in weekly sales totals."""
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "200.00", "27.59", TODAY)
    _make_txn(db, store.id, TransactionStatus.PENDING,   "999.00", "137.79", TODAY)

    r = client.get("/api/v1/reports/weekly", headers=auth,
                   params={"week_ending": str(TODAY)})
    assert r.status_code == 200

    assert r.json()["week_total_sales"] == 200.0, (
        "PENDING transaction is included in weekly total. "
        "Only COMPLETED transactions should count."
    )


def test_weekly_report_store_isolation(client, auth, auth_b, db, store, store_b):
    """
    Store A admin must ONLY see Store A's revenue in their weekly report.
    Store B's transactions must be invisible.
    """
    _make_txn(db, store.id,   TransactionStatus.COMPLETED, "300.00", "41.38", TODAY)
    _make_txn(db, store_b.id, TransactionStatus.COMPLETED, "9999.00", "1379.86", TODAY)

    # Store A's report
    r_a = client.get("/api/v1/reports/weekly", headers=auth,
                     params={"week_ending": str(TODAY)})
    assert r_a.status_code == 200

    total_a = r_a.json()["week_total_sales"]
    assert total_a == 300.0, (
        f"Store A sees {total_a} — should only see 300.00 (its own transactions). "
        "Store B's 9999.00 is leaking across tenant boundary."
    )

    # Store B's report
    r_b = client.get("/api/v1/reports/weekly", headers=auth_b,
                     params={"week_ending": str(TODAY)})
    assert r_b.status_code == 200
    assert r_b.json()["week_total_sales"] == 9999.0


def test_weekly_report_empty_week_returns_zeros(client, auth, store):
    """A week with no transactions must return 0s, not an error."""
    far_future = date(2099, 1, 7)
    r = client.get("/api/v1/reports/weekly", headers=auth,
                   params={"week_ending": str(far_future)})
    assert r.status_code == 200

    data = r.json()
    assert data["week_total_sales"] == 0.0
    assert data["week_total_vat"]   == 0.0
    assert len(data["daily_breakdown"]) == 7, "Must always return 7 days"
    for day in data["daily_breakdown"]:
        assert day["total_sales"]       == 0.0
        assert day["transaction_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Z-TAPE — consistency checks
# ─────────────────────────────────────────────────────────────────────────────

def test_ztape_counts_completed_transactions_only(client, auth, db, store):
    """Z-tape must sum only COMPLETED transactions for the target date."""
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "400.00", "55.17", TODAY)
    _make_txn(db, store.id, TransactionStatus.VOIDED,    "200.00", "27.59", TODAY)
    _make_txn(db, store.id, TransactionStatus.PENDING,   "100.00", "13.79", TODAY)

    r = client.get("/api/v1/reports/z-tape", headers=auth,
                   params={"report_date": str(TODAY)})
    assert r.status_code == 200

    data = r.json()
    assert data["gross_sales"]       == 400.0,  "Only COMPLETED sales should appear in Z-tape"
    assert data["transaction_count"] == 1,       "Only 1 COMPLETED transaction"


def test_ztape_store_isolation(client, auth, auth_b, db, store, store_b):
    """Z-tape must be filtered to the requesting store only."""
    _make_txn(db, store.id,   TransactionStatus.COMPLETED, "500.00", "68.97", TODAY)
    _make_txn(db, store_b.id, TransactionStatus.COMPLETED, "8888.00", "1226.21", TODAY)

    r = client.get("/api/v1/reports/z-tape", headers=auth,
                   params={"report_date": str(TODAY)})
    assert r.status_code == 200
    assert r.json()["gross_sales"] == 500.0, (
        "Store B revenue leaked into Store A's Z-tape"
    )


def test_ztape_payment_method_breakdown(client, auth, db, store):
    """Z-tape must break down revenue by payment method correctly."""
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "100.00", "13.79", TODAY, "cash")
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "200.00", "27.59", TODAY, "mpesa")

    r = client.get("/api/v1/reports/z-tape", headers=auth,
                   params={"report_date": str(TODAY)})
    assert r.status_code == 200

    by_method = r.json()["by_payment_method"]
    assert "cash"  in by_method, "Cash method missing from breakdown"
    assert "mpesa" in by_method, "M-PESA method missing from breakdown"
    assert by_method["cash"]["total"]  == 100.0
    assert by_method["mpesa"]["total"] == 200.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. VAT REPORT — consistency checks
# ─────────────────────────────────────────────────────────────────────────────

def test_vat_report_counts_completed_only(client, auth, db, store):
    """VAT report must include only COMPLETED transactions."""
    _make_txn(db, store.id, TransactionStatus.COMPLETED, "1160.00", "160.00", TODAY)
    _make_txn(db, store.id, TransactionStatus.VOIDED,    "580.00",  "80.00",  TODAY)
    _make_txn(db, store.id, TransactionStatus.PENDING,   "290.00",  "40.00",  TODAY)

    r = client.get("/api/v1/reports/vat", headers=auth,
                   params={"month": TODAY.month, "year": TODAY.year})
    assert r.status_code == 200

    data = r.json()
    assert data["total_vat_collected"] == 160.0, (
        f"VAT report included voided/pending VAT. "
        f"Expected 160.0, got {data['total_vat_collected']}"
    )
    assert data["transaction_count"] == 1


def test_vat_report_store_isolation(client, auth, auth_b, db, store, store_b):
    """VAT report must not aggregate across stores."""
    _make_txn(db, store.id,   TransactionStatus.COMPLETED, "1000.00", "137.93", TODAY)
    _make_txn(db, store_b.id, TransactionStatus.COMPLETED, "5000.00", "689.66", TODAY)

    r_a = client.get("/api/v1/reports/vat", headers=auth,
                     params={"month": TODAY.month, "year": TODAY.year})
    assert r_a.status_code == 200

    assert r_a.json()["total_gross_sales"] == 1000.0, (
        "Store B gross sales leaked into Store A's VAT report"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. REGRESSION GUARD — raw SQL status values
# ─────────────────────────────────────────────────────────────────────────────

def test_no_uppercase_status_literals_in_reports_source():
    """
    Static analysis: reports.py must contain zero hardcoded uppercase status
    string literals ('COMPLETED', 'VOIDED', 'PENDING') in SQL.

    This test reads the source file and fails if any uppercase status literal
    appears in a raw SQL string context, catching future regressions before
    they reach production.
    """
    import pathlib
    source = pathlib.Path(__file__).parent.parent / "app" / "routers" / "reports.py"
    content = source.read_text()

    uppercase_patterns = ["'COMPLETED'", '"COMPLETED"', "'VOIDED'", '"VOIDED"',
                          "'PENDING'",   '"PENDING"']

    violations = [p for p in uppercase_patterns if p in content]
    assert not violations, (
        f"Uppercase status string literal(s) found in reports.py: {violations}. "
        "All SQL status comparisons must use TransactionStatus.<X>.value as a "
        "bind parameter — never a hardcoded uppercase string. "
        "PostgreSQL enum comparisons are case-sensitive."
    )


def test_completed_status_bind_parameter_used_in_all_raw_sql_queries():
    """
    Verify that every raw SQL query in reports.py that filters on 'status'
    uses ':completed_status' as the bind parameter (never a literal string).
    """
    import pathlib, re
    source = pathlib.Path(__file__).parent.parent / "app" / "routers" / "reports.py"
    content = source.read_text()

    # Count lines that have both "AND status" and "= :completed_status"
    status_filter_lines = [
        line for line in content.splitlines()
        if "AND status" in line or "AND t.status" in line
    ]

    for line in status_filter_lines:
        assert ":completed_status" in line, (
            f"SQL status filter line does not use ':completed_status' bind parameter: "
            f"\n  {line.strip()}\n"
            "This will silently fail on PostgreSQL if the literal casing doesn't match "
            "the stored enum value."
        )
