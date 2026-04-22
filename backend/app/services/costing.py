"""
Costing engine — Weighted Average Cost (WAC) v1

Responsibilities:
  1. recalculate_wac()    — called after every GRN post to update product.wac
  2. create_cost_layer()  — called after GRN post to record the cost batch
  3. get_cost_snapshot()  — returns current WAC for use as cost_price_snap at sale time
  4. handle_cost_change() — handles retroactive supplier price correction

WAC Formula:
  New WAC = (existing_qty * old_wac + received_qty * unit_cost) / (existing_qty + received_qty)

FIFO (v2, future):
  When FIFO is enabled per store, consume_cost_layer() is called on each sale
  to decrement the oldest cost layers and compute exact COGS.

IMMUTABILITY RULE:
  Historic cost_price_snap on TransactionItem is NEVER modified.
  Cost corrections create new adjustment journal entries in the CURRENT period.

PERIOD CLOSE RULE:
  GRNs cannot be backdated into a closed period. Backdated GRNs within an
  open period are allowed, but the WAC correction is applied to the current
  state (not retroactively to past sales).
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.product import Product
from app.models.inventory import CostLayer
from app.models.accounting import JournalEntry

logger = logging.getLogger("dukapos.costing")

FOUR_PLACES = Decimal("0.0001")
TWO_PLACES  = Decimal("0.01")


def _q4(value) -> Decimal:
    """Quantize to 4 decimal places (internal cost precision)."""
    return Decimal(str(value)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def _q2(value) -> Decimal:
    """Quantize to 2 decimal places (display/reporting)."""
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def create_cost_layer(
    db: Session,
    product_id: int,
    store_id: int,
    qty_received: int,
    unit_cost: Decimal,
    effective_date: date,
    grn_id: Optional[int] = None,
) -> CostLayer:
    """
    Record a new cost batch after a GRN is posted.
    The layer is used for WAC recalculation and future FIFO support.

    Called by: procurement service after GRN post
    """
    layer = CostLayer(
        product_id    = product_id,
        store_id      = store_id,
        grn_id        = grn_id,
        qty_received  = qty_received,
        qty_remaining = qty_received,   # starts fully available
        unit_cost     = _q4(unit_cost),
        effective_date= effective_date,
    )
    db.add(layer)
    db.flush()
    logger.info(
        "Cost layer created: product_id=%d store_id=%d qty=%d cost=%.4f grn=%s",
        product_id, store_id, qty_received, float(unit_cost), grn_id
    )
    return layer


def recalculate_wac(
    db: Session,
    product_id: int,
    store_id: int,
    new_qty: int,
    new_unit_cost: Decimal,
) -> Decimal:
    """
    Recalculate and persist WAC on the product after a new goods receipt.

    WAC = (existing_stock_value + new_purchase_value) / total_units

    Uses with_for_update() to prevent concurrent GRNs from producing a
    stale WAC (two GRNs for the same product in quick succession).

    Returns the new WAC.

    Called by: procurement service, immediately after create_cost_layer()
    """
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.store_id == store_id)
        .with_for_update()
        .first()
    )
    if not product:
        raise ValueError(f"Product {product_id} not found in store {store_id}")

    current_wac = _q4(product.wac or product.cost_price or Decimal("0"))
    current_qty = max(0, product.stock_quantity)  # never negative for WAC purposes

    old_stock_value  = current_wac * Decimal(str(current_qty))
    new_stock_value  = _q4(new_unit_cost) * Decimal(str(new_qty))
    total_qty        = current_qty + new_qty

    if total_qty <= 0:
        new_wac = _q4(new_unit_cost)
    else:
        new_wac = _q4((old_stock_value + new_stock_value) / Decimal(str(total_qty)))

    # Update product
    product.wac            = new_wac
    product.wac_updated_at = datetime.now(timezone.utc)
    product.stock_quantity = product.stock_quantity + new_qty

    db.flush()

    logger.info(
        "WAC recalculated: product_id=%d store_id=%d old_wac=%.4f new_qty=%d "
        "new_unit_cost=%.4f → new_wac=%.4f new_stock=%d",
        product_id, store_id, float(current_wac), new_qty,
        float(new_unit_cost), float(new_wac), product.stock_quantity,
    )
    return new_wac


def get_cost_snapshot(
    db: Session,
    product_id: int,
    store_id: int,
) -> Decimal:
    """
    Return the current WAC for use as cost_price_snap at sale time.

    Priority:
      1. product.wac           (set by WAC engine after each GRN)
      2. product.cost_price    (fallback for products never received via GRN)
      3. Decimal("0.00")       (zero with warning logged)

    The caller (POS sale creation) must use this value as cost_price_snap
    on TransactionItem. This snapshot is immutable after the sale is completed.
    """
    product = db.query(Product).filter(
        Product.id == product_id, Product.store_id == store_id
    ).first()

    if not product:
        logger.error("get_cost_snapshot: product %d not found", product_id)
        return Decimal("0.00")

    if product.wac and product.wac > Decimal("0"):
        return _q2(product.wac)

    if product.cost_price and product.cost_price > Decimal("0"):
        logger.debug(
            "Using cost_price fallback for product %d (no WAC set yet)", product_id
        )
        return _q2(product.cost_price)

    logger.warning(
        "ZERO COST SNAPSHOT for product_id=%d sku=%s — "
        "no WAC and no cost_price. COGS will be understated. "
        "Set cost_price on this product or receive stock via a GRN.",
        product_id, product.sku
    )
    return Decimal("0.00")


def handle_retroactive_cost_change(
    db: Session,
    product_id: int,
    store_id: int,
    grn_id: int,
    old_unit_cost: Decimal,
    new_unit_cost: Decimal,
    qty: int,
    changed_by: int,
    current_period_entry_date: date,
) -> dict:
    """
    Handle a supplier issuing a revised invoice after goods were already received
    and potentially sold.

    RULE: Historic cost_price_snap on TransactionItem is NEVER modified.

    What this function does:
      1. Updates the cost layer with the corrected unit_cost
      2. Recalculates WAC for remaining (unsold) inventory
      3. Returns the accounting adjustment amounts for the caller to post:
         - inventory_adjustment: (new_cost - old_cost) * qty_remaining
         - cogs_adjustment:      (new_cost - old_cost) * qty_sold

    The caller (procurement router) is responsible for posting the adjustment
    journal entries in the current open period.

    Returns: {
        "inventory_adjustment": Decimal,  # + = inventory value increased
        "cogs_adjustment": Decimal,       # + = COGS should have been higher
        "qty_remaining": int,
        "qty_sold": int,
        "new_wac": Decimal,
    }
    """
    layer = db.query(CostLayer).filter(
        CostLayer.grn_id    == grn_id,
        CostLayer.product_id == product_id,
        CostLayer.store_id  == store_id,
    ).with_for_update().first()

    if not layer:
        raise ValueError(f"No cost layer found for GRN {grn_id} product {product_id}")

    old_cost = _q4(old_unit_cost)
    new_cost = _q4(new_unit_cost)
    cost_delta = new_cost - old_cost

    qty_sold      = layer.qty_received - layer.qty_remaining
    qty_remaining = layer.qty_remaining

    # Update the layer with corrected cost
    layer.unit_cost = new_cost
    db.flush()

    # Recalculate WAC for remaining stock using the cost difference
    product = db.query(Product).filter(
        Product.id == product_id, Product.store_id == store_id
    ).with_for_update().first()

    old_wac = _q4(product.wac or product.cost_price or Decimal("0"))
    current_stock = max(0, product.stock_quantity)

    if current_stock > 0:
        # Adjust WAC by the cost correction on remaining inventory
        inventory_value_before = old_wac * Decimal(str(current_stock))
        inventory_adjustment   = cost_delta * Decimal(str(qty_remaining))
        inventory_value_after  = inventory_value_before + inventory_adjustment
        new_wac = _q4(inventory_value_after / Decimal(str(current_stock)))
        product.wac = new_wac
        product.wac_updated_at = datetime.now(timezone.utc)
        db.flush()
    else:
        new_wac = new_cost

    inventory_adjustment = _q2(cost_delta * Decimal(str(qty_remaining)))
    cogs_adjustment      = _q2(cost_delta * Decimal(str(qty_sold)))

    logger.info(
        "Retroactive cost change: product_id=%d grn=%d old=%.4f new=%.4f "
        "qty_remaining=%d qty_sold=%d inv_adj=%.2f cogs_adj=%.2f new_wac=%.4f",
        product_id, grn_id, float(old_cost), float(new_cost),
        qty_remaining, qty_sold,
        float(inventory_adjustment), float(cogs_adjustment), float(new_wac),
    )

    return {
        "inventory_adjustment": inventory_adjustment,
        "cogs_adjustment":      cogs_adjustment,
        "qty_remaining":        qty_remaining,
        "qty_sold":             qty_sold,
        "new_wac":              new_wac,
    }
