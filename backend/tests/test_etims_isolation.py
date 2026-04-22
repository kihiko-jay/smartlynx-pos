"""
eTIMS security / store-isolation tests — v1.0

Covers the P0 security bugs fixed in etims.py v4.1:

  Bug 1: GET /etims/pending — no store_id filter (cross-tenant data read)
  Bug 2: POST /etims/retry-all — no store_id filter (cross-tenant write trigger)
  Bug 3: POST /etims/submit/{txn_id} — IDOR, no ownership check

Tests:
  1.  /pending returns only the caller's store's unsynced transactions          ← Bug 1
  2.  /pending does NOT return other stores' transactions                        ← Bug 1
  3.  /pending returns 200 with empty list when the caller's store has no pending ← Bug 1 regression
  4.  /retry-all only processes the caller's store's transactions                ← Bug 2
  5.  /retry-all does NOT trigger retry for other stores                         ← Bug 2
  6.  /submit/{txn_id} rejects cross-store submission with 403                  ← Bug 3
  7.  /submit/{txn_id} allows same-store submission (ownership check passes)    ← Bug 3
  8.  /pending cashier gets 403 (role check enforced)                           ← auth gate
  9.  /pending unauthenticated gets 401
  10. /submit/{txn_id} for non-existent txn returns 404
  11. /submit/{txn_id} for PENDING (non-COMPLETED) txn returns 400

Existing service-level tests (test_etims.py) are preserved.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.deps import get_db
from app.database import Base
from app.core.security import create_access_token, hash_password
from app.models.employee import Employee, Role
from app.models.subscription import Store, Plan, SubStatus
from app.models.transaction import Transaction, TransactionStatus, SyncStatus


# ── Isolated test DB ──────────────────────────────────────────────────────────

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
def store_a(db):
    s = Store(name="eTIMS Store A", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s); db.commit(); db.refresh(s)
    return s


@pytest.fixture
def store_b(db):
    s = Store(name="eTIMS Store B", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _make_manager(db, store, email):
    emp = Employee(
        store_id=store.id, full_name="Manager",
        email=email, password=hash_password("pass123"),
        role=Role.MANAGER, is_active=True,
    )
    db.add(emp); db.commit(); db.refresh(emp)
    return emp


def _make_cashier(db, store, email):
    emp = Employee(
        store_id=store.id, full_name="Cashier",
        email=email, password=hash_password("pass123"),
        role=Role.CASHIER, is_active=True,
    )
    db.add(emp); db.commit(); db.refresh(emp)
    return emp


def _make_platform_owner(db, email):
    emp = Employee(
        store_id=None, full_name="Platform Owner",
        email=email, password=hash_password("pass123"),
        role=Role.PLATFORM_OWNER, is_active=True,
    )
    db.add(emp); db.commit(); db.refresh(emp)
    return emp


def _auth(emp):
    tok = create_access_token({"sub": str(emp.id), "role": emp.role.value})
    return {"Authorization": f"Bearer {tok}"}


def _completed_unsynced_txn(db, store_id, txn_number):
    """Create a COMPLETED, etims_synced=False transaction."""
    txn = Transaction(
        txn_number=txn_number,
        store_id=store_id,
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("16.00"),
        total=Decimal("116.00"),
        discount_amount=Decimal("0.00"),
        payment_method="cash",
        status=TransactionStatus.COMPLETED,
        sync_status=SyncStatus.PENDING,
        etims_synced=False,
    )
    db.add(txn); db.commit(); db.refresh(txn)
    return txn


def _pending_txn(db, store_id, txn_number):
    """Create a PENDING (M-PESA in-progress) transaction."""
    txn = Transaction(
        txn_number=txn_number,
        store_id=store_id,
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("16.00"),
        total=Decimal("116.00"),
        discount_amount=Decimal("0.00"),
        payment_method="mpesa",
        status=TransactionStatus.PENDING,
        sync_status=SyncStatus.PENDING,
        etims_synced=False,
    )
    db.add(txn); db.commit(); db.refresh(txn)
    return txn


# ─────────────────────────────────────────────────────────────────────────────
# BUG 1: GET /etims/pending — store_id filter
# ─────────────────────────────────────────────────────────────────────────────

def test_pending_returns_only_own_store_transactions(client, db, store_a, store_b):
    """
    Bug 1 regression: /etims/pending must only return the caller's store's
    unsynced transactions, never another store's.
    """
    mgr_a = _make_manager(db, store_a, "mgr_a_p1@test.com")
    txn_a = _completed_unsynced_txn(db, store_a.id, "ETIMS-A-001")
    _txn_b = _completed_unsynced_txn(db, store_b.id, "ETIMS-B-001")  # must be invisible

    r = client.get("/api/v1/etims/pending", headers=_auth(mgr_a))
    assert r.status_code == 200, r.text

    data = r.json()
    txn_numbers = {t["txn_number"] for t in data["transactions"]}

    assert "ETIMS-A-001" in txn_numbers, "Store A's own pending txn must appear"
    assert "ETIMS-B-001" not in txn_numbers, (
        "P0 DATA LEAK: Store B's pending eTIMS submission is visible to Store A manager. "
        "The store_id filter is missing from GET /etims/pending."
    )


def test_pending_excludes_other_stores_completely(client, db, store_a, store_b):
    """
    Store A's manager must see count=0 even if Store B has pending submissions.
    Unsynced count must reflect only the caller's store.
    """
    mgr_a = _make_manager(db, store_a, "mgr_a_p2@test.com")
    # Only Store B has unsynced transactions — Store A has none
    _completed_unsynced_txn(db, store_b.id, "ETIMS-ONLY-B-001")
    _completed_unsynced_txn(db, store_b.id, "ETIMS-ONLY-B-002")

    r = client.get("/api/v1/etims/pending", headers=_auth(mgr_a))
    assert r.status_code == 200

    data = r.json()
    assert data["unsynced_count"] == 0, (
        f"Expected 0 unsynced for Store A, got {data['unsynced_count']}. "
        "Store B's transactions are leaking into Store A's pending list."
    )
    assert data["transactions"] == []


def test_pending_returns_correct_count_for_own_store(client, db, store_a, store_b):
    """Count must match exactly the number of this store's unsynced txns."""
    mgr_a = _make_manager(db, store_a, "mgr_a_p3@test.com")
    _completed_unsynced_txn(db, store_a.id, "ETIMS-COUNT-A-1")
    _completed_unsynced_txn(db, store_a.id, "ETIMS-COUNT-A-2")
    _completed_unsynced_txn(db, store_b.id, "ETIMS-COUNT-B-1")  # must not count

    r = client.get("/api/v1/etims/pending", headers=_auth(mgr_a))
    assert r.status_code == 200

    assert r.json()["unsynced_count"] == 2, (
        f"Expected 2 (store A's own), got {r.json()['unsynced_count']}"
    )


