# CSV Product Import Implementation

## Overview

This document describes the complete CSV product import functionality for SmartLynx POS. The implementation includes:

1. **CLI Script** (`scripts/import_products_csv.py`) — Bulk import from CSV files
2. **FastAPI Endpoint** (`/products/import/csv`) — Web-based upload with validation
3. **Example CSV Template** (`example_products.csv`) — Reference data format
4. **Schema** (`CSVImportResult`) — Structured import response

---

## 1. CSV Format Specification

### Required Columns

These columns **must** be present in every CSV file:

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| `sku` | String(50) | `MILK-001` | Unique product code per store |
| `name` | String(200) | `Fresh Milk 1L` | Product display name |
| `selling_price` | Decimal(12,2) | `150.00` | Retail price in KES |

### Optional Columns

These columns provide additional product information:

| Column | Type | Default | Example |
|--------|------|---------|---------|
| `barcode` | String(100) | `NULL` | `5901234123457` — EAN/UPC code |
| `itemcode` | Integer | `NULL` | `1001` — Fast POS lookup code |
| `description` | Text | `NULL` | `Fresh whole milk in 1L carton` |
| `category` | String | `NULL` | `Dairy` — Must exist in database |
| `supplier` | String | `NULL` | `Fresh Dairy Ltd` — Must exist in database |
| `cost_price` | Decimal(12,2) | `NULL` | `95.00` — Product cost |
| `vat_exempt` | String | `no` | `yes`/`no`/`true`/`false` |
| `tax_code` | String | `B` | `A` (exempt) or `B` (standard 16%) |
| `stock_quantity` | Integer | `0` | `100` — Initial stock level |
| `reorder_level` | Integer | `10` | `20` — Low stock threshold |
| `unit` | String | `piece` | `kg`, `liter`, `pack`, `box`, etc. |
| `is_active` | String | `yes` | `yes`/`no`/`true`/`false` |

### Column Mapping & Supported Units

#### Unit Values
Accepts common abbreviations, auto-normalized to standard values:

```
Abbreviations → Standard Value
pcs, pc, pieces → piece
kg, kilograms → kilogram
g, grams → gram
l, liter, liters → liter
ml, milliliters → milliliter
pack, packs → pack
box, boxes → box
bottle, bottles → bottle
can, cans → can
carton, cartons → carton
dozen → dozen
bundle → bundle
```

#### Tax Code Values
- `A` = VAT exempt (taxed at 0%)
- `B` = Standard rate (16% VAT) ← default
- Any other value defaults to `B`

#### Boolean Values
Accepts for `vat_exempt` and `is_active`:
- **True**: `yes`, `y`, `1`, `true`, `TRUE`, `True`
- **False**: `no`, `n`, `0`, `false`, `FALSE`, `False`

---

## 2. CLI Import Script

### Usage

```bash
# Basic import
cd backend
python -m scripts.import_products_csv --csv-file products.csv --store-id 1

# Dry run (preview without writing)
python -m scripts.import_products_csv --csv-file products.csv --store-id 1 --dry-run

# Skip individual row errors and continue
python -m scripts.import_products_csv --csv-file products.csv --store-id 1 --skip-errors

# Update existing products (by SKU) instead of skipping
python -m scripts.import_products_csv --csv-file products.csv --store-id 1 --update-existing
```

### Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `--csv-file` | PATH | ✅ Yes | Path to CSV file |
| `--store-id` | INT | ✅ Yes | Target store ID |
| `--dry-run` | Flag | ❌ No | Preview without writing |
| `--skip-errors` | Flag | ❌ No | Continue on individual row errors |
| `--update-existing` | Flag | ❌ No | Update instead of skip existing |

### Script Output

```
======================================================================
  PRODUCT CSV IMPORT
======================================================================
  CSV File:      products.csv
  Store ID:      1
  Dry Run:       False
  Update Mode:   False
  Skip Errors:   False
======================================================================

📖 Reading CSV file...
   ✓ Found 25 data rows

📦 Building category & supplier caches...
   ✓ 5 categories, 3 suppliers

⏳ Processing rows...

   ✓ CREATE  MILK-001: Fresh Milk 1L
   ✓ CREATE  BREAD-001: Wheat Bread 800g
   ↻ UPDATE  RICE-001: Jasmine Rice 2kg
   ✗ SKIP   Row 8: Category 'Unknown' not found

======================================================================
  Total Rows:    25
  Created:       22
  Updated:       2
  Skipped:       1
  Errors:        1

  ⚠️  ERRORS:
     - Row 8: Category 'Unknown' not found
======================================================================
```

