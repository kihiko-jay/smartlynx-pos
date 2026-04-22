"""
Reconciliation router — inventory integrity and period management.

Access: MANAGER and ADMIN only (and PLATFORM_OWNER).

Endpoints:
  POST /reconciliation/run                     — run full reconciliation for store
  GET  /reconciliation/oversell-events         — list pending oversell events
  PATCH /reconciliation/oversell-events/{id}   — resolve an oversell event
  GET  /reconciliation/inventory-ledger        — inventory account vs physical stock diff
  POST /reconciliation/period                  — create an accounting period
  PATCH /reconciliation/period/{id}/close      — close a period (ADMIN only)
  PATCH /reconciliation/period/{id}/lock       — lock a period (PLATFORM_OWNER only)
  GET  /reconciliation/periods                 — list all periods for store
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_manager, get_current_employee
from app.models.employee import Employee, Role
from app.models.inventory import (
    OversellEvent, OversellResolution,
    AccountingPeriod, PeriodStatus,
)
from app.services.reconciliation import (
    run_full_reconciliation,
    detect_oversells,
    get_inventory_ledger_diff,
    assert_period_open,
)

logger = logging.getLogger("dukapos.reconciliation")
router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class OversellResolveRequest(BaseModel):
    resolution:       str   = Field(..., description="written_off | reversed | sourced | ignored")
    resolution_notes: Optional[str] = None


class PeriodCreateRequest(BaseModel):
    period_name: str  = Field(..., example="APR-2026")
    start_date:  date
    end_date:    date


class PeriodCloseRequest(BaseModel):
    notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(current: Employee) -> None:
    if current.role not in (Role.ADMIN, Role.PLATFORM_OWNER):
        raise HTTPException(403, "ADMIN role required for this operation")


def _require_platform_owner(current: Employee) -> None:
    if current.role != Role.PLATFORM_OWNER:
        raise HTTPException(403, "PLATFORM_OWNER role required")


# ── Reconciliation run ────────────────────────────────────────────────────────

@router.post("/run")
def run_reconciliation(
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    Run full reconciliation for the current store.
    Detects oversells, computes inventory-ledger diff, returns health summary.

    Can be called manually by managers or triggered automatically post-sync.
    Safe to run frequently — all operations are read-only except oversell event creation.
    """
    result = run_full_reconciliation(db, current.store_id)
    return result


# ── Oversell events ───────────────────────────────────────────────────────────

@router.get("/oversell-events")
def list_oversell_events(
    resolution: Optional[str] = Query(None, description="Filter by resolution status"),
    limit:      int           = Query(50, ge=1, le=200),
    db:         Session       = Depends(get_db),
    current:    Employee      = Depends(require_manager),
):
    """
    List oversell events for this store. Managers use this to prioritise resolution.

    Filter by resolution=pending to see only unresolved events.
    """
    q = db.query(OversellEvent).filter(OversellEvent.store_id == current.store_id)

    if resolution:
        try:
            res_filter = OversellResolution(resolution)
            q = q.filter(OversellEvent.resolution == res_filter)
        except ValueError:
            raise HTTPException(400, f"Invalid resolution filter. Use one of: {[r.value for r in OversellResolution]}")

    events = q.order_by(OversellEvent.detected_at.desc()).limit(limit).all()

    return {
        "count": len(events),
        "events": [
            {
                "id":                    e.id,
                "product_id":            e.product_id,
                "shortfall_qty":         e.shortfall_qty,
                "stock_before_sync":     e.stock_before_sync,
                "total_sold_offline":    e.total_sold_offline,
                "contributing_terminals": json.loads(e.contributing_terminals or "[]"),
                "candidate_txn_numbers": json.loads(e.candidate_txn_numbers or "[]")[:5],
                "resolution":            e.resolution,
                "resolution_notes":      e.resolution_notes,
                "detected_at":           e.detected_at.isoformat() if e.detected_at else None,
                "resolved_at":           e.resolved_at.isoformat() if e.resolved_at else None,
            }
            for e in events
        ],
    }


@router.patch("/oversell-events/{event_id}")
def resolve_oversell_event(
    event_id: int,
    payload:  OversellResolveRequest,
    db:       Session  = Depends(get_db),
    current:  Employee = Depends(require_manager),
):
    """
    Resolve an oversell event. Manager must choose the resolution action.

    resolution options:
      written_off — accept the stock loss; post a write-off journal entry
      reversed    — a void of the overselling transaction was already processed
      sourced     — emergency restock was found; stock is now correct
      ignored     — low-value item; manager accepts the discrepancy
    """
    event = db.query(OversellEvent).filter(
        OversellEvent.id       == event_id,
        OversellEvent.store_id == current.store_id,
    ).first()

    if not event:
        raise HTTPException(404, "Oversell event not found")

    if event.resolution != OversellResolution.PENDING:
        raise HTTPException(409, f"Event already resolved as '{event.resolution}'")

    try:
        resolution = OversellResolution(payload.resolution)
    except ValueError:
        raise HTTPException(400, f"Invalid resolution '{payload.resolution}'")

    event.resolution       = resolution
    event.resolved_by      = current.id
    event.resolution_notes = payload.resolution_notes
    event.resolved_at      = datetime.now(timezone.utc)

    db.commit()
    db.refresh(event)

    logger.info(
        "Oversell event %d resolved as '%s' by employee %d",
        event_id, resolution, current.id
    )
    return {"id": event_id, "resolution": resolution, "resolved_by": current.id}


