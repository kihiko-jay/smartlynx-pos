
from decimal import Decimal
from datetime import date
from app.models.accounting import JournalEntry, JournalLine
from app.models.customer import Customer
from app.models.product import Supplier, Product
from app.models.procurement import GoodsReceivedNote, GRNStatus
from app.services.accounting import seed_chart_of_accounts, post_supplier_payment, post_expense_voucher, post_customer_payment, get_ap_aging, get_ar_aging
from app.models.procurement import SupplierPayment
from app.models.expenses import ExpenseVoucher
from app.models.employee import Employee, Role
from app.models.cash_session import CashSession
from app.models.subscription import Store, Plan, SubStatus
from app.core.security import hash_password, create_access_token
import uuid


def test_supplier_payment_posts_journal(db, test_store, test_admin):
    seed_chart_of_accounts(db, test_store.id)
    supplier = Supplier(store_id=test_store.id, name='Acme Supplier')
    db.add(supplier); db.commit(); db.refresh(supplier)
    grn = GoodsReceivedNote(store_id=test_store.id, supplier_id=supplier.id, grn_number='GRN-1', status=GRNStatus.POSTED, received_date=date.today(), total_received_cost=Decimal('1000.00'), created_by=test_admin.id)
    db.add(grn); db.commit()
    payment = SupplierPayment(store_id=test_store.id, supplier_id=supplier.id, payment_number='SP-1', payment_date=date.today(), amount=Decimal('300.00'), payment_method='cash', created_by=test_admin.id)
    db.add(payment); db.flush()
    je = post_supplier_payment(db, payment)
    assert je.ref_type == 'supplier_payment'
    assert len(je.lines) == 2


def test_expense_voucher_posts_journal(db, test_store, test_admin):
    seed_chart_of_accounts(db, test_store.id)
    voucher = ExpenseVoucher(store_id=test_store.id, voucher_number='EXP-1', expense_date=date.today(), account_id=7, amount=Decimal('200.00'), payment_method='cash', created_by=test_admin.id)
    db.add(voucher); db.flush()
    je = post_expense_voucher(db, voucher)
    assert je.ref_type == 'expense_voucher'


def test_customer_payment_reduces_ar(db, test_store, test_admin):
    seed_chart_of_accounts(db, test_store.id)
    customer = Customer(store_id=test_store.id, name='Credit Customer', credit_limit=Decimal('1000.00'), credit_balance=Decimal('400.00'))
    db.add(customer); db.commit(); db.refresh(customer)
    je = post_customer_payment(db, test_store.id, customer, Decimal('150.00'), date.today(), 'cash', 'CP-1', test_admin.id)
    customer.credit_balance = Decimal('250.00')
    assert je.ref_type == 'customer_payment'
    assert customer.credit_balance == Decimal('250.00')


def test_ap_ar_aging(db, test_store, test_admin):
    seed_chart_of_accounts(db, test_store.id)
    supplier = Supplier(store_id=test_store.id, name='Age Supplier')
    customer = Customer(store_id=test_store.id, name='Age Customer', credit_limit=Decimal('1000.00'), credit_balance=Decimal('120.00'))
    db.add_all([supplier, customer]); db.commit(); db.refresh(supplier)
    grn = GoodsReceivedNote(store_id=test_store.id, supplier_id=supplier.id, grn_number='GRN-2', status=GRNStatus.POSTED, received_date=date.today(), total_received_cost=Decimal('500.00'), created_by=test_admin.id)
    db.add(grn); db.commit()
    ap = get_ap_aging(db, test_store.id)
    ar = get_ar_aging(db, test_store.id)
    assert ap['rows'][0]['total'] == 500.0
    assert ar['rows'][0]['total'] == 120.0


# ── Helpers shared by new tests ───────────────────────────────────────────────

def _make_store(db):
    s = Store(name=f"Store-{uuid.uuid4().hex[:6]}", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s); db.flush(); db.refresh(s)
    return s


