"""
Customers router — Master data management

Features:
  1. Full CRUD operations (Create, Read, Update, Delete/Deactivate)
  2. Search and pagination support
  3. Credit management and transaction history
  4. Bulk operations (activate/deactivate, credit update, export)
  5. Multi-store isolation via store_id
"""

import logging
import csv
from io import StringIO
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional
from datetime import datetime

from app.core.deps import (
    get_db, require_cashier, require_premium
)
from app.models.customer import Customer, CustomerPayment
from app.models.employee import Employee, Role
from app.models.transaction import Transaction
from app.services.accounting import post_customer_payment, get_customer_statement, get_ar_aging
from pydantic import BaseModel, Field
from decimal import Decimal
import uuid
from app.models.audit import AuditTrail
from app.schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerOut,
    CustomerListResponse, CustomerCreditSummary,
    CustomerTransactionHistory,
)

logger = logging.getLogger("dukapos.customers")
router = APIRouter(prefix="/customers", tags=["Customers"])


class CustomerPaymentCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    payment_method: str
    payment_date: Optional[datetime] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_audit(
    db,
    actor: Employee,
    action: str,
    entity_id: str,
    before=None,
    after=None,
    notes=None,
):
    """Write audit trail entry for customer actions"""
    db.add(AuditTrail(
        store_id=actor.store_id,
        actor_id=actor.id,
        actor_name=actor.full_name,
        action=action,
        entity="customer",
        entity_id=str(entity_id),
        before_val=before,
        after_val=after,
        notes=notes,
    ))


def _own_customer(customer: Customer, current: Employee) -> bool:
    """Check if employee owns/can manage this customer"""
    if current.role == Role.PLATFORM_OWNER:
        return True
    return customer.store_id == current.store_id


# ── CRUD Operations ────────────────────────────────────────────────────────────

@router.get("", response_model=CustomerListResponse)
def list_customers(
    search: Optional[str] = Query(None, description="Search by name, phone, or email"),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    """List customers with pagination and search"""
    q = db.query(Customer)

    if current.role != Role.PLATFORM_OWNER:
        q = q.filter(Customer.store_id == current.store_id)

    # Apply is_active filter
    if is_active is not None:
        q = q.filter(Customer.is_active == is_active)
    else:
        # Default: show only active customers
        q = q.filter(Customer.is_active == True)

    # Apply search filter
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Customer.name.ilike(like),
            Customer.phone.ilike(like),
            Customer.email.ilike(like),
        ))

    # Count total before pagination
    total = q.count()

    # Apply pagination
    results = q.offset(skip).limit(limit).all()

    return CustomerListResponse(
        items=[CustomerOut.model_validate(c) for c in results],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    """Get customer by ID"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")

    if not _own_customer(customer, current):
        raise HTTPException(403, "Customer not found in your store")

    return customer


@router.post("", response_model=CustomerOut)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Create a new customer"""
    # Check for duplicate phone in store (if provided)
    if payload.phone:
        existing = (
            db.query(Customer)
            .filter(Customer.phone == payload.phone)
            .filter(Customer.store_id == current.store_id)
            .first()
        )
        if existing:
            raise HTTPException(
                400,
                f"A customer with phone '{payload.phone}' already exists in your store"
            )

    data = payload.model_dump()
    customer = Customer(**data, store_id=current.store_id)
    db.add(customer)

    _write_audit(
        db,
        current,
        "create",
        customer.name,
        after={"name": customer.name, "phone": customer.phone},
    )

    db.commit()
    db.refresh(customer)
    logger.info(f"Created customer {customer.id} in store {current.store_id}")
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Update customer details"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")

    if not _own_customer(customer, current):
        raise HTTPException(403, "Customer not found in your store")

    before = {
        "name": customer.name,
        "phone": customer.phone,
        "credit_limit": str(customer.credit_limit),
    }

    # Check for duplicate phone if phone is being updated
    if payload.phone and payload.phone != customer.phone:
        existing = (
            db.query(Customer)
            .filter(Customer.phone == payload.phone)
            .filter(Customer.store_id == current.store_id)
            .filter(Customer.id != customer_id)
            .first()
        )
        if existing:
            raise HTTPException(
                400,
                f"A customer with phone '{payload.phone}' already exists in your store"
            )

    # Update fields
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    _write_audit(
        db,
        current,
        "update",
        customer.name,
        before=before,
        after={
            "name": customer.name,
            "phone": customer.phone,
            "credit_limit": str(customer.credit_limit),
        },
    )

    db.commit()
    db.refresh(customer)
    logger.info(f"Updated customer {customer.id} in store {current.store_id}")
    return customer


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Soft delete a customer (deactivate)"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")

    if not _own_customer(customer, current):
        raise HTTPException(403, "Customer not found in your store")

    customer.is_active = False
    _write_audit(
        db,
        current,
        "delete",
        customer.name,
        before={"is_active": True},
        after={"is_active": False},
    )

    db.commit()
    logger.info(f"Deactivated customer {customer.id} in store {current.store_id}")
    return {"success": True, "message": "Customer deactivated"}