### Error Handling

**Errors during import:**
- Row validation errors (invalid price, missing SKU)
- Category not found
- Supplier not found
- Duplicate SKU in CSV file
- Duplicate SKU in database (when `--update-existing` not set)

**Behavior:**
- **Without `--skip-errors`** (default): Stops at first error, rolls back all changes
- **With `--skip-errors`**: Skips error rows, continues importing valid rows
- **With `--dry-run`**: Shows what would happen, rolls back without writing

---

## 3. FastAPI REST Endpoint

### Endpoint

```
POST /products/import/csv
```

### Authentication

Requires `Role.SUPERVISOR` or higher (supervisor, manager, admin, platform_owner).

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `file` | FormData (binary) | required | CSV file (UTF-8 encoded) |
| `update_existing` | boolean | `false` | Update existing products by SKU |

### Request Example

```bash
curl -X POST http://localhost:8000/products/import/csv \
  -H "Authorization: Bearer {token}" \
  -F "file=@products.csv" \
  -F "update_existing=true"
```

### Success Response (200 OK)

```json
{
  "success": true,
  "total_rows": 25,
  "created": 22,
  "updated": 2,
  "skipped": 1,
  "errors": [
    "Row 8: Category 'Unknown' not found"
  ],
  "summary": "Imported 22 new products, updated 2 existing, skipped 1 rows"
}
```

### Error Response (500 Internal Server Error)

```json
{
  "success": false,
  "total_rows": 0,
  "created": 0,
  "updated": 0,
  "skipped": 0,
  "errors": [
    "File processing error: CSV file is empty or has no header row"
  ],
  "summary": "Import failed: CSV file is empty or has no header row"
}
```

### Response Schema

```python
class CSVImportResult(BaseModel):
    success: bool              # Import completed successfully
    total_rows: int            # Total rows processed
    created: int               # New products created
    updated: int               # Existing products updated
    skipped: int               # Rows skipped due to errors
    errors: List[str]          # List of error messages (max 10 shown)
    summary: str               # Human-readable summary
```

---

## 4. Data Validation Rules

### Row-Level Validation

1. **SKU** (required)
   - Cannot be empty
   - Must be unique within CSV file
   - Must be unique within store (unless updating)
   - Max 50 characters

2. **Name** (required)
   - Cannot be empty
   - Max 200 characters

3. **Selling Price** (required)
   - Must be a decimal number ≥ 0.01
   - Rounded to 2 decimal places (KES cents)

4. **Cost Price** (optional)
   - Must be a decimal number if provided
   - Rounded to 2 decimal places

5. **Category** (optional)
   - If provided, must exist in store's categories
   - Case-insensitive matching (`dairy` = `Dairy` = `DAIRY`)

6. **Supplier** (optional)
   - If provided, must exist in store's suppliers
   - Case-insensitive matching

7. **Barcode** (optional)
   - Max 100 characters
   - Must be unique within store (duplicate allowed in update mode)

8. **Item Code** (optional)
   - Must be an integer if provided

### Database Constraints

These are enforced at the database level:

```sql
-- Each store has unique SKU
UNIQUE (store_id, sku)

-- Each store has unique barcode
UNIQUE (store_id, barcode)

-- Foreign key: category must exist
FOREIGN KEY (category_id) REFERENCES categories(id)

-- Foreign key: supplier must exist
FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
```

---

## 5. Example CSV File

### Sample Data (`example_products.csv`)

