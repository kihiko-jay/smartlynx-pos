"""
tests/test_returns.py — Returns & Refunds test suite

Coverage
────────
A. create_return
   A1  Full restorable cash return — happy path
   A2  Partial return (subset of items)
   A3  Partial qty return (less than original qty)
   A4  Damaged / non-restorable item
   A5  Mixed return (one restorable, one damaged)
   A6  Duplicate item in request → 422
   A7  Return against VOIDED transaction → 400
   A8  qty_returned > original qty → 400
   A9  Exceed remaining returnable qty (second return) → 400
   A10 Cross-store return attempt → 403
   A11 Wrong transaction item (item from another txn) → 400
   A12 Non-existent transaction → 404

B. approve_and_complete
   B1  Cashier cannot approve → 403
   B2  Happy path: stock restored, accounting posted, status=COMPLETED
   B3  Approve already-completed return → 400
   B4  Approve rejected return → 400
   B5  Damaged item: no stock change, but revenue/VAT reversed
   B6  Snapshot totals are saved correctly

C. reject_return
   C1  Cashier cannot reject → 403
   C2  Happy path: status=REJECTED, no stock/accounting changes
   C3  Reject already-rejected return → 400
   C4  Reject completed return → 400

D. list / get returns
   D1  Cashier can view returns for own store
   D2  Status filter works
   D3  original_txn_id filter works
   D4  /transactions/{id}/returns works

E. Accounting invariants
   E1  Journal entry is balanced (DR == CR) for restorable return
   E2  Journal entry is balanced for damaged return
   E3  post_return is idempotent (second call returns existing entry, no duplicate)

F. Stock invariants
   F1  stock_quantity increases by qty_returned for restorable items
   F2  stock_quantity unchanged for damaged items
   F3  StockMovement record created with movement_type='return' for restorable
   F4  No StockMovement for damaged items
"""

from __future__ import annotations

import pytest
from decimal import Decimal

from app.core.security import create_access_token, hash_password
from app.models.accounting import Account, JournalEntry, JournalLine
from app.models.employee import Employee, Role
from app.models.product import Product, StockMovement
from app.models.returns import ReturnStatus, ReturnTransaction
from app.models.subscription import Store, Plan, SubStatus
from app.models.transaction import (
    Transaction, TransactionItem, PaymentMethod, TransactionStatus,
)
from app.services.accounting import seed_chart_of_accounts


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(db):
    s = Store(name="Test Store", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s); db.flush(); db.refresh(s)
    return s


