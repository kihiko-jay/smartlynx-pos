"""
csv_export.py — SmartlynX report CSV serialisers

Rules enforced here:
  • Zero business logic — only presentation/formatting.
  • Zero DB access.
  • Zero auth.
  • One flattener per report type; each accepts the same dict the JSON
    endpoint already returns so there is a single source of truth.
  • UTF-8 BOM (\\ufeff) is prepended so Excel on Windows opens the file
    without the "Text Import Wizard" prompt (critical for KRA/accounting
    workflows in Kenya).
  • All monetary values: 2 decimal places, no currency symbol in the
    cell (currency is a separate header column for spreadsheet clarity).
  • Section headers are emitted as comment rows (# …) so automated
    parsers can skip them while humans see clean sections in Excel.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi.responses import StreamingResponse


# ── Internal helpers ──────────────────────────────────────────────────────────

def _make_response(buf: io.StringIO, filename: str, report_type: str) -> StreamingResponse:
    """
    Wrap a StringIO CSV buffer in a StreamingResponse with correct headers.

    Headers set:
      Content-Type        text/csv; charset=utf-8
      Content-Disposition attachment; filename="<filename>"
      X-Report-Type       <report_type>  (for clients that want to inspect type)
      Cache-Control       no-store       (reports are live data)
    """
    raw = "\ufeff" + buf.getvalue()          # UTF-8 BOM for Excel compatibilty

    def _iter():
        yield raw.encode("utf-8")

    return StreamingResponse(
        _iter(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Report-Type":       report_type,
            "Cache-Control":       "no-store",
        },
    )


def _comment(writer: "csv.writer", text: str) -> None:  # type: ignore[name-defined]
    """Write a single comment/section-header row."""
    writer.writerow([f"# {text}"])


def _blank(writer: "csv.writer") -> None:  # type: ignore[name-defined]
    writer.writerow([])


def _money(value: float | int) -> str:
    return f"{float(value):.2f}"


# ── Z-Tape ────────────────────────────────────────────────────────────────────

def ztape_to_csv(data: dict[str, Any], filename: str) -> StreamingResponse:
    """
    Flatten the Z-tape JSON dict into a multi-section CSV.

    Sections:
      1. Summary row     — one header row + one data row
      2. Payment methods — one row per method
      3. Cashier         — one row per cashier
    """
    buf = io.StringIO()
    w   = csv.writer(buf)

    currency = data.get("currency", "KES")

    # ── Section header ────────────────────────────────────────────────────────
    _comment(w, (
        f"SMARTLYNX Z-TAPE \u2500\u2500 {data.get('store_name', '')} "
        f"\u2500\u2500 {data.get('date', '')}"
    ))
    _blank(w)

    # ── 1. Summary ────────────────────────────────────────────────────────────
    _comment(w, "Summary")
    w.writerow([
        "Date",
        "Store Name",
        "Store Location",
        "KRA PIN",
        "Currency",
        "Transaction Count",
        f"Gross Sales ({currency})",
        f"Discounts ({currency})",
        f"Net Sales ex-VAT ({currency})",
        f"VAT Collected ({currency})",
        "VAT Rate",
    ])
    w.writerow([
        data.get("date", ""),
        data.get("store_name", ""),
        data.get("store_location", ""),
        data.get("store_kra_pin", ""),
        currency,
        data.get("transaction_count", 0),
        _money(data.get("gross_sales", 0)),
        _money(data.get("total_discounts", 0)),
        _money(data.get("net_sales_ex_vat", 0)),
        _money(data.get("vat_collected", 0)),
        data.get("vat_rate", ""),
    ])

    # ── 2. Payment method breakdown ───────────────────────────────────────────
    _blank(w)
    _comment(w, "Payment Method Breakdown")
    w.writerow(["Payment Method", "Transaction Count", f"Total ({currency})"])
    for method, info in sorted((data.get("by_payment_method") or {}).items()):
        w.writerow([
            method.upper(),
            info.get("count", 0),
            _money(info.get("total", 0)),
        ])

    # ── 3. Cashier breakdown ──────────────────────────────────────────────────
    _blank(w)
    _comment(w, "Cashier Breakdown")
    w.writerow(["Cashier Name", "Transaction Count", f"Total Sales ({currency})"])
    for row in (data.get("cashier_breakdown") or []):
        w.writerow([
            row.get("cashier_name", "Unknown"),
            row.get("transaction_count", 0),
            _money(row.get("total_sales", 0)),
        ])

    return _make_response(buf, filename, "Z-TAPE")


# ── Weekly Summary ────────────────────────────────────────────────────────────

def weekly_to_csv(data: dict[str, Any], filename: str) -> StreamingResponse:
    """
    Flatten weekly summary into a 7-row CSV with a TOTAL footer.

    Columns: Date, Day, Transaction Count, Total Sales, VAT Collected,
             Net Sales ex-VAT
    """
    buf = io.StringIO()
    w   = csv.writer(buf)

    currency = data.get("currency", "KES")
    period   = data.get("period", {})

    _comment(w, (
        f"SMARTLYNX WEEKLY SUMMARY \u2500\u2500 {data.get('store_name', '')} "
        f"\u2500\u2500 {period.get('from', '')} to {period.get('to', '')}"
    ))
    _blank(w)

    w.writerow([
        "Date",
        "Day",
        "Transaction Count",
        f"Total Sales ({currency})",
        f"VAT Collected ({currency})",
        f"Net Sales ex-VAT ({currency})",
    ])

    for day in (data.get("daily_breakdown") or []):
        total = float(day.get("total_sales", 0))
        vat   = float(day.get("vat_collected", 0))
        w.writerow([
            day.get("date", ""),
            day.get("day", ""),
            day.get("transaction_count", 0),
            _money(total),
            _money(vat),
            _money(total - vat),
        ])

    # TOTAL footer row
    _blank(w)
    w.writerow([
        "TOTAL",
        "",
        "",
        _money(data.get("week_total_sales", 0)),
        _money(data.get("week_total_vat", 0)),
        _money(data.get("week_net_sales", 0)),
    ])

    return _make_response(buf, filename, "WEEKLY_SUMMARY")


# ── VAT Report ────────────────────────────────────────────────────────────────

def vat_to_csv(data: dict[str, Any], filename: str) -> StreamingResponse:
    """
    Flatten VAT monthly report into a single-row KRA-ready CSV.

    One header row + one data row — designed to be copied directly into
    KRA iTax VAT3 submission or handed to an accountant.
    """
    buf = io.StringIO()
    w   = csv.writer(buf)

    currency = data.get("currency", "KES")

    _comment(w, (
        f"SMARTLYNX VAT REPORT \u2500\u2500 {data.get('store_name', '')} "
        f"\u2500\u2500 {data.get('period', '')}"
    ))
    _blank(w)

    w.writerow([
        "Store Name",
        "KRA PIN",
        "Period",
        "Currency",
        "VAT Rate",
        f"Gross Sales ({currency})",
        f"VAT Collected ({currency})",
        f"Net Sales ex-VAT ({currency})",
        "Transaction Count",
        "eTIMS Synced Count",
    ])
    w.writerow([
        data.get("store_name", ""),
        data.get("store_pin", ""),
        data.get("period", ""),
        currency,
        data.get("vat_rate", ""),
        _money(data.get("total_gross_sales", 0)),
        _money(data.get("total_vat_collected", 0)),
        _money(data.get("total_net_sales", 0)),
        data.get("transaction_count", 0),
        data.get("etims_synced_count", 0),
    ])

    return _make_response(buf, filename, "VAT_MONTHLY")


# ── Top Products ──────────────────────────────────────────────────────────────

def top_products_to_csv(data: dict[str, Any], filename: str) -> StreamingResponse:
    """
    Flatten top-products list into a ranked CSV.
    """
    buf = io.StringIO()
    w   = csv.writer(buf)

    _comment(w, f"SMARTLYNX TOP PRODUCTS \u2500\u2500 {data.get('date', '')}")
    _blank(w)

    w.writerow(["Rank", "Product Name", "SKU", "Units Sold", "Revenue (KES)"])

    for rank, product in enumerate((data.get("products") or []), start=1):
        w.writerow([
            rank,
            product.get("product_name", ""),
            product.get("sku", ""),
            product.get("units_sold", 0),
            _money(product.get("revenue", 0)),
        ])

    return _make_response(buf, filename, "TOP_PRODUCTS")


# ── Low Stock ─────────────────────────────────────────────────────────────────

def low_stock_to_csv(data: dict[str, Any], filename: str) -> StreamingResponse:
    """
    Flatten low-stock list into a CSV sorted CRITICAL-first (already sorted
    by the router via stock_quantity ASC).
    """
    buf = io.StringIO()
    w   = csv.writer(buf)

    report_date = __import__("datetime").date.today().isoformat()
    _comment(w, f"SMARTLYNX LOW STOCK ALERT \u2500\u2500 {report_date}")
    _blank(w)

    w.writerow([
        "Status",
        "Product Name",
        "SKU",
        "Current Stock",
        "Reorder Level",
        "Units Below Reorder",
    ])

    for item in (data.get("items") or []):
        w.writerow([
            item.get("status", ""),
            item.get("name", ""),
            item.get("sku", ""),
            item.get("current_stock", 0),
            item.get("reorder_level", 0),
            item.get("units_below_reorder", 0),
        ])

    return _make_response(buf, filename, "LOW_STOCK")