def test_pending_response_includes_store_id_field(client, db, store_a):
    """
    Response must include store_id so clients can detect the scope.
    Prevents silent cross-store data exposure going undetected.
    """
    mgr_a = _make_manager(db, store_a, "mgr_a_p4@test.com")
    r = client.get("/api/v1/etims/pending", headers=_auth(mgr_a))
    assert r.status_code == 200
    assert "store_id" in r.json(), "Response must include store_id field for scope transparency"
    assert r.json()["store_id"] == store_a.id


def test_pending_cashier_role_forbidden(client, db, store_a):
    """Cashier role must receive 403 — /pending requires manager or above."""
    cashier = _make_cashier(db, store_a, "cashier_pending@test.com")
    r = client.get("/api/v1/etims/pending", headers=_auth(cashier))
    assert r.status_code == 403, (
        f"Cashier must not access eTIMS pending list, got {r.status_code}"
    )


def test_pending_unauthenticated_gets_401(client):
    """No Bearer token → 401."""
    r = client.get("/api/v1/etims/pending")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# BUG 2: POST /etims/retry-all — store_id filter
# ─────────────────────────────────────────────────────────────────────────────

def test_retry_all_only_processes_own_store(client, db, store_a, store_b):
    """
    Bug 2 regression: /etims/retry-all must only attempt to resync the
    caller's store's transactions, never another store's.
    """
    mgr_a = _make_manager(db, store_a, "mgr_a_r1@test.com")
    txn_a = _completed_unsynced_txn(db, store_a.id, "RETRY-A-001")
    txn_b = _completed_unsynced_txn(db, store_b.id, "RETRY-B-001")

    # Mock submit_invoice to capture which txn_numbers are retried
    retried_txn_numbers = []

    async def mock_submit(data):
        retried_txn_numbers.append(data["txn_number"])
        return {"etims_invoice_no": "INV-MOCK", "etims_qr_code": None, "etims_synced": True}

    with patch("app.routers.etims.submit_invoice", side_effect=mock_submit):
        r = client.post("/api/v1/etims/retry-all", headers=_auth(mgr_a))

    assert r.status_code == 200, r.text

    assert "RETRY-A-001" in retried_txn_numbers, "Store A's own txn must be retried"
    assert "RETRY-B-001" not in retried_txn_numbers, (
        "P0 SECURITY: Store B's transaction was included in Store A manager's retry-all. "
        "The store_id filter is missing from POST /etims/retry-all."
    )


