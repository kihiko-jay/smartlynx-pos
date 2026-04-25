"""Pydantic schemas for Store API responses."""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.subscription import Plan, SubStatus


class StoreOut(BaseModel):
    """Store details for API responses."""
    id: int
    name: str
    location: Optional[str] = None
    kra_pin: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    plan: Plan
    sub_status: SubStatus
    is_active: bool

    class Config:
        from_attributes = True


class StoreDetailedOut(StoreOut):
    """Detailed store information (includes subscription details)."""
    mpesa_enabled: bool
    mpesa_shortcode: Optional[str] = None
    mpesa_till_number: Optional[str] = None
    trial_ends_at: Optional[str] = None
    sub_ends_at: Optional[str] = None


class StoreBasicOut(BaseModel):
    """Minimal store information for PDFs and receipts."""
    id: int
    name: str
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    kra_pin: Optional[str] = None

    class Config:
        from_attributes = True
