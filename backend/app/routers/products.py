"""
Products router — v4.1

Updates:
  1. Added /products/itemcode/{itemcode} exact lookup route
  2. Added itemcode to general search
  3. Kept store isolation, ownership checks, and cache behavior
"""

import logging
import csv
import io
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String
from typing import List, Optional
from datetime import datetime

from app.core.deps import (
    get_db, require_cashier, require_premium
)
from app.core.cache import (
    cache, product_list_key, product_barcode_key,
    PRODUCT_LIST_TTL, BARCODE_LOOKUP_TTL,
)
from app.models.product import Product, Category, Supplier, StockMovement
from app.models.employee import Employee, Role
from app.models.audit import AuditTrail
from app.services.accounting import post_stock_adjustment as _accounting_post_stock_adjustment
from app.services.reconciliation import assert_period_open
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductOut,
    CategoryCreate, CategoryOut,
    SupplierCreate, SupplierOut,
    StockAdjustment,
    ProductListResponse, CategoryListResponse, SupplierListResponse,
    CSVImportResult,
)

logger = logging.getLogger("dukapos.products")
router = APIRouter(prefix="/products", tags=["Products"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_audit(
    db,
    actor: Employee,
    action: str,
    entity_id: str,
    before=None,
    after=None,
    notes=None,
):
    db.add(AuditTrail(
        store_id=actor.store_id,
        actor_id=actor.id,
        actor_name=actor.full_name,
        action=action,
        entity="product",
        entity_id=str(entity_id),
        before_val=before,
        after_val=after,
        notes=notes,
    ))


def _apply_stock_movement(
    db,
    product: Product,
    delta: int,
    movement_type: str,
    store_id: int = None,
    ref_id: str = None,
    notes: str = None,
    performed_by: int = None,
):
    qty_before = product.stock_quantity
    product.stock_quantity = max(0, product.stock_quantity + delta)
    qty_after = product.stock_quantity

    movement = StockMovement(
        product_id=product.id,
        store_id=store_id,
        movement_type=movement_type,
        qty_delta=delta,
        qty_before=qty_before,
        qty_after=qty_after,
        ref_id=ref_id,
        notes=notes,
        performed_by=performed_by,
    )
    db.add(movement)
    return movement


def _own_product(product: Product, current: Employee) -> bool:
    if current.role == Role.PLATFORM_OWNER:
        return True
    return product.store_id == current.store_id


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=CategoryListResponse)
def list_categories(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    q = db.query(Category)
    if current.role != Role.PLATFORM_OWNER:
        q = q.filter(Category.store_id == current.store_id)
    
    if is_active is not None:
        q = q.filter(Category.is_active == is_active)
    
    if search:
        like = f"%{search}%"
        q = q.filter(Category.name.ilike(like))
    
    total = q.count()
    results = q.offset(skip).limit(limit).all()
    
    return CategoryListResponse(
        items=[CategoryOut.model_validate(c) for c in results],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/categories", response_model=CategoryOut)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    if current.role not in {Role.SUPERVISOR, Role.MANAGER, Role.ADMIN, Role.PLATFORM_OWNER}:
        raise HTTPException(403, "Stock adjustments require supervisor approval")
    assert_period_open(db, current.store_id, datetime.utcnow().date())
    cat = Category(**payload.model_dump(), store_id=current.store_id)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


# ── Suppliers ─────────────────────────────────────────────────────────────────

@router.get("/suppliers", response_model=SupplierListResponse)
def list_suppliers(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    q = db.query(Supplier)
    
    if current.role != Role.PLATFORM_OWNER:
        q = q.filter(Supplier.store_id == current.store_id)
    
    # Default: show only active suppliers
    if is_active is not None:
        q = q.filter(Supplier.is_active == is_active)
    else:
        q = q.filter(Supplier.is_active == True)
    
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Supplier.name.ilike(like),
            Supplier.phone.ilike(like),
            Supplier.email.ilike(like),
        ))
    
    total = q.count()
    results = q.offset(skip).limit(limit).all()
    
    return SupplierListResponse(
        items=[SupplierOut.model_validate(s) for s in results],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    if current.role not in {Role.SUPERVISOR, Role.MANAGER, Role.ADMIN, Role.PLATFORM_OWNER}:
        raise HTTPException(403, "Stock adjustments require supervisor approval")
    assert_period_open(db, current.store_id, datetime.utcnow().date())
    supplier = Supplier(**payload.model_dump(), store_id=current.store_id)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ProductListResponse)
async def list_products(
    search: Optional[str] = Query(None),
    category_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    low_stock: Optional[bool] = None,
    is_active: bool = True,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    sid = current.store_id

    use_cache = (
        search is None
        and category_id is None
        and supplier_id is None
        and low_stock is None
        and is_active is True
        and skip == 0
        and limit == 100
        and current.role != Role.PLATFORM_OWNER
    )

    cache_key = product_list_key(store_id=sid, is_active=is_active)

    if use_cache:
        cached = await cache.get(cache_key)
        if cached is not None:
            return cached

    q = db.query(Product).filter(Product.is_active == is_active)

    if current.role != Role.PLATFORM_OWNER:
        q = q.filter(Product.store_id == sid)

    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Product.name.ilike(like),
            Product.sku.ilike(like),
            Product.barcode.ilike(like),
            cast(Product.itemcode, String).ilike(like),
        ))

    if category_id:
        q = q.filter(Product.category_id == category_id)

    if supplier_id:
        q = q.filter(Product.supplier_id == supplier_id)

    if low_stock:
        q = q.filter(Product.stock_quantity <= Product.reorder_level)

    total = q.count()
    results = q.offset(skip).limit(limit).all()

    if use_cache:
        serialized = [
            ProductOut.model_validate(r).model_dump(mode="json")
            for r in results
        ]
        await cache.set(cache_key, serialized, ttl=PRODUCT_LIST_TTL)

    return ProductListResponse(
        items=[ProductOut.model_validate(r) for r in results],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/barcode/{barcode}", response_model=ProductOut)
async def get_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    cache_key = product_barcode_key(f"{current.store_id}:{barcode}")
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    q = db.query(Product).filter(Product.barcode == barcode)

    if current.role != Role.PLATFORM_OWNER:
        q = q.filter(Product.store_id == current.store_id)

    product = q.first()
    if not product:
        raise HTTPException(404, f"No product found for barcode: {barcode}")

    serialized = ProductOut.model_validate(product).model_dump(mode="json")
    await cache.set(cache_key, serialized, ttl=BARCODE_LOOKUP_TTL)
    return product


@router.get("/itemcode/{itemcode}", response_model=ProductOut)
async def get_by_itemcode(
    itemcode: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    q = db.query(Product).filter(Product.itemcode == itemcode)

    if current.role != Role.PLATFORM_OWNER:
        q = q.filter(Product.store_id == current.store_id)

    product = q.first()
    if not product:
        raise HTTPException(404, f"No product found for item code: {itemcode}")

    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_cashier),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "Product not found")

    if not _own_product(product, current):
        raise HTTPException(403, "Product not found in your store")

    return product


@router.post("", response_model=ProductOut)
async def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    if current.role not in {Role.SUPERVISOR, Role.MANAGER, Role.ADMIN, Role.PLATFORM_OWNER}:
        raise HTTPException(403, "Stock adjustments require supervisor approval")
    assert_period_open(db, current.store_id, datetime.utcnow().date())
    existing = (
        db.query(Product)
        .filter(Product.sku == payload.sku)
        .filter(Product.store_id == current.store_id)
        .first()
    )
    if existing:
        raise HTTPException(400, f"SKU '{payload.sku}' already exists in your store")

    data = payload.model_dump()
    initial_qty = data.pop("stock_quantity", 0)

    product = Product(**data, stock_quantity=0, store_id=current.store_id)
    db.add(product)
    db.flush()

    if initial_qty > 0:
        _apply_stock_movement(
            db,
            product,
            initial_qty,
            "purchase",
            store_id=current.store_id,
            notes="Initial stock on product creation",
            performed_by=current.id,
        )


    _write_audit(
        db,
        current,
        "create",
        product.sku,
        after={"sku": product.sku, "name": product.name},
    )
    db.commit()
    db.refresh(product)
    await cache.invalidate_prefix(f"products:list:{current.store_id}")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    if current.role not in {Role.SUPERVISOR, Role.MANAGER, Role.ADMIN, Role.PLATFORM_OWNER}:
        raise HTTPException(403, "Stock adjustments require supervisor approval")
    assert_period_open(db, current.store_id, datetime.utcnow().date())
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "Product not found")

    if not _own_product(product, current):
        raise HTTPException(403, "Product not found in your store")

    before = {
        "name": product.name,
        "selling_price": str(product.selling_price),
        "itemcode": product.itemcode,
        "barcode": product.barcode,
        "sku": product.sku,
    }

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    _write_audit(
        db,
        current,
        "update",
        product.sku,
        before=before,
        after={
            "name": product.name,
            "selling_price": str(product.selling_price),
            "itemcode": product.itemcode,
            "barcode": product.barcode,
            "sku": product.sku,
        },
    )

    db.commit()
    db.refresh(product)
    await cache.invalidate_prefix(f"products:list:{current.store_id}")
    return product