@pytest.fixture
def store2(db):
    """Second store for cross-store isolation tests."""
    s = Store(name="Other Store", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(s); db.flush(); db.refresh(s)
    return s


@pytest.fixture
def cashier(db, store):
    emp = Employee(
        store_id=store.id, full_name="Alice Cashier", email="alice@test.com",
        password=hash_password("pass"), role=Role.CASHIER, is_active=True,
    )
    db.add(emp); db.flush(); db.refresh(emp)
    return emp


@pytest.fixture
def supervisor(db, store):
    emp = Employee(
        store_id=store.id, full_name="Bob Supervisor", email="bob@test.com",
        password=hash_password("pass"), role=Role.SUPERVISOR, is_active=True,
    )
    db.add(emp); db.flush(); db.refresh(emp)
    return emp


@pytest.fixture
def other_store_manager(db, store2):
    emp = Employee(
        store_id=store2.id, full_name="Carol Manager", email="carol@test.com",
        password=hash_password("pass"), role=Role.MANAGER, is_active=True,
    )
    db.add(emp); db.flush(); db.refresh(emp)
    return emp


@pytest.fixture
def product_a(db, store):
    p = Product(
        store_id=store.id, sku="PRDA", name="Product A",
        selling_price=Decimal("100.00"), cost_price=Decimal("60.00"),
        stock_quantity=50, is_active=True,
    )
    db.add(p); db.flush(); db.refresh(p)
    return p


@pytest.fixture
def product_b(db, store):
    p = Product(
        store_id=store.id, sku="PRDB", name="Product B",
        selling_price=Decimal("200.00"), cost_price=Decimal("120.00"),
        stock_quantity=30, is_active=True,
    )
    db.add(p); db.flush(); db.refresh(p)
    return p


def _make_transaction(db, store, cashier, items_spec, status=TransactionStatus.COMPLETED):
    """
    items_spec: list of (product, qty, unit_price, cost_price_snap, vat_amount, line_total)
    Returns (Transaction, list[TransactionItem])
    """
    import uuid, random, string
    txn_number = "TXN-" + "".join(random.choices(string.digits, k=8))
    total = sum(spec[5] + spec[4] for spec in items_spec)
    txn = Transaction(
        uuid=str(uuid.uuid4()),
        txn_number=txn_number,
        store_id=store.id,
        cashier_id=cashier.id,
        payment_method=PaymentMethod.CASH,
        subtotal=total,
        vat_amount=sum(spec[4] for spec in items_spec),
        total=total,
        discount_amount=Decimal("0"),
        status=status,
    )
    db.add(txn); db.flush()

    txn_items = []
    for product, qty, unit_price, cost_snap, vat_amt, line_total in items_spec:
        ti = TransactionItem(
            transaction_id=txn.id,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            qty=qty,
            unit_price=Decimal(str(unit_price)),
            cost_price_snap=Decimal(str(cost_snap)),
            discount=Decimal("0"),
            vat_amount=Decimal(str(vat_amt)),
            line_total=Decimal(str(line_total)),
        )
        db.add(ti); txn_items.append(ti)
    db.flush()
    db.refresh(txn)
    return txn, txn_items


@pytest.fixture
def seeded_accounts(db, store):
    seed_chart_of_accounts(db, store.id)
    db.flush()


def _cashier_headers(cashier):
    token = create_access_token({"sub": str(cashier.id), "role": cashier.role})
    return {"Authorization": f"Bearer {token}"}


def _supervisor_headers(supervisor):
    token = create_access_token({"sub": str(supervisor.id), "role": supervisor.role})
    return {"Authorization": f"Bearer {token}"}


def _other_headers(emp):
    token = create_access_token({"sub": str(emp.id), "role": emp.role})
    return {"Authorization": f"Bearer {token}"}


# ══ A. create_return ══════════════════════════════════════════════════════════

class TestCreateReturn:

    def test_A1_full_restorable_cash_return(self, client, db, store, cashier, product_a):
        """Full return of one item — happy path."""
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 3, Decimal("100.00"), Decimal("60.00"), Decimal("48.00"), Decimal("252.00")),
        ])

        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 3, "is_restorable": True}],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "pending"
        assert data["original_txn_number"] == txn.txn_number
        assert data["is_partial"] is False
        assert len(data["items"]) == 1
        assert data["items"][0]["qty_returned"] == 3
        assert data["items"][0]["is_restorable"] is True
        assert data["return_number"].startswith("RET-")

    def test_A2_partial_return_subset_of_items(self, client, db, store, cashier, product_a, product_b):
        """Return only product_a from a 2-item transaction."""
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"), Decimal("32.00"), Decimal("168.00")),
            (product_b, 1, Decimal("200.00"), Decimal("120.00"), Decimal("32.00"), Decimal("168.00")),
        ])

        payload = {
            "original_txn_id": txn.id,
            "return_reason": "wrong_item",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 2, "is_restorable": True}],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 201
        data = resp.json()
        assert data["is_partial"] is True

    def test_A3_partial_qty_return(self, client, db, store, cashier, product_a):
        """Return 1 of 3 units — qty validation."""
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 3, Decimal("100.00"), Decimal("60.00"), Decimal("48.00"), Decimal("252.00")),
        ])

        payload = {
            "original_txn_id": txn.id,
            "return_reason": "change_of_mind",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1, "is_restorable": True}],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 201
        data = resp.json()
        assert data["items"][0]["qty_returned"] == 1
        assert data["is_partial"] is True

    def test_A4_damaged_non_restorable(self, client, db, store, cashier, product_a):
        """Damaged item marked non-restorable."""
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"), Decimal("32.00"), Decimal("168.00")),
        ])

        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{
                "original_txn_item_id": items[0].id,
                "qty_returned": 2,
                "is_restorable": False,
                "damaged_notes": "Packaging crushed on delivery",
            }],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 201
        data = resp.json()
        assert data["items"][0]["is_restorable"] is False
        assert "crushed" in data["items"][0]["damaged_notes"]

    def test_A5_mixed_restorable_and_damaged(self, client, db, store, cashier, product_a, product_b):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00")),
            (product_b, 1, Decimal("200.00"), Decimal("120.00"), Decimal("32.00"), Decimal("168.00")),
        ])

        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [
                {"original_txn_item_id": items[0].id, "qty_returned": 1, "is_restorable": True},
                {"original_txn_item_id": items[1].id, "qty_returned": 1, "is_restorable": False,
                 "damaged_notes": "Screen cracked"},
            ],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 201
        data = resp.json()
        restorable_flags = {i["sku"]: i["is_restorable"] for i in data["items"]}
        assert restorable_flags["PRDA"] is True
        assert restorable_flags["PRDB"] is False

    def test_A6_duplicate_item_in_request(self, client, db, store, cashier, product_a):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 3, Decimal("100.00"), Decimal("60.00"), Decimal("48.00"), Decimal("252.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [
                {"original_txn_item_id": items[0].id, "qty_returned": 1},
                {"original_txn_item_id": items[0].id, "qty_returned": 1},  # duplicate
            ],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 422, resp.text

    def test_A7_return_against_voided_transaction(self, client, db, store, cashier, product_a):
        txn, items = _make_transaction(
            db, store, cashier,
            [(product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00"))],
            status=TransactionStatus.VOIDED,
        )
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 400

    def test_A8_qty_returned_exceeds_original(self, client, db, store, cashier, product_a):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"), Decimal("32.00"), Decimal("168.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 5}],  # original=2
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 400
        assert "returnable" in resp.json()["detail"].lower()

    def test_A9_double_return_exceeds_ceiling(self, client, db, store, cashier, supervisor, product_a,
                                               seeded_accounts):
        """First return completes 2/2 units. Second return for same item is rejected."""
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"), Decimal("32.00"), Decimal("168.00")),
        ])
        # First return — complete it
        payload1 = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 2}],
        }
        r1 = client.post("/api/v1/returns", json=payload1, headers=_cashier_headers(cashier))
        assert r1.status_code == 201
        ret_id = r1.json()["id"]

        approve_payload = {"refund_method": "cash"}
        client.post(f"/api/v1/returns/{ret_id}/approve", json=approve_payload,
                    headers=_supervisor_headers(supervisor))

        # Second return — should fail (0 units left)
        payload2 = {
            "original_txn_id": txn.id,
            "return_reason": "change_of_mind",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        r2 = client.post("/api/v1/returns", json=payload2, headers=_cashier_headers(cashier))
        assert r2.status_code == 400
        assert "returnable" in r2.json()["detail"].lower()

    def test_A10_cross_store_return_rejected(self, client, db, store, store2, cashier,
                                              other_store_manager, product_a):
        """Employee from store2 cannot create return against store's transaction."""
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        resp = client.post("/api/v1/returns", json=payload,
                           headers=_other_headers(other_store_manager))
        assert resp.status_code == 403

    def test_A11_item_from_different_transaction(self, client, db, store, cashier, product_a, product_b):
        txn1, items1 = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00")),
        ])
        txn2, items2 = _make_transaction(db, store, cashier, [
            (product_b, 1, Decimal("200.00"), Decimal("120.00"), Decimal("32.00"), Decimal("168.00")),
        ])
        # Attempt to use an item from txn2 in a return against txn1
        payload = {
            "original_txn_id": txn1.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items2[0].id, "qty_returned": 1}],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 400

    def test_A12_nonexistent_transaction(self, client, cashier):
        payload = {
            "original_txn_id": 9999999,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": 1, "qty_returned": 1}],
        }
        resp = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert resp.status_code == 404


