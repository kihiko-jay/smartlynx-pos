"""
pdf_generator.py — SmartlynX PDF generation utilities

Core PDF utilities for generating brand-consistent, print-friendly PDFs.

Rules enforced here:
  • Zero business logic — only presentation/formatting.
  • Zero DB access.
  • Reusable styling and page setup.
  • All monetary values: 2 decimal places, KES currency.
  • A4 page size with standard margins.
  • Store branding: name, location, timezone.
"""

from __future__ import annotations

import io
from typing import Any, List, Optional, Tuple
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    Image,
    HRFlowable,
)
from reportlab.pdfgen import canvas
from fastapi.responses import FileResponse, StreamingResponse


# ── Configuration ─────────────────────────────────────────────────────────────

DEFAULT_PAGE_SIZE = A4
DEFAULT_MARGIN = 15 * mm
DEFAULT_FONT_SIZE_NORMAL = 10
DEFAULT_FONT_SIZE_TITLE = 16
DEFAULT_FONT_SIZE_HEADING = 12
DEFAULT_FONT_SIZE_SMALL = 8


# ── Color scheme ──────────────────────────────────────────────────────────────

class Colors:
    """Brand colors for PDFs."""
    PRIMARY = colors.HexColor("#1e40af")      # Professional blue
    SECONDARY = colors.HexColor("#7c3aed")    # Professional purple
    HEADER_BG = colors.HexColor("#f3f4f6")    # Light gray
    TABLE_HEADER_BG = colors.HexColor("#e5e7eb")  # Slightly darker gray
    TEXT_DARK = colors.HexColor("#1f2937")    # Dark gray
    TEXT_LIGHT = colors.HexColor("#6b7280")   # Medium gray
    BORDER = colors.HexColor("#d1d5db")       # Border gray
    SUCCESS = colors.HexColor("#10b981")      # Green
    WARNING = colors.HexColor("#f59e0b")      # Amber
    ERROR = colors.HexColor("#ef4444")        # Red


# ── Style definitions (with cache to prevent duplicates) ─────────────────────

_styles_cache = None


def get_styles() -> dict:
    """
    Return standard ReportLab styles with Smartlynx branding.
    Styles are cached to prevent duplicate definition errors.
    
    Returns:
        Dictionary of paragraph styles keyed by name.
    """
    global _styles_cache
    if _styles_cache is None:
        _styles_cache = getSampleStyleSheet()
        
        # Define custom styles only if they don't exist
        custom_styles = [
            ('CustomTitle', 'Heading1', DEFAULT_FONT_SIZE_TITLE, Colors.PRIMARY, 1, 4),
            ('DocHeader', 'Heading2', DEFAULT_FONT_SIZE_HEADING, Colors.TEXT_DARK, 0, 2),
            ('Metadata', 'Normal', DEFAULT_FONT_SIZE_SMALL, Colors.TEXT_LIGHT, 0, 1),
            ('BodyText', 'Normal', DEFAULT_FONT_SIZE_NORMAL, Colors.TEXT_DARK, 0, 2),
            ('TableHeader', 'Normal', DEFAULT_FONT_SIZE_NORMAL, Colors.TEXT_DARK, 0, 0),
            ('Footer', 'Normal', DEFAULT_FONT_SIZE_SMALL, Colors.TEXT_LIGHT, 0, 1),
        ]
        
        for style_name, parent_name, font_size, text_color, alignment, space_after in custom_styles:
            if style_name not in _styles_cache:
                _styles_cache.add(ParagraphStyle(
                    name=style_name,
                    parent=_styles_cache[parent_name],
                    fontSize=font_size,
                    textColor=text_color,
                    alignment=alignment,
                    spaceAfter=space_after,
                    fontName='Helvetica' if not style_name.startswith('CustomTitle') else 'Helvetica-Bold',
                ))
            
            # Also set bold version for TableHeader
            if style_name == 'TableHeader':
                bold_name = 'TableHeaderBold'
                if bold_name not in _styles_cache:
                    _styles_cache.add(ParagraphStyle(
                        name=bold_name,
                        parent=_styles_cache[parent_name],
                        fontSize=font_size,
                        textColor=text_color,
                        alignment=alignment,
                        spaceAfter=space_after,
                        fontName='Helvetica-Bold',
                    ))
    
    return _styles_cache


# ── PDF Response helpers ──────────────────────────────────────────────────────

