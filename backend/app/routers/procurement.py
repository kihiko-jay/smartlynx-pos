"""
Procurement router — Purchase Orders, GRNs, Invoice Matching, Packaging.

Permission model:
  - manager / admin : full create / approve / post access
  - supervisor      : create POs and GRNs, cannot approve
  - cashier         : read-only (view POs and GRNs)
  - platform_owner  : full access
"""

import logging
from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import (
    get_db, get_current_employee,
    require_cashier, require_supervisor, require_manager,
)
from app.core.pdf_generator import pdf_response
from app.models.employee import Employee
from app.schemas.procurement import (
    PackagingCreate, PackagingOut,
    POCreate, POUpdate, POOut, POSummary,
    GRNCreate, GRNOut, GRNSummary,
    InvoiceMatchCreate, InvoiceMatchResolve, InvoiceMatchOut,
)
from app.services import procurement as svc
from app.models.procurement import SupplierPayment
from app.services.accounting import post_supplier_payment, get_supplier_statement, get_ap_aging
from pydantic import BaseModel, Field
from decimal import Decimal
import uuid
from app.services import pdf_service

logger = logging.getLogger("dukapos.procurement")
router = APIRouter(prefix="/procurement", tags=["Procurement"])


class SupplierPaymentCreate(BaseModel):
    supplier_id: int
    payment_date: date
    amount: Decimal = Field(..., gt=0)
    payment_method: str
    reference: Optional[str] = None
    notes: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# ProductPackaging
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/products/{product_id}/packaging", response_model=List[PackagingOut],
            dependencies=[Depends(require_cashier)])