# ── Stock ─────────────────────────────────────────────────────────────────────

@router.post("/stock/adjust")
async def adjust_stock(
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    if current.role not in {Role.SUPERVISOR, Role.MANAGER, Role.ADMIN, Role.PLATFORM_OWNER}:
        raise HTTPException(403, "Stock adjustments require supervisor approval")
    assert_period_open(db, current.store_id, datetime.utcnow().date())
    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(404, "Product not found")

    if not _own_product(product, current):
        raise HTTPException(403, "Product not found in your store")

    movement = _apply_stock_movement(
        db,
        product,
        payload.quantity_change,
        movement_type=payload.reason,
        store_id=current.store_id,
        notes=payload.notes,
        performed_by=current.id,
    )

    _accounting_post_stock_adjustment(
        db,
        current.store_id,
        product,
        payload.quantity_change,
        payload.reason,
        payload.notes,
        current.id,
    )

    _write_audit(
        db,
        current,
        "stock_adj",
        product.sku,
        before={"stock": movement.qty_before},
        after={"stock": movement.qty_after},
        notes=f"{payload.reason}: {payload.quantity_change}",
    )

    db.commit()
    await cache.invalidate_prefix(f"products:list:{current.store_id}")

    return {
        "product_id": product.id,
        "sku": product.sku,
        "new_stock": product.stock_quantity,
        "adjustment": payload.quantity_change,
        "reason": payload.reason,
        "movement_id": movement.id,
    }


@router.get("/{product_id}/stock-history")
def stock_history(
    product_id: int,
    limit: int = Query(default=50, le=200),
    since: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    if current.role not in {Role.SUPERVISOR, Role.MANAGER, Role.ADMIN, Role.PLATFORM_OWNER}:
        raise HTTPException(403, "Stock adjustments require supervisor approval")
    assert_period_open(db, current.store_id, datetime.utcnow().date())
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "Product not found")

    if not _own_product(product, current):
        raise HTTPException(403, "Product not found in your store")

    q = db.query(StockMovement).filter(StockMovement.product_id == product_id)

    if since is not None:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(400, "Invalid since datetime — use ISO 8601 format")
        q = q.filter(StockMovement.created_at > since_dt)

    q = q.order_by(StockMovement.created_at.desc())
    total_movements = q.count()
    movements = q.limit(limit).all()

    return {
        "product_id": product.id,
        "product_name": product.name,
        "sku": product.sku,
        "movements": [
            {
                "id": m.id,
                "movement_type": m.movement_type,
                "qty_delta": m.qty_delta,
                "qty_before": m.qty_before,
                "qty_after": m.qty_after,
                "ref_id": m.ref_id,
                "notes": m.notes,
                "performed_by_name": m.employee.full_name if getattr(m, "employee", None) else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in movements
        ],
        "total_movements": total_movements,
    }


# ── CSV Import ─────────────────────────────────────────────────────────────────

@router.post("/import/csv", response_model=CSVImportResult)
async def import_products_csv(
    file: UploadFile = File(...),
    update_existing: bool = Query(False),
    db: Session = Depends(get_db),
    current: Employee = Depends(require_premium),
):
    """
    Import products from CSV file.

    CSV columns (comma-separated):
    - sku (required): Product code
    - name (required): Product name
    - selling_price (required): Retail price
    - barcode (optional): EAN/UPC
    - itemcode (optional): Numeric code
    - description (optional): Product description
    - category (optional): Category name (must exist)
    - supplier (optional): Supplier name (must exist)
    - cost_price (optional): Product cost
    - vat_exempt (optional): yes/no/true/false
    - tax_code (optional): A or B
    - stock_quantity (optional): Initial stock
    - reorder_level (optional): Low stock threshold
    - unit (optional): piece/kg/liter/pack (default: piece)
    - is_active (optional): yes/no/true/false

    Returns:
    - success: True if import completed
    - created: Number of new products
    - updated: Number of updated products
    - skipped: Number of skipped rows
    - errors: List of error messages
    - summary: Human-readable summary
    """
    if current.role not in {Role.SUPERVISOR, Role.MANAGER, Role.ADMIN, Role.PLATFORM_OWNER}:
        raise HTTPException(403, "CSV import requires supervisor or higher")

    try:
        # Read CSV file
        content = await file.read()
        text_content = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(text_content))

        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no header row")

        # Build caches
        categories = db.query(Category).filter(Category.store_id == current.store_id).all()
        category_cache = {cat.name.lower(): cat.id for cat in categories}

        suppliers = db.query(Supplier).filter(Supplier.store_id == current.store_id).all()
        supplier_cache = {sup.name.lower(): sup.id for sup in suppliers}

        result = {
            'success': True,
            'total_rows': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': [],
            'summary': '',
        }

        seen_skus = set()

        for row_num, row in enumerate(reader, start=2):
            try:
                result['total_rows'] += 1
                
                # Validate required fields
                sku = str(row.get('sku', '').strip())
                if not sku:
                    raise ValueError("SKU is required")

                name = str(row.get('name', '').strip())
                if not name:
                    raise ValueError("Product name is required")

                selling_price_str = row.get('selling_price', '').strip()
                if not selling_price_str:
                    raise ValueError("Selling price is required")

                # Check for duplicates
                if sku in seen_skus:
                    raise ValueError(f"Duplicate SKU in CSV: '{sku}'")
                seen_skus.add(sku)

                # Parse prices
                try:
                    selling_price = Decimal(str(selling_price_str)).quantize(Decimal('0.01'))
                except (ValueError, TypeError):
                    raise ValueError(f"Selling price must be a decimal number")

                cost_price = None
                cost_str = row.get('cost_price', '').strip()
                if cost_str:
                    try:
                        cost_price = Decimal(str(cost_str)).quantize(Decimal('0.01'))
                    except (ValueError, TypeError):
                        raise ValueError("Cost price must be a decimal number")

                # Parse category
                category_id = None
                cat_name = row.get('category', '').strip()
                if cat_name:
                    category_id = category_cache.get(cat_name.lower())
                    if category_id is None:
                        raise ValueError(f"Category '{cat_name}' not found")

                # Parse supplier
                supplier_id = None
                sup_name = row.get('supplier', '').strip()
                if sup_name:
                    supplier_id = supplier_cache.get(sup_name.lower())
                    if supplier_id is None:
                        raise ValueError(f"Supplier '{sup_name}' not found")

                # Parse other fields
                barcode = row.get('barcode', '').strip() or None
                description = row.get('description', '').strip() or None

                itemcode = None
                itemcode_str = row.get('itemcode', '').strip()
                if itemcode_str:
                    try:
                        itemcode = int(itemcode_str)
                    except ValueError:
                        raise ValueError("itemcode must be an integer")

                vat_exempt = False
                vat_str = row.get('vat_exempt', 'no').strip().lower()
                if vat_str in ('yes', 'y', '1', 'true'):
                    vat_exempt = True

                tax_code = row.get('tax_code', 'B').strip().upper()
                if tax_code not in ('A', 'B'):
                    tax_code = 'B'

                stock_quantity = 0
                stock_str = row.get('stock_quantity', '').strip()
                if stock_str:
                    try:
                        stock_quantity = int(stock_str)
                    except ValueError:
                        raise ValueError("stock_quantity must be an integer")

                reorder_level = 10
                reorder_str = row.get('reorder_level', '').strip()
                if reorder_str:
                    try:
                        reorder_level = int(reorder_str)
                    except ValueError:
                        raise ValueError("reorder_level must be an integer")

                unit = row.get('unit', 'piece').strip().lower()
                unit_mapping = {
                    'pcs': 'piece', 'pc': 'piece', 'pieces': 'piece',
                    'kg': 'kilogram', 'g': 'gram',
                    'l': 'liter', 'ml': 'milliliter',
                    'pack': 'pack', 'box': 'box', 'bottle': 'bottle',
                    'can': 'can', 'carton': 'carton', 'dozen': 'dozen',
                }
                unit = unit_mapping.get(unit, unit or 'piece')

                is_active = True
                active_str = row.get('is_active', 'yes').strip().lower()
                if active_str in ('no', 'n', '0', 'false'):
                    is_active = False

                # Check if product exists
                existing = db.query(Product).filter(
                    Product.store_id == current.store_id,
                    Product.sku == sku,
                ).first()

                if existing:
                    if not update_existing:
                        result['skipped'] += 1
                        continue

                    # Update existing product
                    existing.name = name
                    existing.barcode = barcode
                    existing.itemcode = itemcode
                    existing.description = description
                    existing.category_id = category_id
                    existing.supplier_id = supplier_id
                    existing.selling_price = selling_price
                    existing.cost_price = cost_price
                    existing.vat_exempt = vat_exempt
                    existing.tax_code = tax_code
                    existing.reorder_level = reorder_level
                    existing.unit = unit
                    existing.is_active = is_active
                    existing.updated_at = datetime.utcnow()
                    db.add(existing)
                    result['updated'] += 1
                else:
                    # Create new product
                    product = Product(
                        store_id=current.store_id,
                        sku=sku,
                        barcode=barcode,
                        itemcode=itemcode,
                        name=name,
                        description=description,
                        category_id=category_id,
                        supplier_id=supplier_id,
                        selling_price=selling_price,
                        cost_price=cost_price,
                        vat_exempt=vat_exempt,
                        tax_code=tax_code,
                        stock_quantity=stock_quantity,
                        reorder_level=reorder_level,
                        unit=unit,
                        is_active=is_active,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(product)

                    # Apply initial stock movement if quantity > 0
                    if stock_quantity > 0:
                        _apply_stock_movement(
                            db,
                            product,
                            stock_quantity,
                            "purchase",
                            store_id=current.store_id,
                            notes="Initial stock from CSV import",
                            performed_by=current.id,
                        )

                    result['created'] += 1

            except ValueError as e:
                result['errors'].append(f"Row {row_num}: {str(e)}")
                result['skipped'] += 1
            except Exception as e:
                result['errors'].append(f"Row {row_num}: Unexpected error - {str(e)}")
                result['skipped'] += 1

        # Commit changes
        db.commit()

        # Invalidate cache
        await cache.invalidate_prefix(f"products:list:{current.store_id}")

        result['summary'] = (
            f"Imported {result['created']} new products, "
            f"updated {result['updated']} existing, "
            f"skipped {result['skipped']} rows"
        )

        # Write audit trail
        _write_audit(
            db,
            current,
            "csv_import",
            "bulk_product_import",
            after={
                "created": result['created'],
                "updated": result['updated'],
                "total": result['total_rows'],
            },
            notes=f"CSV import: {result['summary']}",
        )
        db.commit()

        return result

    except Exception as e:
        result = {
            'success': False,
            'total_rows': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': [f"File processing error: {str(e)}"],
            'summary': f"Import failed: {str(e)}",
        }
        db.rollback()
        return result