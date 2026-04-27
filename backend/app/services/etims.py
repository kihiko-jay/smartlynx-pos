"""
KRA eTIMS (Electronic Tax Invoice Management System) integration — production service.

All VAT-registered businesses in Kenya must submit electronic tax invoices to KRA
in real time via the eTIMS REST API. Each sale must produce a KRA invoice number
and QR code that appears on the customer receipt.

URLs:
  Production: https://etims-api.kra.go.ke/etims-api
  Sandbox:    https://etims-sbx-api.kra.go.ke/etims-api

To test against sandbox:
  Set ETIMS_URL=https://etims-sbx-api.kra.go.ke/etims-api in your .env
  Obtain test credentials from the KRA eTIMS portal.

CRITICAL CONTRACT: submit_invoice() MUST NEVER RAISE.
A failed eTIMS submission must not void or block a completed sale. The sale
is already committed to the database before this function is called. If eTIMS
is unreachable or rejects the payload, we return etims_synced=False and let
the retry scheduler pick it up later.
"""

import logging
import httpx
from decimal import Decimal
from typing import Optional
from app.core.config import settings
from app.core.encryption import decrypt_value

logger = logging.getLogger(__name__)


def _build_item_payload(item: dict) -> dict:
    """
    Build a single KRA item dict from a transaction item snapshot.

    Fix 1: line_total is already VAT-exclusive (net amount).
           taxblAmt should be set to line_total directly.
           taxAmt should be calculated as: line_total * vat_rate using Decimal.
           splyAmt (supply amount) is the VAT-inclusive total: taxblAmt + taxAmt.

    Fix 3: VAT rate derived from settings.VAT_RATE (not hardcoded 1.16).
    Fix 4: taxTyCd read from the item's tax_code/vat_exempt snapshot so
           zero-rated and exempt goods file correctly with KRA.
    """
    vat_rate = Decimal(str(settings.VAT_RATE))  # e.g., Decimal("0.16")
    line_total = Decimal(str(item["line_total"]))

    # Determine the KRA tax type code from the item snapshot.
    # B = standard rate, E = VAT-exempt, Z = zero-rated.
    if item.get("vat_exempt"):
        tax_ty_cd = "E"
        taxbl_amt = round(float(line_total), 2)
        tax_amt = 0.0
        sply_amt = round(float(line_total), 2)
    else:
        raw_code = (item.get("tax_code") or "B").upper()
        if raw_code == "Z":
            tax_ty_cd = "Z"
            taxbl_amt = round(float(line_total), 2)
            tax_amt = 0.0
            sply_amt = round(float(line_total), 2)
        else:
            # Standard rate (code "B" or anything else)
            # line_total is already VAT-exclusive (net)
            tax_ty_cd = "B"
            taxbl_amt = round(float(line_total), 2)
            tax_amt_decimal = line_total * vat_rate
            tax_amt = round(float(tax_amt_decimal), 2)
            sply_amt = round(float(line_total + tax_amt_decimal), 2)

    return {
        "itemNm":   item["product_name"],
        "qty":      item["qty"],
        "prc":      round(float(item["unit_price"]), 2),
        "splyAmt":  sply_amt,
        "dcAmt":    round(float(item.get("discount", 0)), 2),
        "taxblAmt": taxbl_amt,
        "taxAmt":   tax_amt,
        "taxTyCd":  tax_ty_cd,
    }


# Returned whenever eTIMS is unavailable or rejects the submission.
# The transaction is already saved; a background job retries failed invoices.
_FAILED_RESULT = {"etims_invoice_no": None, "etims_qr_code": None, "etims_synced": False}


async def submit_invoice(txn_data: dict, store=None) -> dict:
    """
    Submit a completed sale to KRA eTIMS and return the invoice number + QR URL.

    Args:
        txn_data: dict with keys:
            txn_number (str), total (Decimal|float), vat_amount (Decimal|float),
            created_at (datetime), items (list of dicts with product_name, qty,
            unit_price, line_total, discount)
        store: Optional Store ORM object to read per-store eTIMS credentials from.
               If not provided or credentials incomplete, falls back to global settings.

    Returns:
        dict with:
            etims_invoice_no (str|None)
            etims_qr_code    (str|None)  -- URL provided by KRA, not generated locally
            etims_synced     (bool)

    This function NEVER raises. Any exception -> returns _FAILED_RESULT.
    """
    # ─────────────────────────────────────────────────────────────────
    # STEP 1: Resolve credentials — per-store or global fallback
    # ─────────────────────────────────────────────────────────────────
    pin = None
    branch = None
    serial = None

    # Check for per-store credentials first
    if store and store.has_etims_credentials:
        try:
            pin = decrypt_value(store.etims_pin)
            branch = store.etims_branch_id or "00"
            serial = decrypt_value(store.etims_device_serial)
            logger.debug(
                "Using per-store eTIMS credentials for store_id=%s",
                store.id,
            )
        except Exception as exc:
            logger.error(
                "Failed to decrypt per-store eTIMS credentials for store_id=%s: %s",
                store.id, exc,
            )
            return _FAILED_RESULT
    else:
        # Fall back to global settings
        pin = settings.ETIMS_PIN
        branch = settings.ETIMS_BRANCH_ID
        serial = settings.ETIMS_DEVICE_SERIAL
        if store:
            logger.debug(
                "Using global eTIMS credentials (store_id=%s has no per-store config)",
                store.id,
            )

    # 1. Skip entirely if eTIMS is not configured (dev / unconfigured store)
    if not pin:
        txn_num = txn_data.get("txn_number", "unknown")
        store_id = store.id if store else "unknown"
        logger.warning(
            "eTIMS not configured for store_id=%s -- skipping submission for txn=%s",
            store_id, txn_num,
        )
        return _FAILED_RESULT

    # 2. Use ETIMS_URL from settings (developer switches sandbox <-> production here)
    base_url = settings.ETIMS_URL

    # 3. Build the KRA VSCU payload
    payload = {
        "tpin":         pin,
        "bhfId":        branch,
        "invcNo":       txn_data["txn_number"],
        "salesDt":      txn_data["created_at"].strftime("%Y%m%d"),
        "totTaxblAmt":  round(float(txn_data["total"]) - float(txn_data["vat_amount"]), 2),
        "totTax":       round(float(txn_data["vat_amount"]), 2),
        "totAmt":       round(float(txn_data["total"]), 2),
        "itemList": [
            _build_item_payload(item)
            for item in txn_data["items"]
        ],
    }

    # 4 & 5. POST to KRA, parse result
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base_url}/vscu/req",
                json=payload,
                headers={
                    "bhfId":        branch,
                    "dvcSrlNo":     serial,
                    "Content-Type": "application/json",
                },
            )
            data = response.json()

        result_code = data.get("resultCd")

        if result_code == "000":
            return {
                "etims_invoice_no": data["rcptNo"],
                "etims_qr_code":    data.get("qrCodeUrl", ""),
                "etims_synced":     True,
            }

        logger.error(
            "eTIMS rejection for %s -- resultCd=%s, resultMsg=%s",
            txn_data.get("txn_number"),
            result_code,
            data.get("resultMsg", "no message"),
        )
        return _FAILED_RESULT

    except Exception as exc:
        logger.error(
            "eTIMS submission error for %s: %s",
            txn_data.get("txn_number", "unknown"),
            exc,
        )
        return _FAILED_RESULT
