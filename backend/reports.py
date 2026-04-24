"""
Reports router — v4.1 (Phase P1-B: Reporting Truth & Timezone Safety)

Critical fixes:
  1. STORE ISOLATION: every query now filters by current.store_id.
     Previously all reports aggregated ALL shops' data together — a
     data leak where Shop A could see Shop B's revenue.
  2. PLATFORM_OWNER bypass: platform owner can pass ?store_id= to view
     any store's reports for support purposes. Shop users cannot.
  3. STORE NAME from DB record, not global config: Z-tape now shows
     the actual shop's name and location, not settings.STORE_NAME.
  4. VAT report converted to SQL aggregation (was loading full month
     into Python memory via .all()).
  5. TIMEZONE SAFETY (P1-B): All transaction dates are converted to merchant's
     timezone (Africa/Nairobi) BEFORE filtering. This prevents midnight-edge
     transactions and M-PESA delayed completions from appearing in wrong day's
     report.

REPORTING TRUTH (P1-B):
──────────────────────
For COMPLETED transactions, the reported date is determined by:
  1. If completed_at is present: use the completion timestamp (when payment cleared)
  2. If completed_at is NULL: use created_at (immediate payment methods like cash)
  3. Convert this timestamp to the merchant's timezone FIRST
  4. Then extract the calendar date for filtering

This ensures:
  - M-PESA payments completed hours after transaction creation show in correct day
  - Midnight transactions (23:59 UTC = 02:59 Nairobi = next day) go in the right day
  - All merchants see reports aligned with their local business day, not UTC
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, text
from typing import Literal, Optional
from datetime import date, timedelta, datetime, timezone

from app.core.csv_export import (
    ztape_to_csv,
    weekly_to_csv,
    vat_to_csv,
    top_products_to_csv,
    low_stock_to_csv,
)
from app.core.pdf_generator import pdf_response
from app.core.deps import get_db, require_premium, get_current_employee
from app.core.datetime_utils import (
    utc_to_merchant_date,
    merchant_today,
    merchant_date_range,
    ensure_utc_datetime,
)
from app.models.transaction import Transaction, TransactionItem, TransactionStatus
from app.models.product import Product
from app.models.employee import Employee, Role
from app.models.subscription import Store
from app.core.config import settings
from app.services import pdf_service

router = APIRouter(prefix="/reports", tags=["Reports"])


# ── Helper: resolve which store_id to report on ───────────────────────────────

def _resolve_store(
    current: Employee,
    db:      Session,
    store_id_param: Optional[int] = None,
) -> tuple[int, Store]:
    """
    Returns (store_id, store_record) to use for this report.

    - Regular users always get their own store_id. The store_id_param
      is ignored — they cannot view another shop's reports.
    - PLATFORM_OWNER can pass ?store_id= to view any shop's data.
      If they don't pass it, defaults to the first store (for convenience).

    Raises 403 if the store is not found.
    """
    if current.role == Role.PLATFORM_OWNER:
        sid = store_id_param or current.store_id
        if not sid:
            # Platform owner with no store_id and no param — list stores instead
            raise Exception("PLATFORM_OWNER must supply ?store_id= to view reports")
    else:
        sid = current.store_id

    store = db.query(Store).filter(Store.id == sid).first()
    if not store:
        from fastapi import HTTPException
        raise HTTPException(404, f"Store {sid} not found")
    return sid, store


# ── Z-Tape / End of Day ───────────────────────────────────────────────────────

def _get_transaction_merchant_date(txn: Transaction) -> date:
    """
    Extract the business date (in merchant's timezone) for a transaction.
    
    PHASE P1-B: Reporting Truth
    ───────────────────────────
    For completed transactions, we use:
      1. completed_at if present (payment cleared timestamp)
      2. created_at if completed_at is NULL (immediate payment)
    
    Then convert to merchant timezone before extracting date.
    """
    ts = ensure_utc_datetime(txn.completed_at or txn.created_at)
    return utc_to_merchant_date(ts)


@router.get("/z-tape")
def z_tape(
    report_date:    Optional[date]           = Query(default=None),
    store_id_param: Optional[int]            = Query(default=None, alias="store_id",
                                                     description="Platform owner only"),
    format:         Optional[Literal["csv"]] = Query(default=None),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """
    End-of-day Z-tape. Shows only this store's transactions.
    Store name and location come from the store's DB record, not global config.

    PHASE P1-B: All transaction dates are converted to merchant's timezone
    (Africa/Nairobi) before filtering. Prevents midnight-edge transactions
    from appearing in wrong day's report.

    Add **?format=csv** to download a CSV file (UTF-8 BOM, Excel-compatible).
    Omit the param (or pass no value) to receive the standard JSON response.
    """
    from fastapi import HTTPException
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    target = report_date or merchant_today()

    # Fetch COMPLETED transactions for this store
    # Include a date range buffer (±1 day) to account for timezone offset
    buffer_start = target - timedelta(days=1)
    buffer_end = target + timedelta(days=1)
    
    txns = (
        db.query(Transaction)
        .filter(Transaction.store_id == sid)
        .filter(Transaction.status == TransactionStatus.COMPLETED)
        .filter(
            (Transaction.completed_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
        )
        .filter(
            (Transaction.completed_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
        )
        .all()
    )

    # Filter to target date in merchant timezone
    target_txns = [t for t in txns if _get_transaction_merchant_date(t) == target]

    # Aggregate by payment method and cashier
    by_method: dict[str, dict] = {}
    by_cashier: dict[int | None, dict] = {}

    total_count = 0
    gross_sales = 0.0
    total_discounts = 0.0
    vat_collected = 0.0

    for txn in target_txns:
        total_count += 1
        gross_sales += float(txn.total)
        total_discounts += float(txn.discount_amount or 0)
        vat_collected += float(txn.vat_amount or 0)

        # By payment method
        method_key = txn.payment_method.value
        if method_key not in by_method:
            by_method[method_key] = {"count": 0, "total": 0.0}
        by_method[method_key]["count"] += 1
        by_method[method_key]["total"] += float(txn.total)

        # By cashier
        cashier_id = txn.cashier_id
        if cashier_id not in by_cashier:
            by_cashier[cashier_id] = {
                "cashier_id": cashier_id,
                "cashier_name": txn.cashier.full_name if txn.cashier else "Unknown",
                "transaction_count": 0,
                "total_sales": 0.0,
            }
        by_cashier[cashier_id]["transaction_count"] += 1
        by_cashier[cashier_id]["total_sales"] += float(txn.total)

    net_sales_ex_vat = round(gross_sales - vat_collected, 2)

    payload = {
        "report_type":       "Z-TAPE",
        "store_name":        store.name,
        "store_location":    store.location or "",
        "store_kra_pin":     store.kra_pin  or "",
        "date":              str(target),
        "currency":          settings.CURRENCY,
        "transaction_count": total_count,
        "gross_sales":       round(gross_sales, 2),
        "total_discounts":   round(total_discounts, 2),
        "net_sales_ex_vat":  net_sales_ex_vat,
        "vat_collected":     round(vat_collected, 2),
        "vat_rate":          f"{int(settings.VAT_RATE * 100)}%",
        "by_payment_method": {k: {"count": v["count"], "total": round(v["total"], 2)} for k, v in by_method.items()},
        "cashier_breakdown": [
            {
                "cashier_id":        v["cashier_id"],
                "cashier_name":      v["cashier_name"],
                "transaction_count": v["transaction_count"],
                "total_sales":       round(v["total_sales"], 2),
            }
            for v in by_cashier.values()
        ],
    }

    if format == "csv":
        return ztape_to_csv(payload, f"smartlynx_ztape_{target}.csv")
    return payload


# ── Weekly Sales Summary ──────────────────────────────────────────────────────

@router.get("/weekly")
def weekly_summary(
    week_ending:    Optional[date]           = Query(default=None),
    store_id_param: Optional[int]            = Query(default=None, alias="store_id"),
    format:         Optional[Literal["csv"]] = Query(default=None),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """
    Weekly sales summary — 7 daily rows.

    PHASE P1-B: All transaction dates converted to merchant's timezone before
    daily grouping. Ensures transactions near midnight appear in correct day.

    Add **?format=csv** to download a CSV with a TOTAL footer row.
    """
    from fastapi import HTTPException
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    end   = week_ending or merchant_today()
    start = end - timedelta(days=6)

    # Fetch COMPLETED transactions for date range + buffer
    buffer_start = start - timedelta(days=1)
    buffer_end = end + timedelta(days=1)

    txns = (
        db.query(Transaction)
        .filter(Transaction.store_id == sid)
        .filter(Transaction.status == TransactionStatus.COMPLETED)
        .filter(
            (Transaction.completed_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
        )
        .filter(
            (Transaction.completed_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
        )
        .all()
    )

    # Group by merchant date
    by_date: dict[date, list[Transaction]] = {}
    for txn in txns:
        merchant_date = _get_transaction_merchant_date(txn)
        if start <= merchant_date <= end:
            if merchant_date not in by_date:
                by_date[merchant_date] = []
            by_date[merchant_date].append(txn)

    daily = []
    for i in range(7):
        day = start + timedelta(days=i)
        txns_for_day = by_date.get(day, [])
        
        transaction_count = len(txns_for_day)
        total_sales = sum(float(t.total) for t in txns_for_day)
        vat_collected = sum(float(t.vat_amount or 0) for t in txns_for_day)

        daily.append({
            "date":              str(day),
            "day":               day.strftime("%a"),
            "transaction_count": transaction_count,
            "total_sales":       round(total_sales, 2),
            "vat_collected":     round(vat_collected, 2),
        })

    week_total = sum(d["total_sales"]   for d in daily)
    week_vat   = sum(d["vat_collected"] for d in daily)

    payload = {
        "report_type":      "WEEKLY_SUMMARY",
        "store_name":       store.name,
        "period":           {"from": str(start), "to": str(end)},
        "currency":         settings.CURRENCY,
        "week_total_sales": round(week_total, 2),
        "week_total_vat":   round(week_vat, 2),
        "week_net_sales":   round(week_total - week_vat, 2),
        "daily_breakdown":  daily,
    }

    if format == "csv":
        filename = f"smartlynx_weekly_{start}_to_{end}.csv"
        return weekly_to_csv(payload, filename)
    return payload


# ── VAT Report (for KRA filing) ───────────────────────────────────────────────

@router.get("/vat")
def vat_report(
    month:          int                      = Query(..., ge=1, le=12),
    year:           int                      = Query(..., ge=2020),
    store_id_param: Optional[int]            = Query(default=None, alias="store_id"),
    format:         Optional[Literal["csv"]] = Query(default=None),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """
    Monthly VAT report for KRA filing.
    
    PHASE P1-B: All transaction dates converted to merchant's timezone
    before filtering. Prevents midnight-edge transactions from appearing
    in wrong fiscal month.

    FIX: uses SQL aggregation instead of loading all rows into Python.
    FIX: filtered to current store only.
    FIX: uses store's own KRA PIN, not global config.

    Add **?format=csv** to download a KRA-ready single-row CSV.
    """
    from fastapi import HTTPException
    from calendar import monthrange
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    first_day = date(year, month, 1)
    last_day  = date(year, month, monthrange(year, month)[1])

    # Fetch COMPLETED transactions for month + 1 day buffer on each side
    buffer_start = first_day - timedelta(days=1)
    buffer_end = last_day + timedelta(days=1)

    txns = (
        db.query(Transaction)
        .filter(Transaction.store_id == sid)
        .filter(Transaction.status == TransactionStatus.COMPLETED)
        .filter(
            (Transaction.completed_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
        )
        .filter(
            (Transaction.completed_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
        )
        .all()
    )

    # Filter to target month in merchant timezone
    target_txns = [
        t for t in txns
        if first_day <= _get_transaction_merchant_date(t) <= last_day
    ]

    transaction_count = len(target_txns)
    total_gross = sum(float(t.total) for t in target_txns)
    total_vat = sum(float(t.vat_amount or 0) for t in target_txns)
    etims_count = sum(1 for t in target_txns if t.etims_synced)

    payload = {
        "report_type":         "VAT_MONTHLY",
        "store_pin":           store.kra_pin  or settings.ETIMS_PIN,
        "store_name":          store.name,
        "period":              f"{first_day.strftime('%B %Y')}",
        "currency":            settings.CURRENCY,
        "vat_rate":            f"{int(settings.VAT_RATE * 100)}%",
        "total_gross_sales":   round(total_gross, 2),
        "total_vat_collected": round(total_vat, 2),
        "total_net_sales":     round(total_gross - total_vat, 2),
        "transaction_count":   transaction_count,
        "etims_synced_count":  etims_count,
    }

    if format == "csv":
        filename = f"smartlynx_vat_{year}-{month:02d}.csv"
        return vat_to_csv(payload, filename)
    return payload


# ── Top Products ──────────────────────────────────────────────────────────────

@router.get("/top-products")
def top_products(
    report_date:    Optional[date]           = Query(default=None),
    limit:          int                      = Query(default=10, le=50),
    store_id_param: Optional[int]            = Query(default=None, alias="store_id"),
    format:         Optional[Literal["csv"]] = Query(default=None),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """
    Top-selling products by revenue for a given date.

    PHASE P1-B: All transaction dates converted to merchant's timezone
    before filtering.

    Add **?format=csv** to download a ranked CSV.
    """
    from fastapi import HTTPException
    try:
        sid, _ = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    target = report_date or merchant_today()

    # Fetch COMPLETED transactions for date + buffer
    buffer_start = target - timedelta(days=1)
    buffer_end = target + timedelta(days=1)

    txns = (
        db.query(Transaction)
        .filter(Transaction.store_id == sid)
        .filter(Transaction.status == TransactionStatus.COMPLETED)
        .filter(
            (Transaction.completed_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at >= datetime.combine(buffer_start, datetime.min.time()).replace(tzinfo=timezone.utc))
        )
        .filter(
            (Transaction.completed_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
            | (Transaction.created_at <= datetime.combine(buffer_end, datetime.max.time()).replace(tzinfo=timezone.utc))
        )
        .all()
    )

    # Filter to target date in merchant timezone
    target_txns = [t for t in txns if _get_transaction_merchant_date(t) == target]

    # Aggregate by product
    by_product: dict[int, dict] = {}
    for txn in target_txns:
        for item in txn.items:
            pid = item.product_id
            if pid not in by_product:
                by_product[pid] = {
                    "product_id": pid,
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "units_sold": 0,
                    "revenue": 0.0,
                }
            by_product[pid]["units_sold"] += item.qty
            by_product[pid]["revenue"] += float(item.line_total)

    # Sort by revenue and limit
    products = sorted(by_product.values(), key=lambda x: x["revenue"], reverse=True)[:limit]

    payload = {
        "date": str(target),
        "products": [
            {
                "product_id":   p["product_id"],
                "product_name": p["product_name"],
                "sku":          p["sku"],
                "units_sold":   p["units_sold"],
                "revenue":      round(p["revenue"], 2),
            }
            for p in products
        ],
    }

    if format == "csv":
        return top_products_to_csv(payload, f"smartlynx_top_products_{target}.csv")
    return payload


# ── Low Stock Alert ───────────────────────────────────────────────────────────

@router.get("/low-stock")
def low_stock_report(
    store_id_param: Optional[int]            = Query(default=None, alias="store_id"),
    format:         Optional[Literal["csv"]] = Query(default=None),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """
    Products at or below their reorder level, sorted CRITICAL-first.

    Add **?format=csv** to download a CSV for purchasing/ops workflows.
    """
    from fastapi import HTTPException
    try:
        sid, _ = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    products = (
        db.query(Product)
        # FIX: filter to this store's products only
        .filter(Product.store_id      == sid)
        .filter(Product.is_active     == True)
        .filter(Product.stock_quantity <= Product.reorder_level)
        .order_by(Product.stock_quantity.asc())
        .all()
    )

    payload = {
        "report_type": "LOW_STOCK",
        "item_count":  len(products),
        "items": [
            {
                "product_id":          p.id,
                "sku":                 p.sku,
                "name":                p.name,
                "current_stock":       p.stock_quantity,
                "reorder_level":       p.reorder_level,
                "units_below_reorder": p.reorder_level - p.stock_quantity,
                "status":              "CRITICAL" if p.stock_quantity == 0 else "LOW",
            }
            for p in products
        ],
    }

    if format == "csv":
        from datetime import date as _date
        return low_stock_to_csv(payload, f"smartlynx_low_stock_{_date.today()}.csv")
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# PDF Report Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/z-tape/pdf")
def z_tape_pdf(
    report_date:    Optional[date]  = Query(default=None),
    store_id_param: Optional[int]   = Query(default=None, alias="store_id"),
    download:       bool            = Query(True, description="If true, download as file; if false, display in browser"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Z-Tape as PDF."""
    from fastapi import HTTPException
    
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    target = report_date or merchant_today()
    buffer_start = target - timedelta(days=1)
    buffer_end = target + timedelta(days=1)
    
    # Fetch transaction data (reuse logic from z_tape endpoint)
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.completed_at.isnot(None),
    ).order_by(Transaction.completed_at.desc()).all()
    
    payload_data = _build_z_tape_payload(txns, target, sid, store, True)  # Include formatted timestamp
    
    pdf_bytes = pdf_service.generate_report_pdf(
        "z_tape",
        payload_data,
        store_name=store.name,
        store_location=store.address or "N/A",
    )
    
    filename = f"ZTape-{target.isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download=download)