def pdf_response(
    pdf_bytes: bytes,
    filename: str,
    download: bool = True,
) -> StreamingResponse:
    """
    Wrap PDF bytes in a StreamingResponse with correct headers.
    
    Args:
        pdf_bytes: Raw PDF document bytes
        filename: Name for the PDF file (sets Content-Disposition)
        download: If True, set attachment mode (user downloads file).
                 If False, set inline mode (browser displays/prints).
    
    Returns:
        StreamingResponse configured for PDF delivery.
    """
    disposition_type = "attachment" if download else "inline"
    
    def _iter():
        yield pdf_bytes
    
    return StreamingResponse(
        _iter(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition_type}; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ── Document header/footer helpers ────────────────────────────────────────────

def build_store_header(
    store_name: str,
    store_location: str,
    addition_info: Optional[str] = None,
) -> List:
    """
    Build document header with store branding.
    
    Args:
        store_name: Name of the store (e.g., "My Smartlynx Store")
        store_location: Location (e.g., "Nairobi, Kenya")
        addition_info: Optional additional info line
    
    Returns:
        List of Platypus elements.
    """
    styles = get_styles()
    elements = []
    
    # Store name
    elements.append(Paragraph(store_name, styles["CustomTitle"]))
    
    # Location
    if store_location:
        elements.append(Paragraph(store_location, styles["Metadata"]))
    
    # Additional info if provided
    if addition_info:
        elements.append(Paragraph(addition_info, styles["Metadata"]))
    
    elements.append(Spacer(1, 4 * mm))
    
    return elements


def build_document_info(
    doc_type: str,  # e.g., "PURCHASE ORDER"
    doc_number: str,  # e.g., "PO-2024-001"
    doc_date: datetime,
    additional_fields: Optional[dict[str, str]] = None,
) -> List:
    """
    Build document metadata section.
    
    Args:
        doc_type: Type of document (e.g., "PURCHASE ORDER")
        doc_number: Unique document identifier
        doc_date: Date the document was created
        additional_fields: Dict of additional label->value pairs
    
    Returns:
        List of Platypus elements.
    """
    styles = get_styles()
    elements = []
    
    # Document type
    elements.append(Paragraph(doc_type, styles["DocHeader"]))
    
    # Document number and date
    doc_info = f"Document ID: <b>{doc_number}</b> | Date: <b>{doc_date.strftime('%d %b %Y')}</b>"
    elements.append(Paragraph(doc_info, styles["Metadata"]))
    
    # Additional fields
    if additional_fields:
        for label, value in additional_fields.items():
            field_text = f"{label}: <b>{value}</b>"
            elements.append(Paragraph(field_text, styles["Metadata"]))
    
    elements.append(Spacer(1, 4 * mm))
    
    return elements


def build_section_header(title: str) -> List:
    """Build a section header (e.g., "SUPPLIER DETAILS", "ITEMS")."""
    styles = get_styles()
    elements = []
    elements.append(Paragraph(title, styles["DocHeader"]))
    elements.append(Spacer(1, 2 * mm))
    return elements


def build_footer(
    store_name: str,
    additional_notes: Optional[str] = None,
) -> List:
    """
    Build document footer.
    
    Args:
        store_name: Store name for copyright info
        additional_notes: Optional disclaimer or notes
    
    Returns:
        List of Platypus elements.
    """
    styles = get_styles()
    elements = []
    
    elements.append(Spacer(1, 6 * mm))
    
    # Horizontal line
    elements.append(HRFlowable(width="100%", thickness=0.5, color=Colors.BORDER))
    
    # Store info
    elements.append(Paragraph(f"{store_name} | Smartlynx POS System", styles["Footer"]))
    
    # Additional notes if provided
    if additional_notes:
        elements.append(Paragraph(additional_notes, styles["Footer"]))
    
    # Generation timestamp
    now = datetime.now().strftime("%d %b %Y %H:%M")
    elements.append(Paragraph(f"Generated on {now}", styles["Footer"]))
    
    return elements


# ── Table builders ───────────────────────────────────────────────────────────

def build_two_column_info_table(
    left_label_value_pairs: List[Tuple[str, str]],
    right_label_value_pairs: List[Tuple[str, str]],
) -> List:
    """
    Build a two-column side-by-side information table.
    
    Args:
        left_label_value_pairs: List of (label, value) tuples for left column
        right_label_value_pairs: List of (label, value) tuples for right column
    
    Returns:
        List with Table element.
    """
    styles = get_styles()
    
    # Pad columns to same height
    max_rows = max(len(left_label_value_pairs), len(right_label_value_pairs))
    left_pairs = left_label_value_pairs + [("", "")] * (max_rows - len(left_label_value_pairs))
    right_pairs = right_label_value_pairs + [("", "")] * (max_rows - len(right_label_value_pairs))
    
    rows = []
    for (left_label, left_value), (right_label, right_value) in zip(left_pairs, right_pairs):
        left_cell = Paragraph(f"<b>{left_label}</b><br/>{left_value}", styles["BodyText"])
        right_cell = Paragraph(f"<b>{right_label}</b><br/>{right_value}", styles["BodyText"])
        rows.append([left_cell, right_cell])
    
    table = Table(
        rows,
        colWidths=[85 * mm, 85 * mm],
        rowHeights=None,
    )
    
    table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, Colors.BORDER),
    ]))
    
    return [table, Spacer(1, 4 * mm)]