def test_retry_all_total_reflects_own_store_only(client, db, store_a, store_b):
    """result['total'] must count only the caller's store's pending txns."""
    mgr_a = _make_manager(db, store_a, "mgr_a_r2@test.com")
    _completed_unsynced_txn(db, store_a.id, "RETRY-TOTAL-A-1")
    _completed_unsynced_txn(db, store_a.id, "RETRY-TOTAL-A-2")
    _completed_unsynced_txn(db, store_b.id, "RETRY-TOTAL-B-1")  # must not count

    async def mock_submit(data):
        return {"etims_invoice_no": "INV-X", "etims_qr_code": None, "etims_synced": True}

    with patch("app.routers.etims.submit_invoice", side_effect=mock_submit):
        r = client.post("/api/v1/etims/retry-all", headers=_auth(mgr_a))

    assert r.status_code == 200
    assert r.json()["total"] == 2, (
        f"retry-all total should be 2 (Store A only), got {r.json()['total']}"
    )


def test_retry_all_cashier_role_forbidden(client, db, store_a):
    """Cashier must not trigger a bulk eTIMS retry."""
    cashier = _make_cashier(db, store_a, "cashier_retry@test.com")
    r = client.post("/api/v1/etims/retry-all", headers=_auth(cashier))
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# BUG 3: POST /etims/submit/{txn_id} — IDOR ownership check
# ─────────────────────────────────────────────────────────────────────────────

def test_submit_cross_store_returns_403(client, db, store_a, store_b):
    """
    Bug 3 regression: a cashier from Store A must not be able to submit
    Store B's transaction to KRA — even if they know the txn_id integer.
    """
    cashier_a = _make_cashier(db, store_a, "cashier_a_submit@test.com")
    txn_b = _completed_unsynced_txn(db, store_b.id, "IDOR-TXN-B-001")

    r = client.post(f"/api/v1/etims/submit/{txn_b.id}", headers=_auth(cashier_a))
    assert r.status_code == 403, (
        f"P0 IDOR: Store A cashier submitted Store B's transaction (txn_id={txn_b.id}). "
        f"Expected 403, got {r.status_code}."
    )


