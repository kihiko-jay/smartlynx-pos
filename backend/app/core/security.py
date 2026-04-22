"""
Security utilities: password hashing, JWT access + refresh tokens.

Token architecture:
  - Access token:  short-lived (configurable, default 30 min)
  - Refresh token: long-lived (configurable, default 8 h / one shift)
  - Both are JWTs signed with the same SECRET_KEY but carry a `type` claim
    so a refresh token CANNOT be used as an access token and vice-versa.
  - Token payload always includes `jti` (JWT ID) for future revocation support.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
import time
import secrets
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_ACCESS_TOKEN_TYPE  = "access"
_REFRESH_TOKEN_TYPE = "refresh"


from app.core.distributed_auth import auth_state


# ── Refresh-token revocation blocklist ────────────────────────────────────────
def revoke_token(payload: dict) -> None:
    """Revoke a token by its jti until its natural expiry."""
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    auth_state.revoke_jti(str(jti), float(exp))


def is_token_revoked(payload: dict) -> bool:
    """Return True if this token's jti has been explicitly revoked."""
    jti = payload.get("jti")
    if not jti:
        return False
    return auth_state.is_jti_revoked(str(jti))


# ── Password utils ────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Password Reset Token Utilities ────────────────────────────────────────────

def generate_password_reset_token() -> str:
    """Generate a secure, URL-safe token for password reset."""
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    """Hash the token for secure storage in the database."""
    return pwd_context.hash(token)

def verify_token(token: str, hashed: str) -> bool:
    """Verify a token against its hashed value."""
    return pwd_context.verify(token, hashed)


def fingerprint_token(token: str) -> str:
    """Stable SHA-256 fingerprint for DB/session lookup without storing raw tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Token creation ────────────────────────────────────────────────────────────

def _make_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    payload = data.copy()
    now = datetime.now(timezone.utc)
    payload.update({
        "type": token_type,
        "iat":  now,
        "exp":  now + expires_delta,
        "jti":  str(uuid.uuid4()),   # unique token ID — enables revocation
    })
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _make_token(data, _ACCESS_TOKEN_TYPE, delta)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    delta = expires_delta or timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)
    payload = data.copy()
    payload.setdefault("family", str(uuid.uuid4()))
    payload.setdefault("sid", str(uuid.uuid4()))
    return _make_token(payload, _REFRESH_TOKEN_TYPE, delta)


# ── Token decoding (strict) ───────────────────────────────────────────────────

def _decode_strict(token: str, expected_type: str) -> Optional[dict]:
    """
    Decode and validate a JWT.

    Strict checks:
      1. Signature must be valid
      2. Token must not be expired
      3. `type` claim must match expected_type (prevents refresh-as-access attacks)
      4. `sub` claim must be present and non-empty
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type", "jti"]},
        )
    except JWTError:
        return None

    if payload.get("type") != expected_type:
        return None
    if not payload.get("sub"):
        return None
    if is_token_revoked(payload):
        return None

    return payload


def decode_token(token: str) -> Optional[dict]:
    """Decode an access token. Returns None on any validation failure."""
    return _decode_strict(token, _ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode a refresh token. Returns None on any validation failure."""
    return _decode_strict(token, _REFRESH_TOKEN_TYPE)


# ── Encryption helpers for application secrets ───────────────────────────────

def _derive_fernet_key() -> bytes:
    source = (settings.SECRET_ENCRYPTION_KEY or settings.SECRET_KEY).encode()
    digest = hashlib.sha256(source).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    return Fernet(_derive_fernet_key())


def is_encrypted_value(value: str | None) -> bool:
    return bool(value and isinstance(value, str) and value.startswith("enc::"))


def encrypt_sensitive_value(value: str | None) -> str | None:
    if not value:
        return value
    if is_encrypted_value(value):
        return value
    token = _get_fernet().encrypt(value.encode()).decode()
    return f"enc::{token}"


def decrypt_sensitive_value(value: str | None) -> str | None:
    if not value:
        return value
    if not is_encrypted_value(value):
        return value
    token = value.split("enc::", 1)[1]
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
