"""
Sync conflict resolution manifest — declarative, testable.

Replaces ad-hoc per-field conditional logic scattered across sync routers
with a single source of truth. Every entity+field combination has an explicit
policy. All sync routers call `resolve()` — no policy logic lives anywhere else.

Policies:
  cloud_wins  — cloud value always wins (manager owns catalog)
  local_wins  — local POS value always wins (terminal owns inventory)
  lww         — Last Write Wins using updated_at timestamps
  immutable   — never overwrite (transactions, audit records)

Usage:
    from app.sync.conflict_policy import resolve, MANIFEST

    resolved = resolve("product", "selling_price",
                       local_val=Decimal("100"), cloud_val=Decimal("95"))
    # → Decimal("95")  (cloud_wins for selling_price)

    resolved = resolve("product", "stock_quantity",
                       local_val=8, cloud_val=5)
    # → 8  (local_wins for stock_quantity)
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional


# ── Manifest ──────────────────────────────────────────────────────────────────
# Structure: { entity: { field: policy } }
# "__default__" applies to any field not explicitly listed.
# Policies: "cloud_wins" | "local_wins" | "lww" | "immutable"

MANIFEST: dict[str, dict[str, str]] = {

    # ── Products ──────────────────────────────────────────────────────────────
    # Cloud (manager) owns catalog; POS (terminal) owns physical stock.
    "product": {
        "__default__":          "cloud_wins",   # unknown new fields → cloud wins by default
        # Catalog fields — cloud is authoritative
        "name":                 "cloud_wins",
        "selling_price":        "cloud_wins",
        "cost_price":           "cloud_wins",
        "vat_exempt":           "cloud_wins",
        "tax_code":             "cloud_wins",
        "reorder_level":        "cloud_wins",
        "is_active":            "cloud_wins",
        "category_id":          "cloud_wins",
        "supplier_id":          "cloud_wins",
        "description":          "cloud_wins",
        "image_url":            "cloud_wins",
        "unit":                 "cloud_wins",
        "barcode":              "cloud_wins",
        # Inventory fields — terminal (POS) is authoritative
        "stock_quantity":       "local_wins",   # POS deducted locally; cloud must not overwrite
        "wac":                  "cloud_wins",   # WAC is computed cloud-side after GRN
    },

    # ── Customers ─────────────────────────────────────────────────────────────
    # LWW: whoever updated last wins. Financial fields always cloud-authoritative.
    "customer": {
        "__default__":          "lww",
        "name":                 "lww",
        "email":                "lww",
        "notes":                "lww",
        "is_active":            "lww",
        "loyalty_points":       "lww",
        # Financial fields — cloud always authoritative (prevents local manipulation)
        "credit_limit":         "cloud_wins",
        "credit_balance":       "cloud_wins",
    },

    # ── Transactions ──────────────────────────────────────────────────────────
    # Immutable: once created locally, never overwritten.
    # Cloud is insert-only (idempotency: skip if exists).
    "transaction": {
        "__default__":          "immutable",
        # Every field is immutable — transactions are financial records
    },

    # ── Transaction Items ─────────────────────────────────────────────────────
    "transaction_item": {
        "__default__":          "immutable",
        # Price/cost/tax snapshots captured at sale time are permanent
    },

    # ── Stock Movements ───────────────────────────────────────────────────────
    "stock_movement": {
        "__default__":          "immutable",
        # Stock movement ledger is append-only
    },

    # ── Employees ─────────────────────────────────────────────────────────────
    # Cloud (admin) owns employee records.
    "employee": {
        "__default__":          "cloud_wins",
        "full_name":            "cloud_wins",
        "email":                "cloud_wins",
        "role":                 "cloud_wins",
        "is_active":            "cloud_wins",
        # Sensitive: never sync passwords over the wire
        "password":             "immutable",
        "pin":                  "immutable",
    },
}


# ── Resolver ──────────────────────────────────────────────────────────────────

def resolve(
    entity: str,
    field: str,
    local_val: Any,
    cloud_val: Any,
    local_ts:  Optional[datetime] = None,
    cloud_ts:  Optional[datetime] = None,
) -> Any:
    """
    Resolve a conflict between a local value and a cloud value for a given
    entity type and field name.

    Args:
        entity:    Entity type key (e.g. "product", "customer", "transaction")
        field:     Field name being resolved (e.g. "selling_price", "stock_quantity")
        local_val: Value from the local (terminal) database
        cloud_val: Value from the cloud database
        local_ts:  Timestamp of the local record (required for LWW)
        cloud_ts:  Timestamp of the cloud record (required for LWW)

    Returns:
        The winning value according to the conflict policy.

    Raises:
        ValueError: if policy is unknown or LWW is used without timestamps
        TypeError:  if entity or field is not a string
    """
    if not isinstance(entity, str) or not isinstance(field, str):
        raise TypeError(f"entity and field must be strings, got {type(entity)}, {type(field)}")

    entity_policy = MANIFEST.get(entity, {})
    policy = entity_policy.get(field, entity_policy.get("__default__", "cloud_wins"))

    if policy == "cloud_wins":
        return cloud_val

    if policy == "local_wins":
        return local_val

    if policy == "immutable":
        # Immutable fields always keep their existing cloud value.
        # For new records (no cloud value), the local value becomes the cloud value.
        return cloud_val if cloud_val is not None else local_val

    if policy == "lww":
        # Last Write Wins: whichever timestamp is newer wins.
        # If timestamps are equal or either is missing, cloud wins (safer default).
        if local_ts is None or cloud_ts is None:
            # No timestamps → can't LWW → cloud wins as safe fallback
            return cloud_val

        # Normalise timezone for comparison
        def _norm(ts: datetime) -> datetime:
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts

        if _norm(local_ts) > _norm(cloud_ts):
            return local_val   # local is newer → local wins
        return cloud_val       # cloud is newer or equal → cloud wins

    raise ValueError(
        f"Unknown conflict policy '{policy}' for entity='{entity}' field='{field}'. "
        f"Add it to MANIFEST in app/sync/conflict_policy.py"
    )


def get_policy(entity: str, field: str) -> str:
    """Return the raw policy string for an entity+field. Useful for logging."""
    entity_policy = MANIFEST.get(entity, {})
    return entity_policy.get(field, entity_policy.get("__default__", "cloud_wins"))


def log_conflict(entity: str, field: str, local_val: Any, cloud_val: Any, winner: Any) -> dict:
    """
    Build a structured conflict log entry. Used by sync routers to populate
    sync_log.conflict with both versions and the resolution applied.
    """
    return {
        "entity":      entity,
        "field":       field,
        "policy":      get_policy(entity, field),
        "local_value": str(local_val),
        "cloud_value": str(cloud_val),
        "winner":      "local" if winner == local_val else "cloud",
    }
