
from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException,Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_employee, require_manager, require_cashier
from app.models.employee import Employee
from app.models.expenses import ExpenseVoucher
from app.services.accounting import post_expense_voucher, post_expense_voucher_void
from app.services.reconciliation import assert_period_open

router = APIRouter(prefix="/expenses", tags=["Expenses"])


class ExpenseVoucherCreate(BaseModel):
    expense_date: date
    account_id: int
    amount: Decimal = Field(..., gt=0)
    payment_method: str
    payee: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


@router.post("", dependencies=[Depends(require_manager)])
def create_expense(payload: ExpenseVoucherCreate, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    assert_period_open(db, current.store_id, payload.expense_date)
    voucher = ExpenseVoucher(store_id=current.store_id, voucher_number=f"EXP-{uuid.uuid4().hex[:8].upper()}", expense_date=payload.expense_date, account_id=payload.account_id, amount=payload.amount, payment_method=payload.payment_method, payee=payload.payee, reference=payload.reference, notes=payload.notes, created_by=current.id)
    db.add(voucher)
    db.flush()
    post_expense_voucher(db, voucher)
    db.commit()
    db.refresh(voucher)
    return voucher


@router.get("", dependencies=[Depends(require_cashier)])
def list_expenses(skip: int = 0, limit: int =Query(50,le=200), db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    return db.query(ExpenseVoucher).filter(ExpenseVoucher.store_id == current.store_id).order_by(ExpenseVoucher.expense_date.desc(), ExpenseVoucher.id.desc()).offset(skip).limit(limit).all()


@router.get("/{expense_id}", dependencies=[Depends(require_cashier)])
def get_expense(expense_id: int, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    row = db.query(ExpenseVoucher).filter(ExpenseVoucher.id == expense_id, ExpenseVoucher.store_id == current.store_id).first()
    if not row:
        raise HTTPException(404, "Expense not found")
    return row


@router.post("/{expense_id}/void", dependencies=[Depends(require_manager)])
def void_expense(expense_id: int, reason: str, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    row = db.query(ExpenseVoucher).filter(ExpenseVoucher.id == expense_id, ExpenseVoucher.store_id == current.store_id).first()
    if not row:
        raise HTTPException(404, "Expense not found")
    assert_period_open(db, current.store_id, row.expense_date)
    row.is_void = True
    row.void_reason = reason
    row.voided_at = datetime.utcnow()
    row.voided_by = current.id
    try:
        post_expense_voucher_void(db, row)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to post void reversal: {exc}") from exc
    db.commit()
    return {"message": "Expense voucher voided"}
