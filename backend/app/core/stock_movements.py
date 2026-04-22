"""
Stock Movement Type Constants and Validation

Phase P0-D: Centralized enum for stock ledger movement types.
Ensures consistency across all codebase references.

All stock ledger entries must use one of these constants.
"""

from enum import Enum


class StockMovementType(str, Enum):
    """
    All allowed stock movement types.
    
    Canonical reference for:
    - ORM code (using in StockMovement.movement_type)
    - Route handlers
    - Services
    - Database CHECK constraint
    """
    
    # ─── SALES & RETURNS ─────────────────────────────────────────────────────
    SALE = "sale"                      # Normal POS transaction
    RETURN = "return"                  # Customer return of goods
    VOID_RESTORE = "void_restore"      # Void completed transaction
    
    # ─── PURCHASE & RECEIVING ────────────────────────────────────────────────
    PURCHASE_RECEIVE = "purchase_receive"              # GRN accepted qty
    PURCHASE_RECEIVE_DAMAGED = "purchase_receive_damaged"  # Damaged goods (qty_delta=0)
    PURCHASE_REJECT = "purchase_reject"                # Rejected goods (qty_delta=0)
    
    # ─── M-PESA PAYMENT FAILURES ─────────────────────────────────────────────
    MPESA_FAILED_RESTORE = "mpesa_failed_restore"      # Failed callback restores stock
    MPESA_TIMEOUT_RESTORE = "mpesa_timeout_restore"    # Timeout cleanup restores stock
    
    # ─── STOCK ADJUSTMENTS ───────────────────────────────────────────────────
    ADJUSTMENT = "adjustment"          # Manual adjustment (write-off, shrinkage, etc.)
    
    # ─── SYNC OPERATIONS ─────────────────────────────────────────────────────
    SYNC = "sync"                      # Cloud sync reconciliation
    
    def __str__(self) -> str:
        return self.value


# Canonical list for CHECK constraint and validation
VALID_MOVEMENT_TYPES = [
    StockMovementType.SALE,
    StockMovementType.RETURN,
    StockMovementType.VOID_RESTORE,
    StockMovementType.PURCHASE_RECEIVE,
    StockMovementType.PURCHASE_RECEIVE_DAMAGED,
    StockMovementType.PURCHASE_REJECT,
    StockMovementType.MPESA_FAILED_RESTORE,
    StockMovementType.MPESA_TIMEOUT_RESTORE,
    StockMovementType.ADJUSTMENT,
    StockMovementType.SYNC,
]

VALID_MOVEMENT_TYPE_VALUES = [t.value for t in VALID_MOVEMENT_TYPES]


def validate_movement_type(movement_type: str) -> bool:
    """Validate that movement_type is in the canonical list."""
    return movement_type in VALID_MOVEMENT_TYPE_VALUES


def check_constraint_sql() -> str:
    """Generate CHECK constraint SQL for migrations.
    
    Returns:
        SQL string for use in migration upgrade()
    """
    types_csv = ", ".join(f"'{t}'" for t in VALID_MOVEMENT_TYPE_VALUES)
    return f"movement_type IN ({types_csv})"