# ── Bulk Operations ────────────────────────────────────────────────────────────

@router.post("/bulk/activate")
def bulk_activate_customers(
    customer_ids: List[int],
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Activate multiple customers"""
    customers = (
        db.query(Customer)
        .filter(Customer.id.in_(customer_ids))
        .filter(Customer.store_id == current.store_id)
        .all()
    )

    if not customers:
        raise HTTPException(404, "No customers found")

    for customer in customers:
        customer.is_active = True
        _write_audit(
            db, current, "bulk_activate", customer.name,
            before={"is_active": False},
            after={"is_active": True},
        )

    db.commit()
    return {
        "success": True,
        "count": len(customers),
        "message": f"Activated {len(customers)} customers",
    }


@router.post("/bulk/deactivate")
def bulk_deactivate_customers(
    customer_ids: List[int],
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Deactivate multiple customers"""
    customers = (
        db.query(Customer)
        .filter(Customer.id.in_(customer_ids))
        .filter(Customer.store_id == current.store_id)
        .all()
    )

    if not customers:
        raise HTTPException(404, "No customers found")

    for customer in customers:
        customer.is_active = False
        _write_audit(
            db, current, "bulk_deactivate", customer.name,
            before={"is_active": True},
            after={"is_active": False},
        )

    db.commit()
    return {
        "success": True,
        "count": len(customers),
        "message": f"Deactivated {len(customers)} customers",
    }


@router.post("/bulk/export")
def export_customers(
    customer_ids: Optional[List[int]] = None,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Export customers to CSV"""
    q = db.query(Customer).filter(Customer.store_id == current.store_id)

    if customer_ids:
        q = q.filter(Customer.id.in_(customer_ids))

    customers = q.all()

    if not customers:
        raise HTTPException(404, "No customers found")

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Name", "Phone", "Email",
        "Credit Limit", "Credit Balance", "Loyalty Points",
        "Active", "Created At", "Updated At",
    ])

    for c in customers:
        writer.writerow([
            c.id, c.name, c.phone or "", c.email or "",
            str(c.credit_limit), str(c.credit_balance), c.loyalty_points,
            "Yes" if c.is_active else "No",
            c.created_at.isoformat() if c.created_at else "",
            c.updated_at.isoformat() if c.updated_at else "",
        ])

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customers.csv"},
    )


# ── Credit & Transaction History ──────────────────────────────────────────────

@router.get("/{customer_id}/credit-summary", response_model=CustomerCreditSummary)
def get_customer_credit_summary(
    customer_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    """Get customer credit summary"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")

    if not _own_customer(customer, current):
        raise HTTPException(403, "Customer not found in your store")

    available = customer.credit_limit - customer.credit_balance
    utilization = (
        float((customer.credit_balance / customer.credit_limit) * 100)
        if customer.credit_limit > 0
        else 0
    )

    return CustomerCreditSummary(
        customer_id=customer.id,
        customer_name=customer.name,
        credit_limit=customer.credit_limit,
        credit_balance=customer.credit_balance,
        available_credit=available,
        credit_utilization_percent=utilization,
    )


@router.get("/{customer_id}/transactions", response_model=CustomerTransactionHistory)
def get_customer_transaction_history(
    customer_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    """Get customer transaction history summary"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")

    if not _own_customer(customer, current):
        raise HTTPException(403, "Customer not found in your store")

    # Query transactions for this customer
    q = db.query(Transaction).filter(Transaction.customer_id == customer_id)
    total_transactions = q.count()

    # Calculate totals
    total_amount = db.query(func.sum(Transaction.total)).filter(
        Transaction.customer_id == customer_id
    ).scalar() or 0

    # Get last transaction date
    last_txn = q.order_by(Transaction.created_at.desc()).first()
    last_date = last_txn.created_at if last_txn else None

    return CustomerTransactionHistory(
        customer_id=customer.id,
        customer_name=customer.name,
        total_transactions=total_transactions,
        total_amount=total_amount,
        last_transaction_date=last_date,
        loyalty_points=customer.loyalty_points,
    )


# ── Post-transaction credit updates ────────────────────────────────────────────

@router.patch("/{customer_id}/credit-balance")
def update_customer_credit_balance(
    customer_id: int,
    amount_delta: float,
    reason: str = Query(..., description="Reason for credit adjustment"),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Update customer credit balance (for post-transaction adjustments)"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")

    if not _own_customer(customer, current):
        raise HTTPException(403, "Customer not found in your store")

    before_balance = float(customer.credit_balance)

    # Update balance (ensure it doesn't exceed credit limit or go below 0)
    new_balance = float(customer.credit_balance) + amount_delta
    customer.credit_balance = max(0, min(customer.credit_limit, new_balance))

    _write_audit(
        db,
        current,
        "credit_adjustment",
        customer.name,
        before={"credit_balance": before_balance},
        after={"credit_balance": float(customer.credit_balance)},
        notes=f"Reason: {reason}",
    )

    db.commit()
    db.refresh(customer)

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "previous_balance": before_balance,
        "new_balance": float(customer.credit_balance),
        "credit_limit": float(customer.credit_limit),
    }



@router.post("/{customer_id}/payments")
def create_customer_payment(customer_id: int, payload: CustomerPaymentCreate, db: Session = Depends(get_db), current: Employee = Depends(require_premium)):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == current.store_id).with_for_update().first()
    if not customer:
        raise HTTPException(404, "Customer not found")
    amount = Decimal(str(payload.amount))
    if amount > Decimal(str(customer.credit_balance or 0)):
        raise HTTPException(400, "Payment cannot exceed outstanding customer balance")
    payment_number = f"CP-{uuid.uuid4().hex[:8].upper()}"
    cp = CustomerPayment(store_id=current.store_id, customer_id=customer.id, payment_number=payment_number, payment_date=payload.payment_date or datetime.utcnow(), amount=amount, payment_method=payload.payment_method, reference=payload.reference, notes=payload.notes, created_by=current.id)
    db.add(cp)
    customer.credit_balance = (Decimal(str(customer.credit_balance or 0)) - amount).quantize(Decimal("0.01"))
    post_customer_payment(db, current.store_id, customer, amount, (payload.payment_date or datetime.utcnow()).date(), payload.payment_method, payload.reference or payment_number, current.id)
    _write_audit(db, current, "customer_payment", customer.name, before=None, after={"amount": float(amount), "payment_number": payment_number})
    db.commit()
    return {"payment_number": payment_number, "customer_id": customer.id, "new_balance": float(customer.credit_balance)}


@router.get("/{customer_id}/statement")
def customer_statement(customer_id: int, db: Session = Depends(get_db), current: Employee = Depends(require_cashier)):
    return get_customer_statement(db, current.store_id, customer_id)


@router.get("/aging")
def customers_aging(db: Session = Depends(get_db), current: Employee = Depends(require_cashier)):
    return get_ar_aging(db, current.store_id)
