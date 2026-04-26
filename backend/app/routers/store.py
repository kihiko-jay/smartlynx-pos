"""Store API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_employee, require_admin, require_manager
from app.models.subscription import Store
from app.schemas.store import StoreOut, StoreBasicOut
from app.models.employee import Employee
from app.core.encryption import encrypt_value, is_encryption_configured

router = APIRouter(prefix="/stores", tags=["stores"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models (Credentials Update & Status)
# ─────────────────────────────────────────────────────────────────────────────

class MpesaCredentialsUpdate(BaseModel):
    """Request body for updating per-store M-Pesa credentials."""
    consumer_key: Optional[str] = None
    consumer_secret: Optional[str] = None
    shortcode: Optional[str] = None
    passkey: Optional[str] = None
    till_number: Optional[str] = None
    callback_url: Optional[str] = None
    enabled: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class EtimsCredentialsUpdate(BaseModel):
    """Request body for updating per-store eTIMS credentials."""
    pin: Optional[str] = None
    branch_id: Optional[str] = None
    device_serial: Optional[str] = None
    enabled: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class CredentialsStatusResponse(BaseModel):
    """Response body for GET /stores/credentials/status endpoint."""
    mpesa: dict = {}
    etims: dict = {}

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Existing Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=StoreOut, dependencies=[Depends(get_current_employee)])
def get_current_store(
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """
    Get current store details (multi-tenant safe).
    
    Returns store information for the current employee's store.
    Requires authentication but no specific role restriction.
    """
    if not current.store_id:
        raise HTTPException(status_code=404, detail="Employee not associated with a store")
    
    store = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    return store


@router.get("/basic", response_model=StoreBasicOut, dependencies=[Depends(get_current_employee)])
def get_current_store_basic(
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """
    Get minimal store details (for PDFs and receipts).
    
    Returns only essential information: name, location, phone, email, KRA PIN.
    """
    if not current.store_id:
        raise HTTPException(status_code=404, detail="Employee not associated with a store")
    
    store = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    return store


# ─────────────────────────────────────────────────────────────────────────────
# Credential Management Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/credentials/mpesa")
def update_mpesa_credentials(
    payload: MpesaCredentialsUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_admin),
):
    """
    Update per-store M-Pesa credentials (admin only).
    
    Encrypts sensitive fields (consumer_key, consumer_secret, passkey) before storing.
    Only provided fields are updated; omitted fields are left unchanged.
    Never returns decrypted credential values.
    
    Security: Requires ADMIN role. Only store admins may configure payment credentials.
    """
    if not current.store_id:
        raise HTTPException(status_code=403, detail="Employee not associated with a store")
    
    if not is_encryption_configured():
        raise HTTPException(
            status_code=500,
            detail="Encryption not configured. Cannot store credentials securely."
        )
    
    store = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Update only provided fields
    if payload.consumer_key is not None:
        store.mpesa_consumer_key = encrypt_value(payload.consumer_key)
    if payload.consumer_secret is not None:
        store.mpesa_consumer_secret = encrypt_value(payload.consumer_secret)
    if payload.passkey is not None:
        store.mpesa_passkey = encrypt_value(payload.passkey)
    if payload.shortcode is not None:
        store.mpesa_shortcode = payload.shortcode
    if payload.till_number is not None:
        store.mpesa_till_number = payload.till_number
    if payload.callback_url is not None:
        store.mpesa_callback_url = payload.callback_url
    if payload.enabled is not None:
        store.mpesa_enabled = payload.enabled
    
    db.commit()
    
    return {
        "message": "M-Pesa credentials updated",
        "store_id": store.id,
    }


@router.patch("/credentials/etims")
def update_etims_credentials(
    payload: EtimsCredentialsUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_admin),
):
    """
    Update per-store eTIMS credentials (admin only).
    
    Encrypts sensitive fields (pin, device_serial) before storing.
    Only provided fields are updated; omitted fields are left unchanged.
    Never returns decrypted credential values.
    
    Security: Requires ADMIN role. Only store admins may configure tax credentials.
    """
    if not current.store_id:
        raise HTTPException(status_code=403, detail="Employee not associated with a store")
    
    if not is_encryption_configured():
        raise HTTPException(
            status_code=500,
            detail="Encryption not configured. Cannot store credentials securely."
        )
    
    store = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Update only provided fields
    if payload.pin is not None:
        store.etims_pin = encrypt_value(payload.pin)
    if payload.branch_id is not None:
        store.etims_branch_id = payload.branch_id
    if payload.device_serial is not None:
        store.etims_device_serial = encrypt_value(payload.device_serial)
    if payload.enabled is not None:
        store.etims_enabled = payload.enabled
    
    db.commit()
    
    return {
        "message": "eTIMS credentials updated",
        "store_id": store.id,
    }


@router.get("/credentials/status", response_model=CredentialsStatusResponse)
def get_credentials_status(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    Get credential configuration status for current store (manager+).
    
    Returns status WITHOUT revealing credential values (encrypted at rest).
    branch_id is NOT sensitive and is returned (for reference only).
    
    Security: Requires MANAGER role. Only managers and admins may view configuration.
    """
    if not current.store_id:
        raise HTTPException(status_code=403, detail="Employee not associated with a store")
    
    store = db.query(Store).filter(Store.id == current.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Build response — NEVER include decrypted values
    status = {
        "mpesa": {
            "configured": bool(store.mpesa_consumer_key and store.mpesa_shortcode),
            "enabled": store.mpesa_enabled,
        },
        "etims": {
            "configured": bool(store.etims_pin and store.etims_device_serial),
            "enabled": store.etims_enabled,
            "branch_id": store.etims_branch_id,
        },
    }
    
    return status
