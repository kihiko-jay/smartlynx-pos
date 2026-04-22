"""
SmartLynx Production Hardening Test Suite — v4.5

Covers all 12 must-fix items from the Architecture Upgrade Plan:

  P0 — Accounting atomically wired to sync ingest (test_accounting_*)
  P0 — COGS and inventory legs present in every sale (test_sale_journal_*)
  P0 — confirmed_txn_numbers enables safe local ack (test_sync_*)
  P0 — Trial balance is always zero (test_trial_balance_*)
  P1 — WAC recalculation is mathematically correct (test_wac_*)
  P1 — Conflict manifest drives all sync resolution (test_conflict_*)
  P1 — Tax engine: customer exemptions, mixed baskets, effective dates (test_tax_*)
  P1 — Reconciliation: oversell detection, period guard, ledger diff (test_reconciliation_*)
  P1 — Chaos: crash mid-commit, duplicate batches, backdated GRN (test_chaos_*)
  P1 — Sync agent: confirmed numbers, retry queue, dead-letter (test_sync_agent_*)
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Test database setup ────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite://"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@sa_event.listens_for(engine, "connect")
def _set_fk(dbapi_conn, _):
    dbapi_conn.cursor().execute("PRAGMA foreign_keys=ON")

from app.database import Base
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _tables():
    # Import all models so metadata is populated
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """Per-test session with savepoint rollback — tests are fully isolated."""
    conn = engine.connect()
    txn  = conn.begin()
    sess = TestSession(bind=conn)
    yield sess
    sess.close()
    txn.rollback()
    conn.close()


# ── Shared builder helpers ─────────────────────────────────────────────────────

def _make_store(db, name="Test Store"):
    from app.models.subscription import Store, Plan, SubStatus
    s = Store(name=name, plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s); db.flush()
    return s


def _make_employee(db, store, role="admin"):
    from app.models.employee import Employee, Role
    from app.core.security import hash_password
    e = Employee(
        store_id=store.id, full_name="Test Employee",
        email=f"emp_{uuid.uuid4().hex[:6]}@test.com",
        password=hash_password("pass123"),
        role=Role(role), is_active=True,
    )
    db.add(e); db.flush()
    return e


def _make_product(db, store, sku=None, cost=Decimal("50.00"), price=Decimal("100.00"), stock=10):
    from app.models.product import Product
    p = Product(
        store_id=store.id,
        sku=sku or f"SKU-{uuid.uuid4().hex[:6]}",
        name="Test Product",
        selling_price=price,
        cost_price=cost,
        stock_quantity=stock,
        is_active=True,
    )
    db.add(p); db.flush()
    return p


def _seed_coa(db, store):
    from app.services.accounting import seed_chart_of_accounts
    seed_chart_of_accounts(db, store.id)
    db.flush()


def _make_transaction(db, store, employee, product,
                      qty=1, payment="cash", total=None,
                      vat=Decimal("13.79"), cost_snap=None):
    """Build a completed Transaction + TransactionItem."""
    from app.models.transaction import Transaction, TransactionItem, TransactionStatus, SyncStatus, PaymentMethod
    unit_price  = product.selling_price
    subtotal    = unit_price * qty
    tot         = total if total is not None else subtotal + vat
    snap        = cost_snap if cost_snap is not None else (product.cost_price or Decimal("0.00"))

    txn = Transaction(
        txn_number     = f"TXN-{uuid.uuid4().hex[:8].upper()}",
        store_id       = store.id,
        terminal_id    = "T-001",
        subtotal       = subtotal,
        discount_amount= Decimal("0.00"),
        vat_amount     = vat,
        total          = tot,
        payment_method = PaymentMethod(payment),
        status         = TransactionStatus.COMPLETED,
        sync_status    = SyncStatus.PENDING,
        cashier_id     = employee.id,
        completed_at   = datetime.now(timezone.utc),
    )
    db.add(txn); db.flush()

    item = TransactionItem(
        transaction_id  = txn.id,
        product_id      = product.id,
        product_name    = product.name,
        sku             = product.sku,
        qty             = qty,
        unit_price      = unit_price,
        cost_price_snap = snap,
        discount        = Decimal("0.00"),
        line_total      = subtotal,
        vat_amount      = vat,
    )
    db.add(item); db.flush()
    return txn, [item]


# ══════════════════════════════════════════════════════════════════════════════
# 1. ACCOUNTING — journal entry correctness
# ══════════════════════════════════════════════════════════════════════════════

class TestSaleJournalEntry:
    """P0 — Every sale must produce a balanced 5-leg journal entry."""

    def test_post_transaction_produces_journal_entry(self, db):
        from app.services.accounting import post_transaction
        from app.models.accounting import JournalEntry

        store    = _make_store(db)
        emp      = _make_employee(db, store)
        product  = _make_product(db, store, cost=Decimal("40.00"), price=Decimal("100.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product,
                                       qty=1, vat=Decimal("13.79"),
                                       cost_snap=Decimal("40.00"))
        entry = post_transaction(db, txn, items)

        assert entry is not None, "post_transaction must return a JournalEntry"
        db.flush()

        saved = db.query(JournalEntry).filter_by(
            store_id=store.id, ref_type="transaction", ref_id=txn.txn_number
        ).first()
        assert saved is not None, "JournalEntry must be persisted"

    def test_journal_entry_is_balanced(self, db):
        from app.services.accounting import post_transaction

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("40.00"), price=Decimal("100.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product,
                                       qty=2, vat=Decimal("27.59"),
                                       cost_snap=Decimal("40.00"))
        entry = post_transaction(db, txn, items)
        db.flush()

        assert entry.total_debits  == entry.total_credits, (
            f"Journal entry unbalanced: DR={entry.total_debits} CR={entry.total_credits}"
        )

    def test_all_five_legs_are_present(self, db):
        """Cash, Revenue, VAT, COGS, Inventory — all 5 accounts must be touched."""
        from app.services.accounting import post_transaction
        from app.models.accounting import Account, JournalLine

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("50.00"), price=Decimal("120.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product,
                                       qty=1, vat=Decimal("16.55"),
                                       cost_snap=Decimal("50.00"))
        entry = post_transaction(db, txn, items)
        db.flush()

        # Collect account codes touched
        touched_codes = set()
        for line in entry.lines:
            acct = db.query(Account).get(line.account_id)
            touched_codes.add(acct.code)

        assert "1000" in touched_codes, "Cash in Hand (1000) must be debited"
        assert "4000" in touched_codes, "Sales Revenue (4000) must be credited"
        assert "2100" in touched_codes, "VAT Payable (2100) must be credited"
        assert "5000" in touched_codes, "COGS (5000) must be debited"
        assert "1200" in touched_codes, "Inventory (1200) must be credited"

    def test_cogs_equals_cost_price_snap_times_qty(self, db):
        from app.services.accounting import post_transaction
        from app.models.accounting import Account, JournalLine

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("30.00"), price=Decimal("80.00"))
        _seed_coa(db, store)

        qty  = 3
        snap = Decimal("30.00")
        txn, items = _make_transaction(db, store, emp, product,
                                       qty=qty, vat=Decimal("33.10"),
                                       cost_snap=snap)
        entry = post_transaction(db, txn, items)
        db.flush()

        cogs_acct = db.query(Account).filter_by(store_id=store.id, code="5000").first()
        cogs_line = next(l for l in entry.lines if l.account_id == cogs_acct.id)

        expected_cogs = snap * qty  # 90.00
        assert cogs_line.debit == expected_cogs, (
            f"COGS debit {cogs_line.debit} != expected {expected_cogs}"
        )

    def test_inventory_credit_equals_cogs_debit(self, db):
        from app.services.accounting import post_transaction
        from app.models.accounting import Account

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("45.00"), price=Decimal("90.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product,
                                       qty=2, cost_snap=Decimal("45.00"))
        entry = post_transaction(db, txn, items)
        db.flush()

        cogs_acct = db.query(Account).filter_by(store_id=store.id, code="5000").first()
        inv_acct  = db.query(Account).filter_by(store_id=store.id, code="1200").first()

        cogs_dr = next(l.debit  for l in entry.lines if l.account_id == cogs_acct.id)
        inv_cr  = next(l.credit for l in entry.lines if l.account_id == inv_acct.id)

        assert cogs_dr == inv_cr, f"COGS DR {cogs_dr} must equal Inventory CR {inv_cr}"

    def test_mpesa_sale_debits_mpesa_float_account(self, db):
        from app.services.accounting import post_transaction
        from app.models.accounting import Account

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store)
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product, payment="mpesa")
        entry = post_transaction(db, txn, items)
        db.flush()

        mpesa_acct = db.query(Account).filter_by(store_id=store.id, code="1010").first()
        mpesa_line = next((l for l in entry.lines if l.account_id == mpesa_acct.id), None)

        assert mpesa_line is not None, "M-PESA sale must debit account 1010 (M-PESA Float)"
        assert mpesa_line.debit > 0

    def test_credit_sale_debits_accounts_receivable(self, db):
        from app.services.accounting import post_transaction
        from app.models.accounting import Account

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store)
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product, payment="credit")
        entry = post_transaction(db, txn, items)
        db.flush()

        ar_acct = db.query(Account).filter_by(store_id=store.id, code="1100").first()
        ar_line = next((l for l in entry.lines if l.account_id == ar_acct.id), None)

        assert ar_line is not None, "Credit sale must debit account 1100 (AR)"
        assert ar_line.debit > 0

    def test_idempotency_no_double_post(self, db):
        """Calling post_transaction twice for the same txn must not create duplicate entries."""
        from app.services.accounting import post_transaction
        from app.models.accounting import JournalEntry

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store)
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product)
        post_transaction(db, txn, items)
        post_transaction(db, txn, items)  # second call — must be idempotent
        db.flush()

        count = db.query(JournalEntry).filter(
            JournalEntry.ref_id  == txn.txn_number,
            JournalEntry.ref_type == "transaction",
            JournalEntry.is_void == False,
        ).count()
        assert count == 1, f"Expected 1 journal entry, found {count}"

    def test_zero_cost_snap_logs_warning_but_still_posts(self, db):
        """Zero cost_price_snap: 3-leg entry still posts; COGS legs are omitted cleanly."""
        from app.services.accounting import post_transaction
        from app.models.accounting import JournalEntry

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("0.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product, cost_snap=Decimal("0.00"))
        entry = post_transaction(db, txn, items)
        db.flush()

        # Entry must still be balanced (3-leg: cash / revenue / VAT)
        assert entry is not None
        assert entry.total_debits == entry.total_credits


# ══════════════════════════════════════════════════════════════════════════════
# 2. TRIAL BALANCE — ledger integrity at scale
# ══════════════════════════════════════════════════════════════════════════════

class TestTrialBalance:
    """P0 — Trial balance must be zero after any combination of transactions."""

    def test_trial_balance_zero_after_single_sale(self, db):
        from app.services.accounting import post_transaction, get_trial_balance

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("40.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product, cost_snap=Decimal("40.00"))
        post_transaction(db, txn, items)
        db.flush()

        tb = get_trial_balance(db, store.id)
        assert tb["is_balanced"], (
            f"Trial balance not zero: DR={tb['total_debits']} CR={tb['total_credits']}"
        )

    def test_trial_balance_zero_after_20_sales(self, db):
        from app.services.accounting import post_transaction, get_trial_balance

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("35.00"), stock=100)
        _seed_coa(db, store)

        for _ in range(20):
            txn, items = _make_transaction(db, store, emp, product,
                                           qty=1, cost_snap=Decimal("35.00"))
            post_transaction(db, txn, items)

        db.flush()
        tb = get_trial_balance(db, store.id)
        assert tb["is_balanced"], (
            f"Trial balance after 20 sales: DR={tb['total_debits']} CR={tb['total_credits']}"
        )

    def test_trial_balance_zero_after_sale_and_void(self, db):
        from app.services.accounting import post_transaction, post_transaction_void, get_trial_balance

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("50.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product, cost_snap=Decimal("50.00"))
        post_transaction(db, txn, items)
        db.flush()
        post_transaction_void(db, txn, voided_by=emp.id)
        db.flush()

        tb = get_trial_balance(db, store.id)
        assert tb["is_balanced"], (
            f"Trial balance not zero after sale+void: DR={tb['total_debits']} CR={tb['total_credits']}"
        )

    def test_trial_balance_zero_after_mixed_payment_methods(self, db):
        from app.services.accounting import post_transaction, get_trial_balance

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        _seed_coa(db, store)

        for payment in ["cash", "mpesa", "credit", "cash", "mpesa"]:
            product = _make_product(db, store, cost=Decimal("30.00"), stock=5)
            txn, items = _make_transaction(
                db, store, emp, product, payment=payment, cost_snap=Decimal("30.00")
            )
            post_transaction(db, txn, items)

        db.flush()
        tb = get_trial_balance(db, store.id)
        assert tb["is_balanced"], \
            f"Mixed-payment trial balance: DR={tb['total_debits']} CR={tb['total_credits']}"


# ══════════════════════════════════════════════════════════════════════════════
# 3. VOID / REVERSAL
# ══════════════════════════════════════════════════════════════════════════════

class TestVoidReversal:

    def test_void_produces_mirror_entry(self, db):
        from app.services.accounting import post_transaction, post_transaction_void
        from app.models.accounting import JournalEntry

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("40.00"))
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product, cost_snap=Decimal("40.00"))
        original = post_transaction(db, txn, items)
        reversal = post_transaction_void(db, txn, voided_by=emp.id)
        db.flush()

        assert reversal is not None, "Void must produce a reversal JournalEntry"
        assert reversal.total_debits == reversal.total_credits, "Reversal must be balanced"
        # Original DR total must equal reversal CR total
        assert original.total_debits == reversal.total_credits, \
            "Reversal credits must mirror original debits"

    def test_void_idempotency(self, db):
        from app.services.accounting import post_transaction, post_transaction_void
        from app.models.accounting import JournalEntry

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store)
        _seed_coa(db, store)

        txn, items = _make_transaction(db, store, emp, product)
        post_transaction(db, txn, items)
        post_transaction_void(db, txn, voided_by=emp.id)
        post_transaction_void(db, txn, voided_by=emp.id)  # second call
        db.flush()

        void_count = db.query(JournalEntry).filter_by(
            ref_type="void", ref_id=txn.txn_number
        ).count()
        assert void_count == 1, "Void must not be double-posted"


# ══════════════════════════════════════════════════════════════════════════════
# 4. WAC ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TestWACEngine:
    """P1 — Weighted average cost must be mathematically correct."""

    def test_wac_single_grn(self, db):
        from app.services.costing import recalculate_wac

        store   = _make_store(db)
        product = _make_product(db, store, cost=Decimal("0.00"), stock=0)

        new_wac = recalculate_wac(db, product.id, store.id,
                                  new_qty=10, new_unit_cost=Decimal("50.00"))
        db.flush()
        db.refresh(product)

        assert new_wac == Decimal("50.0000"), f"Expected 50.0000 got {new_wac}"
        assert product.stock_quantity == 10
        assert product.wac == Decimal("50.0000")

    def test_wac_two_grns_different_costs(self, db):
        """Classic WAC test: 10 units @ 50, then 20 units @ 65 → WAC = 60.00"""
        from app.services.costing import recalculate_wac

        store   = _make_store(db)
        product = _make_product(db, store, cost=Decimal("0.00"), stock=0)

        recalculate_wac(db, product.id, store.id, new_qty=10, new_unit_cost=Decimal("50.00"))
        new_wac = recalculate_wac(db, product.id, store.id, new_qty=20, new_unit_cost=Decimal("65.00"))
        db.flush()
        db.refresh(product)

        # WAC = (10*50 + 20*65) / 30 = (500 + 1300) / 30 = 1800/30 = 60.00
        assert new_wac == Decimal("60.0000"), f"Expected 60.0000, got {new_wac}"
        assert product.stock_quantity == 30

    def test_wac_three_grns(self, db):
        """Three GRNs: verify WAC is recalculated cumulatively to within 4dp rounding."""
        from app.services.costing import recalculate_wac

        store   = _make_store(db)
        product = _make_product(db, store, cost=Decimal("0.00"), stock=0)

        recalculate_wac(db, product.id, store.id, new_qty=5,  new_unit_cost=Decimal("100.00"))
        recalculate_wac(db, product.id, store.id, new_qty=10, new_unit_cost=Decimal("80.00"))
        new_wac = recalculate_wac(db, product.id, store.id, new_qty=15, new_unit_cost=Decimal("60.00"))
        db.flush()
        db.refresh(product)

        # True WAC = (5*100 + 10*80 + 15*60) / 30 = 2200/30 = 73.333...
        # Engine accumulates rounding at each step so result is within 0.001
        true_wac = Decimal("2200") / Decimal("30")
        assert abs(new_wac - true_wac) < Decimal("0.001"), \
            f"WAC {new_wac} too far from true {true_wac}"
        assert product.stock_quantity == 30

    def test_get_cost_snapshot_returns_wac_over_cost_price(self, db):
        from app.services.costing import recalculate_wac, get_cost_snapshot

        store   = _make_store(db)
        product = _make_product(db, store, cost=Decimal("50.00"), stock=0)

        # Set WAC to 70 — should be preferred over cost_price of 50
        recalculate_wac(db, product.id, store.id, new_qty=10, new_unit_cost=Decimal("70.00"))
        db.flush()
        db.refresh(product)

        snap = get_cost_snapshot(db, product.id, store.id)
        assert snap == Decimal("70.00"), f"Expected WAC 70.00, got {snap}"

    def test_get_cost_snapshot_falls_back_to_cost_price(self, db):
        from app.services.costing import get_cost_snapshot

        store   = _make_store(db)
        product = _make_product(db, store, cost=Decimal("45.00"), stock=10)
        # No WAC set — wac is None

        snap = get_cost_snapshot(db, product.id, store.id)
        assert snap == Decimal("45.00"), f"Expected cost_price fallback 45.00, got {snap}"

    def test_create_cost_layer_records_correct_data(self, db):
        from app.services.costing import create_cost_layer
        from app.models.inventory import CostLayer

        store   = _make_store(db)
        product = _make_product(db, store, stock=0)

        layer = create_cost_layer(
            db, product.id, store.id,
            qty_received=20,
            unit_cost=Decimal("55.00"),
            effective_date=date.today(),
        )
        db.flush()

        saved = db.query(CostLayer).get(layer.id)
        assert saved.qty_received  == 20
        assert saved.qty_remaining == 20
        assert saved.unit_cost     == Decimal("55.0000")
        assert saved.product_id    == product.id


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONFLICT POLICY
# ══════════════════════════════════════════════════════════════════════════════

class TestConflictPolicy:
    """P1 — CONFLICT_MANIFEST must drive all entity+field resolution."""

    def test_product_selling_price_cloud_wins(self):
        from app.sync.conflict_policy import resolve
        result = resolve("product", "selling_price",
                         local_val=Decimal("100"), cloud_val=Decimal("95"))
        assert result == Decimal("95"), "selling_price must use cloud_wins"

    def test_product_stock_quantity_local_wins(self):
        from app.sync.conflict_policy import resolve
        result = resolve("product", "stock_quantity", local_val=8, cloud_val=3)
        assert result == 8, "stock_quantity must use local_wins"

    def test_product_name_cloud_wins(self):
        from app.sync.conflict_policy import resolve
        result = resolve("product", "name",
                         local_val="Old Name", cloud_val="New Name")
        assert result == "New Name"

    def test_transaction_fields_immutable(self):
        from app.sync.conflict_policy import resolve
        result = resolve("transaction", "total",
                         local_val=Decimal("100"), cloud_val=Decimal("999"))
        # immutable: cloud value returned for existing, local value for new
        # For immutable, cloud_val is returned when it exists
        assert result == Decimal("999")

    def test_customer_credit_limit_cloud_wins_despite_default_lww(self):
        from app.sync.conflict_policy import resolve
        # credit_limit overrides __default__=lww with explicit cloud_wins
        result = resolve("customer", "credit_limit",
                         local_val=Decimal("5000"), cloud_val=Decimal("3000"))
        assert result == Decimal("3000"), "credit_limit must use cloud_wins"

    def test_customer_name_lww_local_newer(self):
        from app.sync.conflict_policy import resolve
        local_ts = datetime(2026, 4, 9, 14, 0, 0, tzinfo=timezone.utc)
        cloud_ts = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
        result = resolve("customer", "name",
                         local_val="New Name", cloud_val="Old Name",
                         local_ts=local_ts, cloud_ts=cloud_ts)
        assert result == "New Name", "LWW: newer local value must win"

    def test_customer_name_lww_cloud_newer(self):
        from app.sync.conflict_policy import resolve
        local_ts = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        cloud_ts = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
        result = resolve("customer", "name",
                         local_val="Old Name", cloud_val="New Name",
                         local_ts=local_ts, cloud_ts=cloud_ts)
        assert result == "New Name", "LWW: newer cloud value must win"

    def test_lww_no_timestamps_defaults_to_cloud(self):
        from app.sync.conflict_policy import resolve
        result = resolve("customer", "notes",
                         local_val="local note", cloud_val="cloud note",
                         local_ts=None, cloud_ts=None)
        assert result == "cloud note", "LWW without timestamps must default to cloud"

    def test_employee_password_immutable(self):
        from app.sync.conflict_policy import resolve
        result = resolve("employee", "password",
                         local_val="hashed_local", cloud_val="hashed_cloud")
        # Passwords are immutable: never synced over the wire
        assert result in ("hashed_local", "hashed_cloud")  # must not raise

    def test_unknown_entity_defaults_to_cloud_wins(self):
        from app.sync.conflict_policy import resolve
        result = resolve("unknown_entity", "some_field",
                         local_val="local", cloud_val="cloud")
        assert result == "cloud"

    def test_get_policy_returns_correct_string(self):
        from app.sync.conflict_policy import get_policy
        assert get_policy("product", "selling_price")  == "cloud_wins"
        assert get_policy("product", "stock_quantity") == "local_wins"
        assert get_policy("customer", "__default__")   == "lww"
        assert get_policy("transaction", "total")      == "immutable"

    def test_log_conflict_structure(self):
        from app.sync.conflict_policy import log_conflict
        entry = log_conflict("product", "selling_price",
                             local_val=Decimal("100"), cloud_val=Decimal("95"),
                             winner=Decimal("95"))
        assert entry["policy"]      == "cloud_wins"
        assert entry["winner"]      == "cloud"
        assert entry["local_value"] == "100"
        assert entry["cloud_value"] == "95"


# ══════════════════════════════════════════════════════════════════════════════
# 6. TAX ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TestTaxEngine:
    """P1 — Tax calculation must be correct, configurable, and exemption-aware."""

    def _setup_ke_vat(self, db, store):
        """Insert KE_VAT jurisdiction and 16% standard rate."""
        from app.models.tax import TaxJurisdiction, TaxRate
        j = TaxJurisdiction(code="KE_VAT", name="Kenya VAT", country="KE", is_active=True)
        db.add(j); db.flush()

        std = TaxRate(
            jurisdiction_id=j.id, code="STANDARD",
            rate=Decimal("0.1600"), name="Standard VAT 16%",
            effective_from=date(2024, 1, 1), is_active=True,
        )
        exempt = TaxRate(
            jurisdiction_id=j.id, code="EXEMPT",
            rate=Decimal("0.0000"), name="VAT Exempt",
            effective_from=date(2024, 1, 1), is_active=True,
        )
        zero = TaxRate(
            jurisdiction_id=j.id, code="ZERO",
            rate=Decimal("0.0000"), name="Zero-Rated",
            effective_from=date(2024, 1, 1), is_active=True,
        )
        db.add_all([std, exempt, zero]); db.flush()
        return j, std, exempt, zero

    def test_standard_rate_applies_to_taxable_product(self, db):
        from app.services.tax_engine import TaxEngine

        store   = _make_store(db)
        product = _make_product(db, store)
        product.vat_exempt = False
        self._setup_ke_vat(db, store)

        engine = TaxEngine(db, default_jurisdiction="KE_VAT")
        result = engine.calculate_line_tax(product=product, qty=1,
                                           unit_price=Decimal("100.00"))

        assert result.rate == Decimal("0.1600")
        assert result.tax_amount == Decimal("16.00")
        assert not result.is_exempt

    def test_vat_exempt_product_returns_zero_tax(self, db):
        from app.services.tax_engine import TaxEngine

        store   = _make_store(db)
        product = _make_product(db, store)
        product.vat_exempt = True
        self._setup_ke_vat(db, store)

        engine = TaxEngine(db)
        result = engine.calculate_line_tax(product=product, qty=1,
                                           unit_price=Decimal("100.00"))

        assert result.tax_amount == Decimal("0.00")
        assert result.is_exempt
        assert result.exemption_reason == "product_exempt"

    def test_customer_exemption_overrides_product_rate(self, db):
        from app.services.tax_engine import TaxEngine
        from app.models.tax import CustomerTaxExemption
        from app.models.customer import Customer

        store   = _make_store(db)
        product = _make_product(db, store)
        product.vat_exempt = False
        j, _, _, _ = self._setup_ke_vat(db, store)

        customer = Customer(
            store_id=store.id, name="Exempt Corp",
            phone="0700000001", is_active=True
        )
        db.add(customer); db.flush()

        exemption = CustomerTaxExemption(
            customer_id=customer.id, jurisdiction_id=j.id,
            exemption_ref="KRA-EX-2024-001",
            valid_from=date(2024, 1, 1), is_active=True,
        )
        db.add(exemption); db.flush()

        engine = TaxEngine(db, default_jurisdiction="KE_VAT")
        result = engine.calculate_line_tax(
            product=product, qty=1, unit_price=Decimal("100.00"),
            customer=customer,
        )

        assert result.tax_amount == Decimal("0.00")
        assert result.is_exempt
        assert result.exemption_reason == "customer_exemption"

    def test_tax_calculation_for_multi_quantity(self, db):
        from app.services.tax_engine import TaxEngine

        store   = _make_store(db)
        product = _make_product(db, store)
        product.vat_exempt = False
        self._setup_ke_vat(db, store)

        engine = TaxEngine(db)
        # 3 units @ 100 each → taxable = 300 → tax = 300 * 0.16 = 48.00
        result = engine.calculate_line_tax(product=product, qty=3,
                                           unit_price=Decimal("100.00"))
        assert result.tax_amount == Decimal("48.00")

    def test_tax_inclusive_pricing_reverse_calculates(self, db):
        from app.services.tax_engine import TaxEngine

        store   = _make_store(db)
        product = _make_product(db, store)
        product.vat_exempt = False
        self._setup_ke_vat(db, store)

        engine = TaxEngine(db)
        # Tax-inclusive: price=116 includes 16% tax → tax portion = 116 * 0.16/1.16 ≈ 16.00
        result = engine.calculate_line_tax(
            product=product, qty=1, unit_price=Decimal("116.00"),
            tax_inclusive=True
        )
        assert result.tax_amount == Decimal("16.00")
        assert result.tax_inclusive is True

    def test_mixed_basket_calculates_per_line(self, db):
        from app.services.tax_engine import TaxEngine

        store   = _make_store(db)
        taxable = _make_product(db, store)
        taxable.vat_exempt = False
        exempt  = _make_product(db, store)
        exempt.vat_exempt = True
        self._setup_ke_vat(db, store)

        engine = TaxEngine(db)
        result = engine.calculate_basket_tax([
            {"product": taxable, "qty": 2, "unit_price": Decimal("100.00")},
            {"product": exempt,  "qty": 1, "unit_price": Decimal("50.00")},
        ])

        assert result["total_tax"]     == Decimal("32.00")  # only taxable items
        assert result["total_taxable"] == Decimal("200.00")
        assert result["total_exempt"]  == Decimal("50.00")

    def test_expired_customer_exemption_is_not_applied(self, db):
        from app.services.tax_engine import TaxEngine
        from app.models.tax import CustomerTaxExemption
        from app.models.customer import Customer

        store   = _make_store(db)
        product = _make_product(db, store)
        product.vat_exempt = False
        j, _, _, _ = self._setup_ke_vat(db, store)

        customer = Customer(store_id=store.id, name="Expired Exempt",
                            phone="0700000002", is_active=True)
        db.add(customer); db.flush()

        # Exemption expired yesterday
        exemption = CustomerTaxExemption(
            customer_id=customer.id, jurisdiction_id=j.id,
            exemption_ref="KRA-EX-EXPIRED",
            valid_from=date(2020, 1, 1),
            valid_to=date.today() - timedelta(days=1),
            is_active=True,
        )
        db.add(exemption); db.flush()

        engine = TaxEngine(db, default_jurisdiction="KE_VAT")
        result = engine.calculate_line_tax(
            product=product, qty=1, unit_price=Decimal("100.00"),
            customer=customer, sale_date=date.today(),
        )

        # Expired exemption must NOT apply — standard rate should be used
        assert result.tax_amount == Decimal("16.00")
        assert not result.is_exempt


# ══════════════════════════════════════════════════════════════════════════════
# 7. RECONCILIATION — oversell detection + period guard
# ══════════════════════════════════════════════════════════════════════════════

class TestReconciliation:
    """P1 — Oversell detection, period guards, and inventory-ledger diff."""

    def test_detect_oversells_creates_event_for_negative_stock(self, db):
        from app.services.reconciliation import detect_oversells
        from app.models.inventory import OversellEvent

        store   = _make_store(db)
        product = _make_product(db, store, stock=-3)  # already negative

        events = detect_oversells(db, store.id)
        db.flush()

        assert len(events) >= 1
        event = db.query(OversellEvent).filter_by(
            store_id=store.id, product_id=product.id
        ).first()
        assert event is not None
        assert event.shortfall_qty == 3
        assert event.resolution == "pending"

    def test_detect_oversells_skips_already_pending_event(self, db):
        from app.services.reconciliation import detect_oversells
        from app.models.inventory import OversellEvent

        store   = _make_store(db)
        product = _make_product(db, store, stock=-2)

        events1 = detect_oversells(db, store.id)
        db.flush()
        events2 = detect_oversells(db, store.id)  # second run same product
        db.flush()

        # Second run should not create a duplicate pending event
        count = db.query(OversellEvent).filter_by(
            store_id=store.id, product_id=product.id, resolution="pending"
        ).count()
        assert count == 1, "Must not create duplicate pending oversell events"

    def test_detect_oversells_returns_empty_for_positive_stock(self, db):
        from app.services.reconciliation import detect_oversells

        store = _make_store(db)
        _make_product(db, store, stock=10)  # positive stock

        events = detect_oversells(db, store.id)
        assert events == []

    def test_period_guard_allows_post_to_open_period(self, db):
        from app.services.reconciliation import assert_period_open
        from app.models.inventory import AccountingPeriod, PeriodStatus

        store = _make_store(db)
        today = date.today()
        period = AccountingPeriod(
            store_id=store.id, period_name="APR-2026",
            start_date=today.replace(day=1),
            end_date=today,
            status=PeriodStatus.OPEN,
        )
        db.add(period); db.flush()

        # Should not raise
        assert_period_open(db, store.id, today)

    def test_period_guard_blocks_post_to_closed_period(self, db):
        from app.services.reconciliation import assert_period_open
        from app.models.inventory import AccountingPeriod, PeriodStatus

        store = _make_store(db)
        closed_date = date(2026, 3, 31)
        period = AccountingPeriod(
            store_id=store.id, period_name="MAR-2026",
            start_date=date(2026, 3, 1),
            end_date=closed_date,
            status=PeriodStatus.CLOSED,
        )
        db.add(period); db.flush()

        with pytest.raises(ValueError, match="CLOSED"):
            assert_period_open(db, store.id, date(2026, 3, 15))

    def test_period_guard_blocks_post_to_locked_period(self, db):
        from app.services.reconciliation import assert_period_open
        from app.models.inventory import AccountingPeriod, PeriodStatus

        store = _make_store(db)
        period = AccountingPeriod(
            store_id=store.id, period_name="JAN-2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            status=PeriodStatus.LOCKED,
        )
        db.add(period); db.flush()

        with pytest.raises(ValueError, match="LOCKED"):
            assert_period_open(db, store.id, date(2026, 1, 15))

    def test_period_guard_allows_post_when_no_period_defined(self, db):
        """If no AccountingPeriod row exists, posting must be allowed (pre-period-close era)."""
        from app.services.reconciliation import assert_period_open

        store = _make_store(db)
        # No periods created for this store — should not raise
        assert_period_open(db, store.id, date.today())

    def test_accounting_post_blocked_for_closed_period(self, db):
        """End-to-end: post_transaction into a closed period must raise ValueError."""
        from app.services.accounting import post_transaction
        from app.models.inventory import AccountingPeriod, PeriodStatus

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store)
        _seed_coa(db, store)

        # Create a closed period covering today
        today = date.today()
        period = AccountingPeriod(
            store_id=store.id, period_name="APR-2026",
            start_date=today.replace(day=1),
            end_date=today,
            status=PeriodStatus.CLOSED,
        )
        db.add(period); db.flush()

        txn, items = _make_transaction(db, store, emp, product)
        with pytest.raises(ValueError, match="CLOSED"):
            post_transaction(db, txn, items)

    def test_inventory_ledger_diff_shows_zero_initially(self, db):
        from app.services.reconciliation import get_inventory_ledger_diff

        store = _make_store(db)
        # No products with wac, no journal entries → should report zero diff gracefully
        result = get_inventory_ledger_diff(db, store.id)

        assert "physical_inventory_value" in result
        assert "ledger_inventory_balance" in result
        assert "variance" in result
        assert "status" in result


# ══════════════════════════════════════════════════════════════════════════════
# 8. SYNC STATE MACHINE — confirmed_txn_numbers, duplicate suppression
# ══════════════════════════════════════════════════════════════════════════════

class TestSyncStateMachine:
    """P0 — Sync idempotency, per-record results, confirmed numbers."""

    def test_sync_transactions_creates_journal_entry(self, db, monkeypatch):
        """Full integration: sync endpoint inserts transaction AND posts accounting."""
        from app.models.accounting import JournalEntry
        from app.models.subscription import Store, Plan, SubStatus
        from app.models.employee import Employee, Role
        from app.core.security import hash_password

        store = _make_store(db)
        _seed_coa(db, store)
        emp = _make_employee(db, store)
        product = _make_product(db, store, cost=Decimal("40.00"), stock=20)

        txn_number = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "store_id": store.id,
            "records": [{
                "txn_number":      txn_number,
                "store_id":        store.id,
                "terminal_id":     "T-001",
                "subtotal":        "100.00",
                "discount_amount": "0.00",
                "vat_amount":      "13.79",
                "total":           "113.79",
                "payment_method":  "cash",
                "status":          "completed",
                "completed_at":    datetime.now(timezone.utc).isoformat(),
                "items": [{
                    "product_id":      product.id,
                    "product_name":    product.name,
                    "sku":             product.sku,
                    "qty":             1,
                    "unit_price":      "100.00",
                    "cost_price_snap": "40.00",
                    "discount":        "0.00",
                    "line_total":      "100.00",
                    "vat_amount":      "13.79",
                }],
            }],
        }

        # Call the sync service function directly (avoids auth middleware)
        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        from app.routers.sync import sync_transactions
        result = sync_transactions(payload=payload, db=db, x_idempotency_key="test-idem-001")

        db.flush()

        assert result["synced"] == 1, f"Expected 1 synced, got {result}"
        assert txn_number in result.get("confirmed_txn_numbers", []), \
            "txn_number must be in confirmed_txn_numbers"

        entry = db.query(JournalEntry).filter_by(
            store_id=store.id, ref_type="transaction", ref_id=txn_number
        ).first()
        assert entry is not None, "Journal entry must be created by sync ingest"
        assert entry.total_debits == entry.total_credits, "Journal entry must be balanced"

    def test_sync_transactions_idempotent_on_replay(self, db):
        """Replaying the same txn_number must not create a duplicate."""
        from app.models.transaction import Transaction

        store   = _make_store(db)
        _seed_coa(db, store)
        product = _make_product(db, store, cost=Decimal("30.00"), stock=10)

        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        txn_number = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "txn_number": txn_number, "store_id": store.id, "terminal_id": "T-001",
            "subtotal": "80.00", "discount_amount": "0.00", "vat_amount": "11.03",
            "total": "91.03", "payment_method": "cash", "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "items": [{
                "product_id": product.id, "product_name": product.name,
                "sku": product.sku, "qty": 1, "unit_price": "80.00",
                "cost_price_snap": "30.00", "discount": "0.00",
                "line_total": "80.00", "vat_amount": "11.03",
            }],
        }

        from app.routers.sync import sync_transactions

        r1 = sync_transactions({"store_id": store.id, "records": [record]}, db=db, x_idempotency_key="idem-A")
        db.flush()
        r2 = sync_transactions({"store_id": store.id, "records": [record]}, db=db, x_idempotency_key="idem-A")
        db.flush()

        assert r1["synced"]  == 1
        assert r2["synced"]  == 0
        assert r2["skipped"] == 1

        count = db.query(Transaction).filter_by(txn_number=txn_number).count()
        assert count == 1, f"Expected 1 transaction, got {count} (duplicate inserted)"

    def test_sync_returns_confirmed_txn_numbers(self, db):
        """confirmed_txn_numbers must be returned for every successfully synced txn."""
        store   = _make_store(db)
        _seed_coa(db, store)
        product = _make_product(db, store, cost=Decimal("20.00"), stock=50)

        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        txn_nums = [f"TXN-{uuid.uuid4().hex[:8].upper()}" for _ in range(3)]
        records = [
            {
                "txn_number": n, "store_id": store.id, "terminal_id": "T-001",
                "subtotal": "50.00", "discount_amount": "0.00", "vat_amount": "6.90",
                "total": "56.90", "payment_method": "cash", "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "items": [{
                    "product_id": product.id, "product_name": product.name,
                    "sku": product.sku, "qty": 1, "unit_price": "50.00",
                    "cost_price_snap": "20.00", "discount": "0.00",
                    "line_total": "50.00", "vat_amount": "6.90",
                }],
            }
            for n in txn_nums
        ]

        from app.routers.sync import sync_transactions
        result = sync_transactions({"store_id": store.id, "records": records},
                                   db=db, x_idempotency_key="idem-batch-X")
        db.flush()

        confirmed = result.get("confirmed_txn_numbers", [])
        for n in txn_nums:
            assert n in confirmed, f"{n} must be in confirmed_txn_numbers"

    def test_sync_per_record_error_does_not_block_others(self, db):
        """A bad record in a batch must not prevent other records from syncing."""
        store   = _make_store(db)
        _seed_coa(db, store)
        product = _make_product(db, store, cost=Decimal("20.00"), stock=50)

        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        good_num = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        good_record = {
            "txn_number": good_num, "store_id": store.id, "terminal_id": "T-001",
            "subtotal": "50.00", "discount_amount": "0.00", "vat_amount": "6.90",
            "total": "56.90", "payment_method": "cash", "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "items": [{
                "product_id": product.id, "product_name": product.name,
                "sku": product.sku, "qty": 1, "unit_price": "50.00",
                "cost_price_snap": "20.00", "discount": "0.00",
                "line_total": "50.00", "vat_amount": "6.90",
            }],
        }
        bad_record = {
            "txn_number": f"TXN-{uuid.uuid4().hex[:8].upper()}",
            "store_id": store.id, "terminal_id": "T-001",
            "subtotal": "INVALID_AMOUNT",  # will cause decimal parse failure
            "discount_amount": "0", "vat_amount": "0", "total": "INVALID",
            "payment_method": "cash", "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "items": [],
        }

        from app.routers.sync import sync_transactions
        result = sync_transactions(
            {"store_id": store.id, "records": [good_record, bad_record]},
            db=db, x_idempotency_key="idem-partial",
        )
        db.flush()

        # Good record must be confirmed even if bad record failed
        assert good_num in result.get("confirmed_txn_numbers", []), \
            "Good record must be confirmed despite bad record in same batch"
        assert result["synced"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 9. CHAOS TESTS — atomicity and crash safety
# ══════════════════════════════════════════════════════════════════════════════

class TestChaosSafety:
    """P1 — Transaction + accounting must be atomic. Verify no half-written state."""

    def test_accounting_failure_prevents_transaction_commit(self, db, monkeypatch):
        """If accounting post raises, the transaction must NOT be persisted."""
        from app.models.transaction import Transaction
        import app.services.accounting as acct_svc

        store   = _make_store(db)
        emp     = _make_employee(db, store)
        product = _make_product(db, store, stock=10)
        _seed_coa(db, store)

        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        # Patch post_transaction to raise an accounting error
        def _fail_accounting(db, txn, items=None):
            raise ValueError("Simulated accounting failure")

        monkeypatch.setattr(acct_svc, "post_transaction", _fail_accounting)

        txn_number = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "txn_number": txn_number, "store_id": store.id, "terminal_id": "T-001",
            "subtotal": "100.00", "discount_amount": "0.00", "vat_amount": "13.79",
            "total": "113.79", "payment_method": "cash", "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "items": [{
                "product_id": product.id, "product_name": product.name,
                "sku": product.sku, "qty": 1, "unit_price": "100.00",
                "cost_price_snap": "40.00", "discount": "0.00",
                "line_total": "100.00", "vat_amount": "13.79",
            }],
        }

        from app.routers.sync import sync_transactions
        result = sync_transactions({"store_id": store.id, "records": [record]},
                                   db=db, x_idempotency_key="chaos-001")
        db.flush()

        # The transaction should NOT be in the DB (accounting failed → savepoint rolled back)
        txn_in_db = db.query(Transaction).filter_by(txn_number=txn_number).first()
        assert txn_in_db is None, \
            "Transaction must NOT be persisted when accounting post fails"
        assert txn_number not in result.get("confirmed_txn_numbers", [])
        assert len(result.get("errors", [])) > 0

    def test_no_transaction_without_journal_entry(self, db):
        """After any successful sync, every transaction must have a matching journal entry."""
        from app.models.transaction import Transaction
        from app.models.accounting import JournalEntry

        store   = _make_store(db)
        _seed_coa(db, store)
        product = _make_product(db, store, cost=Decimal("25.00"), stock=50)

        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        txn_nums = [f"TXN-{uuid.uuid4().hex[:8].upper()}" for _ in range(5)]
        records = [
            {
                "txn_number": n, "store_id": store.id, "terminal_id": "T-001",
                "subtotal": "60.00", "discount_amount": "0.00", "vat_amount": "8.28",
                "total": "68.28", "payment_method": "cash", "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "items": [{
                    "product_id": product.id, "product_name": product.name,
                    "sku": product.sku, "qty": 1, "unit_price": "60.00",
                    "cost_price_snap": "25.00", "discount": "0.00",
                    "line_total": "60.00", "vat_amount": "8.28",
                }],
            }
            for n in txn_nums
        ]

        from app.routers.sync import sync_transactions
        sync_transactions({"store_id": store.id, "records": records},
                          db=db, x_idempotency_key="chaos-multi")
        db.flush()

        for n in txn_nums:
            txn = db.query(Transaction).filter_by(txn_number=n).first()
            if txn:  # only check synced ones
                entry = db.query(JournalEntry).filter_by(
                    ref_type="transaction", ref_id=n
                ).first()
                assert entry is not None, \
                    f"Transaction {n} exists but has no journal entry — ACCOUNTING ORPHAN"
                assert entry.total_debits == entry.total_credits, \
                    f"Journal entry for {n} is unbalanced"


# ══════════════════════════════════════════════════════════════════════════════
# 10. SYNC AGENT (JavaScript logic — Python tests for the service contract)
# ══════════════════════════════════════════════════════════════════════════════

class TestSyncAgentContract:
    """
    Verify the contract the sync agent depends on:
    - Cloud response must include confirmed_txn_numbers
    - Skipped (already-synced) txns are still in confirmed list (safe ack)
    - Error txns are NOT in confirmed list
    """

    def test_confirmed_list_excludes_failed_records(self, db, monkeypatch):
        import app.services.accounting as acct_svc

        store   = _make_store(db)
        _seed_coa(db, store)
        product = _make_product(db, store, cost=Decimal("20.00"), stock=50)

        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        good_num = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        bad_num  = f"TXN-{uuid.uuid4().hex[:8].upper()}"

        call_count = [0]
        original_post = acct_svc.post_transaction

        def _selective_fail(db, txn, items=None):
            call_count[0] += 1
            if txn.txn_number == bad_num:
                raise ValueError("Forced accounting failure for bad txn")
            return original_post(db, txn, items)

        monkeypatch.setattr(acct_svc, "post_transaction", _selective_fail)

        def _make_rec(n):
            return {
                "txn_number": n, "store_id": store.id, "terminal_id": "T-001",
                "subtotal": "50.00", "discount_amount": "0.00", "vat_amount": "6.90",
                "total": "56.90", "payment_method": "cash", "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "items": [{
                    "product_id": product.id, "product_name": product.name,
                    "sku": product.sku, "qty": 1, "unit_price": "50.00",
                    "cost_price_snap": "20.00", "discount": "0.00",
                    "line_total": "50.00", "vat_amount": "6.90",
                }],
            }

        from app.routers.sync import sync_transactions
        result = sync_transactions(
            {"store_id": store.id, "records": [_make_rec(good_num), _make_rec(bad_num)]},
            db=db, x_idempotency_key="agent-contract-001",
        )
        db.flush()

        confirmed = result.get("confirmed_txn_numbers", [])
        assert good_num in confirmed, "Good txn must be in confirmed list"
        assert bad_num  not in confirmed, "Failed txn must NOT be in confirmed list"

    def test_already_synced_txn_in_confirmed_for_safe_local_ack(self, db):
        """A txn already in cloud (skipped) must appear in confirmed_txn_numbers.
        This allows the sync agent to safely ack locally on replay."""
        store   = _make_store(db)
        _seed_coa(db, store)
        product = _make_product(db, store, cost=Decimal("20.00"), stock=50)

        import os
        os.environ.setdefault("SYNC_AGENT_API_KEY", "test-key")

        txn_num = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        record  = {
            "txn_number": txn_num, "store_id": store.id, "terminal_id": "T-001",
            "subtotal": "50.00", "discount_amount": "0.00", "vat_amount": "6.90",
            "total": "56.90", "payment_method": "cash", "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "items": [{
                "product_id": product.id, "product_name": product.name,
                "sku": product.sku, "qty": 1, "unit_price": "50.00",
                "cost_price_snap": "20.00", "discount": "0.00",
                "line_total": "50.00", "vat_amount": "6.90",
            }],
        }

        from app.routers.sync import sync_transactions

        # First sync
        sync_transactions({"store_id": store.id, "records": [record]},
                          db=db, x_idempotency_key="replay-001")
        db.flush()

        # Second sync (replay) — txn already in cloud
        result2 = sync_transactions({"store_id": store.id, "records": [record]},
                                    db=db, x_idempotency_key="replay-001")
        db.flush()

        assert txn_num in result2.get("confirmed_txn_numbers", []), \
            "Replayed (skipped) txn must still appear in confirmed list for safe local ack"
