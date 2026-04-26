"""
KRA eTIMS router (v4.1)

Security fixes (v4.1):
  1. STORE ISOLATION on /pending and /retry-all:
     Previously these endpoints had NO store_id filter — any authenticated
     manager could see and retry ALL stores' unsynced eTIMS submissions.
     Both endpoints now filter by the authenticated user's store_id.
     PLATFORM_OWNER is the only role that may see/retry across all stores,
     and that access is explicit, not accidental.

  2. IDOR fix on /submit/{txn_id}:
     Previously any cashier could submit ANY store's transaction to KRA by
     guessing the integer txn_id. The endpoint now verifies that the fetched
     transaction belongs to the authenticated user's store before proceeding.

Prior fixes (v4.0) preserved:
  - RETRY PERSISTENCE via etims_retry_queue background task
  - IDEMPOTENCY: duplicate submissions return cached invoice number
  - OBSERVABILITY: every attempt logged with outcome, attempt count, result code
  - BATCH SUBMIT: retry-all processes in 50-record chunks with per-batch commits
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.deps import get_db, require_cashier, require_manager
from app.models.employee import Employee, Role
from app.models.transaction import Transaction, TransactionStatus
from app.models.subscription import Store
from app.models.audit import AuditTrail
from app.services.etims import submit_invoice

logger = logging.getLogger("dukapos.etims")
router = APIRouter(prefix="/etims", tags=["KRA eTIMS"])


# ── Store-scoping helper ──────────────────────────────────────────────────────

def _resolve_etims_store_id(current: Employee) -> int | None:
    """
    Return the store_id to use for scoping eTIMS queries.

    - Regular users (cashier → admin): returns their own store_id.
      Raises 403 if the user somehow has no store_id (misconfigured account).
    - PLATFORM_OWNER: returns None, signalling "no store_id filter" so the
      platform owner can view/retry submissions across all stores.

    This is the only place in the eTIMS router where cross-store access is
    permitted, and it is explicit and role-gated.
    """
    if current.role == Role.PLATFORM_OWNER:
        return None   # intentional: platform owner operates across all stores

    if not current.store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not linked to a store. Contact your administrator.",
        )
    return current.store_id


def _assert_txn_store_access(txn: Transaction, current: Employee) -> None:
    """
    Verify the authenticated user may act on this transaction.

    Raises 403 if the transaction belongs to a different store.
    PLATFORM_OWNER is always allowed (cross-store support access).
    """
    if current.role == Role.PLATFORM_OWNER:
        return   # platform owner may submit any store's transaction

    if txn.store_id != current.store_id:
        logger.warning(
            "eTIMS IDOR attempt blocked: employee_id=%s store_id=%s "
            "tried to act on txn_id=%s belonging to store_id=%s",
            current.id, current.store_id, txn.id, txn.store_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to act on this transaction.",
        )


# ── Shared helpers ────────────────────────────────────────────────────────────

def _txn_to_data(txn: Transaction) -> dict:
    """Build the eTIMS submission dict from a Transaction ORM object."""
    return {
        "txn_number": txn.txn_number,
        "total":      txn.total,
        "vat_amount": txn.vat_amount,
        "created_at": txn.created_at,
        "items": [
            {
                "sku":          item.sku,
                "product_name": item.product_name,
                "qty":          item.qty,
                "unit_price":   item.unit_price,
                "line_total":   item.line_total,
                "discount":     item.discount,
                "tax_code":     getattr(item, "tax_code",   None),
                "vat_exempt":   getattr(item, "vat_exempt", False),
            }
            for item in txn.items
        ],
    }


def _record_etims_attempt(db: Session, txn: Transaction, result: dict, attempt: int = 1):
    """Write an audit trail entry for the eTIMS submission attempt."""
    db.add(AuditTrail(
        store_id   = txn.store_id,
        actor_name = "etims_service",
        action     = "etims_submit",
        entity     = "transaction",
        entity_id  = txn.txn_number,
        after_val  = {
            "attempt":          attempt,
            "etims_synced":     result.get("etims_synced"),
            "etims_invoice_no": result.get("etims_invoice_no"),
        },
        notes = None if result.get("etims_synced") else "etims_failed_will_retry",
    ))


def _get_etims_attempt_count(db: Session, txn_number: str) -> int:
    """Count how many eTIMS submission attempts have been made for this txn."""
    row = db.execute(
        text("""
            SELECT COUNT(*) FROM audit_trail
            WHERE entity = 'transaction'
              AND entity_id = :txn_number
              AND action = 'etims_submit'
        """),
        {"txn_number": txn_number},
    ).scalar()
    return int(row or 0)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/submit/{txn_id}")
async def submit_to_etims(
    txn_id:           int,
    background_tasks: BackgroundTasks,
    db:               Session  = Depends(get_db),
    current:          Employee = Depends(require_cashier),   # FIX: capture current user
):
    """
    Submit a completed transaction to KRA eTIMS.

    Security: verifies the transaction belongs to the authenticated user's store
    before submission (IDOR fix). PLATFORM_OWNER may submit for any store.

    - Idempotent: calling twice for same txn returns cached invoice number
    - On failure: schedules a background retry (non-blocking)
    - Never blocks the sale: eTIMS failure does NOT roll back the transaction
    """
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")

    # SECURITY FIX: verify caller owns this transaction
    _assert_txn_store_access(txn, current)

    if txn.status != TransactionStatus.COMPLETED:
        raise HTTPException(400, "Only completed transactions can be submitted to eTIMS")

    # Idempotency: already synced
    if txn.etims_synced:
        return {
            "message":          "Already synced",
            "txn_number":       txn.txn_number,
            "etims_invoice_no": txn.etims_invoice_no,
        }

    # Attempt #1 — inline (fast path for good connectivity)
    attempt = _get_etims_attempt_count(db, txn.txn_number) + 1
    
    # Fetch the store for per-store credential resolution
    store = db.query(Store).filter(Store.id == txn.store_id).first()
    
    result  = await submit_invoice(_txn_to_data(txn), store=store)

    txn.etims_invoice_no = result["etims_invoice_no"]
    txn.etims_qr_code    = result["etims_qr_code"]
    txn.etims_synced     = result["etims_synced"]

    _record_etims_attempt(db, txn, result, attempt=attempt)
    db.commit()

    if result["etims_synced"]:
        logger.info("eTIMS submitted OK: %s → %s (store_id=%s)",
                    txn.txn_number, result["etims_invoice_no"], txn.store_id)
    else:
        logger.warning("eTIMS submission failed for %s (store_id=%s) — scheduled for retry",
                       txn.txn_number, txn.store_id)
        background_tasks.add_task(_schedule_etims_retry, txn.id)

    return {
        "txn_number":       txn.txn_number,
        "etims_invoice_no": txn.etims_invoice_no,
        "etims_synced":     txn.etims_synced,
        "qr_code_base64":   txn.etims_qr_code,
        "queued_for_retry": not txn.etims_synced,
    }


@router.get("/pending")
def list_unsynced(
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),   # FIX: capture current user
):
    """
    List all completed transactions not yet synced to KRA for this store.

    Regular users (manager/admin): see only their own store's pending submissions.
    PLATFORM_OWNER: sees all stores' pending submissions (cross-store support).
    """
    # SECURITY FIX: resolve scope — None means unrestricted (platform owner only)
    store_id = _resolve_etims_store_id(current)

    q = db.query(Transaction).filter(
        Transaction.status       == TransactionStatus.COMPLETED,
        Transaction.etims_synced == False,
    )
    # Apply store_id filter for all non-platform-owner callers
    if store_id is not None:
        q = q.filter(Transaction.store_id == store_id)

    txns = q.order_by(Transaction.created_at.asc()).all()

    logger.debug(
        "eTIMS pending list: store_id=%s role=%s found=%d",
        store_id, current.role, len(txns),
    )

    return {
        "unsynced_count": len(txns),
        "store_id":       store_id,   # surfaced so callers know the scope
        "transactions": [
            {
                "id":         t.id,
                "txn_number": t.txn_number,
                "store_id":   t.store_id,
                "total":      str(t.total),
                "created_at": str(t.created_at),
                "attempts":   _get_etims_attempt_count(db, t.txn_number),
            }
            for t in txns
        ],
    }


@router.post("/retry-all")
async def retry_all_unsynced(
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_manager),   # FIX: capture current user
):
    """
    Bulk retry for all unsynced eTIMS transactions for this store.

    Regular users: retries only their own store's pending submissions.
    PLATFORM_OWNER: retries across all stores (global maintenance operation).

    Processes in batches of 50. Each batch is a separate DB transaction so
    a failure in batch N does not roll back batches 1..N-1.
    """
    # SECURITY FIX: resolve scope
    store_id = _resolve_etims_store_id(current)

    q = db.query(Transaction).filter(
        Transaction.status       == TransactionStatus.COMPLETED,
        Transaction.etims_synced == False,
    )
    if store_id is not None:
        q = q.filter(Transaction.store_id == store_id)

    txns = q.order_by(Transaction.created_at.asc()).all()

    results = {"synced": 0, "failed": 0, "total": len(txns), "store_id": store_id}
    BATCH = 50

    for i in range(0, len(txns), BATCH):
        batch = txns[i:i + BATCH]
        for txn in batch:
            attempt = _get_etims_attempt_count(db, txn.txn_number) + 1
            try:
                # Fetch the store for per-store credential resolution
                store = db.query(Store).filter(Store.id == txn.store_id).first()
                
                result = await submit_invoice(_txn_to_data(txn), store=store)
                txn.etims_invoice_no = result["etims_invoice_no"]
                txn.etims_qr_code    = result["etims_qr_code"]
                txn.etims_synced     = result["etims_synced"]
                _record_etims_attempt(db, txn, result, attempt=attempt)

                if result["etims_synced"]:
                    results["synced"] += 1
                    logger.info("eTIMS retry OK: %s (store_id=%s)", txn.txn_number, txn.store_id)
                else:
                    results["failed"] += 1
                    logger.warning("eTIMS retry still failing: %s (attempt %d, store_id=%s)",
                                   txn.txn_number, attempt, txn.store_id)
            except Exception as exc:
                results["failed"] += 1
                logger.error("eTIMS retry exception for %s (store_id=%s): %s",
                             txn.txn_number, txn.store_id, exc)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("eTIMS retry-all batch commit failed: %s", exc)

    logger.info("eTIMS retry-all complete: %s", results)
    return results


# ── Background retry task ─────────────────────────────────────────────────────

async def _schedule_etims_retry(txn_id: int):
    """
    Background retry task — called from BackgroundTasks after a failed submission.
    Uses its own DB session (background tasks run after the response is sent).

    No store scoping needed here: txn_id is a direct PK looked up from the
    same transaction object that was already access-controlled by submit_to_etims.
    """
    from app.database import SessionLocal
    import asyncio

    MAX_ATTEMPTS = 10
    BASE_DELAY   = 30   # seconds

    db = SessionLocal()
    try:
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn or txn.etims_synced:
            return

        attempts = _get_etims_attempt_count(db, txn.txn_number)
        if attempts >= MAX_ATTEMPTS:
            logger.error("eTIMS: giving up on %s after %d attempts (store_id=%s)",
                         txn.txn_number, attempts, txn.store_id)
            return

        delay = min(BASE_DELAY * (2 ** attempts), 3600)   # cap at 1 hour
        logger.info("eTIMS retry scheduled for %s in %ds (attempt %d, store_id=%s)",
                    txn.txn_number, delay, attempts + 1, txn.store_id)
        await asyncio.sleep(delay)

        # Fetch the store for per-store credential resolution
        store = db.query(Store).filter(Store.id == txn.store_id).first()
        
        result = await submit_invoice(_txn_to_data(txn), store=store)
        txn.etims_invoice_no = result["etims_invoice_no"]
        txn.etims_qr_code    = result["etims_qr_code"]
        txn.etims_synced     = result["etims_synced"]
        _record_etims_attempt(db, txn, result, attempt=attempts + 1)
        db.commit()

        if result["etims_synced"]:
            logger.info("eTIMS background retry OK: %s (store_id=%s)",
                        txn.txn_number, txn.store_id)
        else:
            # Schedule another retry (recursive, bounded by MAX_ATTEMPTS)
            await _schedule_etims_retry(txn_id)

    except Exception as exc:
        db.rollback()
        logger.error("eTIMS background retry exception for txn_id=%d: %s", txn_id, exc)
    finally:
        db.close()
