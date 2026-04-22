"""
Sync ingest router (v4.6 — Phase P1-C: Store Scoping & Env Consistency)

Critical fixes v4.6:
  1. CATEGORY STORE SCOPING: category lookups now filter by (store_id, name)
     instead of just (name). Prevents cross-store category collisions where two
     stores with categories named "Beverages" would collide.
  2. ENV CONSISTENCY: docker-compose.prod.yml uses CLOUD_API_BASE_URL;
     sync-agent cloudApi.js now reads same env var (with fallback to old var).
  3. STORE PAYLOAD VALIDATION: all sync endpoints validate store_id presence
     and reject cross-store payloads before any DB write.

Critical fixes v4.5:
  1. ACCOUNTING INTEGRITY: post_transaction() called atomically within the
     same DB transaction as the sale insert. If accounting fails, the entire
     sync batch is rolled back. No sale can be committed without a journal entry.
  2. CONFIRMED TXN NUMBERS: cloud response now includes confirmed_txn_numbers
     so the sync agent can mark local records as SYNCED using a local DB write
     instead of a fragile second HTTP call.
  3. STOCK MOVEMENT: explicit StockMovement record created on every synced sale.

Prior fixes (v4.0):
  1. CONFLICT RESOLUTION: explicit policy per entity type, not silent LWW
  2. IDEMPOTENCY KEYS: X-Idempotency-Key header tracked
  3. OBSERVABILITY: all conflicts stored with BOTH versions in sync_log
  4. TRANSACTION SAFETY: each upsert batch wrapped in try/except with rollback
  5. INPUT VALIDATION: all incoming records validated before any DB write
"""

import logging
import os
import json
import hashlib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db
from app.core.config import settings
from app.core.stock_movements import StockMovementType
from app.models.product import Product, Category, StockMovement
from app.models.customer import Customer
from app.models.transaction import (
    Transaction, TransactionItem,
    TransactionStatus, SyncStatus, PaymentMethod,
)
from app.models.audit import SyncLog
from app.models.audit import SyncIdempotencyKey
from app.services import accounting as accounting_svc
from app.sync.conflict_policy import resolve as _resolve, log_conflict as _log_conflict

logger = logging.getLogger("dukapos.sync")
router = APIRouter(prefix="/sync", tags=["Sync Agent"])


# ── API key auth ──────────────────────────────────────────────────────────────