def build_items_table(
    headers: List[str],
    rows: List[List],
    col_widths: Optional[List[float]] = None,
) -> List:
    """
    Build a standard items/lines table with header row.
    
    Args:
        headers: List of column headers
        rows: List of rows, each row is a list matching header count
        col_widths: Optional list of column widths in mm
    
    Returns:
        List with Table element.
    """
    styles = get_styles()
    
    # Use sensible defaults if not provided
    if not col_widths:
        available_width = 170 * mm  # Page width minus margins
        col_widths = [available_width / len(headers)] * len(headers)
    else:
        col_widths = [w * mm for w in col_widths]
    
    # Build header row
    header_cells = [Paragraph(f"<b>{h}</b>", styles["TableHeaderBold"]) for h in headers]
    
    # Build data rows
    data_rows = [[Paragraph(str(cell), styles["BodyText"]) for cell in row] for row in rows]
    
    all_rows = [header_cells] + data_rows
    
    table = Table(all_rows, colWidths=col_widths)
    
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), Colors.TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), Colors.TEXT_DARK),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, Colors.BORDER),
        ("ALIGN", (0, 1), (-1, -1), "LEFT"),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 1), (-1, -1), 4),
        ("RIGHTPADDING", (0, 1), (-1, -1), 4),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, Colors.BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, Colors.HEADER_BG]),
    ]))
    
    return [table, Spacer(1, 4 * mm)]


def build_totals_section(
    items: List[Tuple[str, str]],
) -> List:
    """
    Build a right-aligned totals section.
    
    Args:
        items: List of (label, value) tuples e.g., [("Subtotal", "10,000.00"), ...]
    
    Returns:
        List with Table element.
    """
    styles = get_styles()
    
    rows = []
    for label, value in items:
        is_total = "total" in label.lower()
        color = Colors.PRIMARY if is_total else Colors.TEXT_DARK
        
        label_cell = Paragraph(f"<font color='{color}'><b>{label}</b></font>", styles["BodyText"])
        value_cell = Paragraph(
            f"<font color='{color}'><b>{value}</b></font>",
            styles["BodyText"]
        )
        rows.append([label_cell, value_cell])
    
    table = Table(rows, colWidths=[100 * mm, 70 * mm])
    
    table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    
    # Add bottom border if there are items
    if items:
        table.setStyle(TableStyle([
            ("LINEBELOW", (0, -1), (-1, -1), 1, Colors.PRIMARY),
        ]))
    
    return [Spacer(1, 30 * mm), table, Spacer(1, 6 * mm)]


# ── Main PDF document builder ────────────────────────────────────────────────

def create_pdf_document(
    elements: List,
    page_size=DEFAULT_PAGE_SIZE,
    margin=DEFAULT_MARGIN,
) -> bytes:
    """
    Build a complete Platypus PDF document from a list of elements.
    
    Args:
        elements: List of Platypus elements (Paragraphs, Tables, Spacers, etc.)
        page_size: Page size (default: A4)
        margin: Page margins in reportlab units (default: 15mm)
    
    Returns:
        PDF document as bytes.
    """
    pdf_buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=page_size,
        topMargin=margin,
        bottomMargin=margin,
        leftMargin=margin,
        rightMargin=margin,
        title="Smartlynx Document",
    )
    
    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def format_currency(value: float | int) -> str:
    """Format a number as KES currency (e.g., 'KES 1,234.56')."""
    return f"KES {value:,.2f}"