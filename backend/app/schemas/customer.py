from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Annotated
from datetime import datetime
from decimal import Decimal


class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = None
    credit_limit: Annotated[Optional[Decimal], Field(default=0)] = 0
    notes: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = None
    credit_limit: Annotated[Optional[Decimal], Field(default=None)] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerOut(CustomerBase):
    id: int
    store_id: int
    loyalty_points: int
    credit_balance: Decimal
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    """Paginated response for customer list"""
    items: List[CustomerOut]
    total: int
    skip: int
    limit: int


class CustomerCreditSummary(BaseModel):
    """Customer credit summary"""
    customer_id: int
    customer_name: str
    credit_limit: Decimal
    credit_balance: Decimal
    available_credit: Decimal  # credit_limit - credit_balance
    credit_utilization_percent: float  # (credit_balance / credit_limit) * 100


class CustomerTransactionHistory(BaseModel):
    """Customer transaction history summary"""
    customer_id: int
    customer_name: str
    total_transactions: int
    total_amount: Decimal
    last_transaction_date: Optional[datetime] = None
    loyalty_points: int
