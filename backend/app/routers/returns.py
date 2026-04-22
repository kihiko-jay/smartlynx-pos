"""
Returns & Refunds API router — SmartlynX POS v4.6

Endpoints
─────────
POST   /returns                       Create return request (cashier+)
GET    /returns                       List returns for store (cashier+)
GET    /returns/{return_id}           Get return detail (cashier+)
POST   /returns/{return_id}/approve   Approve + execute return (supervisor+)
POST   /returns/{return_id}/reject    Reject return (supervisor+)
GET    /transactions/{txn_id}/returns All returns against one transaction (cashier+)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_employee,
    get_db,
    require_cashier,
    require_supervisor,
)
from app.models.employee import Employee
from app.models.returns import ReturnTransaction
from app.schemas.returns import (
    ReturnApproveRequest,
    ReturnCreate,
    ReturnOut,
    ReturnRejectRequest,
    ReturnSummary,
)
from app.services import returns as returns_svc

logger = logging.getLogger("smartlynx.routers.returns")

router = APIRouter(prefix="/returns", tags=["Returns"])


@router.post(
    "",
    response_model=ReturnOut,
    status_code=201,
    summary="Create return request",
    description=(
        "Cashier creates a return request against a completed transaction. "
        "The request enters PENDING status until a supervisor approves it. "
        "Validates qty ceilings against existing completed returns."
    ),
)
def create_return(
    payload:  ReturnCreate,
    db:       Session  = Depends(get_db),
    employee: Employee = Depends(require_cashier),
):
    return returns_svc.create_return(db, employee, payload)


@router.get(
    "",
    response_model=List[ReturnSummary],
    summary="List returns for store",
)
def list_returns(
    status:          Optional[str] = Query(None, description="Filter by status: pending|completed|rejected"),
    original_txn_id: Optional[int] = Query(None, description="Filter by original transaction ID"),
    limit:           int            = Query(50, ge=1, le=200),
    offset:          int            = Query(0, ge=0),
    db:              Session        = Depends(get_db),
    employee:        Employee       = Depends(require_cashier),
):
    return returns_svc.list_returns(
        db, employee,
        status_filter   = status,
        original_txn_id = original_txn_id,
        limit           = limit,
        offset          = offset,
    )


@router.get(
    "/{return_id}",
    response_model=ReturnOut,
    summary="Get return detail",
)
def get_return(
    return_id: int,
    db:        Session  = Depends(get_db),
    employee:  Employee = Depends(require_cashier),
):
    return returns_svc.get_return(db, employee, return_id)


@router.post(
    "/{return_id}/approve",
    response_model=ReturnOut,
    summary="Approve and execute return",
    description=(
        "Supervisor/manager approves a pending return and atomically executes it: "
        "restores stock for restorable items, posts accounting reversal, "
        "and transitions status to COMPLETED. This cannot be undone."
    ),
)
def approve_return(
    return_id: int,
    payload:   ReturnApproveRequest,
    db:        Session  = Depends(get_db),
    employee:  Employee = Depends(require_supervisor),
):
    return returns_svc.approve_and_complete(db, employee, return_id, payload)


@router.post(
    "/{return_id}/reject",
    response_model=ReturnOut,
    summary="Reject return request",
    description=(
        "Supervisor/manager rejects a pending return. "
        "No stock or accounting changes are made. Rejection is permanent."
    ),
)
def reject_return(
    return_id: int,
    payload:   ReturnRejectRequest,
    db:        Session  = Depends(get_db),
    employee:  Employee = Depends(require_supervisor),
):
    return returns_svc.reject_return(db, employee, return_id, payload)


# ── Convenience: returns against a specific transaction ──────────────────────

txn_returns_router = APIRouter(prefix="/transactions", tags=["Transactions"])


@txn_returns_router.get(
    "/{txn_id}/returns",
    response_model=List[ReturnSummary],
    summary="Returns against a transaction",
    description="Returns all return records linked to a specific transaction.",
)
def get_txn_returns(
    txn_id:   int,
    db:       Session  = Depends(get_db),
    employee: Employee = Depends(require_cashier),
):
    return returns_svc.list_returns(
        db, employee,
        original_txn_id = txn_id,
        limit           = 100,
    )