# ══ B. approve_and_complete ═══════════════════════════════════════════════════

class TestApproveReturn:

    def _pending_return(self, client, db, store, cashier, product, txn=None, items=None,
                        qty=2, is_restorable=True):
        if txn is None:
            txn, items = _make_transaction(db, store, cashier, [
                (product, qty, Decimal("100.00"), Decimal("60.00"),
                 Decimal("32.00"), Decimal("168.00")),
            ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{
                "original_txn_item_id": items[0].id,
                "qty_returned": qty,
                "is_restorable": is_restorable,
            }],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert r.status_code == 201
        return r.json()["id"], txn, items

    def test_B1_cashier_cannot_approve(self, client, db, store, cashier, product_a):
        ret_id, *_ = self._pending_return(client, db, store, cashier, product_a)
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_cashier_headers(cashier))
        assert resp.status_code == 403

    def test_B2_approve_restores_stock_and_posts_accounting(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        """Full happy-path: approve a 3-unit restorable return."""
        qty = 3
        original_stock = product_a.stock_quantity
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, qty, Decimal("100.00"), Decimal("60.00"),
             Decimal("48.00"), Decimal("252.00")),
        ])
        ret_id, *_ = self._pending_return(
            client, db, store, cashier, product_a, txn=txn, items=items, qty=qty
        )
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "completed"
        assert data["refund_method"] == "cash"
        assert data["approved_by"] == supervisor.id
        assert data["completed_at"] is not None

        # Stock restored
        db.expire(product_a)
        db.refresh(product_a)
        assert product_a.stock_quantity == original_stock + qty  # was halved by txn, now restored

        # Journal entry exists
        je = db.query(JournalEntry).filter(
            JournalEntry.ref_type == "return",
            JournalEntry.store_id == store.id,
        ).first()
        assert je is not None

    def test_B3_approve_already_completed(self, client, db, store, cashier, supervisor,
                                           product_a, seeded_accounts):
        ret_id, *_ = self._pending_return(client, db, store, cashier, product_a)
        client.post(f"/api/v1/returns/{ret_id}/approve",
                    json={"refund_method": "cash"},
                    headers=_supervisor_headers(supervisor))
        # Approve again
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 400

    def test_B4_approve_rejected_return(self, client, db, store, cashier, supervisor, product_a):
        ret_id, *_ = self._pending_return(client, db, store, cashier, product_a)
        client.post(f"/api/v1/returns/{ret_id}/reject",
                    json={"rejection_notes": "Customer abusive"},
                    headers=_supervisor_headers(supervisor))
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 400

    def test_B5_damaged_item_no_stock_change(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        original_stock = product_a.stock_quantity
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"),
             Decimal("32.00"), Decimal("168.00")),
        ])
        ret_id, *_ = self._pending_return(
            client, db, store, cashier, product_a,
            txn=txn, items=items, qty=2, is_restorable=False
        )
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 200

        # Stock must NOT have changed
        db.expire(product_a)
        db.refresh(product_a)
        assert product_a.stock_quantity == original_stock  # unchanged

        # No StockMovement with movement_type='return'
        sm = db.query(StockMovement).filter(
            StockMovement.movement_type == "return",
            StockMovement.product_id == product_a.id,
        ).first()
        assert sm is None

    def test_B6_snapshot_totals_saved(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"),
             Decimal("32.00"), Decimal("168.00")),
        ])
        ret_id, *_ = self._pending_return(
            client, db, store, cashier, product_a, txn=txn, items=items, qty=2
        )
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_refund_gross"] is not None
        assert data["total_vat_reversed"] is not None
        assert data["total_cogs_reversed"] is not None
        assert Decimal(str(data["total_cogs_reversed"])) == Decimal("120.00")  # 60 × 2