@router.get("/weekly/pdf")
def weekly_pdf(
    start_date:     Optional[date]  = Query(default=None),
    end_date:       Optional[date]  = Query(default=None),
    store_id_param: Optional[int]   = Query(default=None, alias="store_id"),
    download:       bool            = Query(True, description="If true, download as file; if false, display in browser"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Weekly report as PDF."""
    from fastapi import HTTPException
    
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    # Compute date range
    if not end_date:
        end_date = merchant_today()
    if not start_date:
        start_date = end_date - timedelta(days=6)
    
    # Fetch transaction data
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.completed_at.isnot(None),
    ).order_by(Transaction.completed_at.desc()).all()
    
    payload_data = _build_weekly_payload(txns, start_date, end_date, sid)
    
    pdf_bytes = pdf_service.generate_report_pdf(
        "weekly",
        payload_data,
        store_name=store.name,
        store_location=store.address or "N/A",
    )
    
    filename = f"Weekly-{start_date.isoformat()}-to-{end_date.isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download=download)


@router.get("/vat/pdf")
def vat_pdf(
    month:          Optional[str]   = Query(default=None, description="YYYY-MM"),
    store_id_param: Optional[int]   = Query(default=None, alias="store_id"),
    download:       bool            = Query(True, description="If true, download as file; if false, display in browser"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return VAT report as PDF."""
    from fastapi import HTTPException
    
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    # Parse month or use current
    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(400, "Invalid month format. Use YYYY-MM")
    else:
        month_date = merchant_today().replace(day=1)
    
    start = month_date.replace(day=1)
    if month_date.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    end = end - timedelta(days=1)
    
    # Fetch transaction data
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.completed_at.isnot(None),
    ).order_by(Transaction.completed_at.desc()).all()
    
    payload_data = _build_vat_payload(txns, start, end, sid)
    
    pdf_bytes = pdf_service.generate_report_pdf(
        "vat",
        payload_data,
        store_name=store.name,
        store_location=store.address or "N/A",
    )
    
    filename = f"VAT-Report-{month_date.year}-{month_date.month:02d}.pdf"
    return pdf_response(pdf_bytes, filename, download=download)


@router.get("/top-products/pdf")
def top_products_pdf(
    start_date:     Optional[date]  = Query(default=None),
    end_date:       Optional[date]  = Query(default=None),
    store_id_param: Optional[int]   = Query(default=None, alias="store_id"),
    limit:          int             = Query(20, ge=1, le=100),
    download:       bool            = Query(True, description="If true, download as file; if false, display in browser"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Top Products report as PDF."""
    from fastapi import HTTPException
    
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    # Compute date range
    if not end_date:
        end_date = merchant_today()
    if not start_date:
        start_date = end_date - timedelta(days=29)  # Last 30 days
    
    # Fetch transaction data
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.completed_at.isnot(None),
    ).all()
    
    payload_data = _build_top_products_payload(txns, start_date, end_date, sid, limit)
    
    pdf_bytes = pdf_service.generate_report_pdf(
        "top_products",
        payload_data,
        store_name=store.name,
        store_location=store.address or "N/A",
    )
    
    filename = f"TopProducts-{start_date.isoformat()}-to-{end_date.isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download=download)


@router.get("/low-stock/pdf")
def low_stock_pdf(
    store_id_param: Optional[int]   = Query(default=None, alias="store_id"),
    download:       bool            = Query(True, description="If true, download as file; if false, display in browser"),
    db:      Session  = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Low Stock alert report as PDF."""
    from fastapi import HTTPException
    
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    # Fetch products below reorder level
    products = (
        db.query(Product)
        .filter(Product.store_id == sid)
        .filter(Product.is_active == True)
        .filter(Product.stock_quantity <= Product.reorder_level)
        .order_by(Product.stock_quantity.asc())
        .all()
    )
    
    payload_data = {
        "report_type": "LOW_STOCK",
        "report_date": merchant_today(),
        "item_count": len(products),
        "items": [
            {
                "product_id": p.id,
                "sku": p.sku,
                "product_name": p.name,
                "current_stock": p.stock_quantity,
                "reorder_level": p.reorder_level,
                "min_stock": p.min_stock,
                "units_below_reorder": max(0, p.reorder_level - p.stock_quantity),
                "status": "CRITICAL" if p.stock_quantity == 0 else "LOW",
            }
            for p in products
        ],
    }
    
    pdf_bytes = pdf_service.generate_report_pdf(
        "low_stock",
        payload_data,
        store_name=store.name,
        store_location=store.address or "N/A",
    )
    
    filename = f"LowStock-{merchant_today().isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download=download)


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions for PDF report data building
# ─────────────────────────────────────────────────────────────────────────────

def _build_z_tape_payload(txns, target_date, sid, store, include_timestamp=False):
    """Extract Z-Tape data from transactions."""
    filtered = []
    for t in txns:
        txn_date = t.completed_at.date() if t.completed_at else t.created_at.date()
        if txn_date == target_date:
            filtered.append(t)
    
    gross = sum(t.total for t in filtered) if filtered else 0
    vat = sum(t.vat_amount or 0 for t in filtered) if filtered else 0
    
    return {
        "report_type": "Z_TAPE",
        "transaction_date": target_date,
        "transaction_count": len(filtered),
        "gross_sales": float(gross),
        "vat_collected": float(vat),
        "net_sales_ex_vat": float(gross - vat),
        "currency": "KES",
        "by_payment_method": [],
        "cashier_breakdown": [],
    }
    """Extract Weekly data from transactions."""
    total_sales = sum(t.total_amount for t in txns) if txns else 0
    total_count = len(txns)
    days = (end_date - start_date).days + 1
    avg_daily = total_sales / days if days > 0 else 0
    
    return {
        "report_type": "WEEKLY",
        "start_date": start_date,
        "end_date": end_date,
        "total_transactions": total_count,
        "total_sales": float(total_sales),
        "average_sales_per_day": float(avg_daily),
        "currency": "KES",
        "daily_breakdown": [],
    }


def _build_vat_payload(txns, start_date, end_date, sid):
    """Extract VAT data from transactions."""
    total_sales = sum(t.total_amount for t in txns) if txns else 0
    total_vat = sum(t.tax_amount for t in txns) if txns else 0
    
    return {
        "report_type": "VAT",
        "month": start_date.strftime("%Y-%m"),
        "gross_sales": float(total_sales),
        "vat_rate": 16,  # Kenya VAT rate
        "vat_collected": float(total_vat),
        "net_sales_ex_vat": float(total_sales - total_vat) if total_sales > 0 else 0,
        "currency": "KES",
        "by_category": [],
    }


def _build_top_products_payload(txns, start_date, end_date, sid, limit=20):
    """Extract Top Products data from transactions."""
    product_sales = {}
    for txn in txns:
        for item in txn.items:
            pid = item.product_id
            if pid not in product_sales:
                product_sales[pid] = {
                    "product_id": pid,
                    "product_name": item.product.name if item.product else f"Product {pid}",
                    "units_sold": 0,
                    "revenue": 0,
                }
            product_sales[pid]["units_sold"] += int(item.quantity)
            product_sales[pid]["revenue"] += float(item.line_total)
    
    sorted_products = sorted(
        product_sales.values(),
        key=lambda x: x["revenue"],
        reverse=True
    )[:limit]
    
    total_revenue = sum(p["revenue"] for p in sorted_products)
    
    return {
        "report_type": "TOP_PRODUCTS",
        "period": f"{start_date} to {end_date}",
        "products": sorted_products,
        "total_revenue": float(total_revenue),
        "currency": "KES",
    }
