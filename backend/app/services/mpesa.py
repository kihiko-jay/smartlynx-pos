"""
M-PESA Daraja API integration — Lipa Na M-PESA STK Push (per-store).

Safaricom sandbox: https://sandbox.safaricom.co.ke
Production:        https://api.safaricom.co.ke

Steps:
  1. POST /oauth/v1/generate  → get access token
  2. POST /mpesa/stkpush/v1/processrequest → trigger STK push on customer phone
  3. Safaricom hits MPESA_CALLBACK_URL with payment result
  4. Our callback handler marks the transaction COMPLETED

CHANGE: Each store now has its own M-PESA paybill (shortcode), credentials, and callback URL.
"""

import base64
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.subscription import Store
from app.core.config import settings
from app.core.security import decrypt_sensitive_value


SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
PROD_BASE    = "https://api.safaricom.co.ke"


def _base_url(store: Store | None = None) -> str:
    """Use store's M-PESA env if configured, else fall back to global settings."""
    # For now, all stores use the same environment (sandbox/prod)
    # In future, could be per-store if needed
    return SANDBOX_BASE if settings.MPESA_ENV == "sandbox" else PROD_BASE


async def get_access_token(consumer_key: str, consumer_secret: str) -> str:
    """Fetch a short-lived OAuth2 access token from Safaricom."""
    credentials = base64.b64encode(
        f"{consumer_key}:{consumer_secret}".encode()
    ).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {credentials}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def _generate_password(shortcode: str, passkey: str) -> tuple[str, str]:
    """
    Returns (password, timestamp).
    Password = base64(shortcode + passkey + timestamp)
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


async def stk_push(
    phone: str,
    amount: float,
    txn_number: str,
    store: Store,
) -> dict:
    """
    Trigger an STK Push to the customer's phone using store-specific M-Pesa config.

    Args:
        phone:      Customer phone in format 2547XXXXXXXX
        amount:     Amount in KES (will be rounded to int — M-PESA requires whole shillings)
        txn_number: Our internal transaction reference
        store:      Store model instance with M-PESA credentials

    Returns:
        Daraja API response dict with CheckoutRequestID

    Raises:
        ValueError: If store's M-PESA is not configured
    """
    # Validate store M-PESA config
    if not store.mpesa_enabled:
        raise ValueError(f"M-PESA not enabled for store '{store.name}'")
    if not store.mpesa_consumer_key:
        raise ValueError(f"M-PESA consumer key not configured for store '{store.name}'")
    if not store.mpesa_consumer_secret:
        raise ValueError(f"M-PESA consumer secret not configured for store '{store.name}'")
    if not store.mpesa_shortcode:
        raise ValueError(f"M-PESA paybill (shortcode) not configured for store '{store.name}'")
    if not store.mpesa_passkey:
        raise ValueError(f"M-PESA passkey not configured for store '{store.name}'")
    if not store.mpesa_callback_url:
        raise ValueError(f"M-PESA callback URL not configured for store '{store.name}'")

    # Normalise phone: 07XX → 2547XX
    phone = phone.strip().replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]

    consumer_key = decrypt_sensitive_value(store.mpesa_consumer_key)
    consumer_secret = decrypt_sensitive_value(store.mpesa_consumer_secret)
    passkey = decrypt_sensitive_value(store.mpesa_passkey)

    token = await get_access_token(consumer_key, consumer_secret)
    password, timestamp = _generate_password(store.mpesa_shortcode, passkey)

    payload = {
        "BusinessShortCode": store.mpesa_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerBuyGoodsOnline",
        "Amount": int(round(amount)),
        "PartyA": phone,
        "PartyB": store.mpesa_shortcode,
        "PhoneNumber": phone,
        "CallBackURL": store.mpesa_callback_url,
        "AccountReference": txn_number,
        "TransactionDesc": f"Payment for {txn_number} - {store.name}",  # Use store name
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url(store)}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def query_stk_status(
    checkout_request_id: str,
    store: Store,
) -> dict:
    """
    Query the status of an STK push using store-specific credentials.

    Args:
        checkout_request_id: Safaricom's CheckoutRequestID
        store:               Store model with M-PESA credentials

    Returns:
        Daraja API response dict with payment status
    """
    if not store.mpesa_enabled:
        raise ValueError(f"M-PESA not enabled for store '{store.name}'")
    if not store.mpesa_consumer_key or not store.mpesa_consumer_secret:
        raise ValueError(f"M-PESA credentials not configured for store '{store.name}'")

    consumer_key = decrypt_sensitive_value(store.mpesa_consumer_key)
    consumer_secret = decrypt_sensitive_value(store.mpesa_consumer_secret)
    passkey = decrypt_sensitive_value(store.mpesa_passkey)

    token = await get_access_token(consumer_key, consumer_secret)
    password, timestamp = _generate_password(store.mpesa_shortcode, passkey)

    payload = {
        "BusinessShortCode": store.mpesa_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url(store)}/mpesa/stkpush/v1/query",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


# ── Webhook signature verification ───────────────────────────────────────────

import hashlib
import hmac
import logging

_sig_logger = logging.getLogger(__name__)


def verify_mpesa_callback_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify the Daraja callback HMAC-SHA256 signature.

    Single canonical implementation — imported by both app/routers/mpesa.py and
    app/routers/subscription.py. Any change here applies to both callbacks.

    If MPESA_WEBHOOK_SECRET is not set, verification is skipped for backward
    compatibility — nginx IP allowlisting is assumed as the outer guard.
    """
    secret = settings.MPESA_WEBHOOK_SECRET
    if not secret:
        return True  # No secret configured — rely on IP allowlisting
    if not signature_header:
        _sig_logger.warning("M-PESA callback received without signature header")
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