```csv
sku,name,barcode,itemcode,description,category,supplier,selling_price,cost_price,vat_exempt,tax_code,stock_quantity,reorder_level,unit,is_active
MILK-001,Fresh Milk 1L,5901234123457,1001,Fresh whole milk in 1L carton,Dairy,Fresh Dairy Ltd,150.00,95.00,no,B,100,20,liter,yes
BREAD-001,Wheat Bread 800g,5909876543210,1002,Freshly baked wheat bread loaf,Bakery,Local Bakery,80.00,45.00,no,B,50,15,piece,yes
RICE-001,Jasmine Rice 2kg,5912345678901,1003,Premium jasmine rice from Thailand,Grains,Agro Supplies,350.00,280.00,no,B,200,50,kg,yes
EGGS-001,Eggs (30 pieces),5905555555555,1004,Free-range chicken eggs - 30 pack,Poultry,Poultry Farm Ltd,450.00,320.00,no,B,75,25,pack,yes
```

---

## 6. Multi-Store Isolation

All imports are automatically scoped to the importing user's store:

```python
# Import always creates/updates products in current user's store
product.store_id = current.store_id

# Categories/suppliers filtered by store
category_cache = build_category_cache(db, current.store_id)
supplier_cache = build_supplier_cache(db, current.store_id)
```

**Security guarantee:** Users cannot import products into another store.

---

## 7. Transaction Handling

### Success Path

1. Categories and suppliers pre-validated (must exist)
2. All products added to session
3. Initial stock movements created (if `stock_quantity > 0`)
4. Audit trail logged
5. **Transaction committed** ← All changes become permanent
6. Product list cache invalidated

### Failure Path

1. First validation error encountered
2. **Transaction rolled back** ← No changes saved
3. Error message returned to user
4. User can fix CSV and retry

### Dry Run Path

1. All validations performed (same as success)
2. All processing completed (same as success)
3. **Transaction rolled back** ← No changes saved
4. Summary returned to user for preview

---

## 8. Audit Trail

Every CSV import is logged as a single audit event:

```python
AuditTrail(
    action="csv_import",
    entity="bulk_product_import",
    before_val=None,
    after_val={
        "created": 22,
        "updated": 2,
        "total": 25
    },
    notes="CSV import: Imported 22 new products, updated 2 existing, skipped 1 rows"
)
```

**Queryable by:**
- User who performed import
- Import timestamp
- Store ID
- Number of products created/updated

---

## 9. Performance Considerations

### Load Testing (Estimated)

| Data Size | Time | Notes |
|-----------|------|-------|
| 100 products | 2-3 sec | Single transaction, fast |
| 1,000 products | 15-20 sec | Single transaction, moderate |
| 10,000 products | 2-3 min | Single transaction, slower |

### Optimization Tips

1. **Use CLI script instead of endpoint** for bulk imports (better performance)
2. **Pre-validate CSV** before upload (check SKU uniqueness, prices)
3. **Create categories/suppliers first** (reduces lookups)
4. **Use `--dry-run`** to validate before actual import
5. **Split huge files** (>10K rows) into multiple imports

### Resource Usage

- **Memory:** Proportional to file size (reads entire file into memory)
- **Database:** Single transaction (moderate lock duration)
- **CPU:** Primarily CSV parsing and data validation

---

## 10. Troubleshooting

### Common Errors & Solutions

#### ❌ "CSV file is empty or has no header row"
- **Cause:** CSV file has no column headers
- **Fix:** First row must contain column names

#### ❌ "SKU is required"
- **Cause:** One or more rows have empty SKU column
- **Fix:** Fill all SKU cells (or remove rows)

#### ❌ "Category 'Dairy' not found"
- **Cause:** Category doesn't exist in store
- **Fix:** Create category first, or match exact name case

#### ❌ "Duplicate SKU in CSV"
- **Cause:** Same SKU appears twice in file
- **Fix:** Remove duplicate row or change SKU

#### ❌ "Selling price must be a decimal number"
- **Cause:** Price contains invalid characters (e.g., "KES 150" or "150/2")
- **Fix:** Use only numbers and decimal point: `150.00`

#### ✅ "Row 5: Unexpected error - ..."
- **Cause:** Unhandled validation error
- **Fix:** Check row data, try `--skip-errors` to continue, or contact support

### Testing the Import