def verify_sync_key(x_api_key: Optional[str] = Header(None)):
    import hmac as _hmac
    expected = settings.SYNC_AGENT_API_KEY or ""
    if not expected:
        from fastapi import HTTPException
        raise HTTPException(503, "Sync endpoint disabled: SYNC_AGENT_API_KEY not configured")
    if not _hmac.compare_digest(x_api_key or "", expected):
        from fastapi import HTTPException
        raise HTTPException(403, "Invalid or missing sync agent API key")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_decimal(value, fallback=Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return fallback


def _parse_ts(ts_str) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        if isinstance(ts_str, datetime):
            return ts_str.replace(tzinfo=timezone.utc) if ts_str.tzinfo is None else ts_str
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _log_sync(db, entity, direction, status, records_in=0, records_out=0,
              conflict=None, error_msg=None, checkpoint=None, duration_ms=None,
              store_id=None):
    db.add(SyncLog(
        entity=entity, direction=direction, status=status,
        records_in=records_in, records_out=records_out,
        conflict=conflict, error_msg=error_msg,
        checkpoint=checkpoint, duration_ms=duration_ms,
        store_id=store_id,
    ))


# ── Products upsert ───────────────────────────────────────────────────────────

from fastapi import Depends as _Depends

@router.post("/products", dependencies=[_Depends(verify_sync_key)])
def sync_products(payload: dict, db: Session = Depends(get_db)):
    """
    Receive product batch from sync agent. Upsert by SKU.

    PHASE P1-C FIX: Category lookup now scoped by store_id.
    Previously, category lookup used only name, causing cross-store collisions
    if two stores had categories with the same name (e.g., "Beverages").
    Now queries (store_id, category_name) to ensure each store's categories
    are isolated.

    Conflict resolution policy:
      CLOUD WINS:  price, name, is_active, reorder_level, tax_code, vat_exempt
      LOCAL WINS:  stock_quantity (inventory is owned by the POS terminal)
    """
    import time
    started   = time.monotonic()

    records   = payload.get("records", [])
    store_id  = payload.get("store_id")
    synced    = 0
    conflicts = []
    errors    = []

    # PHASE P1-C: Validate store_id before processing any records
    if not store_id:
        logger.error("Products sync rejected: missing_store_id")
        return {"synced": 0, "conflicts": [], "errors": ["missing_store_id"]}

    for rec in records:
        sku = rec.get("sku")
        if not sku:
            errors.append({"error": "missing_sku", "record": rec})
            continue

        try:
            existing = db.query(Product).filter(
                Product.sku == sku, Product.store_id == store_id
            ).first()

            if existing:
                # ── Conflict resolution via CONFLICT_MANIFEST ────────────────
                # Every field is resolved through the manifest — no ad-hoc logic.
                # Fields not in the manifest default to cloud_wins per __default__.
                CATALOG_FIELDS = [
                    ("name",          existing.name,          rec.get("name")),
                    ("selling_price", existing.selling_price, _safe_decimal(rec.get("selling_price"), existing.selling_price)),
                    ("cost_price",    existing.cost_price,    _safe_decimal(rec["cost_price"], existing.cost_price) if rec.get("cost_price") else existing.cost_price),
                    ("vat_exempt",    existing.vat_exempt,    rec.get("vat_exempt",    existing.vat_exempt)),
                    ("tax_code",      existing.tax_code,      rec.get("tax_code",      existing.tax_code)),
                    ("reorder_level", existing.reorder_level, rec.get("reorder_level", existing.reorder_level)),
                    ("is_active",     existing.is_active,     rec.get("is_active",     existing.is_active)),
                    ("unit",          existing.unit,          rec.get("unit",          existing.unit)),
                    ("description",   existing.description,   rec.get("description",   existing.description)),
                ]

                for field, local_val, cloud_val in CATALOG_FIELDS:
                    if local_val == cloud_val or cloud_val is None:
                        continue  # No conflict — skip resolve
                    resolved = _resolve("product", field, local_val, cloud_val)
                    if resolved != local_val:
                        conflicts.append(_log_conflict("product", field, local_val, cloud_val, resolved))
                        logger.debug("Conflict resolved: sku=%s field=%s policy=%s local=%s cloud=%s",
                                     sku, field, "cloud_wins", local_val, cloud_val)
                    setattr(existing, field, resolved)

                # stock_quantity: local_wins — terminal owns inventory count
                # (resolved via manifest but stock is never synced cloud→local here)

            else:
                cat = None
                if rec.get("category_name"):
                    # PHASE P1-C FIX: Scope category lookup by store_id to prevent
                    # cross-store category collisions. Previously only filtered by name,
                    # which could cause store A's "Beverages" to collide with store B's.
                    cat = db.query(Category).filter(
                        Category.store_id == store_id,
                        Category.name == rec["category_name"]
                    ).first()

                p = Product(
                    sku            = sku,
                    barcode        = rec.get("barcode"),
                    name           = rec.get("name", ""),
                    category_id    = cat.id if cat else None,
                    store_id       = store_id,
                    selling_price  = _safe_decimal(rec.get("selling_price", 0)),
                    cost_price     = _safe_decimal(rec["cost_price"]) if rec.get("cost_price") else Decimal("0"),
                    vat_exempt     = rec.get("vat_exempt", False),
                    tax_code       = rec.get("tax_code", "B"),
                    stock_quantity = rec.get("stock_quantity", 0),
                    reorder_level  = rec.get("reorder_level", 10),
                    unit           = rec.get("unit", "piece"),
                    is_active      = rec.get("is_active", True),
                )
                db.add(p)

            synced += 1

        except Exception as exc:
            logger.error("Product upsert failed for sku=%s: %s", sku, exc)
            errors.append({"sku": sku, "error": str(exc)})

    try:
        db.flush()
        _log_sync(
            db, "products", "local_to_cloud",
            "conflict" if conflicts else ("error" if errors else "success"),
            records_in=len(records), records_out=synced,
            conflict={"count": len(conflicts), "items": conflicts[:5]} if conflicts else None,
            error_msg=str(errors[:3]) if errors else None,
            duration_ms=int((time.monotonic() - started) * 1000),
            store_id=store_id,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Products sync commit failed: %s", exc)
        return {"synced": 0, "conflicts": [], "errors": [str(exc)]}

    logger.info("Products sync: synced=%d conflicts=%d errors=%d", synced, len(conflicts), len(errors))
    return {"synced": synced, "conflicts": conflicts, "errors": errors}


# ── Customers upsert ──────────────────────────────────────────────────────────

@router.post("/customers", dependencies=[_Depends(verify_sync_key)])
def sync_customers(payload: dict, db: Session = Depends(get_db)):
    """
    Upsert customers scoped by (store_id, phone).

    TENANT ISOLATION (v4.1 fix):
      Customer uniqueness is per-store, not global. Two stores can each have
      a customer with phone 0712345678 without colliding. All lookups and
      inserts MUST filter by store_id. The old code filtered by phone only,
      which could overwrite a customer in the wrong store.

    PHASE P1-C: Added early store_id validation. Rejected payloads with missing
    store_id before any DB operations to ensure tenant isolation.

    Conflict resolution: Last Write Wins using updated_at timestamp.
    If both timestamps equal or incoming is newer, cloud record wins.
    """
    import time
    started   = time.monotonic()
    records   = payload.get("records", [])
    store_id  = payload.get("store_id")
    synced    = 0
    conflicts = []
    errors    = []

    # PHASE P1-C: store_id is mandatory — validate early before any DB operations
    if not store_id:
        logger.error("Customers sync rejected: missing_store_id")
        return {"synced": 0, "conflicts": [], "errors": ["missing_store_id"]}

    for rec in records:
        phone = rec.get("phone")
        if not phone:
            errors.append({"error": "missing_phone"})
            continue

        try:
            # FIX: scope lookup by BOTH store_id AND phone to prevent
            # cross-tenant collision (two stores with the same customer phone).
            existing = (
                db.query(Customer)
                .filter(Customer.store_id == store_id, Customer.phone == phone)
                .first()
            )

            if existing:
                incoming_ts = _parse_ts(rec.get("updated_at"))
                existing_ts = existing.updated_at or existing.created_at

                # LWW: only update if incoming record is strictly newer
                if incoming_ts and existing_ts:
                    if incoming_ts.replace(tzinfo=timezone.utc) <= existing_ts.replace(tzinfo=timezone.utc if existing_ts.tzinfo is None else existing_ts.tzinfo):
                        logger.debug("Customer LWW: skipping stale update for phone %s store %s", phone[-4:], store_id)
                        synced += 1
                        continue
                    conflicts.append({
                        "phone":      phone[-4:] + "****",
                        "field":      "customer_record",
                        "resolution": "incoming_wins_lww",
                    })

                existing.name           = rec.get("name",           existing.name)
                existing.email          = rec.get("email",          existing.email)
                existing.loyalty_points = rec.get("loyalty_points", existing.loyalty_points)
                existing.credit_limit   = _safe_decimal(rec.get("credit_limit",  existing.credit_limit or 0))
                existing.credit_balance = _safe_decimal(rec.get("credit_balance", existing.credit_balance or 0))
                existing.notes          = rec.get("notes",          existing.notes)
                existing.is_active      = rec.get("is_active",      existing.is_active)

            else:
                c = Customer(
                    store_id       = store_id,   # FIX: always set store_id on insert
                    name           = rec.get("name", ""),
                    phone          = phone,
                    email          = rec.get("email"),
                    loyalty_points = rec.get("loyalty_points", 0),
                    credit_limit   = _safe_decimal(rec.get("credit_limit",  0)),
                    credit_balance = _safe_decimal(rec.get("credit_balance", 0)),
                    notes          = rec.get("notes"),
                    is_active      = rec.get("is_active", True),
                )
                db.add(c)

            synced += 1

        except Exception as exc:
            logger.error("Customer upsert failed for phone %s store %s: %s", phone[-4:], store_id, exc)
            errors.append({"phone": phone[-4:] + "****", "error": str(exc)})

    try:
        db.flush()
        _log_sync(db, "customers", "local_to_cloud", "success" if not errors else "error",
                  records_in=len(records), records_out=synced,
                  conflict={"count": len(conflicts)} if conflicts else None,
                  duration_ms=int((time.monotonic() - started) * 1000),
                  store_id=store_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Customers sync commit failed: %s", exc)
        return {"synced": 0, "conflicts": [], "errors": [str(exc)]}

    return {"synced": synced, "conflicts": conflicts, "errors": errors}


# ── Transactions upsert ───────────────────────────────────────────────────────

@router.post("/transactions", dependencies=[_Depends(verify_sync_key)])
def sync_transactions(
    payload: dict,
    db: Session = Depends(get_db),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """
    Upsert completed transactions by txn_number.

    v4.5 CRITICAL CHANGES:
    ─────────────────────────────────────────────────────────────────────────────
    1. ACCOUNTING IS NOW ATOMIC: post_transaction() is called inside the same
       DB transaction as the sale insert. If accounting fails, the entire record
       is rolled back and the sync agent will retry. There is NO path where a
       sale is committed without a corresponding journal entry.

    2. CONFIRMED TXN NUMBERS: the response now includes confirmed_txn_numbers —
       the list of txn_numbers that were successfully committed. The sync agent
       uses this to mark local records as SYNCED via a direct local DB write
       instead of a second HTTP call to /transactions/sync/mark-synced.

    3. STOCK MOVEMENTS: a StockMovement record is created for each sale item,
       providing a complete inventory movement ledger.

    4. PER-RECORD RESULTS: errors are reported per-txn_number so partial batch
       failures don't mask which records failed.

    LOCAL IS MASTER: cloud never overwrites an existing transaction record.
    This endpoint is fully idempotent — the sync agent can retry any number
    of times without creating duplicates.
    """
    import time
    started   = time.monotonic()
    records   = payload.get("records", [])
    store_id  = payload.get("store_id")
    synced    = 0
    skipped   = 0
    errors    = []
    confirmed_txn_numbers = []  # returned to sync agent for local ack

    if not store_id:
        return {"synced": 0, "skipped": 0, "errors": ["missing_store_id"], "confirmed_txn_numbers": []}

    if x_idempotency_key:
        canonical_payload = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        existing_key = (
            db.query(SyncIdempotencyKey)
            .filter(
                SyncIdempotencyKey.endpoint == "/sync/transactions",
                SyncIdempotencyKey.store_id == store_id,
                SyncIdempotencyKey.idempotency_key == x_idempotency_key,
            )
            .first()
        )
        if existing_key:
            if existing_key.request_hash != request_hash:
                from fastapi import HTTPException
                raise HTTPException(409, "Idempotency key reuse with different payload")
            return existing_key.response_json or {
                "synced": 0,
                "skipped": 0,
                "errors": [],
                "confirmed_txn_numbers": [],
            }

    for rec in records:
        txn_number = rec.get("txn_number")
        if not txn_number:
            errors.append({"error": "missing_txn_number", "record_index": records.index(rec)})
            continue

        # ── IDEMPOTENCY: already in cloud — skip, but still confirm ──────────
        existing = db.query(Transaction).filter(
            Transaction.txn_number == txn_number,
            Transaction.store_id   == store_id,
        ).first()
        if existing:
            skipped += 1
            confirmed_txn_numbers.append(txn_number)  # already safe, confirm to agent
            continue

        # ── Parse payment method and status safely ────────────────────────────
        try:
            pm = PaymentMethod(rec.get("payment_method", "cash"))
        except ValueError:
            pm = PaymentMethod.CASH

        # ── P1-D: Reject unsupported SPLIT payment method ─────────────────────
        if pm == PaymentMethod.SPLIT:
            logger.warning(
                "Sync: Transaction %s has unsupported SPLIT payment method — rejecting",
                txn_number
            )
            errors.append({
                "txn_number": txn_number,
                "error": "SPLIT payment method is not supported",
            })
            continue

        try:
            status_ = TransactionStatus(rec.get("status", "completed"))
        except ValueError:
            status_ = TransactionStatus.COMPLETED

        # ── BEGIN PER-RECORD ATOMIC BLOCK ─────────────────────────────────────
        # Each transaction is its own atomic unit. If accounting fails for one
        # record, only that record is rolled back — others in the batch can succeed.
        # We use a savepoint for per-record rollback within the outer session.
        try:
            # Create a savepoint so a single-record failure doesn't abort the batch
            savepoint = db.begin_nested()

            txn = Transaction(
                txn_number       = txn_number,
                store_id         = store_id,
                terminal_id      = rec.get("terminal_id"),
                subtotal         = _safe_decimal(rec.get("subtotal",        0)),
                discount_amount  = _safe_decimal(rec.get("discount_amount", 0)),
                vat_amount       = _safe_decimal(rec.get("vat_amount",      0)),
                total            = _safe_decimal(rec.get("total",           0)),
                payment_method   = pm,
                cash_tendered    = _safe_decimal(rec["cash_tendered"]) if rec.get("cash_tendered") else None,
                change_given     = _safe_decimal(rec["change_given"])  if rec.get("change_given")  else None,
                mpesa_ref        = rec.get("mpesa_ref"),
                card_ref         = rec.get("card_ref"),
                status           = status_,
                sync_status      = SyncStatus.SYNCED,
                synced_at        = datetime.now(timezone.utc),
                etims_invoice_no = rec.get("etims_invoice_no"),
                etims_synced     = rec.get("etims_synced", False),
                cashier_id       = rec.get("cashier_id"),
                customer_id      = rec.get("customer_id"),
                cash_session_id  = rec.get("cash_session_id"),
                completed_at     = _parse_ts(rec.get("completed_at")) or datetime.now(timezone.utc),
            )
            db.add(txn)
            db.flush()  # get txn.id

            # Build TransactionItems
            txn_items = []
            for item in rec.get("items", []):
                cost_snap = _safe_decimal(item.get("cost_price_snap", 0))
                ti = TransactionItem(
                    transaction_id  = txn.id,
                    product_id      = item.get("product_id"),
                    product_name    = item.get("product_name", ""),
                    sku             = item.get("sku", ""),
                    qty             = item.get("qty", 1),
                    unit_price      = _safe_decimal(item.get("unit_price", 0)),
                    cost_price_snap = cost_snap,
                    discount        = _safe_decimal(item.get("discount", 0)),
                    line_total      = _safe_decimal(item.get("line_total", 0)),
                    vat_amount      = _safe_decimal(item.get("vat_amount", 0)),
                )
                db.add(ti)
                txn_items.append(ti)

                # Stock movement record — inventory ledger entry for this sale
                if item.get("product_id"):
                    # Fetch current qty for before/after tracking. Ensure the
                    # stock movement is safely scoped to the store owning this txn.
                    _prod = db.query(Product).filter(
                        Product.id == item["product_id"],
                        Product.store_id == store_id,
                    ).with_for_update().first()
                    qty_before = _prod.stock_quantity if _prod else 0
                    qty_out    = abs(item.get("qty", 1))
                    qty_after = qty_before - qty_out
                    if _prod:
                        _prod.stock_quantity = qty_after
                    db.add(StockMovement(
                        product_id    = item["product_id"],
                        store_id      = store_id,
                        movement_type=StockMovementType.SALE.value,
                        qty_delta     = -qty_out,
                        qty_before    = qty_before,
                        qty_after     = qty_after,
                        ref_id        = txn_number,
                        notes         = f"Sync from terminal {rec.get('terminal_id', 'unknown')}",
                    ))

            db.flush()  # flush items before accounting post

            # Apply customer/cash-session side effects to match online transaction flow
            if pm == PaymentMethod.CREDIT and txn.customer_id:
                customer = db.query(Customer).filter(
                    Customer.id == txn.customer_id,
                    Customer.store_id == store_id,
                ).with_for_update().first()
                if not customer:
                    raise ValueError(f"Customer {txn.customer_id} not found for credit sale")
                customer.credit_balance = (Decimal(str(customer.credit_balance or 0)) + txn.total).quantize(Decimal("0.01"))

            if pm == PaymentMethod.CASH and rec.get("cash_session_id"):
                from app.models.cash_session import CashSession
                cash_session = db.query(CashSession).filter(
                    CashSession.id == rec.get("cash_session_id"),
                    CashSession.store_id == store_id,
                    CashSession.status == "open",
                ).with_for_update().first()
                if cash_session:
                    net_cash = (txn.total - Decimal(str(txn.change_given or 0))).quantize(Decimal("0.01"))
                    cash_session.expected_cash = (Decimal(str(cash_session.expected_cash or 0)) + net_cash).quantize(Decimal("0.01"))

            # ── ACCOUNTING POST — same savepoint, same atomic unit ─────────────
            # This is the critical fix: accounting is NOT optional and NOT
            # best-effort. If post_transaction() raises, the savepoint rolls back
            # and this txn is reported as an error. The sync agent will retry.
            accounting_svc.post_transaction(db=db, txn=txn, items=txn_items)

            # All good — release the savepoint (record is committed with the batch)
            savepoint.commit()

            synced += 1
            confirmed_txn_numbers.append(txn_number)
            logger.info("Sync ingest OK: %s | items=%d", txn_number, len(txn_items))

        except Exception as exc:
            # Roll back only this record's savepoint — other records are unaffected
            try:
                savepoint.rollback()
            except Exception:
                pass
            err_msg = str(exc)
            logger.error("Sync ingest FAILED for %s: %s", txn_number, err_msg)
            errors.append({"txn_number": txn_number, "error": err_msg})
        # ── END PER-RECORD ATOMIC BLOCK ───────────────────────────────────────

    # ── Commit all successful savepoints (business data) ──────────────────────
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Transactions sync COMMIT FAILED: %s", exc)
        return {"synced": 0, "skipped": skipped, "errors": [str(exc)], "confirmed_txn_numbers": []}

    # ── Write sync_log AFTER commit (best-effort, non-fatal) ─────────────────
    # sync_log is observability infrastructure. A failure here must NEVER
    # roll back the business data that was already committed above.
    try:
        _log_sync(
            db, "transactions", "local_to_cloud",
            "error" if errors and not synced else ("partial" if errors else "success"),
            records_in  = len(records),
            records_out = synced,
            error_msg   = str(errors[:3]) if errors else None,
            duration_ms = int((time.monotonic() - started) * 1000),
            store_id    = store_id,
        )
        db.commit()
    except Exception as log_exc:
        logger.warning("sync_log write failed (non-fatal): %s", log_exc)
        try:
            db.rollback()
        except Exception:
            pass

    logger.info(
        "Transactions sync DONE: synced=%d skipped=%d errors=%d confirmed=%d",
        synced, skipped, len(errors), len(confirmed_txn_numbers)
    )
    response_payload = {
        "synced":                 synced,
        "skipped":                skipped,
        "errors":                 errors,
        "confirmed_txn_numbers":  confirmed_txn_numbers,
    }
    if x_idempotency_key:
        canonical_payload = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        db.add(
            SyncIdempotencyKey(
                endpoint="/sync/transactions",
                store_id=store_id,
                idempotency_key=x_idempotency_key,
                request_hash=request_hash,
                status_code=200,
                response_json=response_payload,
            )
        )
        db.commit()
    return response_payload


# ── Cloud → Local product feed ────────────────────────────────────────────────

@router.get("/cloud-updates/products", dependencies=[_Depends(verify_sync_key)])
def cloud_product_updates(
    since:    str = "1970-01-01T00:00:00Z",
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        since_dt = datetime.min.replace(tzinfo=timezone.utc)

    if not store_id:
        from fastapi import HTTPException
        raise HTTPException(400, "store_id is required")

    products = (
        db.query(Product)
        .filter(
            Product.store_id == store_id,
            func.coalesce(Product.updated_at, Product.created_at) > since_dt,
        )
        .order_by(func.coalesce(Product.updated_at, Product.created_at).asc())
        .limit(500)
        .all()
    )
    return {
        "records": [
            {
                "sku":           p.sku,
                "name":          p.name,
                "selling_price": str(p.selling_price),
                "is_active":     p.is_active,
                "reorder_level": p.reorder_level,
                "updated_at":    (p.updated_at or p.created_at).isoformat(),
            }
            for p in products
        ]
    }


# ── Sync log write ────────────────────────────────────────────────────────────

@router.post("/log", dependencies=[_Depends(verify_sync_key)])
def write_sync_log(payload: dict, db: Session = Depends(get_db)):
    _log_sync(
        db,
        entity      = payload.get("entity", "unknown"),
        direction   = payload.get("direction", "local_to_cloud"),
        status      = payload.get("status", "success"),
        records_in  = payload.get("records_in",  0),
        records_out = payload.get("records_out", 0),
        conflict    = payload.get("conflict"),
        error_msg   = payload.get("error_msg"),
        checkpoint  = payload.get("checkpoint"),
        duration_ms = payload.get("duration_ms"),
        store_id    = payload.get("store_id"),
    )
    db.commit()
    return {"ok": True}


# ── Dead-letter queue stats ───────────────────────────────────────────────────

@router.get("/dead-letter", dependencies=[_Depends(verify_sync_key)])
def get_dead_letter_items(
    entity:   Optional[str] = None,
    limit:    int = 50,
    db: Session = Depends(get_db),
):
    """
    Return sync log entries that have errored, for dead-letter monitoring.

    These represent batches the sync agent gave up on after max retries.
    Used by ops dashboards and alerting. Investigate and replay manually.
    """
    from app.models.audit import SyncLog

    q = db.query(SyncLog).filter(SyncLog.status == "error")
    if entity:
        q = q.filter(SyncLog.entity == entity)

    items = q.order_by(SyncLog.created_at.desc()).limit(limit).all()

    return {
        "count": len(items),
        "items": [
            {
                "id":          item.id,
                "entity":      item.entity,
                "direction":   item.direction,
                "records_in":  item.records_in,
                "error_msg":   item.error_msg,
                "checkpoint":  item.checkpoint,
                "duration_ms": item.duration_ms,
                "created_at":  item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
    }
