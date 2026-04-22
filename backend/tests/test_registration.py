"""
Integration tests — Store registration flow (Phase 2)

Covers:
  - Happy path: store created, admin created, 201 returned, trial_ends_at set
  - Duplicate admin email returns 400
  - Duplicate store name returns 400
  - Missing required fields return 422
  - Registration seeds a chart of accounts
"""

import pytest
from sqlalchemy import text

from app.models.employee import Employee, Role
from app.models.subscription import Store, SubStatus


_VALID_PAYLOAD = {
    "store_name": "Nairobi Grocers",
    "store_location": "Westlands, Nairobi",
    "admin_full_name": "Jane Wanjiku",
    "admin_email": "jane@nairobigrocers.co.ke",
    "admin_password": "Secure1234!",
}


class TestRegistrationHappyPath:

    def test_register_returns_201(self, client):
        resp = client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        assert resp.status_code == 201

    def test_register_response_contains_store_and_admin_ids(self, client):
        resp = client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        body = resp.json()
        assert "store_id" in body
        assert "admin_id" in body
        assert body["store_name"] == _VALID_PAYLOAD["store_name"]
        assert body["admin_email"] == _VALID_PAYLOAD["admin_email"]

    def test_register_creates_store_in_db(self, client, db):
        client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        store = db.query(Store).filter(Store.name == _VALID_PAYLOAD["store_name"]).first()
        assert store is not None
        assert store.sub_status == SubStatus.TRIALING

    def test_register_creates_admin_employee_in_db(self, client, db):
        client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        emp = db.query(Employee).filter(Employee.email == _VALID_PAYLOAD["admin_email"]).first()
        assert emp is not None
        assert emp.role == Role.ADMIN
        assert emp.is_active is True

    def test_register_sets_trial_ends_at(self, client):
        resp = client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        body = resp.json()
        assert "trial_ends_at" in body
        assert body["trial_ends_at"] is not None

    def test_register_seeds_chart_of_accounts(self, client, db):
        resp = client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        store_id = resp.json()["store_id"]
        count = db.execute(
            text("SELECT COUNT(*) FROM accounts WHERE store_id = :sid"),
            {"sid": store_id},
        ).scalar()
        assert count > 0, "Chart of accounts must be seeded on registration"


class TestRegistrationValidation:

    def test_duplicate_admin_email_returns_400(self, client):
        client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        resp = client.post("/api/v1/auth/register", json={
            **_VALID_PAYLOAD,
            "store_name": "Different Store Name",
        })
        assert resp.status_code == 400
        assert "email" in resp.json()["detail"].lower()

    def test_duplicate_store_name_returns_400(self, client):
        client.post("/api/v1/auth/register", json=_VALID_PAYLOAD)
        resp = client.post("/api/v1/auth/register", json={
            **_VALID_PAYLOAD,
            "admin_email": "other@example.com",
        })
        assert resp.status_code == 400
        assert "store" in resp.json()["detail"].lower()

    def test_missing_store_name_returns_422(self, client):
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "store_name"}
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 422

    def test_missing_admin_email_returns_422(self, client):
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "admin_email"}
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 422

    def test_missing_admin_password_returns_422(self, client):
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "admin_password"}
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 422

    def test_password_too_short_returns_422(self, client):
        resp = client.post("/api/v1/auth/register", json={
            **_VALID_PAYLOAD,
            "admin_password": "short",
        })
        assert resp.status_code == 422

    def test_invalid_email_format_returns_422(self, client):
        resp = client.post("/api/v1/auth/register", json={
            **_VALID_PAYLOAD,
            "admin_email": "not-an-email",
        })
        assert resp.status_code == 422