```bash
# 1. Create test categories first
curl -X POST http://localhost:8000/products/categories \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Dairy", "description": "Dairy products"}'

# 2. Create test suppliers
curl -X POST http://localhost:8000/products/suppliers \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Fresh Dairy Ltd",
    "phone": "0712345678",
    "email": "info@freshdairy.com"
  }'

# 3. Test dry-run import
python -m scripts.import_products_csv \
  --csv-file products.csv \
  --store-id 1 \
  --dry-run

# 4. Perform actual import
python -m scripts.import_products_csv \
  --csv-file products.csv \
  --store-id 1

# 5. Verify import
curl -X GET http://localhost:8000/products?skip=0&limit=50 \
  -H "Authorization: Bearer {token}"
```

---

## 11. Integration with Frontend

The FastAPI endpoint is ready for frontend file upload implementation:

```javascript
// Example: React component for CSV upload
async function handleCSVUpload(file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('update_existing', false);

  const response = await fetch('/products/import/csv', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  });

  const result = await response.json();
  console.log(`Created: ${result.created}, Updated: ${result.updated}`);
  if (result.errors.length > 0) {
    console.error('Import errors:', result.errors);
  }
}
```

---

## 12. Limitations & Future Enhancements

### Current Limitations

1. Only creates product records (no images imported)
2. No partial/conditional updates (all-or-nothing per row)
3. Categories/suppliers must pre-exist (no inline creation)
4. No duplicate barcode detection during update mode
5. Max file size: ~100MB (FastAPI default)

### Planned Enhancements

1. **Image import** — Process image URLs/attachments
2. **Template export** — Download empty CSV template from UI
3. **Field mapping** — User-defined column order/naming
4. **Batch scheduling** — Schedule imports for off-peak hours
5. **Preview mode** — Show first 10 rows before importing
6. **SKU collision detection** — Alert before overwriting
7. **Rollback history** — Undo previous imports by ID
8. **Performance optimization** — Async processing for huge files

---

## 13. API Documentation (OpenAPI)

The endpoint is fully documented in Swagger UI:

```
GET    http://localhost:8000/docs
POST   /products/import/csv    ← See full OpenAPI schema here
```

**Schema details:**
- Request: `file` (UploadFile), `update_existing` (boolean)
- Response: `CSVImportResult` (see section 3)
- Errors: 401 Unauthorized, 403 Forbidden, 500 Server Error

---

## Example Workflows

### Workflow 1: Initial Store Setup (25 products)

```bash
# 1. Create categories
curl ... POST /products/categories {"name": "Dairy"}
curl ... POST /products/categories {"name": "Bakery"}
curl ... POST /products/categories {"name": "Grains"}

# 2. Create suppliers
curl ... POST /products/suppliers {"name": "Fresh Dairy Ltd", "phone": "..."}
curl ... POST /products/suppliers {"name": "Local Bakery", "phone": "..."}

# 3. Import products (CLI for better performance)
cd backend
python -m scripts.import_products_csv --csv-file products.csv --store-id 1

# Result: 25 products created with initial stock
```

### Workflow 2: Update Pricing (10 products)

```bash
# 1. Extract current products to CSV
# (manual or via /products endpoint export)

# 2. Update selling_price column in CSV

# 3. Re-import with update flag
python -m scripts.import_products_csv \
  --csv-file products_updated.csv \
  --store-id 1 \
  --update-existing

# Result: 10 products updated with new prices
```

### Workflow 3: Test Before Committing (safe approach)

```bash
# 1. Dry-run to preview changes
python -m scripts.import_products_csv \
  --csv-file new_products.csv \
  --store-id 1 \
  --dry-run

# 2. Review output, ensure no errors

# 3. Actual import
python -m scripts.import_products_csv \
  --csv-file new_products.csv \
  --store-id 1

# Result: Confirmed changes are applied
```

---

## Support & Questions

For issues or questions about CSV import:

1. Check **Troubleshooting** section (section 10)
2. Review **Example CSV** file and **Data Validation** rules
3. Verify **categories and suppliers** exist before import
4. Try **--dry-run** mode to preview changes
5. Check application logs for detailed error messages

---

**Last Updated:** April 25, 2026  
**Version:** 1.0  
**Status:** Production Ready ✅
