from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.audit import AuditTrail
from app.models.cash_session import CashSession
from app.models.employee import Role
from app.routers import cash_sessions as cs_router


class _FakeQuery:
    def __init__(self, obj):
        self._obj = obj

    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._obj


class _FakeDB:
    def __init__(self, query_obj):
        self._query_obj = query_obj
        self.added = []
        self.committed = False

    def query(self, model):
        return _FakeQuery(self._query_obj)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        return None

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        return None

    def rollback(self):
        return None


def _actor():
    return SimpleNamespace(
        id=10,
        full_name="Tester",
        store_id=1,
        terminal_id="T01",
        role=Role.ADMIN,
    )


def test_open_cash_session_accounting_failure_records_pending(monkeypatch):
    db = _FakeDB(query_obj=None)  # no existing open session
    current = _actor()

    def _boom(*args, **kwargs):
        raise ValueError("forced accounting failure open")

    monkeypatch.setattr(cs_router, "post_cash_session_open", _boom)

    row = cs_router.open_cash_session(
        payload=cs_router.CashSessionOpen(opening_float=Decimal("1000.00"), terminal_id="T01"),
        db=db,
        current=current,
    )

    assert isinstance(row, CashSession)
    assert db.committed is True
    pending = [a for a in db.added if isinstance(a, AuditTrail) and a.action == "accounting_pending_cash_session_open"]
    assert pending, "Expected durable pending accounting marker"
    assert pending[-1].entity == "cash_session"


def test_close_cash_session_accounting_failure_records_pending(monkeypatch):
    current = _actor()
    open_row = CashSession(
        id=55,
        store_id=1,
        cashier_id=current.id,
        terminal_id="T01",
        session_number="CS-TEST-1",
        status="open",
        expected_cash=Decimal("500.00"),
    )
    db = _FakeDB(query_obj=open_row)

    def _boom(*args, **kwargs):
        raise ValueError("forced accounting failure close")

    monkeypatch.setattr(cs_router, "post_cash_session_close", _boom)

    result = cs_router.close_cash_session(
        session_id=55,
        payload=cs_router.CashSessionClose(
            payment_counts={"cash": Decimal("450.00"), "mpesa": 0, "card": 0, "credit": 0, "store_credit": 0},
            total_counted=Decimal("450.00"),
        ),
        db=db,
        current=current,
    )

    assert result.status == "closed"
    assert db.committed is True
    pending = [a for a in db.added if isinstance(a, AuditTrail) and a.action == "accounting_pending_cash_session_close"]
    assert pending, "Expected durable pending accounting marker"
    assert pending[-1].entity_id == "CS-TEST-1"
