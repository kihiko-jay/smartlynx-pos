"""
Integration tests — Employee management endpoints (Phase 2)

Covers:
  - GET /employees returns only employees from the current store
  - POST /employees creates employee with is_password_reset_required=True
  - POST /employees cannot create ADMIN role — returns 422
  - POST /employees with duplicate email returns 400
  - PUT /employees/{id} can update role and active status
  - PUT /employees/{id} cannot update an employee from a different store — returns 404
  - Non-admin role cannot call any /employees endpoint — returns 403
"""

import pytest
from app.core.security import hash_password, create_access_token
from app.models.employee import Employee, Role
from app.models.subscription import Store, Plan, SubStatus


_NEW_EMPLOYEE_PAYLOAD = {
    "full_name": "Mary Njeri",
    "email": "mary@teststore.co.ke",
    "role": "cashier",
}


@pytest.fixture
def other_store(db):
    """A second store with its own admin — used to test cross-store isolation."""
    store = Store(name="Other Store", plan=Plan.STARTER, sub_status=SubStatus.ACTIVE)
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@pytest.fixture
def other_admin(db, other_store):
    emp = Employee(
        store_id=other_store.id,
        full_name="Other Admin",
        email="other_admin@otherstore.co.ke",
        password=hash_password("otherpass123"),
        role=Role.ADMIN,
        is_active=True,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@pytest.fixture
def other_auth_headers(other_admin):
    token = create_access_token({"sub": str(other_admin.id), "role": other_admin.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def cashier(db, test_store):
    emp = Employee(
        store_id=test_store.id,
        full_name="Sam Cashier",
        email="cashier@teststore.co.ke",
        password=hash_password("cashierpass123"),
        role=Role.CASHIER,
        is_active=True,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@pytest.fixture
def cashier_auth_headers(cashier):
    token = create_access_token({"sub": str(cashier.id), "role": cashier.role})
    return {"Authorization": f"Bearer {token}"}


# ── Store isolation ───────────────────────────────────────────────────────────

class TestEmployeeListIsolation:

    def test_list_returns_only_own_store_employees(self, client, db, auth_headers, test_store, other_store):
        """Admin sees only their store's employees — not those from other stores."""
        outsider = Employee(
            store_id=other_store.id,
            full_name="Outsider",
            email="outsider@other.co.ke",
            password=hash_password("pass1234!"),
            role=Role.CASHIER,
            is_active=True,
        )
        db.add(outsider)
        db.commit()

        resp = client.get("/api/v1/employees", headers=auth_headers)
        assert resp.status_code == 200
        emails = [e["email"] for e in resp.json()["employees"]]
        assert "outsider@other.co.ke" not in emails

    def test_list_includes_own_store_employees(self, client, db, auth_headers, test_store):
        emp = Employee(
            store_id=test_store.id,
            full_name="Insider",
            email="insider@teststore.co.ke",
            password=hash_password("pass1234!"),
            role=Role.CASHIER,
            is_active=True,
        )
        db.add(emp)
        db.commit()

        resp = client.get("/api/v1/employees", headers=auth_headers)
        emails = [e["email"] for e in resp.json()["employees"]]
        assert "insider@teststore.co.ke" in emails


# ── Create employee ───────────────────────────────────────────────────────────

class TestCreateEmployee:

    def test_create_employee_returns_201(self, client, auth_headers):
        resp = client.post("/api/v1/employees", json=_NEW_EMPLOYEE_PAYLOAD, headers=auth_headers)
        assert resp.status_code == 201

    def test_created_employee_has_password_reset_required(self, client, db, auth_headers):
        resp = client.post("/api/v1/employees", json=_NEW_EMPLOYEE_PAYLOAD, headers=auth_headers)
        emp_id = resp.json()["id"]
        db.expire_all()
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        assert emp.is_password_reset_required is True

    def test_cannot_create_admin_role_returns_422(self, client, auth_headers):
        resp = client.post("/api/v1/employees", json={
            **_NEW_EMPLOYEE_PAYLOAD,
            "role": "admin",
        }, headers=auth_headers)
        assert resp.status_code == 422

    def test_duplicate_email_returns_400(self, client, auth_headers):
        client.post("/api/v1/employees", json=_NEW_EMPLOYEE_PAYLOAD, headers=auth_headers)
        resp = client.post("/api/v1/employees", json=_NEW_EMPLOYEE_PAYLOAD, headers=auth_headers)
        assert resp.status_code == 400

    def test_missing_full_name_returns_422(self, client, auth_headers):
        payload = {k: v for k, v in _NEW_EMPLOYEE_PAYLOAD.items() if k != "full_name"}
        resp = client.post("/api/v1/employees", json=payload, headers=auth_headers)
        assert resp.status_code == 422

    def test_invalid_email_format_returns_422(self, client, auth_headers):
        resp = client.post("/api/v1/employees", json={
            **_NEW_EMPLOYEE_PAYLOAD,
            "email": "not-an-email",
        }, headers=auth_headers)
        assert resp.status_code == 422


# ── Update employee ───────────────────────────────────────────────────────────

class TestUpdateEmployee:

    def test_can_update_role(self, client, db, auth_headers, test_store):
        emp = Employee(
            store_id=test_store.id,
            full_name="Updatable",
            email="updatable@teststore.co.ke",
            password=hash_password("pass1234!"),
            role=Role.CASHIER,
            is_active=True,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)

        resp = client.put(f"/api/v1/employees/{emp.id}", json={"role": "supervisor"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "supervisor"

    def test_can_deactivate_employee(self, client, db, auth_headers, test_store):
        emp = Employee(
            store_id=test_store.id,
            full_name="Deactivatable",
            email="deactivatable@teststore.co.ke",
            password=hash_password("pass1234!"),
            role=Role.CASHIER,
            is_active=True,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)

        resp = client.put(f"/api/v1/employees/{emp.id}", json={"is_active": False}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_cannot_update_employee_from_different_store_returns_404(
        self, client, db, auth_headers, other_store
    ):
        outsider = Employee(
            store_id=other_store.id,
            full_name="Cross-store Target",
            email="target@other.co.ke",
            password=hash_password("pass1234!"),
            role=Role.CASHIER,
            is_active=True,
        )
        db.add(outsider)
        db.commit()
        db.refresh(outsider)

        resp = client.put(f"/api/v1/employees/{outsider.id}", json={"role": "supervisor"}, headers=auth_headers)
        assert resp.status_code == 404


# ── Role enforcement ──────────────────────────────────────────────────────────

class TestRoleEnforcement:

    def test_cashier_cannot_list_employees(self, client, cashier_auth_headers):
        resp = client.get("/api/v1/employees", headers=cashier_auth_headers)
        assert resp.status_code == 403

    def test_cashier_cannot_create_employee(self, client, cashier_auth_headers):
        resp = client.post("/api/v1/employees", json=_NEW_EMPLOYEE_PAYLOAD, headers=cashier_auth_headers)
        assert resp.status_code == 403

    def test_cashier_cannot_update_employee(self, client, db, cashier_auth_headers, test_store):
        emp = Employee(
            store_id=test_store.id,
            full_name="Target",
            email="target_role@teststore.co.ke",
            password=hash_password("pass1234!"),
            role=Role.CASHIER,
            is_active=True,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)

        resp = client.put(f"/api/v1/employees/{emp.id}", json={"role": "supervisor"}, headers=cashier_auth_headers)
        assert resp.status_code == 403

    def test_unauthenticated_request_returns_401(self, client):
        resp = client.get("/api/v1/employees")
        assert resp.status_code == 401
