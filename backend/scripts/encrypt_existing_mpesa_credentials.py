#!/usr/bin/env python
"""
One-time data migration: Encrypt existing plaintext M-Pesa credentials.

This script runs AFTER the Alembic migration (0034_per_store_etims_credentials.py)
to encrypt M-Pesa consumer_key, consumer_secret, and passkey columns.

Why needed:
  - Before this deployment, M-Pesa credentials were stored in plaintext
  - New credential endpoints (PATCH /stores/credentials/mpesa) encrypt values before saving
  - But existing records in the database are still unencrypted
  - This script finds those plaintext values and encrypts them one-time

How to run:
  cd backend
  python scripts/encrypt_existing_mpesa_credentials.py

Safety:
  - Idempotent: skips values that are already encrypted (start with "gAAAAAB")
  - Dry-run option: pass --dry-run to preview changes without applying
  - Logs all changes for audit trail
"""

import sys
import logging
from pathlib import Path

# Setup path for app imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.subscription import Store
from app.core.encryption import encrypt_value, is_encryption_configured

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _is_encrypted(value: str) -> bool:
    """
    Check if a value appears to be already encrypted.
    
    Fernet tokens start with the standard prefix "gAAAAAB".
    This is a heuristic check; not foolproof but sufficient for this use case.
    """
    if not value:
        return False
    return value.startswith("gAAAAAB")


def main(dry_run: bool = False):
    """
    Encrypt all plaintext M-Pesa credentials in the database.
    
    Args:
        dry_run: If True, log what would be changed but don't apply
    """
    if not is_encryption_configured():
        logger.error(
            "SECRET_ENCRYPTION_KEY is not configured. "
            "Cannot encrypt credentials. Aborting."
        )
        sys.exit(1)
    
    db = SessionLocal()
    try:
        stores = db.query(Store).all()
        logger.info(f"Found {len(stores)} stores to check")
        
        encrypted_count = 0
        skipped_count = 0
        
        for store in stores:
            store_changes = []
            
            # Check and encrypt consumer_key
            if store.mpesa_consumer_key and not _is_encrypted(store.mpesa_consumer_key):
                store_changes.append("consumer_key")
                if not dry_run:
                    store.mpesa_consumer_key = encrypt_value(store.mpesa_consumer_key)
            
            # Check and encrypt consumer_secret
            if store.mpesa_consumer_secret and not _is_encrypted(store.mpesa_consumer_secret):
                store_changes.append("consumer_secret")
                if not dry_run:
                    store.mpesa_consumer_secret = encrypt_value(store.mpesa_consumer_secret)
            
            # Check and encrypt passkey
            if store.mpesa_passkey and not _is_encrypted(store.mpesa_passkey):
                store_changes.append("passkey")
                if not dry_run:
                    store.mpesa_passkey = encrypt_value(store.mpesa_passkey)
            
            if store_changes:
                encrypted_count += 1
                action = "[DRY RUN] Would encrypt" if dry_run else "Encrypted"
                logger.info(
                    f"{action} store_id={store.id} ({store.name}): {', '.join(store_changes)}"
                )
            else:
                skipped_count += 1
        
        if not dry_run:
            db.commit()
            logger.info(
                f"Migration complete: {encrypted_count} stores encrypted, "
                f"{skipped_count} stores skipped"
            )
        else:
            logger.info(
                f"[DRY RUN] Would encrypt: {encrypted_count} stores, "
                f"skip: {skipped_count} stores"
            )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    if dry_run:
        logger.info("Running in DRY-RUN mode (no changes will be applied)")
    main(dry_run=dry_run)
    logger.info("Done.")
