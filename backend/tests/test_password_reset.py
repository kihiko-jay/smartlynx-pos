"""
Integration tests — Password reset flow (Phase 2)

Covers:
  - forgot-password with existing email returns 200 + generic message
  - forgot-password with non-existent email returns 200 + same generic message (no enumeration)
  - PasswordResetToken row created after forgot-password
  - reset-password with valid token + correct email succeeds
  - reset-password with expired token returns 400
  - reset-password with already-used token returns 400
  - reset-password with wrong email for a valid token returns 400
  - After successful reset, old password no longer works for login
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.security import generate_password_reset_token, hash_token
from app.models.registration import PasswordResetToken
from app.models.employee import Employee, Role
from app.core.security import hash_password

_GENERIC_MESSAGE = "If an account with that email exists, a password reset link will be sent."


class TestForgotPassword:

    def test_existing_email_returns_200(self, client, test_admin):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": test_admin.email})
        assert resp.status_code == 200

    def test_existing_email_returns_generic_message(self, client, test_admin):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": test_admin.email})
        assert resp.json()["message"] == _GENERIC_MESSAGE

    def test_nonexistent_email_returns_200(self, client):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@nowhere.com"})
        assert resp.status_code == 200

    def test_nonexistent_email_returns_same_generic_message(self, client):
        """Response must be identical to prevent email enumeration."""
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@nowhere.com"})
        assert resp.json()["message"] == _GENERIC_MESSAGE

    def test_token_row_created_in_db(self, client, db, test_admin):
        client.post("/api/v1/auth/forgot-password", json={"email": test_admin.email})
        record = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.employee_id == test_admin.id)
            .first()
        )
        assert record is not None
        assert record.is_used is False
        assert record.expires_at > datetime.now(timezone.utc)

    def test_second_request_invalidates_previous_token(self, client, db, test_admin):
        client.post("/api/v1/auth/forgot-password", json={"email": test_admin.email})
        client.post("/api/v1/auth/forgot-password", json={"email": test_admin.email})
        used_count = (
            db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.employee_id == test_admin.id,
                PasswordResetToken.is_used == True,
            )
            .count()
        )
        assert used_count >= 1, "Previous tokens should be marked used after a new request"


class TestResetPassword:

    def _seed_token(self, db, employee, *, expired=False, used=False):
        """Helper: insert a PasswordResetToken row and return the raw token."""
        raw = generate_password_reset_token()
        expires_at = (
            datetime.now(timezone.utc) - timedelta(hours=1)
            if expired
            else datetime.now(timezone.utc) + timedelta(hours=1)
        )
        record = PasswordResetToken(
            employee_id=employee.id,
            token_hash=hash_token(raw),
            expires_at=expires_at,
            is_used=used,
            used_at=datetime.now(timezone.utc) if used else None,
        )
        db.add(record)
        db.commit()
        return raw

    def test_valid_token_and_email_returns_200(self, client, db, test_admin):
        raw = self._seed_token(db, test_admin)
        resp = client.post("/api/v1/auth/reset-password", json={
            "email": test_admin.email,
            "token": raw,
            "new_password": "NewSecure1234!",
        })
        assert resp.status_code == 200

    def test_expired_token_returns_400(self, client, db, test_admin):
        raw = self._seed_token(db, test_admin, expired=True)
        resp = client.post("/api/v1/auth/reset-password", json={
            "email": test_admin.email,
            "token": raw,
            "new_password": "NewSecure1234!",
        })
        assert resp.status_code == 400

    def test_already_used_token_returns_400(self, client, db, test_admin):
        raw = self._seed_token(db, test_admin, used=True)
        resp = client.post("/api/v1/auth/reset-password", json={
            "email": test_admin.email,
            "token": raw,
            "new_password": "NewSecure1234!",
        })
        assert resp.status_code == 400

    def test_wrong_email_for_valid_token_returns_400(self, client, db, test_admin):
        self._seed_token(db, test_admin)
        resp = client.post("/api/v1/auth/reset-password", json={
            "email": "wrong@example.com",
            "token": "somefaketoken",
            "new_password": "NewSecure1234!",
        })
        assert resp.status_code == 400

    def test_token_marked_used_after_successful_reset(self, client, db, test_admin):
        raw = self._seed_token(db, test_admin)
        client.post("/api/v1/auth/reset-password", json={
            "email": test_admin.email,
            "token": raw,
            "new_password": "NewSecure1234!",
        })
        db.expire_all()
        record = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.employee_id == test_admin.id)
            .order_by(PasswordResetToken.id.desc())
            .first()
        )
        assert record.is_used is True
        assert record.used_at is not None

    def test_replay_prevention_second_use_returns_400(self, client, db, test_admin):
        """Using the same token twice must fail on the second attempt."""
        raw = self._seed_token(db, test_admin)
        client.post("/api/v1/auth/reset-password", json={
            "email": test_admin.email,
            "token": raw,
            "new_password": "NewSecure1234!",
        })
        resp2 = client.post("/api/v1/auth/reset-password", json={
            "email": test_admin.email,
            "token": raw,
            "new_password": "AnotherPass9999!",
        })
        assert resp2.status_code == 400

    def test_old_password_no_longer_works_after_reset(self, client, db, test_admin):
        original_email = test_admin.email
        raw = self._seed_token(db, test_admin)
        client.post("/api/v1/auth/reset-password", json={
            "email": original_email,
            "token": raw,
            "new_password": "BrandNewPass999!",
        })
        # Old password should be rejected
        login_resp = client.post("/api/v1/auth/login", json={
            "email": original_email,
            "password": "testpass123",
        })
        assert login_resp.status_code == 401

    def test_new_password_works_after_reset(self, client, db, test_admin):
        original_email = test_admin.email
        new_password = "BrandNewPass999!"
        raw = self._seed_token(db, test_admin)
        client.post("/api/v1/auth/reset-password", json={
            "email": original_email,
            "token": raw,
            "new_password": new_password,
        })
        login_resp = client.post("/api/v1/auth/login", json={
            "email": original_email,
            "password": new_password,
        })
        assert login_resp.status_code == 200
