"""
pdf_service.py — SmartlynX PDF generation business logic

Service layer for generating PDFs from domain models:
  • PurchaseOrder → PDF
  • GoodsReceivedNote → PDF
  • Reports (Z-Tape, Weekly, VAT, Top Products, Low Stock) → PDF

Rules:
  • Reuses existing models (PurchaseOrder, GoodsReceivedNote, Report dicts).
  • Zero duplicate data logic — sources from same schemas as JSON endpoints.
  • Handles currency formatting and timezone awareness.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional
from decimal import Decimal

from app.core.pdf_generator import (
    build_store_header,
    build_document_info,
    build_section_header,
    build_two_column_info_table,
    build_items_table,
    build_totals_section,
    build_footer,
    create_pdf_document,
    format_currency,
)

logger = logging.getLogger("smartlynx.pdf_service")


# ── Purchase Order PDF ────────────────────────────────────────────────────────

def generate_po_pdf(
    po_dict: dict[str, Any],
    store_name: str,
    store_location: str,
    supplier_payment_terms: Optional[str] = None,
) -> bytes:
    """
    Generate a PDF from a Purchase Order dictionary (as returned by POOut schema).
    
    Args:
        po_dict: Dictionary containing PO data (id, po_number, subtotal, tax_amount,
                total_amount, currency, status, order_date, expected_date, items, etc.)
        store_name: Store name for header
        store_location: Store location for header
        supplier_payment_terms: Optional payment terms (displayed on PDF)
    
    Returns:
        PDF document as bytes.
    """
    elements = []
    
    # Header
    elements.extend(build_store_header(store_name, store_location, "Purchase Order"))
    
    # Document info
    additional_fields = {
        "Status": po_dict.get("status", "DRAFT").upper(),
        "Expected Delivery": po_dict.get("expected_date", "N/A"),
    }
    elements.extend(build_document_info(
        "PURCHASE ORDER",
        po_dict.get("po_number", "N/A"),
        po_dict.get("order_date", datetime.now()),
        additional_fields=additional_fields,
    ))
    
    # Supplier details
    elements.extend(build_section_header("SUPPLIER DETAILS"))
    # Handle both old nested structure and new flat structure
    supplier = po_dict.get("supplier", {})
    supplier_name = supplier.get("supplier_name") if supplier else None
    supplier_name = supplier_name or po_dict.get("supplier_name", "N/A")
    contact_person = supplier.get("contact_person", "N/A") if supplier else "N/A"
    email = supplier.get("email", "N/A") if supplier else "N/A"
    phone = supplier.get("phone_number", "N/A") if supplier else "N/A"
    
    supplier_details = [
        ("Supplier Name", supplier_name),
        ("Contact Person", contact_person),
        ("Email", email),
        ("Phone", phone),
    ]
    # Handle both old "creator" and new "created_by" fields
    creator_field = po_dict.get("creator", {})
    created_by_name = creator_field.get("display_name") if isinstance(creator_field, dict) else "N/A"
    created_by_name = created_by_name or "N/A"
    
    payment_terms_info = [
        ("Payment Terms", supplier_payment_terms or "To be agreed upon"),
        ("Currency", po_dict.get("currency", "KES")),
        ("Created By", created_by_name),
        ("Notes", po_dict.get("notes", "None")),
    ]
    elements.extend(build_two_column_info_table(supplier_details, payment_terms_info))
    
    # Items table
    elements.extend(build_section_header("ITEMS"))
    items_rows = []
    for item in po_dict.get("items", []):
        # Handle both old nested "product" structure and new flat structure
        product = item.get("product", {})
        product_name = product.get("product_name") if product else None
        product_name = product_name or item.get("product_name", "N/A")
        
        items_rows.append([
            product_name,
            f"{item.get('ordered_qty_purchase', 0)} {item.get('purchase_unit_type', 'unit')}",
            f"{format_currency(item.get('unit_cost', 0))}",
            f"{format_currency(item.get('line_total', 0))}",
        ])
    
    if items_rows:
        elements.extend(build_items_table(
            headers=["Product", "Quantity", "Unit Price", "Total"],
            rows=items_rows,
            col_widths=[70, 30, 35, 35],
        ))
    
    # Totals section
    totals_data = [
        ("Subtotal", format_currency(po_dict.get("subtotal", 0))),
        ("Tax (16%)", format_currency(po_dict.get("tax_amount", 0))),
        ("Total Amount", format_currency(po_dict.get("total_amount", 0))),
    ]
    elements.extend(build_totals_section(totals_data))
    
    # Footer
    footer_info = f"{store_name} | {store_location} | PO System"
    elements.extend(build_footer(footer_info, "This is a system-generated document."))
    
    return create_pdf_document(elements)


# ── Goods Received Note PDF ───────────────────────────────────────────────────

def generate_grn_pdf(
    grn_dict: dict[str, Any],
    store_name: str,
    store_location: str,
) -> bytes:
    """
    Generate a PDF from a Goods Received Note dictionary (as returned by GRNOut schema).
    
    Args:
        grn_dict: Dictionary containing GRN data (id, grn_number, received_date, status,
                 items, supplier, purchase_order, etc.)
        store_name: Store name for header
        store_location: Store location for header
    
    Returns:
        PDF document as bytes.
    """
    elements = []
    
    # Header
    elements.extend(build_store_header(store_name, store_location, "Goods Receipt Note"))
    
    # Document info
    po_ref = grn_dict.get("purchase_order", {})
    additional_fields = {
        "Status": grn_dict.get("status", "DRAFT").upper(),
        "PO Reference": po_ref.get("po_number", "Direct Receipt") if po_ref else "Direct Receipt",
    }
    elements.extend(build_document_info(
        "GOODS RECEIVED NOTE (GRN)",
        grn_dict.get("grn_number", "N/A"),
        grn_dict.get("received_date", datetime.now()),
        additional_fields=additional_fields,
    ))
    
    # Supplier & receipt details
    elements.extend(build_section_header("RECEIPT DETAILS"))
    # Handle both old nested structure and new flat structure
    supplier = grn_dict.get("supplier", {})
    supplier_name = supplier.get("supplier_name") if supplier else None
    supplier_name = supplier_name or grn_dict.get("supplier_name", "N/A")
    contact_person = supplier.get("contact_person", "N/A") if supplier else "N/A"
    email = supplier.get("email", "N/A") if supplier else "N/A"
    
    supplier_info = [
        ("Supplier", supplier_name),
        ("Contact", contact_person),
        ("Email", email),
    ]
    
    # Handle receiver/checker - support both nested and direct fields
    receiver_field = grn_dict.get("receiver", {})
    receiver_name = receiver_field.get("display_name") if isinstance(receiver_field, dict) else "N/A"
    receiver_name = receiver_name or "N/A"
    
    checker_field = grn_dict.get("checker", {})
    checker_name = checker_field.get("display_name") if isinstance(checker_field, dict) else "N/A"
    checker_name = checker_name or "N/A"
    
    receipt_info = [
        ("Received By", receiver_name),
        ("Checked By", checker_name),
        ("Supplier Invoice #", grn_dict.get("supplier_invoice_number", "N/A")),
        ("Delivery Note #", grn_dict.get("supplier_delivery_note", "N/A")),
    ]
    elements.extend(build_two_column_info_table(supplier_info, receipt_info))
    
    # Items received
    elements.extend(build_section_header("ITEMS RECEIVED"))
    items_rows = []
    for item in grn_dict.get("items", []):
        # Handle both old nested "product" structure and new flat structure
        product = item.get("product", {})
        product_name = product.get("product_name") if product else None
        product_name = product_name or item.get("product_name", "N/A")
        
        items_rows.append([
            product_name,
            f"{item.get('received_qty_purchase', 0)} {item.get('purchase_unit_type', 'unit')}",
            str(item.get("received_qty_base", 0)),
            str(item.get("damaged_qty_base", 0)),
            str(item.get("rejected_qty_base", 0)),
            str(item.get("accepted_qty_base", 0)),
        ])
    
    if items_rows:
        elements.extend(build_items_table(
            headers=["Product", "Qty (purc.)", "Received", "Damaged", "Rejected", "Accepted"],
            rows=items_rows,
            col_widths=[40, 25, 20, 20, 20, 20],
        ))
    
    # Batch info section (if available)
    batch_items = [item for item in grn_dict.get("items", []) if item.get("batch_number")]
    if batch_items:
        elements.extend(build_section_header("BATCH & EXPIRY TRACKING"))
        batch_rows = []
        for item in batch_items:
            # Handle both old nested and new flat structure
            product = item.get("product", {})
            product_name = product.get("product_name") if product else None
            product_name = product_name or item.get("product_name", "N/A")
            
            batch_rows.append([
                product_name,
                item.get("batch_number", "N/A"),
                item.get("expiry_date", "N/A"),
            ])
        elements.extend(build_items_table(
            headers=["Product", "Batch #", "Expiry Date"],
            rows=batch_rows,
            col_widths=[60, 40, 40],
        ))
    
    # Footer
    footer_info = f"{store_name} | {store_location} | GRN System"
    elements.extend(build_footer(footer_info, "This receipt confirms goods received. Please verify quantity and quality."))
    
    return create_pdf_document(elements)


# ── Report PDFs ───────────────────────────────────────────────────────────────

def generate_report_pdf(
    report_type: str,  # 'z_tape', 'weekly', 'vat', 'top_products', 'low_stock'
    report_dict: dict[str, Any],
    store_name: str,
    store_location: str,
) -> bytes:
    """
    Generate a PDF from a Report dictionary (as returned by reports endpoints).
    
    Args:
        report_type: One of 'z_tape', 'weekly', 'vat', 'top_products', 'low_stock'
        report_dict: Dictionary containing report data
        store_name: Store name for header
        store_location: Store location for header
    
    Returns:
        PDF document as bytes.
    """
    elements = []
    
    # Map report type to human-readable title
    report_titles = {
        "z_tape": "Z-Tape Report (Daily Sales Summary)",
        "weekly": "Weekly Sales Report",
        "vat": "VAT Report (Monthly)",
        "top_products": "Top Products Report",
        "low_stock": "Low Stock Alert Report",
    }
    report_title = report_titles.get(report_type, "Report")
    
    # Header
    elements.extend(build_store_header(store_name, store_location, report_title))
    
    # Document info
    report_date = report_dict.get("report_date") or report_dict.get("transaction_date") or datetime.now().date()
    elements.extend(build_document_info(
        report_title.upper(),
        f"Report-{report_type.upper()}-{report_date}",
        report_date if isinstance(report_date, datetime) else datetime.combine(report_date, datetime.min.time()),
    ))
    
    # Report-specific content
    if report_type == "z_tape":
        _add_z_tape_content(elements, report_dict)
    elif report_type == "weekly":
        _add_weekly_content(elements, report_dict)
    elif report_type == "vat":
        _add_vat_content(elements, report_dict)
    elif report_type == "top_products":
        _add_top_products_content(elements, report_dict)
    elif report_type == "low_stock":
        _add_low_stock_content(elements, report_dict)
    
    # Footer
    footer_info = f"{store_name} | {store_location} | Report System"
    elements.extend(build_footer(footer_info, f"Report type: {report_title}"))
    
    return create_pdf_document(elements)


def _add_z_tape_content(elements: List, report_dict: dict[str, Any]) -> None:
    """Add Z-Tape specific content to elements list."""
    elements.extend(build_section_header("SALES SUMMARY"))
    
    # Summary metrics
    summary_rows = [
        ["Total Transactions", str(report_dict.get("transaction_count", 0))],
        ["Gross Sales", f"{format_currency(report_dict.get('gross_sales', 0))} KES"],
        ["VAT Collected", f"{format_currency(report_dict.get('vat_collected', 0))} KES"],
        ["Net Sales (ex. VAT)", f"{format_currency(report_dict.get('net_sales_ex_vat', 0))} KES"],
    ]
    elements.extend(build_items_table(
        headers=["Metric", "Value"],
        rows=summary_rows,
        col_widths=[80, 90],
    ))
    
    # By payment method
    payment_methods = report_dict.get("by_payment_method", [])
    if payment_methods:
        elements.extend(build_section_header("SALES BY PAYMENT METHOD"))
        payment_rows = [
            [pm.get("payment_method", "N/A"), str(pm.get("transaction_count", 0)), f"{format_currency(pm.get('total_amount', 0))} KES"]
            for pm in payment_methods
        ]
        elements.extend(build_items_table(
            headers=["Payment Method", "Transactions", "Amount"],
            rows=payment_rows,
            col_widths=[60, 40, 70],
        ))
    
    # By cashier
    cashiers = report_dict.get("cashier_breakdown", [])
    if cashiers:
        elements.extend(build_section_header("SALES BY CASHIER"))
        cashier_rows = [
            [c.get("cashier_name", "N/A"), str(c.get("transaction_count", 0)), f"{format_currency(c.get('total_amount', 0))} KES"]
            for c in cashiers
        ]
        elements.extend(build_items_table(
            headers=["Cashier", "Transactions", "Amount"],
            rows=cashier_rows,
            col_widths=[60, 40, 70],
        ))


def _add_weekly_content(elements: List, report_dict: dict[str, Any]) -> None:
    """Add Weekly sales content to elements list."""
    elements.extend(build_section_header("DAILY BREAKDOWN"))
    
    daily_data = report_dict.get("daily_breakdown", [])
    if daily_data:
        daily_rows = [
            [d.get("date", "N/A"), str(d.get("transactions", 0)), f"{format_currency(d.get('sales', 0))} KES"]
            for d in daily_data
        ]
        elements.extend(build_items_table(
            headers=["Date", "Transactions", "Sales"],
            rows=daily_rows,
            col_widths=[50, 40, 80],
        ))
    
    # Summary
    elements.extend(build_section_header("WEEKLY SUMMARY"))
    summary_rows = [
        ["Total Transactions", str(report_dict.get("total_transactions", 0))],
        ["Total Sales", f"{format_currency(report_dict.get('total_sales', 0))} KES"],
        ["Average Daily Sales", f"{format_currency(report_dict.get('average_sales_per_day', 0))} KES"],
    ]
    elements.extend(build_items_table(
        headers=["Metric", "Value"],
        rows=summary_rows,
        col_widths=[80, 90],
    ))


def _add_vat_content(elements: List, report_dict: dict[str, Any]) -> None:
    """Add VAT report content to elements list."""
    elements.extend(build_section_header("VAT SUMMARY"))
    
    # Summary metrics
    summary_rows = [
        ["Total Sales (Gross)", f"{format_currency(report_dict.get('gross_sales', 0))} KES"],
        ["VAT Rate", f"{report_dict.get('vat_rate', 16)}%"],
        ["VAT Collected", f"{format_currency(report_dict.get('vat_collected', 0))} KES"],
        ["Net Sales (ex. VAT)", f"{format_currency(report_dict.get('net_sales_ex_vat', 0))} KES"],
    ]
    elements.extend(build_items_table(
        headers=["Item", "Amount"],
        rows=summary_rows,
        col_widths=[80, 90],
    ))
    
    # By category
    by_category = report_dict.get("by_category", [])
    if by_category:
        elements.extend(build_section_header("VAT BY PRODUCT CATEGORY"))
        category_rows = [
            [c.get("category", "N/A"), f"{format_currency(c.get('sales', 0))} KES", f"{format_currency(c.get('vat', 0))} KES"]
            for c in by_category
        ]
        elements.extend(build_items_table(
            headers=["Category", "Sales", "VAT"],
            rows=category_rows,
            col_widths=[50, 60, 60],
        ))


def _add_top_products_content(elements: List, report_dict: dict[str, Any]) -> None:
    """Add Top Products report content to elements list."""
    elements.extend(build_section_header("TOP SELLING PRODUCTS"))
    
    products = report_dict.get("products", [])
    if products:
        product_rows = [
            [p.get("product_name", "N/A"), str(p.get("units_sold", 0)), f"{format_currency(p.get('revenue', 0))} KES"]
            for p in products[:20]  # Top 20 products
        ]
        elements.extend(build_items_table(
            headers=["Product", "Units Sold", "Revenue"],
            rows=product_rows,
            col_widths=[80, 35, 55],
        ))
    
    # Summary
    elements.extend(build_section_header("SUMMARY"))
    summary_rows = [
        ["Total Products Sold", str(len(products))],
        ["Total Revenue from Top Products", f"{format_currency(report_dict.get('total_revenue', 0))} KES"],
    ]
    elements.extend(build_items_table(
        headers=["Metric", "Value"],
        rows=summary_rows,
        col_widths=[80, 90],
    ))


def _add_low_stock_content(elements: List, report_dict: dict[str, Any]) -> None:
    """Add Low Stock alert report content to elements list."""
    elements.extend(build_section_header("LOW STOCK ITEMS"))
    
    items = report_dict.get("items", [])
    if items:
        stock_rows = [
            [i.get("product_name", "N/A"), str(i.get("current_stock", 0)), str(i.get("reorder_level", 0)), str(i.get("min_stock", 0))]
            for i in items
        ]
        elements.extend(build_items_table(
            headers=["Product", "Current Stock", "Reorder Level", "Min Stock"],
            rows=stock_rows,
            col_widths=[60, 35, 35, 35],
        ))
    
    # Summary
    elements.extend(build_section_header("ALERT SUMMARY"))
    summary_rows = [
        ["Items Below Reorder Level", str(len([i for i in items if int(i.get("current_stock", 0)) < int(i.get("reorder_level", 0))]))],
        ["Total Items Scanned", str(len(items))],
        ["Report Generated", datetime.now().strftime("%d %b %Y %H:%M:%S")],
    ]
    elements.extend(build_items_table(
        headers=["Metric", "Value"],
        rows=summary_rows,
        col_widths=[80, 90],
    ))