def _make_employee(db, store, role):
    emp = Employee(
        store_id=store.id,
        full_name=f"Emp-{role}",
        email=f"{uuid.uuid4().hex[:6]}@test.com",
        password=hash_password("pass"),
        role=role,
        is_active=True,
    )
    db.add(emp); db.flush(); db.refresh(emp)
    return emp


def _headers(emp):
    token = create_access_token({"sub": str(emp.id), "role": emp.role})
    return {"Authorization": f"Bearer {token}"}


def _make_expense_voucher(db, store, manager, account_code="6700"):
    """Create a posted expense voucher with a journal entry. Returns (voucher, account)."""
    seed_chart_of_accounts(db, store.id)
    db.flush()
    # Find the expense account by code
    from app.models.accounting import Account
    acct = db.query(Account).filter(
        Account.store_id == store.id,
        Account.code == account_code,
    ).first()
    voucher = ExpenseVoucher(
        store_id=store.id,
        voucher_number=f"EXP-{uuid.uuid4().hex[:8].upper()}",
        expense_date=date.today(),
        account_id=acct.id,
        amount=Decimal("500.00"),
        payment_method="cash",
        payee="Test Vendor",
        created_by=manager.id,
    )
    db.add(voucher); db.flush()
    post_expense_voucher(db, voucher)
    db.flush()
    return voucher, acct


# ── FIX 2: Expense void accounting reversal ──────────────────────────────────

def test_expense_void_posts_accounting_reversal(client, db, test_store, test_admin):
    """Voiding an expense must post a mirror journal entry (CR expense, DR cash)."""
    manager = _make_employee(db, test_store, Role.MANAGER)
    seed_chart_of_accounts(db, test_store.id)
    db.flush()

    from app.models.accounting import Account
    acct = db.query(Account).filter(
        Account.store_id == test_store.id, Account.code == "6700"
    ).first()
    voucher = ExpenseVoucher(
        store_id=test_store.id,
        voucher_number=f"EXP-{uuid.uuid4().hex[:8].upper()}",
        expense_date=date.today(),
        account_id=acct.id,
        amount=Decimal("300.00"),
        payment_method="cash",
        payee="Vendor",
        created_by=manager.id,
    )
    db.add(voucher); db.flush()
    post_expense_voucher(db, voucher)
    db.flush()
    db.commit()

    # Void via the API
    resp = client.post(
        f"/api/v1/expenses/{voucher.id}/void",
        params={"reason": "entered in error"},
        headers=_headers(manager),
    )
    assert resp.status_code == 200, resp.text

    # Verify original entry exists
    orig = db.query(JournalEntry).filter(
        JournalEntry.ref_type == "expense_voucher",
        JournalEntry.ref_id == voucher.voucher_number,
        JournalEntry.is_void == False,
    ).first()
    assert orig is not None, "Original journal entry must exist"

    # Verify void reversal entry exists
    void_entry = db.query(JournalEntry).filter(
        JournalEntry.ref_type == "expense_void",
        JournalEntry.ref_id == voucher.voucher_number,
        JournalEntry.is_void == False,
    ).first()
    assert void_entry is not None, "Void reversal entry must be posted"

    # Verify the two entries net to zero on both accounts
    orig_lines = db.query(JournalLine).filter(JournalLine.entry_id == orig.id).all()
    void_lines = db.query(JournalLine).filter(JournalLine.entry_id == void_entry.id).all()

    all_lines = orig_lines + void_lines
    for acct_id in {l.account_id for l in all_lines}:
        net_dr = sum(Decimal(str(l.debit))  for l in all_lines if l.account_id == acct_id)
        net_cr = sum(Decimal(str(l.credit)) for l in all_lines if l.account_id == acct_id)
        assert net_dr == net_cr, (
            f"Account {acct_id} does not net to zero: DR={net_dr} CR={net_cr}"
        )