def list_product_packaging(
    product_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    from app.models.procurement import ProductPackaging
    rows = db.query(ProductPackaging).filter(
        ProductPackaging.product_id == product_id,
        ProductPackaging.store_id   == current.store_id,
    ).all()
    return rows


@router.post("/products/{product_id}/packaging", response_model=PackagingOut,
             dependencies=[Depends(require_manager)])
def upsert_product_packaging(
    product_id: int,
    payload: PackagingCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    pkg = svc.upsert_packaging(
        db, product_id, current.store_id,
        payload.purchase_unit_type, payload.units_per_purchase,
        payload.label, payload.is_default,
    )
    db.commit()
    db.refresh(pkg)
    return pkg


# ─────────────────────────────────────────────────────────────────────────────
# Purchase Orders
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/purchase-orders", response_model=List[POSummary],
            dependencies=[Depends(require_cashier)])
def list_purchase_orders(
    supplier_id: Optional[int] = None,
    status:      Optional[str] = None,
    skip:  int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    pos = svc.list_pos(db, current.store_id, supplier_id, status, skip, limit)
    out = []
    for po in pos:
        supplier_name = po.supplier.name if po.supplier else None
        out.append(POSummary(
            id            = po.id,
            po_number     = po.po_number,
            supplier_name = supplier_name,
            status        = po.status.value,
            order_date    = po.order_date,
            expected_date = po.expected_date,
            total_amount  = po.total_amount,
            created_at    = po.created_at,
            item_count    = len(po.items),
        ))
    return out


@router.post("/purchase-orders", response_model=POOut,
             dependencies=[Depends(require_supervisor)])
def create_purchase_order(
    payload: POCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        po = svc.create_po(db, payload, current)
        db.commit()
        db.refresh(po)
        return _po_out(po)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        logger.error("PO create failed: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to create purchase order") from exc


@router.get("/purchase-orders/{po_id}", response_model=POOut,
            dependencies=[Depends(require_cashier)])
def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    po = svc._get_po(db, po_id, current.store_id)
    return _po_out(po)


@router.patch("/purchase-orders/{po_id}", response_model=POOut,
              dependencies=[Depends(require_supervisor)])
def update_purchase_order(
    po_id: int,
    payload: POUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        po = svc.update_po(db, po_id, payload, current)
        db.commit(); db.refresh(po)
        return _po_out(po)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Failed to update PO") from exc


@router.post("/purchase-orders/{po_id}/submit", response_model=POOut,
             dependencies=[Depends(require_supervisor)])
def submit_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        po = svc.submit_po(db, po_id, current)
        db.commit(); db.refresh(po)
        return _po_out(po)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Failed to submit PO") from exc


@router.post("/purchase-orders/{po_id}/approve", response_model=POOut,
             dependencies=[Depends(require_manager)])
def approve_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        po = svc.approve_po(db, po_id, current)
        db.commit(); db.refresh(po)
        return _po_out(po)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Failed to approve PO") from exc


@router.post("/purchase-orders/{po_id}/cancel", response_model=POOut,
             dependencies=[Depends(require_manager)])
def cancel_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        po = svc.cancel_po(db, po_id, current)
        db.commit(); db.refresh(po)
        return _po_out(po)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Failed to cancel PO") from exc


@router.get("/purchase-orders/{po_id}/pdf",
            dependencies=[Depends(require_cashier)])
def get_purchase_order_pdf(
    po_id: int,
    download: bool = Query(True, description="If true, download as file; if false, display in browser"),
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """
    Generate and return a PO as PDF.
    
    Query parameters:
      download=true  (default)  — User downloads the PDF file
      download=false            — Browser displays/prints the PDF
    """
   # Add to app/services/procurement.py
def get_po(db, po_id, store_id):
    """Get purchase order by ID for a specific store."""
    return _get_po(db, po_id, store_id)
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    # Convert ORM model to dict for PDF service
    po_dict = _po_out(po)  # Reuse existing _po_out function
    
    # Generate PDF
    pdf_bytes = pdf_service.generate_po_pdf(
        po_dict,
        store_name=settings.STORE_NAME,
        store_location=settings.STORE_LOCATION,
        supplier_payment_terms="Net 14 days",  # Default; could be enhanced with supplier-specific terms
    )
    
    filename = f"PO-{po.po_number}.pdf"
    return pdf_response(pdf_bytes, filename, download=download)


@router.post("/purchase-orders/{po_id}/send-email",
             dependencies=[Depends(require_manager)])
def send_purchase_order_email(
    po_id: int,
    recipient_email: str = Query(..., description="Supplier email address"),
    message: str = Query("", description="Optional custom message"),
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """
    Send a Purchase Order to supplier via email with PDF attachment.
    
    Only available for POs in APPROVED status or later.
    """
    from app.services import email as email_svc
    
    po = svc.get_po(db, po_id, current.store_id)
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    # Only send approved or later POs
    if po.status not in [po.status.APPROVED, po.status.PARTIALLY_RECEIVED, 
                          po.status.FULLY_RECEIVED, po.status.CLOSED]:
        raise HTTPException(
            status_code=400,
            detail=f"Can only email approved POs. Current status: {po.status.value}"
        )
    
    # Validate email format
    if "@" not in recipient_email or "." not in recipient_email.split("@")[1]:
        raise HTTPException(status_code=400, detail="Invalid email address")
    
    try:
        # Generate PDF
        po_dict = _po_out(po)
        pdf_bytes = pdf_service.generate_po_pdf(
            po_dict,
            store_name=settings.STORE_NAME,
            store_location=settings.STORE_LOCATION,
            supplier_payment_terms="Net 14 days",
        )
        
        # Send email
        supplier = po.supplier
        supplier_name = supplier.name if supplier else "Valued Supplier"
        
        email_svc.send_purchase_order_email(
            to_email=recipient_email,
            recipient_name=supplier_name,
            po_number=po.po_number,
            pdf_bytes=pdf_bytes,
            pdf_filename=f"PO-{po.po_number}.pdf",
            supplier_name=supplier_name,
            message=message or f"Please find attached PO {po.po_number} from {settings.STORE_NAME}.",
        )
        
        return {
            "status": "success",
            "message": f"PO {po.po_number} sent to {recipient_email}",
            "po_id": po.id,
            "po_number": po.po_number,
        }
    
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Email service unavailable: {str(e)}")
    except Exception as e:
        logger.exception("Failed to send PO email: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# GRN
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/grns", response_model=List[GRNSummary],
            dependencies=[Depends(require_cashier)])
def list_grns(
    supplier_id: Optional[int] = None,
    po_id:       Optional[int] = None,
    status:      Optional[str] = None,
    skip:  int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    grns = svc.list_grns(db, current.store_id, supplier_id, po_id, status, skip, limit)
    out = []
    for grn in grns:
        po_number = grn.purchase_order.po_number if grn.purchase_order else None
        out.append(GRNSummary(
            id                = grn.id,
            grn_number        = grn.grn_number,
            supplier_name     = grn.supplier.name if grn.supplier else None,
            purchase_order_id = grn.purchase_order_id,
            po_number         = po_number,
            status            = grn.status.value,
            received_date     = grn.received_date,
            created_at        = grn.created_at,
            item_count        = len(grn.items),
        ))
    return out


@router.post("/grns", response_model=GRNOut,
             dependencies=[Depends(require_supervisor)])
def create_grn(
    payload: GRNCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        grn = svc.create_grn(db, payload, current)
        db.commit(); db.refresh(grn)
        return _grn_out(grn)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        logger.error("GRN create failed: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to create GRN") from exc


@router.get("/grns/{grn_id}", response_model=GRNOut,
            dependencies=[Depends(require_cashier)])
def get_grn(
    grn_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    from app.models.procurement import GoodsReceivedNote
    grn = db.query(GoodsReceivedNote).filter(GoodsReceivedNote.id == grn_id).first()
    if not grn:
        raise HTTPException(404, "GRN not found")
    if grn.store_id != current.store_id:
        raise HTTPException(403, "Access denied")
    return _grn_out(grn)


@router.post("/grns/{grn_id}/post", response_model=GRNOut,
             dependencies=[Depends(require_manager)])
def post_grn(
    grn_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        grn = svc.post_grn(db, grn_id, current)
        db.commit(); db.refresh(grn)
        return _grn_out(grn)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        logger.error("GRN post failed: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to post GRN") from exc


@router.post("/grns/{grn_id}/cancel", response_model=GRNOut,
             dependencies=[Depends(require_manager)])
def cancel_grn(
    grn_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        grn = svc.cancel_grn(db, grn_id, current)
        db.commit(); db.refresh(grn)
        return _grn_out(grn)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Failed to cancel GRN") from exc


@router.get("/grns/{grn_id}/pdf",
            dependencies=[Depends(require_cashier)])
def get_grn_pdf(
    grn_id: int,
    download: bool = Query(True, description="If true, download as file; if false, display in browser"),
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """
    Generate and return a GRN as PDF.
    
    Query parameters:
      download=true  (default)  — User downloads the PDF file
      download=false            — Browser displays/prints the PDF
    """
    from app.models.procurement import GoodsReceivedNote
    grn = db.query(GoodsReceivedNote).filter(GoodsReceivedNote.id == grn_id).first()
    if not grn:
        raise HTTPException(status_code=404, detail="GRN not found")
    if grn.store_id != current.store_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Convert ORM model to dict for PDF service
    grn_dict = _grn_out(grn)
    
    # Generate PDF
    pdf_bytes = pdf_service.generate_grn_pdf(
        grn_dict,
        store_name=settings.STORE_NAME,
        store_location=settings.STORE_LOCATION,
    )
    
    filename = f"GRN-{grn.grn_number}.pdf"
    return pdf_response(pdf_bytes, filename, download=download)


# ─────────────────────────────────────────────────────────────────────────────
# Invoice Matching
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/invoice-matches", response_model=List[InvoiceMatchOut],
            dependencies=[Depends(require_cashier)])
def list_invoice_matches(
    supplier_id: Optional[int] = None,
    status:      Optional[str] = None,
    skip:  int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    from app.models.procurement import SupplierInvoiceMatch
    q = db.query(SupplierInvoiceMatch).filter(
        SupplierInvoiceMatch.store_id == current.store_id
    )
    if supplier_id:
        q = q.filter(SupplierInvoiceMatch.supplier_id == supplier_id)
    if status:
        q = q.filter(SupplierInvoiceMatch.matched_status == status)
    matches = q.order_by(SupplierInvoiceMatch.created_at.desc()).offset(skip).limit(limit).all()
    return [_match_out(m) for m in matches]


@router.post("/invoice-matches", response_model=InvoiceMatchOut,
             dependencies=[Depends(require_manager)])
def create_invoice_match(
    payload: InvoiceMatchCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        match = svc.create_invoice_match(db, payload, current)
        db.commit(); db.refresh(match)
        return _match_out(match)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Failed to create invoice match") from exc


@router.get("/invoice-matches/{match_id}", response_model=InvoiceMatchOut,
            dependencies=[Depends(require_cashier)])
def get_invoice_match(
    match_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    from app.models.procurement import SupplierInvoiceMatch
    m = db.query(SupplierInvoiceMatch).filter(SupplierInvoiceMatch.id == match_id).first()
    if not m:
        raise HTTPException(404, "Invoice match not found")
    if m.store_id != current.store_id:
        raise HTTPException(403, "Access denied")
    return _match_out(m)


@router.patch("/invoice-matches/{match_id}/resolve", response_model=InvoiceMatchOut,
              dependencies=[Depends(require_manager)])
def resolve_invoice_match(
    match_id: int,
    payload: InvoiceMatchResolve,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    try:
        match = svc.resolve_invoice_match(db, match_id, payload, current)
        db.commit(); db.refresh(match)
        return _match_out(match)
    except HTTPException:
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Failed to resolve invoice match") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/reports/received", dependencies=[Depends(require_manager)])
def report_received(
    date_from:   date,
    date_to:     date,
    supplier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    grns = svc.report_received_by_date(db, current.store_id, date_from, date_to)
    if supplier_id:
        grns = [g for g in grns if g.supplier_id == supplier_id]
    return {
        "period": {"from": str(date_from), "to": str(date_to)},
        "grn_count": len(grns),
        "grns": [_grn_out(g) for g in grns],
    }


@router.get("/reports/open-pos", dependencies=[Depends(require_manager)])
def report_open_pos(
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    pos = svc.report_open_pos(db, current.store_id)
    return {
        "count": len(pos),
        "purchase_orders": [_po_out(po) for po in pos],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Response helpers (enrich ORM objects → schema)
# ─────────────────────────────────────────────────────────────────────────────

def _po_out(po) -> POOut:
    items = []
    for item in po.items:
        p = item.product
        items.append(POOut.__fields__  # access via dict to stay flexible
                     and POSummary)    # placeholder — use dict below
    item_list = []
    for item in po.items:
        p = item.product
        item_list.append({
            "id":                   item.id,
            "product_id":           item.product_id,
            "product_name":         p.name if p else None,
            "product_sku":          p.sku  if p else None,
            "ordered_qty_purchase": item.ordered_qty_purchase,
            "purchase_unit_type":   item.purchase_unit_type.value
                                    if hasattr(item.purchase_unit_type, "value")
                                    else item.purchase_unit_type,
            "units_per_purchase":   item.units_per_purchase,
            "ordered_qty_base":     item.ordered_qty_base,
            "unit_cost":            item.unit_cost,
            "line_total":           item.line_total,
            "received_qty_base":    item.received_qty_base,
            "damaged_qty_base":     item.damaged_qty_base,
            "rejected_qty_base":    item.rejected_qty_base,
            "remaining_qty_base":   item.remaining_qty_base,
            "accepted_qty_base":    item.accepted_qty_base,
            "notes":                item.notes,
        })
    return {
        "id":            po.id,
        "store_id":      po.store_id,
        "supplier_id":   po.supplier_id,
        "supplier_name": po.supplier.name if po.supplier else None,
        "po_number":     po.po_number,
        "status":        po.status.value if hasattr(po.status, "value") else po.status,
        "order_date":    po.order_date,
        "expected_date": po.expected_date,
        "notes":         po.notes,
        "currency":      po.currency,
        "subtotal":      po.subtotal,
        "tax_amount":    po.tax_amount,
        "total_amount":  po.total_amount,
        "created_by":    po.created_by,
        "approved_by":   po.approved_by,
        "approved_at":   po.approved_at,
        "created_at":    po.created_at,
        "items":         item_list,
    }


def _grn_out(grn) -> dict:
    item_list = []
    for item in grn.items:
        p = item.product
        item_list.append({
            "id":                    item.id,
            "product_id":            item.product_id,
            "product_name":          p.name if p else None,
            "product_sku":           p.sku  if p else None,
            "purchase_order_item_id": item.purchase_order_item_id,
            "received_qty_purchase": item.received_qty_purchase,
            "purchase_unit_type":    item.purchase_unit_type.value
                                     if hasattr(item.purchase_unit_type, "value")
                                     else item.purchase_unit_type,
            "units_per_purchase":    item.units_per_purchase,
            "received_qty_base":     item.received_qty_base,
            "damaged_qty_base":      item.damaged_qty_base,
            "rejected_qty_base":     item.rejected_qty_base,
            "accepted_qty_base":     item.accepted_qty_base,
            "cost_per_base_unit":    item.cost_per_base_unit,
            "line_total":            item.line_total,
            "batch_number":          item.batch_number,
            "expiry_date":           item.expiry_date,
            "notes":                 item.notes,
        })
    po_number = grn.purchase_order.po_number if grn.purchase_order else None
    return {
        "id":                      grn.id,
        "store_id":                grn.store_id,
        "supplier_id":             grn.supplier_id,
        "supplier_name":           grn.supplier.name if grn.supplier else None,
        "purchase_order_id":       grn.purchase_order_id,
        "po_number":               po_number,
        "grn_number":              grn.grn_number,
        "status":                  grn.status.value if hasattr(grn.status, "value") else grn.status,
        "received_date":           grn.received_date,
        "supplier_invoice_number": grn.supplier_invoice_number,
        "supplier_delivery_note":  grn.supplier_delivery_note,
        "notes":                   grn.notes,
        "received_by":             grn.received_by,
        "checked_by":              grn.checked_by,
        "posted_at":               grn.posted_at,
        "created_at":              grn.created_at,
        "items":                   item_list,
    }


def _match_out(m) -> dict:
    return {
        "id":                 m.id,
        "store_id":           m.store_id,
        "supplier_id":        m.supplier_id,
        "supplier_name":      m.supplier.name if m.supplier else None,
        "purchase_order_id":  m.purchase_order_id,
        "po_number":          m.purchase_order.po_number if m.purchase_order else None,
        "grn_id":             m.grn_id,
        "grn_number":         m.grn.grn_number if m.grn else None,
        "invoice_number":     m.invoice_number,
        "invoice_date":       m.invoice_date,
        "invoice_total":      m.invoice_total,
        "matched_status":     m.matched_status.value if hasattr(m.matched_status, "value") else m.matched_status,
        "discrepancy_notes":  m.discrepancy_notes,
        "variance_json":      m.variance_json,
        "created_by":         m.created_by,
        "resolved_by":        m.resolved_by,
        "resolved_at":        m.resolved_at,
        "created_at":         m.created_at,
    }



@router.post("/supplier-payments", dependencies=[Depends(require_manager)])
def create_supplier_payment(payload: SupplierPaymentCreate, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    supplier = db.query(Supplier).filter(
        Supplier.id == payload.supplier_id,
        Supplier.store_id == current.store_id,
    ).first()
    if not supplier:
        raise HTTPException(404, "Supplier not found in your store")

    posted_grns = db.query(svc.GoodsReceivedNote).filter(
        svc.GoodsReceivedNote.store_id == current.store_id,
        svc.GoodsReceivedNote.supplier_id == supplier.id,
        svc.GoodsReceivedNote.status == svc.GRNStatus.POSTED,
    ).all()
    prior_payments = db.query(SupplierPayment).filter(
        SupplierPayment.store_id == current.store_id,
        SupplierPayment.supplier_id == supplier.id,
        SupplierPayment.is_void == False,
    ).all()
    outstanding = sum((Decimal(str(g.total_received_cost or 0)) for g in posted_grns), Decimal("0.00")) - sum((Decimal(str(p.amount or 0)) for p in prior_payments), Decimal("0.00"))
    if Decimal(str(payload.amount)) > outstanding and outstanding > Decimal("0.00"):
        raise HTTPException(400, f"Payment exceeds supplier outstanding balance of {outstanding.quantize(Decimal('0.01'))}")

    payment_number = f"SP-{uuid.uuid4().hex[:8].upper()}"
    payment = SupplierPayment(store_id=current.store_id, supplier_id=payload.supplier_id, payment_number=payment_number, payment_date=payload.payment_date, amount=payload.amount, payment_method=payload.payment_method, reference=payload.reference, notes=payload.notes, created_by=current.id)
    db.add(payment)
    db.flush()
    post_supplier_payment(db, payment)
    db.commit()
    db.refresh(payment)
    return payment


@router.get("/supplier-payments", dependencies=[Depends(require_cashier)])
def list_supplier_payments(db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    return db.query(SupplierPayment).filter(SupplierPayment.store_id == current.store_id).order_by(SupplierPayment.payment_date.desc(), SupplierPayment.id.desc()).all()


@router.get("/supplier-payments/{payment_id}", dependencies=[Depends(require_cashier)])
def get_supplier_payment(payment_id: int, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    row = db.query(SupplierPayment).filter(SupplierPayment.id == payment_id, SupplierPayment.store_id == current.store_id).first()
    if not row:
        raise HTTPException(404, "Supplier payment not found")
    return row


@router.get("/suppliers/{supplier_id}/statement", dependencies=[Depends(require_cashier)])
def supplier_statement(supplier_id: int, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    return get_supplier_statement(db, current.store_id, supplier_id)


@router.get("/suppliers/aging", dependencies=[Depends(require_cashier)])
def suppliers_aging(db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    return get_ap_aging(db, current.store_id)