# ══ C. reject_return ══════════════════════════════════════════════════════════

class TestRejectReturn:

    def _pending_return(self, client, db, store, cashier, product):
        txn, items = _make_transaction(db, store, cashier, [
            (product, 1, Decimal("100.00"), Decimal("60.00"),
             Decimal("16.00"), Decimal("84.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "change_of_mind",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        assert r.status_code == 201
        return r.json()["id"]

    def test_C1_cashier_cannot_reject(self, client, db, store, cashier, product_a):
        ret_id = self._pending_return(client, db, store, cashier, product_a)
        resp = client.post(f"/api/v1/returns/{ret_id}/reject",
                           json={"rejection_notes": "nope"},
                           headers=_cashier_headers(cashier))
        assert resp.status_code == 403

    def test_C2_reject_happy_path(self, client, db, store, cashier, supervisor, product_a):
        original_stock = product_a.stock_quantity
        ret_id = self._pending_return(client, db, store, cashier, product_a)
        resp = client.post(f"/api/v1/returns/{ret_id}/reject",
                           json={"rejection_notes": "Goods show signs of deliberate damage"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["rejection_notes"] == "Goods show signs of deliberate damage"
        assert data["rejected_by"] == supervisor.id

        # Stock must be unchanged
        db.expire(product_a)
        db.refresh(product_a)
        assert product_a.stock_quantity == original_stock

        # No journal entry
        je = db.query(JournalEntry).filter(
            JournalEntry.ref_type == "return",
            JournalEntry.store_id == store.id,
        ).first()
        assert je is None

    def test_C3_reject_already_rejected(self, client, db, store, cashier, supervisor, product_a):
        ret_id = self._pending_return(client, db, store, cashier, product_a)
        client.post(f"/api/v1/returns/{ret_id}/reject",
                    json={"rejection_notes": "nope"},
                    headers=_supervisor_headers(supervisor))
        resp = client.post(f"/api/v1/returns/{ret_id}/reject",
                           json={"rejection_notes": "nope again"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 400

    def test_C4_reject_completed_return(self, client, db, store, cashier, supervisor,
                                         product_a, seeded_accounts):
        ret_id = self._pending_return(client, db, store, cashier, product_a)
        client.post(f"/api/v1/returns/{ret_id}/approve",
                    json={"refund_method": "cash"},
                    headers=_supervisor_headers(supervisor))
        resp = client.post(f"/api/v1/returns/{ret_id}/reject",
                           json={"rejection_notes": "too late"},
                           headers=_supervisor_headers(supervisor))
        assert resp.status_code == 400


# ══ D. List and Get ═══════════════════════════════════════════════════════════

class TestListAndGet:

    def test_D1_cashier_can_list_own_store_returns(self, client, db, store, cashier, product_a):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))

        resp = client.get("/api/v1/returns", headers=_cashier_headers(cashier))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_D2_status_filter(self, client, db, store, cashier, supervisor, product_a, seeded_accounts):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        ret_id = r.json()["id"]
        client.post(f"/api/v1/returns/{ret_id}/approve",
                    json={"refund_method": "cash"},
                    headers=_supervisor_headers(supervisor))

        # Filter completed
        resp = client.get("/api/v1/returns?status=completed", headers=_cashier_headers(cashier))
        assert resp.status_code == 200
        statuses = {r["status"] for r in resp.json()}
        assert statuses == {"completed"}

        # Filter pending — should be empty
        resp2 = client.get("/api/v1/returns?status=pending", headers=_cashier_headers(cashier))
        assert resp2.status_code == 200

    def test_D3_original_txn_id_filter(self, client, db, store, cashier, product_a, product_b):
        txn1, items1 = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00")),
        ])
        txn2, items2 = _make_transaction(db, store, cashier, [
            (product_b, 1, Decimal("200.00"), Decimal("120.00"), Decimal("32.00"), Decimal("168.00")),
        ])
        for txn, items in [(txn1, items1), (txn2, items2)]:
            payload = {
                "original_txn_id": txn.id,
                "return_reason": "defective",
                "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
            }
            client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))

        resp = client.get(f"/api/v1/returns?original_txn_id={txn1.id}",
                          headers=_cashier_headers(cashier))
        assert resp.status_code == 200
        txn_ids = {r["original_txn_id"] for r in resp.json()}
        assert txn_ids == {txn1.id}

    def test_D4_txn_returns_sub_route(self, client, db, store, cashier, product_a):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"), Decimal("16.00"), Decimal("84.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "expired",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))

        resp = client.get(f"/api/v1/transactions/{txn.id}/returns",
                          headers=_cashier_headers(cashier))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        assert resp.json()[0]["original_txn_id"] == txn.id