def test_submit_own_store_txn_allowed(client, db, store_a):
    """
    A cashier submitting their own store's COMPLETED transaction must succeed
    (mocked KRA call).
    """
    cashier_a = _make_cashier(db, store_a, "cashier_a_own@test.com")
    txn_a = _completed_unsynced_txn(db, store_a.id, "OWN-TXN-A-001")

    async def mock_submit(data):
        return {
            "etims_invoice_no": "KRA-OWN-001",
            "etims_qr_code":    "https://qr.kra.go.ke/x",
            "etims_synced":     True,
        }

    with patch("app.routers.etims.submit_invoice", side_effect=mock_submit):
        r = client.post(f"/api/v1/etims/submit/{txn_a.id}", headers=_auth(cashier_a))

    assert r.status_code == 200, r.text
    assert r.json()["etims_synced"] is True
    assert r.json()["etims_invoice_no"] == "KRA-OWN-001"


def test_submit_nonexistent_txn_returns_404(client, db, store_a):
    """Submitting a txn_id that does not exist must return 404, not 500."""
    cashier_a = _make_cashier(db, store_a, "cashier_a_404@test.com")
    r = client.post("/api/v1/etims/submit/9999999", headers=_auth(cashier_a))
    assert r.status_code == 404


def test_submit_pending_txn_returns_400(client, db, store_a):
    """Submitting a PENDING (not COMPLETED) transaction must return 400."""
    cashier_a = _make_cashier(db, store_a, "cashier_a_pending@test.com")
    pending = _pending_txn(db, store_a.id, "PENDING-TXN-001")
    r = client.post(f"/api/v1/etims/submit/{pending.id}", headers=_auth(cashier_a))
    assert r.status_code == 400


def test_submit_unauthenticated_returns_401(client, db, store_a):
    """No auth token → 401."""
    txn_a = _completed_unsynced_txn(db, store_a.id, "UNAUTH-TXN-001")
    r = client.post(f"/api/v1/etims/submit/{txn_a.id}")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM OWNER BEHAVIOUR
# ─────────────────────────────────────────────────────────────────────────────

def test_pending_platform_owner_sees_all_stores(client, db, store_a, store_b):
    """
    PLATFORM_OWNER must see unsynced submissions from ALL stores —
    this is intentional for cross-store support and is explicitly gated by role.
    """
    platform = _make_platform_owner(db, "platform_pending@test.com")
    _completed_unsynced_txn(db, store_a.id, "PLATFORM-A-001")
    _completed_unsynced_txn(db, store_b.id, "PLATFORM-B-001")

    r = client.get("/api/v1/etims/pending", headers=_auth(platform))
    assert r.status_code == 200

    txn_numbers = {t["txn_number"] for t in r.json()["transactions"]}
    assert "PLATFORM-A-001" in txn_numbers, "Platform owner must see Store A's pending"
    assert "PLATFORM-B-001" in txn_numbers, "Platform owner must see Store B's pending"

    # store_id in response must be None for platform owner (cross-store scope)
    assert r.json()["store_id"] is None, (
        "Platform owner response must show store_id=None to indicate cross-store scope"
    )


def test_submit_platform_owner_can_submit_any_store_txn(client, db, store_a, store_b):
    """
    PLATFORM_OWNER must be able to submit any store's transaction —
    this supports cross-store maintenance and is explicitly role-gated.
    """
    platform = _make_platform_owner(db, "platform_submit@test.com")
    txn_b = _completed_unsynced_txn(db, store_b.id, "PLATFORM-SUBMIT-B-001")

    async def mock_submit(data):
        return {"etims_invoice_no": "KRA-PLATFORM-001", "etims_qr_code": None, "etims_synced": True}

    with patch("app.routers.etims.submit_invoice", side_effect=mock_submit):
        r = client.post(f"/api/v1/etims/submit/{txn_b.id}", headers=_auth(platform))

    assert r.status_code == 200, r.text
    assert r.json()["etims_synced"] is True
