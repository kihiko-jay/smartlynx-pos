"""Store API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_employee
from app.models.subscription import Store
from app.schemas.store import StoreOut, StoreBasicOut
from app.models.employee import Employee

router = APIRouter(prefix="/stores", tags=["stores"])


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
