from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import encrypt_sensitive_value, hash_password
from app.models.employee import Employee, Role
from app.models.subscription import Plan, Store, SubStatus

TRIAL_DAYS = 30


def create_store_with_admin(
    *,
    db: Session,
    store_name: str,
    store_location: str | None,
    store_email: str | None = None,
    store_phone: str | None = None,
    store_kra_pin: str | None = None,
    admin_full_name: str,
    admin_email: str,
    admin_password: str,
    admin_phone: str | None = None,
    mpesa_enabled: bool = False,
    mpesa_consumer_key: str | None = None,
    mpesa_consumer_secret: str | None = None,
    mpesa_shortcode: str | None = None,
    mpesa_passkey: str | None = None,
    mpesa_callback_url: str | None = None,
    mpesa_till_number: str | None = None,
    mpesa_phone: str | None = None,
):
    if db.query(Employee).filter(Employee.email == admin_email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(Store).filter(Store.name == store_name).first():
        raise HTTPException(status_code=400, detail="Store name already registered")

    trial_end = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
    store = Store(
        name=store_name,
        location=store_location,
        email=store_email,
        phone=store_phone,
        kra_pin=store_kra_pin,
        plan=Plan.FREE,
        sub_status=SubStatus.TRIALING,
        trial_ends_at=trial_end,
        is_active=True,
        mpesa_enabled=mpesa_enabled or False,
        mpesa_consumer_key=encrypt_sensitive_value(mpesa_consumer_key),
        mpesa_consumer_secret=encrypt_sensitive_value(mpesa_consumer_secret),
        mpesa_shortcode=mpesa_shortcode,
        mpesa_passkey=encrypt_sensitive_value(mpesa_passkey),
        mpesa_callback_url=mpesa_callback_url,
        mpesa_till_number=mpesa_till_number,
        mpesa_phone=mpesa_phone,
    )
    db.add(store)
    db.flush()

    admin = Employee(
        store_id=store.id,
        full_name=admin_full_name,
        email=admin_email,
        phone=admin_phone,
        password=hash_password(admin_password),
        role=Role.ADMIN,
        is_active=True,
    )
    db.add(admin)

    from app.services.accounting import seed_chart_of_accounts
    seed_chart_of_accounts(db, store.id)

    db.commit()
    db.refresh(store)
    db.refresh(admin)
    return store, admin, trial_end
