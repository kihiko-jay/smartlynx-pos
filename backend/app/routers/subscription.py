"""
Subscription management router.

Handles:
  - Store registration (creates store + admin account)
  - Plan info / current subscription status
  - M-PESA payment to upgrade
  - M-PESA callback to activate premium
"""

import hashlib
import hmac
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

from app.core.deps import get_db, get_current_employee, require_admin, require_platform_owner
from app.core.datetime_utils import ensure_utc_datetime
from app.core.security import encrypt_sensitive_value
from app.models.subscription import Store, SubPayment, Plan, SubStatus
from app.models.employee import Employee, Role
from app.core.deps import _plan_details
from app.schemas.registration import StoreMpesaConfigUpdateRequest

import logging

router = APIRouter(prefix="/subscription", tags=["Subscription"])

logger = logging.getLogger(__name__)


from app.services.mpesa import verify_mpesa_callback_signature as _verify_subscription_callback_signature

PLAN_PRICES = {
    Plan.STARTER: 1500,
    Plan.GROWTH:  3500,
    Plan.PRO:     7500,
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class UpgradeRequest(BaseModel):
    plan:        Plan
    months:      int  = 1
    mpesa_phone: str       # phone to send STK push to


# ── Get current subscription status ──────────────────────────────────────────

@router.get("/status")
def get_status(
    current: Employee = Depends(get_current_employee),
    db:      Session  = Depends(get_db),
):
    if not current.store_id:
        return {"plan": "free", "is_premium": False, "message": "No store linked to this account."}

    store = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(404, "Store not found")

    now = datetime.now(timezone.utc)
    days_left = None
    trial_ends_at = ensure_utc_datetime(store.trial_ends_at)
    sub_ends_at = ensure_utc_datetime(store.sub_ends_at)

    if store.sub_status == SubStatus.TRIALING and trial_ends_at:
        days_left = max(0, (trial_ends_at - now).days)
    elif store.sub_status == SubStatus.ACTIVE and sub_ends_at:
        days_left = max(0, (sub_ends_at - now).days)

    if store.sub_status in {SubStatus.TRIALING, SubStatus.ACTIVE} and not (trial_ends_at or sub_ends_at):
        logger.warning(
            "Subscription status datetime missing",
            extra={"employee_id": current.id, "store_id": store.id, "sub_status": store.sub_status.value},
        )

    return {
        "store_id":     store.id,
        "store_name":   store.name,
        "plan":         store.plan,
        "plan_label":   store.plan_label,
        "status":       store.sub_status,
        "is_premium":   store.is_premium,
        "days_left":    days_left,
        "trial_ends":   str(trial_ends_at.date()) if trial_ends_at else None,
        "sub_ends":     str(sub_ends_at.date())   if sub_ends_at   else None,
        "available_plans": _plan_details(),
    }


# ── Initiate upgrade via M-PESA ───────────────────────────────────────────────

@router.post("/upgrade")
async def initiate_upgrade(
    payload:  UpgradeRequest,
    current:  Employee = Depends(require_admin),
    db:       Session  = Depends(get_db),
):
    if payload.plan == Plan.FREE:
        raise HTTPException(400, "Cannot upgrade to Free plan.")

    price    = PLAN_PRICES[payload.plan] * payload.months
    store    = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(404, "Store not found")

    # Create pending payment record
    payment = SubPayment(
        store_id    = store.id,
        amount      = price,
        plan        = payload.plan,
        months      = payload.months,
        status      = "pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    # Trigger M-PESA STK push
    try:
        from app.services.mpesa import stk_push
        result = await stk_push(
            phone      = payload.mpesa_phone,
            amount     = price,
            txn_number = f"SUB-{payment.id}",
        )
        return {
            "message":            f"STK push sent to {payload.mpesa_phone}. Enter your M-PESA PIN to activate {payload.plan.value} plan.",
            "amount":             price,
            "plan":               payload.plan,
            "months":             payload.months,
            "payment_id":         payment.id,
            "checkout_request_id": result.get("CheckoutRequestID"),
        }
    except Exception as e:
        raise HTTPException(502, f"M-PESA STK push failed: {str(e)}")


# ── M-PESA callback — activates the plan ─────────────────────────────────────

@router.post("/mpesa-callback")
async def subscription_mpesa_callback(request: Request, db: Session = Depends(get_db)):
    """
    Safaricom posts here after payment.
    Set MPESA_CALLBACK_URL_SUBSCRIPTION in .env to point here.

    Security: HMAC-SHA256 signature is verified when MPESA_WEBHOOK_SECRET is
    set. If the secret is not configured the check is skipped for backward
    compatibility — nginx IP allowlisting is assumed to be the outer guard.
    """
    raw_body   = await request.body()
    sig_header = request.headers.get("X-Mpesa-Signature")

    if not _verify_subscription_callback_signature(raw_body, sig_header):
        logger.error(
            "Subscription M-PESA callback: invalid signature — request rejected",
            extra={"signature_header": sig_header},
        )
        raise HTTPException(status_code=400, detail="Invalid callback signature")

    logger.info(
        "Subscription M-PESA callback: signature verified (or secret not configured)",
        extra={"signature_present": sig_header is not None},
    )

    try:
        request_body = json.loads(raw_body)
    except Exception:
        logger.error("Subscription M-PESA callback: could not parse request body as JSON")
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    try:
        stk = request_body["Body"]["stkCallback"]
        if stk["ResultCode"] != 0:
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        metadata  = {i["Name"]: i.get("Value") for i in stk["CallbackMetadata"]["Item"]}
        mpesa_ref = metadata.get("MpesaReceiptNumber")
        acct_ref  = metadata.get("AccountReference", "")   # SUB-{payment_id}

        if not acct_ref.startswith("SUB-"):
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        payment_id = int(acct_ref.split("-")[1])
        payment    = db.query(SubPayment).filter(SubPayment.id == payment_id).first()

        if payment and payment.status == "pending":
            payment.mpesa_ref = mpesa_ref
            payment.status    = "confirmed"

            # Activate the store's plan
            store = db.query(Store).filter(Store.id == payment.store_id).first()
            if store:
                now = datetime.now(timezone.utc)
                # If renewing, extend from current expiry; otherwise start now
                base = (store.sub_ends_at if store.sub_ends_at and store.sub_ends_at > now else now)
                store.plan        = payment.plan
                store.sub_status  = SubStatus.ACTIVE
                store.sub_ends_at = base + timedelta(days=30 * payment.months)

            db.commit()

    except Exception as e:
        logger.exception("Subscription callback processing error: %s", e)

    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# ── Admin: manually activate (for cash/bank payments) ────────────────────────
# SECURITY (v4.1): restricted to PLATFORM_OWNER only.
#
# Previously used require_admin, which allowed any store admin to activate
# ANY store by guessing or knowing its ID — a tenant-boundary violation.
# require_platform_owner ensures only the global operator account can call this.

@router.post("/activate/{store_id}", dependencies=[Depends(require_platform_owner)])
def manually_activate(
    store_id: int,
    plan:     Plan,
    months:   int = 1,
    db: Session = Depends(get_db),
):
    """
    Manually activate a store subscription (cash/bank payment path).
    Platform owner only — store admins are explicitly excluded.
    """
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(404, "Store not found")

    now       = datetime.now(timezone.utc)
    base      = store.sub_ends_at if store.sub_ends_at and store.sub_ends_at > now else now
    store.plan        = plan
    store.sub_status  = SubStatus.ACTIVE
    store.sub_ends_at = base + timedelta(days=30 * months)
    db.commit()

    return {"message": f"Store {store.name} activated on {plan.value} plan until {store.sub_ends_at.date()}"}


@router.patch('/store/mpesa-config', summary='Update store M-PESA configuration securely')
def update_store_mpesa_config(
    payload: StoreMpesaConfigUpdateRequest,
    current: Employee = Depends(require_admin),
    db: Session = Depends(get_db),
):
    store = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(404, 'Store not found')

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field in {'mpesa_consumer_key', 'mpesa_consumer_secret', 'mpesa_passkey'}:
            value = encrypt_sensitive_value(value) if value else None
        setattr(store, field, value)

    db.commit()
    return {
        'message': 'Store M-PESA configuration updated.',
        'mpesa_enabled': bool(store.mpesa_enabled),
        'configured': bool(store.mpesa_shortcode and store.mpesa_callback_url and store.mpesa_consumer_key),
    }
