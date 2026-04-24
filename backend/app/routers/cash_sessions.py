from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_employee, require_cashier
from app.core.config import settings
from app.models.employee import Employee, Role
from app.models.cash_session import CashSession
from app.services.accounting import post_cash_session_open, post_cash_session_close

router = APIRouter(prefix="/cash-sessions", tags=["Cash Sessions"])


class CashSessionOpen(BaseModel):
    opening_float: Decimal = Field(..., ge=0)
    terminal_id: Optional[str] = None
    notes: Optional[str] = None


class CashSessionClose(BaseModel):
    payment_counts: dict = Field(..., description="Counted amounts by payment method")
    total_counted: Decimal = Field(..., ge=0, description="Total of all counted amounts")
    notes: Optional[str] = None


@router.post("/open", dependencies=[Depends(require_cashier)])
def open_cash_session(
    payload: CashSessionOpen, 
    db: Session = Depends(get_db), 
    current: Employee = Depends(get_current_employee)
):
    # Use the terminal_id from payload or from employee's current terminal
    terminal_id = payload.terminal_id or current.terminal_id or "T01"
    
    # Check for existing open session
    existing = db.query(CashSession).filter(
        CashSession.store_id == current.store_id,
        CashSession.cashier_id == current.id,
        CashSession.terminal_id == terminal_id,
        CashSession.status == 'open'
    ).first()
    
    if existing:
        raise HTTPException(400, 'Cashier already has an open session on this terminal')
    
    # Create new cash session
    row = CashSession(
        store_id=current.store_id,
        cashier_id=current.id,
        terminal_id=terminal_id,
        session_number=f"CS-{uuid.uuid4().hex[:8].upper()}",
        opening_float=payload.opening_float,
        expected_cash=payload.opening_float,
        status='open',
        opened_by=current.id,
        notes=payload.notes
    )
    db.add(row)
    db.flush()
    
    try:
        post_cash_session_open(db, row)
    except (ValueError, Exception) as e:
        print(f"Warning: Failed to post cash session accounting entry: {e}")
    
    db.commit()
    db.refresh(row)
    return row


@router.get("", dependencies=[Depends(require_cashier)])
def list_cash_sessions(
    db: Session = Depends(get_db), 
    current: Employee = Depends(get_current_employee)
):
    """List all cash sessions for the current store"""
    return db.query(CashSession).filter(
        CashSession.store_id == current.store_id
    ).order_by(CashSession.opened_at.desc()).all()


@router.get("/current", dependencies=[Depends(require_cashier)])
def get_current_cash_session(
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """
    Get the current open cash session for the cashier.
    Uses terminal_id from employee record if available.
    """
    # Try exact match with terminal_id
    terminal_id = current.terminal_id
    
    if terminal_id:
        row = db.query(CashSession).filter(
            CashSession.store_id == current.store_id,
            CashSession.cashier_id == current.id,
            CashSession.terminal_id == terminal_id,
            CashSession.status == "open",
        ).order_by(CashSession.opened_at.desc()).first()
        
        if row:
            return row
    
    # Fallback: any open session for this cashier (regardless of terminal)
    row = db.query(CashSession).filter(
        CashSession.store_id == current.store_id,
        CashSession.cashier_id == current.id,
        CashSession.status == "open",
    ).order_by(CashSession.opened_at.desc()).first()
    
    return row


@router.get("/{session_id}", dependencies=[Depends(require_cashier)])
def get_cash_session(
    session_id: int, 
    db: Session = Depends(get_db), 
    current: Employee = Depends(get_current_employee)
):
    row = db.query(CashSession).filter(
        CashSession.id == session_id, 
        CashSession.store_id == current.store_id
    ).first()
    if not row:
        raise HTTPException(404, 'Cash session not found')
    return row


@router.post("/{session_id}/close", dependencies=[Depends(require_cashier)])
def close_cash_session(
    session_id: int, 
    payload: CashSessionClose, 
    db: Session = Depends(get_db), 
    current: Employee = Depends(get_current_employee)
):
    row = db.query(CashSession).filter(
        CashSession.id == session_id, 
        CashSession.store_id == current.store_id
    ).with_for_update().first()
    
    if not row:
        raise HTTPException(404, 'Cash session not found')
    if row.status != 'open':
        raise HTTPException(400, 'Cash session is not open')

    # Ownership guard — cashiers may only close their own sessions
    if current.role == Role.CASHIER and row.cashier_id != current.id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Cashiers may only close their own sessions. "
                "Ask a supervisor or manager to close this session."
            ),
        )

    row.counted_cash = payload.payment_counts.get('cash', 0)
    row.counted_mpesa = payload.payment_counts.get('mpesa', 0)
    row.counted_card = payload.payment_counts.get('card', 0)
    row.counted_credit = payload.payment_counts.get('credit', 0)
    row.counted_store_credit = payload.payment_counts.get('store_credit', 0)
    row.total_counted = payload.total_counted
    row.variance = (
        Decimal(str(payload.payment_counts.get('cash', 0))) - Decimal(str(row.expected_cash or 0))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    row.closed_at = datetime.utcnow()
    row.closed_by = current.id
    row.status = 'closed'
    if payload.notes:
        row.notes = (row.notes or "") + "\nClose: " + payload.notes

    # Variance threshold enforcement
    VARIANCE_ALERT_THRESHOLD = getattr(settings, 'CASH_VARIANCE_THRESHOLD', 1000)

    if row.variance is not None and abs(row.variance) > VARIANCE_ALERT_THRESHOLD:
        if current.role == Role.CASHIER:
            # Roll back the partial changes before raising
            db.rollback()
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Variance of KES {abs(row.variance):.2f} exceeds the allowed threshold "
                    f"(KES {VARIANCE_ALERT_THRESHOLD:.2f}). "
                    f"A supervisor or manager must close this session."
                ),
            )

    try:
        post_cash_session_close(db, row)
    except (ValueError, Exception) as e:
        print(f"Warning: Failed to post cash session close accounting entry: {e}")
    
    db.commit()
    db.refresh(row)
    return row