# ── Inventory-ledger diff ─────────────────────────────────────────────────────

@router.get("/inventory-ledger")
def get_inventory_ledger_reconciliation(
    as_of_date: Optional[date] = Query(None, description="Reconcile as of this date (defaults to today)"),
    db:         Session        = Depends(get_db),
    current:    Employee       = Depends(require_manager),
):
    """
    Compare physical inventory value (stock * WAC) against account 1200 balance.

    A non-zero variance indicates unposted movements, accounting errors, or
    WAC drift. This report is the primary tool for identifying accounting gaps.
    """
    return get_inventory_ledger_diff(db, current.store_id, as_of_date)


# ── Accounting periods ────────────────────────────────────────────────────────

@router.get("/periods")
def list_periods(
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """List all accounting periods for this store."""
    periods = (
        db.query(AccountingPeriod)
        .filter(AccountingPeriod.store_id == current.store_id)
        .order_by(AccountingPeriod.start_date.desc())
        .all()
    )
    return {
        "periods": [
            {
                "id":          p.id,
                "period_name": p.period_name,
                "start_date":  str(p.start_date),
                "end_date":    str(p.end_date),
                "status":      p.status,
                "closed_at":   p.closed_at.isoformat() if p.closed_at else None,
                "locked_at":   p.locked_at.isoformat() if p.locked_at else None,
                "notes":       p.notes,
            }
            for p in periods
        ]
    }


@router.post("/period")
def create_period(
    payload: PeriodCreateRequest,
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),
):
    """
    Create a new accounting period. ADMIN required.

    A store should have exactly one OPEN period at a time. Creating a period
    does not automatically close any existing period.
    """
    _require_admin(current)

    if payload.start_date >= payload.end_date:
        raise HTTPException(400, "start_date must be before end_date")

    # Check for overlapping periods
    overlap = (
        db.query(AccountingPeriod)
        .filter(
            AccountingPeriod.store_id   == current.store_id,
            AccountingPeriod.start_date <= payload.end_date,
            AccountingPeriod.end_date   >= payload.start_date,
        )
        .first()
    )
    if overlap:
        raise HTTPException(409, f"Period '{overlap.period_name}' overlaps with the requested dates")

    period = AccountingPeriod(
        store_id    = current.store_id,
        period_name = payload.period_name,
        start_date  = payload.start_date,
        end_date    = payload.end_date,
        status      = PeriodStatus.OPEN,
    )
    db.add(period)
    db.commit()
    db.refresh(period)

    logger.info("Period '%s' created for store %d by employee %d",
                payload.period_name, current.store_id, current.id)
    return {"id": period.id, "period_name": period.period_name, "status": period.status}


@router.patch("/period/{period_id}/close")
def close_period(
    period_id: int,
    payload:   PeriodCloseRequest,
    db:        Session  = Depends(get_db),
    current:   Employee = Depends(require_manager),
):
    """
    Close an accounting period. ADMIN required.

    Effect: journal entries can no longer be posted with dates in this period.
    Any backdating attempts will return HTTP 409.

    This action is reversible only by PLATFORM_OWNER.
    """
    _require_admin(current)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.id       == period_id,
        AccountingPeriod.store_id == current.store_id,
    ).first()

    if not period:
        raise HTTPException(404, "Period not found")

    if period.status == PeriodStatus.CLOSED:
        raise HTTPException(409, f"Period '{period.period_name}' is already closed")

    if period.status == PeriodStatus.LOCKED:
        raise HTTPException(409, f"Period '{period.period_name}' is locked and cannot be modified")

    period.status    = PeriodStatus.CLOSED
    period.closed_by = current.id
    period.closed_at = datetime.now(timezone.utc)
    period.notes     = payload.notes or period.notes

    db.commit()

    logger.info("Period '%s' CLOSED for store %d by employee %d",
                period.period_name, current.store_id, current.id)
    return {"period_name": period.period_name, "status": "closed", "closed_at": period.closed_at.isoformat()}


@router.patch("/period/{period_id}/lock")
def lock_period(
    period_id: int,
    db:        Session  = Depends(get_db),
    current:   Employee = Depends(require_manager),
):
    """
    Permanently lock an accounting period. PLATFORM_OWNER only.

    A locked period cannot be unlocked. Use after a formal financial audit
    or annual close. No journal entries — including reversals — can be posted
    into a locked period.
    """
    _require_platform_owner(current)

    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.id == period_id
    ).first()

    if not period:
        raise HTTPException(404, "Period not found")

    if period.status == PeriodStatus.OPEN:
        raise HTTPException(409, "Cannot lock an OPEN period. Close it first.")

    if period.status == PeriodStatus.LOCKED:
        raise HTTPException(409, f"Period '{period.period_name}' is already locked")

    period.status    = PeriodStatus.LOCKED
    period.locked_by = current.id
    period.locked_at = datetime.now(timezone.utc)

    db.commit()

    logger.warning("Period '%s' LOCKED by PLATFORM_OWNER %d", period.period_name, current.id)
    return {"period_name": period.period_name, "status": "locked", "locked_at": period.locked_at.isoformat()}