# ══ E. Accounting invariants ══════════════════════════════════════════════════

class TestAccountingInvariants:

    def _full_return(self, client, db, store, cashier, supervisor, product,
                     qty=2, is_restorable=True):
        txn, items = _make_transaction(db, store, cashier, [
            (product, qty, Decimal("100.00"), Decimal("60.00"),
             Decimal("32.00"), Decimal("168.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id,
                        "qty_returned": qty, "is_restorable": is_restorable}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        ret_id = r.json()["id"]
        client.post(f"/api/v1/returns/{ret_id}/approve",
                    json={"refund_method": "cash"},
                    headers=_supervisor_headers(supervisor))
        return ret_id

    def _get_journal_entry(self, db, store, return_number):
        return db.query(JournalEntry).filter(
            JournalEntry.store_id == store.id,
            JournalEntry.ref_type == "return",
            JournalEntry.ref_id   == return_number,
        ).first()

    def test_E1_journal_balanced_restorable(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        ret_id = self._full_return(client, db, store, cashier, supervisor, product_a, qty=2)
        data = client.get(f"/api/v1/returns/{ret_id}", headers=_cashier_headers(cashier)).json()
        je = self._get_journal_entry(db, store, data["return_number"])
        assert je is not None

        lines = db.query(JournalLine).filter(JournalLine.entry_id == je.id).all()
        total_dr = sum(Decimal(str(l.debit))  for l in lines)
        total_cr = sum(Decimal(str(l.credit)) for l in lines)
        assert total_dr == total_cr, f"Unbalanced: DR={total_dr} CR={total_cr}"

    def test_E2_journal_balanced_damaged(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        ret_id = self._full_return(
            client, db, store, cashier, supervisor, product_a, qty=2, is_restorable=False
        )
        data = client.get(f"/api/v1/returns/{ret_id}", headers=_cashier_headers(cashier)).json()
        je = self._get_journal_entry(db, store, data["return_number"])
        assert je is not None

        lines = db.query(JournalLine).filter(JournalLine.entry_id == je.id).all()
        total_dr = sum(Decimal(str(l.debit))  for l in lines)
        total_cr = sum(Decimal(str(l.credit)) for l in lines)
        assert total_dr == total_cr

        # Damaged: should have only 3 legs (cash CR, revenue DR, VAT DR)
        assert len(lines) == 3

    def test_E3_post_return_idempotent(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        """Calling post_return twice for the same return_number must not create a duplicate entry."""
        from app.services.accounting import post_return as _post_return

        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"),
             Decimal("16.00"), Decimal("84.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 1}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        ret_id = r.json()["id"]
        client.post(f"/api/v1/returns/{ret_id}/approve",
                    json={"refund_method": "cash"},
                    headers=_supervisor_headers(supervisor))

        # Call post_return again directly
        ret_txn = db.query(ReturnTransaction).filter(ReturnTransaction.id == ret_id).first()
        result = _post_return(db, ret_txn, ret_txn.items)

        count = db.query(JournalEntry).filter(
            JournalEntry.ref_type == "return",
            JournalEntry.ref_id   == ret_txn.return_number,
        ).count()
        assert count == 1, f"Expected 1 journal entry, got {count}"


# ══ F. Stock invariants ════════════════════════════════════════════════════════

class TestStockInvariants:

    def test_F1_stock_restored_for_restorable(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        qty = 3
        original_stock = product_a.stock_quantity
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, qty, Decimal("100.00"), Decimal("60.00"),
             Decimal("48.00"), Decimal("252.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": qty}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        ret_id = r.json()["id"]
        client.post(f"/api/v1/returns/{ret_id}/approve",
                    json={"refund_method": "cash"},
                    headers=_supervisor_headers(supervisor))

        db.expire(product_a)
        db.refresh(product_a)
        assert product_a.stock_quantity == original_stock + qty

    def test_F2_stock_unchanged_for_damaged(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        original_stock = product_a.stock_quantity
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"),
             Decimal("32.00"), Decimal("168.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id,
                        "qty_returned": 2, "is_restorable": False}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        ret_id = r.json()["id"]
        client.post(f"/api/v1/returns/{ret_id}/approve",
                    json={"refund_method": "cash"},
                    headers=_supervisor_headers(supervisor))

        db.expire(product_a)
        db.refresh(product_a)
        assert product_a.stock_quantity == original_stock

    def test_F3_stock_movement_created_for_restorable(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 2, Decimal("100.00"), Decimal("60.00"),
             Decimal("32.00"), Decimal("168.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id, "qty_returned": 2}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        ret_id = r.json()["id"]
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_supervisor_headers(supervisor))
        data = resp.json()

        sm = db.query(StockMovement).filter(
            StockMovement.movement_type == "return",
            StockMovement.product_id   == product_a.id,
            StockMovement.ref_id       == data["return_number"],
        ).first()
        assert sm is not None
        assert sm.qty_delta == 2
        assert sm.qty_delta > 0   # positive = stock in
        assert sm.performed_by == supervisor.id

    def test_F4_no_stock_movement_for_damaged(
        self, client, db, store, cashier, supervisor, product_a, seeded_accounts
    ):
        txn, items = _make_transaction(db, store, cashier, [
            (product_a, 1, Decimal("100.00"), Decimal("60.00"),
             Decimal("16.00"), Decimal("84.00")),
        ])
        payload = {
            "original_txn_id": txn.id,
            "return_reason": "defective",
            "items": [{"original_txn_item_id": items[0].id,
                        "qty_returned": 1, "is_restorable": False}],
        }
        r = client.post("/api/v1/returns", json=payload, headers=_cashier_headers(cashier))
        ret_id = r.json()["id"]
        resp = client.post(f"/api/v1/returns/{ret_id}/approve",
                           json={"refund_method": "cash"},
                           headers=_supervisor_headers(supervisor))
        return_number = resp.json()["return_number"]

        sm = db.query(StockMovement).filter(
            StockMovement.movement_type == "return",
            StockMovement.ref_id       == return_number,
        ).first()
        assert sm is None


# ══ G. Status filter fix (FIX 4) ═════════════════════════════════════════════

class TestListReturnsStatusFilter:

    def test_list_returns_invalid_status_returns_422(self, client, cashier):
        """Passing an unrecognised status string must return HTTP 422, not silently return []."""
        resp = client.get(
            "/api/v1/returns?status=GARBAGE_STATUS",
            headers=_cashier_headers(cashier),
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid status, got {resp.status_code}: {resp.text}"
        )
        detail = resp.json().get("detail", "")
        # The error message must name the bad value and hint at valid ones
        assert "GARBAGE_STATUS" in detail or "invalid" in detail.lower(), detail

    def test_list_returns_valid_status_pending_returns_200(
        self, client, db, store, cashier, product_a
    ):
        """Filter by 'pending' must return 200 and only pending returns."""
        import uuid as _uuid_mod
        from app.models.transaction import Transaction, PaymentMethod, TransactionStatus
        from app.models.returns import ReturnTransaction, ReturnStatus, ReturnReason

        # Create a minimal transaction row with a proper UUID object (SQLite requires this)
        txn = Transaction(
            uuid=_uuid_mod.uuid4(),
            txn_number="TXN-FILTPEND-001",
            store_id=store.id,
            cashier_id=cashier.id,
            payment_method=PaymentMethod.CASH,
            subtotal=Decimal("100.00"),
            vat_amount=Decimal("0.00"),
            total=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            status=TransactionStatus.COMPLETED,
        )
        db.add(txn); db.flush()

        ret = ReturnTransaction(
            return_number="RET-FILTPEND-01",
            store_id=store.id,
            original_txn_id=txn.id,
            original_txn_number=txn.txn_number,
            status=ReturnStatus.PENDING,
            return_reason=ReturnReason.DEFECTIVE,
            requested_by=cashier.id,
        )
        db.add(ret); db.flush()

        resp = client.get("/api/v1/returns?status=pending", headers=_cashier_headers(cashier))
        assert resp.status_code == 200, resp.text
        for r in resp.json():
            assert r["status"] == "pending"

    def test_list_returns_valid_status_completed_filters_correctly(
        self, client, db, store, cashier, supervisor, seeded_accounts
    ):
        """Filter by 'completed' returns only completed returns, not pending ones."""
        import uuid as _uuid_mod
        from app.models.transaction import Transaction, PaymentMethod, TransactionStatus
        from app.models.returns import ReturnTransaction, ReturnStatus, ReturnReason

        def _txn(txn_num):
            t = Transaction(
                uuid=_uuid_mod.uuid4(),
                txn_number=txn_num,
                store_id=store.id,
                cashier_id=cashier.id,
                payment_method=PaymentMethod.CASH,
                subtotal=Decimal("100.00"),
                vat_amount=Decimal("0.00"),
                total=Decimal("100.00"),
                discount_amount=Decimal("0.00"),
                status=TransactionStatus.COMPLETED,
            )
            db.add(t); db.flush()
            return t

        t1 = _txn("TXN-FILTCOMP-001")
        t2 = _txn("TXN-FILTCOMP-002")

        pending = ReturnTransaction(
            return_number="RET-FILTCOMP-P1",
            store_id=store.id,
            original_txn_id=t1.id,
            original_txn_number=t1.txn_number,
            status=ReturnStatus.PENDING,
            return_reason=ReturnReason.DEFECTIVE,
            requested_by=cashier.id,
        )
        completed = ReturnTransaction(
            return_number="RET-FILTCOMP-C1",
            store_id=store.id,
            original_txn_id=t2.id,
            original_txn_number=t2.txn_number,
            status=ReturnStatus.COMPLETED,
            return_reason=ReturnReason.WRONG_ITEM,
            requested_by=cashier.id,
        )
        db.add_all([pending, completed]); db.flush()

        resp = client.get("/api/v1/returns?status=completed", headers=_cashier_headers(cashier))
        assert resp.status_code == 200, resp.text
        statuses = {r["status"] for r in resp.json()}
        assert "pending" not in statuses, f"pending found in completed-filtered results: {statuses}"
        assert "completed" in statuses
