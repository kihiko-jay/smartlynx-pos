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

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Literal, Optional
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from io import BytesIO

from app.core.csv_export import (
    ztape_to_csv,
    weekly_to_csv,
    vat_to_csv,
    top_products_to_csv,
    low_stock_to_csv,
)
from app.core.pdf_generator import (
    pdf_response,
    get_styles,
    build_store_header,
    build_footer,
    create_pdf_document,
    format_currency,
)
from app.core.deps import get_db, require_premium, get_current_employee
from app.core.datetime_utils import (
    utc_to_merchant_date,
    merchant_today,
    ensure_utc_datetime,
)
from app.models.transaction import Transaction, TransactionStatus
from app.models.product import Product
from app.models.employee import Employee, Role
from app.models.subscription import Store
from app.core.config import settings
from app.core.money import quantize_money
from app.core.report_aggregates import (
    aggregate_completed_txn_financials,
    money_json,
    quantize_txn_field,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


# ── Helper: resolve which store_id to report on ───────────────────────────────

def _resolve_store(
    current: Employee,
    db: Session,
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
            raise HTTPException(400, "PLATFORM_OWNER must supply ?store_id= to view reports")
    else:
        sid = current.store_id

    store = db.query(Store).filter(Store.id == sid).first()
    if not store:
        raise HTTPException(404, f"Store {sid} not found")
    return sid, store


def _get_transaction_merchant_date(txn: Transaction) -> date:
    """Extract the business date (in merchant's timezone) for a transaction."""
    ts = ensure_utc_datetime(txn.completed_at or txn.created_at)
    return utc_to_merchant_date(ts)


# ── Z-Tape / End of Day ───────────────────────────────────────────────────────

@router.get("/z-tape")
def z_tape(
    report_date: Optional[date] = Query(default=None),
    store_id_param: Optional[int] = Query(default=None, alias="store_id", description="Platform owner only"),
    format: Optional[Literal["csv"]] = Query(default=None),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """End-of-day Z-tape. Shows only this store's transactions."""
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    target = report_date or merchant_today()
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

    target_txns = [t for t in txns if _get_transaction_merchant_date(t) == target]

    agg = aggregate_completed_txn_financials(target_txns)
    total_count = len(target_txns)

    # Aggregate by payment method and cashier (Decimal buckets → JSON at payload)
    by_method: dict[str, dict] = {}
    by_cashier: dict[int | None, dict] = {}

    for txn in target_txns:
        method_key = txn.payment_method.value
        if method_key not in by_method:
            by_method[method_key] = {"count": 0, "total": Decimal("0")}
        by_method[method_key]["count"] += 1
        by_method[method_key]["total"] += quantize_txn_field(txn.total)

        cashier_id = txn.cashier_id
        if cashier_id not in by_cashier:
            by_cashier[cashier_id] = {
                "cashier_id": cashier_id,
                "cashier_name": txn.cashier.full_name if txn.cashier else "Unknown",
                "transaction_count": 0,
                "total_sales": Decimal("0"),
            }
        by_cashier[cashier_id]["transaction_count"] += 1
        by_cashier[cashier_id]["total_sales"] += quantize_txn_field(txn.total)

    payload = {
        "report_type": "Z-TAPE",
        "store_name": store.name,
        "store_location": store.location or "",
        "store_kra_pin": store.kra_pin or "",
        "date": str(target),
        "currency": settings.CURRENCY,
        "transaction_count": total_count,
        "gross_sales": money_json(agg["gross_sales"]),
        "total_discounts": money_json(agg["total_discounts"]),
        "net_sales_ex_vat": money_json(agg["net_sales_ex_vat"]),
        "vat_collected": money_json(agg["vat_collected"]),
        "vat_rate": f"{int(Decimal(str(settings.VAT_RATE)) * 100)}%",
        "by_payment_method": {
            k: {"count": v["count"], "total": money_json(quantize_money(v["total"]))}
            for k, v in by_method.items()
        },
        "cashier_breakdown": [
            {
                "cashier_id": v["cashier_id"],
                "cashier_name": v["cashier_name"],
                "transaction_count": v["transaction_count"],
                "total_sales": money_json(quantize_money(v["total_sales"])),
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
    week_ending: Optional[date] = Query(default=None),
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    format: Optional[Literal["csv"]] = Query(default=None),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Weekly sales summary — 7 daily rows."""
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    end = week_ending or merchant_today()
    start = end - timedelta(days=6)
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

    by_date: dict[date, list[Transaction]] = {}
    for txn in txns:
        merchant_date = _get_transaction_merchant_date(txn)
        if start <= merchant_date <= end:
            by_date.setdefault(merchant_date, []).append(txn)

    daily = []
    week_total_dec = Decimal("0")
    week_vat_dec = Decimal("0")
    week_net_dec = Decimal("0")
    for i in range(7):
        day = start + timedelta(days=i)
        txns_for_day = by_date.get(day, [])

        transaction_count = len(txns_for_day)
        day_agg = aggregate_completed_txn_financials(txns_for_day)
        total_sales = day_agg["gross_sales"]
        vat_collected = day_agg["vat_collected"]
        net_ex = day_agg["net_sales_ex_vat"]

        week_total_dec += total_sales
        week_vat_dec += vat_collected
        week_net_dec += net_ex

        daily.append({
            "date": str(day),
            "day": day.strftime("%a"),
            "transaction_count": transaction_count,
            "total_sales": money_json(total_sales),
            "vat_collected": money_json(vat_collected),
        })

    week_total_dec = quantize_money(week_total_dec)
    week_vat_dec = quantize_money(week_vat_dec)
    week_net_dec = quantize_money(week_net_dec)

    payload = {
        "report_type": "WEEKLY_SUMMARY",
        "store_name": store.name,
        "period": {"from": str(start), "to": str(end)},
        "currency": settings.CURRENCY,
        "week_total_sales": money_json(week_total_dec),
        "week_total_vat": money_json(week_vat_dec),
        "week_net_sales": money_json(week_net_dec),
        "daily_breakdown": daily,
    }

    if format == "csv":
        return weekly_to_csv(payload, f"smartlynx_weekly_{start}_to_{end}.csv")
    return payload


# ── VAT Report ────────────────────────────────────────────────────────────────

@router.get("/vat")
def vat_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    format: Optional[Literal["csv"]] = Query(default=None),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Monthly VAT report for KRA filing."""
    from calendar import monthrange
    
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
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

    target_txns = [t for t in txns if first_day <= _get_transaction_merchant_date(t) <= last_day]

    transaction_count = len(target_txns)
    vat_agg = aggregate_completed_txn_financials(target_txns)
    etims_count = sum(1 for t in target_txns if t.etims_synced)

    payload = {
        "report_type": "VAT_MONTHLY",
        "store_pin": store.kra_pin or settings.ETIMS_PIN,
        "store_name": store.name,
        "period": f"{first_day.strftime('%B %Y')}",
        "currency": settings.CURRENCY,
        "vat_rate": f"{int(Decimal(str(settings.VAT_RATE)) * 100)}%",
        "total_gross_sales": money_json(vat_agg["gross_sales"]),
        "total_vat_collected": money_json(vat_agg["vat_collected"]),
        "total_net_sales": money_json(vat_agg["net_sales_ex_vat"]),
        "transaction_count": transaction_count,
        "etims_synced_count": etims_count,
    }

    if format == "csv":
        return vat_to_csv(payload, f"smartlynx_vat_{year}-{month:02d}.csv")
    return payload


# ── Top Products ──────────────────────────────────────────────────────────────

@router.get("/top-products")
def top_products(
    report_date: Optional[date] = Query(default=None),
    limit: int = Query(default=10, le=50),
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    format: Optional[Literal["csv"]] = Query(default=None),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Top-selling products by revenue for a given date."""
    try:
        sid, _ = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    target = report_date or merchant_today()
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

    target_txns = [t for t in txns if _get_transaction_merchant_date(t) == target]

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
                    "revenue": Decimal("0"),
                }
            by_product[pid]["units_sold"] += item.qty
            by_product[pid]["revenue"] += quantize_txn_field(item.line_total)

    products = sorted(by_product.values(), key=lambda x: x["revenue"], reverse=True)[:limit]

    payload = {
        "date": str(target),
        "products": [
            {
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "sku": p["sku"],
                "units_sold": p["units_sold"],
                "revenue": money_json(quantize_money(p["revenue"])),
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
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    format: Optional[Literal["csv"]] = Query(default=None),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Products at or below their reorder level, sorted CRITICAL-first."""
    try:
        sid, _ = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))

    products = (
        db.query(Product)
        .filter(Product.store_id == sid)
        .filter(Product.is_active == True)
        .filter(Product.stock_quantity <= Product.reorder_level)
        .order_by(Product.stock_quantity.asc())
        .all()
    )

    payload = {
        "report_type": "LOW_STOCK",
        "item_count": len(products),
        "items": [
            {
                "product_id": p.id,
                "sku": p.sku,
                "name": p.name,
                "current_stock": p.stock_quantity,
                "reorder_level": p.reorder_level,
                "units_below_reorder": p.reorder_level - p.stock_quantity,
                "status": "CRITICAL" if p.stock_quantity == 0 else "LOW",
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

def _build_z_tape_pdf_elements(data: dict, store_name: str, store_location: str):
    """Build PDF elements for Z-Tape report."""
    styles = get_styles()
    elements = []
    
    # Header
    report_title = f"Z-TAPE REPORT - {data.get('transaction_date', 'N/A')}"
    elements.extend(build_store_header(store_name, store_location, report_title))
    
    # Summary section
    elements.append(Paragraph("SUMMARY", styles["DocHeader"]))
    elements.append(Spacer(1, 5 * mm))
    
    summary_data = [
        ["Metric", "Value"],
        ["Transaction Count", str(data.get('transaction_count', 0))],
        ["Gross Sales", format_currency(data.get('gross_sales', 0))],
        ["VAT Collected (16%)", format_currency(data.get('vat_collected', 0))],
        ["Net Sales (ex VAT)", format_currency(data.get('net_sales_ex_vat', 0))],
    ]
    
    summary_table = Table(summary_data, colWidths=[80 * mm, 80 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10 * mm))
    
    elements.extend(build_footer(store_name, "End of Z-Tape Report"))
    return elements


def _build_weekly_pdf_elements(data: dict, store_name: str, store_location: str):
    """Build PDF elements for Weekly report."""
    styles = get_styles()
    elements = []
    
    period = data.get('period', 'N/A')
    if isinstance(period, dict):
        period_str = f"{period.get('from', '')} to {period.get('to', '')}"
    else:
        period_str = str(period)
    
    report_title = f"WEEKLY SALES REPORT - {period_str}"
    elements.extend(build_store_header(store_name, store_location, report_title))
    
    elements.append(Paragraph("SUMMARY", styles["DocHeader"]))
    elements.append(Spacer(1, 5 * mm))
    
    summary_data = [
        ["Metric", "Value"],
        ["Total Transactions", str(data.get('total_transactions', 0))],
        ["Total Sales", format_currency(data.get('total_sales', 0))],
        ["Average Daily Sales", format_currency(data.get('average_sales_per_day', 0))],
    ]
    
    summary_table = Table(summary_data, colWidths=[80 * mm, 80 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10 * mm))
    
    elements.extend(build_footer(store_name))
    return elements


def _build_vat_pdf_elements(data: dict, store_name: str, store_location: str):
    """Build PDF elements for VAT report."""
    styles = get_styles()
    elements = []
    
    report_title = f"VAT REPORT - {data.get('month', 'N/A')}"
    elements.extend(build_store_header(store_name, store_location, report_title))
    
    elements.append(Paragraph("VAT SUMMARY", styles["DocHeader"]))
    elements.append(Spacer(1, 5 * mm))
    
    summary_data = [
        ["Metric", "Value"],
        ["Gross Sales", format_currency(data.get('gross_sales', 0))],
        ["VAT Rate", f"{data.get('vat_rate', 16)}%"],
        ["VAT Collected", format_currency(data.get('vat_collected', 0))],
        ["Net Sales (ex VAT)", format_currency(data.get('net_sales_ex_vat', 0))],
    ]
    
    summary_table = Table(summary_data, colWidths=[80 * mm, 80 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10 * mm))
    
    elements.extend(build_footer(store_name, "For KRA filing purposes"))
    return elements


def _build_top_products_pdf_elements(data: dict, store_name: str, store_location: str):
    """Build PDF elements for Top Products report."""
    styles = get_styles()
    elements = []
    
    report_title = f"TOP PRODUCTS REPORT - {data.get('period', 'N/A')}"
    elements.extend(build_store_header(store_name, store_location, report_title))
    
    products = data.get('products', [])
    if products:
        elements.append(Paragraph("PRODUCTS BY REVENUE", styles["DocHeader"]))
        elements.append(Spacer(1, 5 * mm))
        
        product_data = [["Rank", "Product Name", "Units Sold", "Revenue"]]
        for idx, product in enumerate(products, 1):
            product_data.append([
                str(idx),
                product.get('product_name', 'Unknown')[:40],
                str(product.get('units_sold', 0)),
                format_currency(product.get('revenue', 0))
            ])
        
        product_table = Table(product_data, colWidths=[20 * mm, 90 * mm, 30 * mm, 40 * mm])
        product_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(product_table)
        elements.append(Spacer(1, 10 * mm))
        
        elements.append(Paragraph(f"Total Revenue: {format_currency(data.get('total_revenue', 0))}", 
                                   styles["DocHeader"]))
    else:
        elements.append(Paragraph("No product sales data available for this period.", 
                                   styles["BodyText"]))
    
    elements.append(Spacer(1, 10 * mm))
    elements.extend(build_footer(store_name))
    return elements


def _build_low_stock_pdf_elements(data: dict, store_name: str, store_location: str):
    """Build PDF elements for Low Stock report."""
    styles = get_styles()
    elements = []
    
    report_title = f"LOW STOCK ALERT - {data.get('report_date', 'N/A')}"
    elements.extend(build_store_header(store_name, store_location, report_title))
    
    items = data.get('items', [])
    if items:
        elements.append(Paragraph("PRODUCTS BELOW REORDER LEVEL", styles["DocHeader"]))
        elements.append(Spacer(1, 5 * mm))
        
        item_data = [["SKU", "Product Name", "Current Stock", "Reorder Level", "Status"]]
        for item in items:
            status = item.get('status', 'LOW')
            item_data.append([
                item.get('sku', '-'),
                item.get('product_name', 'Unknown')[:40],
                str(item.get('current_stock', 0)),
                str(item.get('reorder_level', 0)),
                status
            ])
        
        item_table = Table(item_data, colWidths=[35 * mm, 80 * mm, 25 * mm, 25 * mm, 25 * mm])
        
        table_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]
        
        # Color rows by status
        for idx, item in enumerate(items, 1):
            status = item.get('status', 'LOW')
            if status == "CRITICAL":
                table_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#fee2e2")))
            elif status == "LOW":
                table_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#fef3c7")))
        
        item_table.setStyle(TableStyle(table_style))
        elements.append(item_table)
        elements.append(Spacer(1, 10 * mm))
        
        elements.append(Paragraph(f"Total items below reorder level: {data.get('item_count', 0)}", 
                                   styles["BodyText"]))
    else:
        elements.append(Paragraph("No products are currently below reorder level.", 
                                   styles["BodyText"]))
    
    elements.append(Spacer(1, 10 * mm))
    elements.extend(build_footer(store_name, "Please reorder soon to avoid stockouts"))
    return elements


@router.get("/z-tape/pdf")
def z_tape_pdf(
    report_date: Optional[date] = Query(default=None),
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    download: bool = Query(True, description="If true, download as file; if false, display in browser"),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Z-Tape as PDF."""
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    target = report_date or merchant_today()
    
    # Get transactions for the date
    start_date = datetime.combine(target, datetime.min.time())
    end_date = datetime.combine(target, datetime.max.time())
    
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date,
    ).all()
    
    pdf_agg = aggregate_completed_txn_financials(txns)
    transaction_count = len(txns)

    data = {
        "report_type": "z_tape",
        "transaction_date": target,
        "transaction_count": transaction_count,
        "gross_sales": money_json(pdf_agg["gross_sales"]),
        "vat_collected": money_json(pdf_agg["vat_collected"]),
        "net_sales_ex_vat": money_json(pdf_agg["net_sales_ex_vat"]),
        "currency": settings.CURRENCY,
    }
    
    # Build PDF
    elements = _build_z_tape_pdf_elements(data, store.name, store.location or "")
    pdf_bytes = create_pdf_document(elements)
    
    filename = f"ZTape-{target.isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download)


@router.get("/weekly/pdf")
def weekly_pdf(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    download: bool = Query(True, description="If true, download as file; if false, display in browser"),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Weekly report as PDF."""
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    if not end_date:
        end_date = merchant_today()
    if not start_date:
        start_date = end_date - timedelta(days=6)
    
    # Get transactions for the period
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.created_at >= start_dt,
        Transaction.created_at <= end_dt,
    ).all()
    
    w_agg = aggregate_completed_txn_financials(txns)
    total_sales_dec = w_agg["gross_sales"]
    transaction_count = len(txns)
    days = (end_date - start_date).days + 1
    avg_daily_dec = quantize_money(total_sales_dec / Decimal(days)) if days > 0 else Decimal("0")

    data = {
        "report_type": "weekly",
        "period": {"from": start_date, "to": end_date},
        "total_transactions": transaction_count,
        "total_sales": money_json(total_sales_dec),
        "average_sales_per_day": money_json(avg_daily_dec),
        "currency": settings.CURRENCY,
    }
    
    # Build PDF
    elements = _build_weekly_pdf_elements(data, store.name, store.location or "")
    pdf_bytes = create_pdf_document(elements)
    
    filename = f"Weekly-{start_date.isoformat()}-to-{end_date.isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download)


@router.get("/vat/pdf")
def vat_pdf(
    month: Optional[str] = Query(default=None, description="YYYY-MM"),
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    download: bool = Query(True, description="If true, download as file; if false, display in browser"),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return VAT report as PDF."""
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
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
    
    # Get transactions for the month
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
    
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.created_at >= start_dt,
        Transaction.created_at <= end_dt,
    ).all()
    
    v_agg = aggregate_completed_txn_financials(txns)

    data = {
        "report_type": "vat",
        "month": month_date.strftime("%B %Y"),
        "gross_sales": money_json(v_agg["gross_sales"]),
        "vat_rate": int(Decimal(str(settings.VAT_RATE)) * 100),
        "vat_collected": money_json(v_agg["vat_collected"]),
        "net_sales_ex_vat": money_json(v_agg["net_sales_ex_vat"]),
        "currency": settings.CURRENCY,
    }
    
    # Build PDF
    elements = _build_vat_pdf_elements(data, store.name, store.location or "")
    pdf_bytes = create_pdf_document(elements)
    
    filename = f"VAT-Report-{month_date.year}-{month_date.month:02d}.pdf"
    return pdf_response(pdf_bytes, filename, download)


@router.get("/top-products/pdf")
def top_products_pdf(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    limit: int = Query(20, ge=1, le=100),
    download: bool = Query(True, description="If true, download as file; if false, display in browser"),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Top Products report as PDF."""
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    if not end_date:
        end_date = merchant_today()
    if not start_date:
        start_date = end_date - timedelta(days=29)
    
    # Get transactions for the period
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    txns = db.query(Transaction).filter(
        Transaction.store_id == sid,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.created_at >= start_dt,
        Transaction.created_at <= end_dt,
    ).all()
    
    product_sales: dict = {}
    for txn in txns:
        for item in txn.items:
            pid = item.product_id
            if pid not in product_sales:
                product_sales[pid] = {
                    "product_id": pid,
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "units_sold": 0,
                    "revenue": Decimal("0"),
                }
            product_sales[pid]["units_sold"] += int(item.qty)
            product_sales[pid]["revenue"] += quantize_txn_field(item.line_total)

    sorted_products = sorted(
        product_sales.values(),
        key=lambda x: x["revenue"],
        reverse=True,
    )[:limit]

    total_revenue_dec = quantize_money(sum(p["revenue"] for p in sorted_products))
    pdf_products = [
        {**p, "revenue": money_json(quantize_money(p["revenue"]))}
        for p in sorted_products
    ]

    data = {
        "report_type": "top_products",
        "period": f"{start_date} to {end_date}",
        "products": pdf_products,
        "total_revenue": money_json(total_revenue_dec),
        "currency": settings.CURRENCY,
    }
    
    # Build PDF
    elements = _build_top_products_pdf_elements(data, store.name, store.location or "")
    pdf_bytes = create_pdf_document(elements)
    
    filename = f"TopProducts-{start_date.isoformat()}-to-{end_date.isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download)


@router.get("/low-stock/pdf")
def low_stock_pdf(
    store_id_param: Optional[int] = Query(default=None, alias="store_id"),
    download: bool = Query(True, description="If true, download as file; if false, display in browser"),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """Generate and return Low Stock alert report as PDF."""
    try:
        sid, store = _resolve_store(current, db, store_id_param)
    except Exception as e:
        raise HTTPException(400, str(e))
    
    products = db.query(Product).filter(
        Product.store_id == sid,
        Product.is_active == True,
        Product.stock_quantity <= Product.reorder_level,
    ).order_by(Product.stock_quantity.asc()).all()
    
    items = []
    for p in products:
        status = "CRITICAL" if p.stock_quantity == 0 else "LOW"
        items.append({
            "product_id": p.id,
            "sku": p.sku,
            "product_name": p.name,
            "current_stock": p.stock_quantity,
            "reorder_level": p.reorder_level,
            "status": status,
        })
    
    # Prepare data for PDF
    data = {
        "report_type": "low_stock",
        "report_date": merchant_today(),
        "item_count": len(items),
        "items": items,
    }
    
    # Build PDF
    elements = _build_low_stock_pdf_elements(data, store.name, store.location or "")
    pdf_bytes = create_pdf_document(elements, page_size=landscape(A4))
    
    filename = f"LowStock-{merchant_today().isoformat()}.pdf"
    return pdf_response(pdf_bytes, filename, download)


# ── Health check endpoint ─────────────────────────────────────────────────────

@router.get("/health")
def reports_health(current: Employee = Depends(require_premium)):
    """Health check for reports module."""
    return {"status": "healthy", "module": "reports", "store_id": current.store_id}