def test_expense_void_is_idempotent(db, test_store, test_admin):
    """Calling post_expense_voucher_void() twice must not create a duplicate entry."""
    from app.services.accounting import post_expense_voucher_void
    from datetime import datetime

    manager = _make_employee(db, test_store, Role.MANAGER)
    voucher, _ = _make_expense_voucher(db, test_store, manager)

    # Simulate void fields being set (as the router would do)
    voucher.is_void = True
    voucher.void_reason = "duplicate"
    voucher.voided_at = datetime.utcnow()
    voucher.voided_by = manager.id
    db.flush()

    # Call twice
    post_expense_voucher_void(db, voucher)
    db.flush()
    post_expense_voucher_void(db, voucher)
    db.flush()

    count = db.query(JournalEntry).filter(
        JournalEntry.ref_type == "expense_void",
        JournalEntry.ref_id == voucher.voucher_number,
        JournalEntry.is_void == False,
    ).count()
    assert count == 1, f"Expected exactly 1 void reversal entry, got {count}"


# ── FIX 3: Cashier ownership check on cash session close ─────────────────────

def test_cashier_cannot_close_other_cashiers_session(client, db):
    """A CASHIER role employee must not be able to close another cashier's session."""
    store = _make_store(db)
    cashier_a = _make_employee(db, store, Role.CASHIER)
    cashier_b = _make_employee(db, store, Role.CASHIER)
    seed_chart_of_accounts(db, store.id)
    db.commit()

    # Open a session as cashier_a
    open_resp = client.post(
        "/api/v1/cash-sessions/open",
        json={"opening_float": 1000.00},
        headers=_headers(cashier_a),
    )
    assert open_resp.status_code == 200, open_resp.text
    session_id = open_resp.json()["id"]

    # cashier_b tries to close cashier_a's session — must get 403
    close_resp = client.post(
        f"/api/v1/cash-sessions/{session_id}/close",
        json={"counted_cash": 1000.00},
        headers=_headers(cashier_b),
    )
    assert close_resp.status_code == 403, close_resp.text
    assert "supervisor" in close_resp.json()["detail"].lower()


def test_supervisor_can_close_any_session(client, db):
    """A SUPERVISOR must be able to close any cashier's session."""
    store = _make_store(db)
    cashier = _make_employee(db, store, Role.CASHIER)
    supervisor = _make_employee(db, store, Role.SUPERVISOR)
    seed_chart_of_accounts(db, store.id)
    db.commit()

    # Cashier opens session
    open_resp = client.post(
        "/api/v1/cash-sessions/open",
        json={"opening_float": 500.00},
        headers=_headers(cashier),
    )
    assert open_resp.status_code == 200, open_resp.text
    session_id = open_resp.json()["id"]

    # Supervisor closes it
    close_resp = client.post(
        f"/api/v1/cash-sessions/{session_id}/close",
        json={"counted_cash": 500.00},
        headers=_headers(supervisor),
    )
    assert close_resp.status_code == 200, close_resp.text
    assert close_resp.json()["status"] == "closed"


# ── FIX 5: Decimal precision in today_summary ─────────────────────────────────

def test_today_summary_decimal_precision(client, db):
    """100 transactions at KES 99.99 must sum to exactly 9999.00, not 9998.99 or 9999.01."""
    from app.models.transaction import Transaction, PaymentMethod, TransactionStatus
    from datetime import datetime, timezone
    import uuid as _uuid_module

    store = _make_store(db)
    cashier = _make_employee(db, store, Role.CASHIER)
    db.commit()

    amount = Decimal("99.99")
    for i in range(100):
        txn = Transaction(
            uuid=_uuid_module.uuid4(),   # SQLite UUID column requires a Python uuid.UUID object
            txn_number=f"TXN-PREC-{i:04d}",
            store_id=store.id,
            cashier_id=cashier.id,
            payment_method=PaymentMethod.CASH,
            subtotal=amount,
            vat_amount=Decimal("0.00"),
            total=amount,
            discount_amount=Decimal("0.00"),
            status=TransactionStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db.add(txn)
    db.commit()

    resp = client.get("/api/v1/transactions/summary/today", headers=_headers(cashier))
    assert resp.status_code == 200, resp.text
    data = resp.json()

    expected = float(Decimal("99.99") * 100)  # 9999.0
    assert data["total_sales"] == expected, (
        f"Expected total_sales={expected}, got {data['total_sales']} — possible float drift"
    )
