
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
    counted_cash: Decimal = Field(..., ge=0)
    notes: Optional[str] = None


@router.post("/open", dependencies=[Depends(require_cashier)])
def open_cash_session(payload: CashSessionOpen, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    existing = db.query(CashSession).filter(CashSession.store_id == current.store_id, CashSession.cashier_id == current.id, CashSession.terminal_id == payload.terminal_id, CashSession.status == 'open').first()
    if existing:
        raise HTTPException(400, 'Cashier already has an open session on this terminal')
    row = CashSession(store_id=current.store_id, cashier_id=current.id, terminal_id=payload.terminal_id, session_number=f"CS-{uuid.uuid4().hex[:8].upper()}", opening_float=payload.opening_float, expected_cash=payload.opening_float, status='open', opened_by=current.id, notes=payload.notes)
    db.add(row)
    db.flush()
    try:
        post_cash_session_open(db, row)
    except (ValueError, Exception) as e:
        # Accounting system may not be fully initialized; allow session creation anyway
        print(f"Warning: Failed to post cash session accounting entry: {e}")
    db.commit(); db.refresh(row)
    return row


@router.get("", dependencies=[Depends(require_cashier)])
def list_cash_sessions(db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    return db.query(CashSession).filter(CashSession.store_id == current.store_id).order_by(CashSession.opened_at.desc()).all()


@router.get("/{session_id}", dependencies=[Depends(require_cashier)])
def get_cash_session(session_id: int, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    row = db.query(CashSession).filter(CashSession.id == session_id, CashSession.store_id == current.store_id).first()
    if not row:
        raise HTTPException(404, 'Cash session not found')
    return row


@router.post("/{session_id}/close", dependencies=[Depends(require_cashier)])
def close_cash_session(session_id: int, payload: CashSessionClose, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    row = db.query(CashSession).filter(CashSession.id == session_id, CashSession.store_id == current.store_id).with_for_update().first()
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

    row.counted_cash = payload.counted_cash
    row.variance = (
        Decimal(str(payload.counted_cash)) - Decimal(str(row.expected_cash or 0))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    row.closed_at = datetime.utcnow()
    row.closed_by = current.id
    row.status = 'closed'
    if payload.notes:
        row.notes = (row.notes or "") + "\nClose: " + payload.notes

    # Variance threshold enforcement — large variances require supervisor or above
    VARIANCE_ALERT_THRESHOLD = settings.CASH_VARIANCE_THRESHOLD  # KES 1000 — adjust via config if needed

    if row.variance is not None and abs(row.variance) > VARIANCE_ALERT_THRESHOLD:
        if current.role == Role.CASHIER:
            # Roll back the partial changes before raising
            row.counted_cash = None
            row.variance     = None
            row.closed_at    = None
            row.closed_by    = None
            row.status       = "open"
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
        # Accounting system may not be fully initialized; allow session close anyway
        print(f"Warning: Failed to post cash session close accounting entry: {e}")
    db.commit(); db.refresh(row)
    return row
