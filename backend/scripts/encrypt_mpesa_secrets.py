#!/usr/bin/env python3
"""
encrypt_mpesa_secrets.py — One-time migration to encrypt plaintext M-PESA secrets.

Targets Store rows where mpesa_consumer_key IS NOT NULL and does NOT start with
the 'enc::' prefix written by encrypt_sensitive_value().  Safe to run multiple
times (idempotent).

Usage:
    python scripts/encrypt_mpesa_secrets.py
    python scripts/encrypt_mpesa_secrets.py --dry-run

Requirements:
    DATABASE_URL and SECRET_ENCRYPTION_KEY must be set in the environment
    (or in a .env file loaded before running this script).
"""

import argparse
import os
import sys

# ── Bootstrap Django-style path so app.* imports work when run from /backend ─
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()  # pick up .env if present

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.security import encrypt_sensitive_value

_ENCRYPTED_PREFIX = "enc::"
_SENSITIVE_FIELDS = ("mpesa_consumer_key", "mpesa_consumer_secret", "mpesa_passkey")


def _needs_encryption(value: str | None) -> bool:
    """Return True if the value is present and not yet encrypted."""
    if not value:
        return False
    return not value.startswith(_ENCRYPTED_PREFIX)


def run(dry_run: bool) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    encryption_key = os.environ.get("SECRET_ENCRYPTION_KEY")
    if not encryption_key:
        print("ERROR: SECRET_ENCRYPTION_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        # Fetch stores that have at least one plaintext credential field.
        rows = session.execute(
            text(
                """
                SELECT id, mpesa_consumer_key, mpesa_consumer_secret, mpesa_passkey
                FROM stores
                WHERE mpesa_consumer_key IS NOT NULL
                   OR mpesa_consumer_secret IS NOT NULL
                   OR mpesa_passkey IS NOT NULL
                """
            )
        ).fetchall()

        encrypted_count = 0
        skipped_count = 0

        for row in rows:
            store_id = row[0]
            current = {
                "mpesa_consumer_key": row[1],
                "mpesa_consumer_secret": row[2],
                "mpesa_passkey": row[3],
            }

            updates = {}
            for field in _SENSITIVE_FIELDS:
                value = current[field]
                if _needs_encryption(value):
                    updates[field] = encrypt_sensitive_value(value)

            if not updates:
                skipped_count += 1
                print(f"  SKIP  store_id={store_id}  (already encrypted or null)")
                continue

            fields_changed = list(updates.keys())
            print(f"  {'DRY-RUN' if dry_run else 'ENCRYPT'}  store_id={store_id}  fields={fields_changed}")

            if not dry_run:
                set_clause = ", ".join(f"{f} = :{f}" for f in updates)
                session.execute(
                    text(f"UPDATE stores SET {set_clause} WHERE id = :store_id"),
                    {**updates, "store_id": store_id},
                )
            encrypted_count += 1

        if not dry_run:
            session.commit()

    mode = "DRY-RUN — no changes written" if dry_run else "committed to database"
    print(
        f"\nDone ({mode}).\n"
        f"  Encrypted: {encrypted_count} store(s)\n"
        f"  Skipped:   {skipped_count} store(s) (already encrypted or all-null)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be changed without writing to the database.",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("Running in DRY-RUN mode — no changes will be written.\n")

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
