# SmartLynX Alembic Profiles

SmartLynX now has two migration entry paths:

- `legacy` profile: upgrades existing customer databases through historical migrations.
- `bootstrap` profile: initializes a brand new empty database in final schema form.

Both paths converge at revision `2000`, and all future migrations must depend on `2000`.

## Profile commands

Run from `backend/`:

```bash
# Existing deployed databases (safe default profile)
alembic -c alembic/alembic.ini -x profile=legacy upgrade head

# Brand new empty database on a fresh machine
alembic -c alembic/alembic.ini -x profile=bootstrap upgrade head
```

If `-x profile=...` is omitted, Alembic defaults to `legacy`.

## Which profile to use

- Use `legacy` when a database already contains historical SmartLynX POS data/tables.
- Use `bootstrap` only when the database is empty and has never been migrated.

Do not run `bootstrap` against an existing customer database.

## Directory layout

- `alembic/versions_legacy/`: historical upgrade chain (`0001` ... `0032`).
- `alembic/versions_bootstrap/`: fresh-install bootstrap chain (`1000` ...).
- `alembic/versions_common/`: convergence merge and future shared migrations.

## Future migration rule

After this change, new migrations should target `alembic/versions_common/` and use:

- `down_revision = "2000"` for the next migration after convergence.

## Validation workflow

### 1) Fresh empty database

```bash
dropdb --if-exists smartlynx_bootstrap_test
createdb smartlynx_bootstrap_test
DATABASE_URL=postgresql://<user>:<pass>@<host>:5432/smartlynx_bootstrap_test \
  alembic -c alembic/alembic.ini -x profile=bootstrap upgrade head
```

Expected:

- migration completes at head with no missing-table errors
- core tables exist (`stores`, `employees`, `products`, `transactions`, `transaction_items`)
- `store_id` is `NOT NULL` where required by current models

### 2) Legacy upgrade database

```bash
# Point DATABASE_URL at an existing pre-convergence customer DB
DATABASE_URL=postgresql://<user>:<pass>@<host>:5432/<existing_db> \
  alembic -c alembic/alembic.ini -x profile=legacy upgrade head
```

Expected:

- historical migrations apply safely
- no regression in customer data
- revision reaches the same converged head as bootstrap path
