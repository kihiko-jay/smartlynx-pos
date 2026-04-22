# Smartlynx Backend API

Smartlynx is a cloud-native POS and retail operations backend for the Kenyan market, built with FastAPI and PostgreSQL. This backend powers sales, stock control, procurement, M-PESA workflows, audit trails, reporting, and store-level access control.

## Stack
- FastAPI
- PostgreSQL 16 + SQLAlchemy 2
- Alembic migrations
- JWT auth
- Redis for distributed auth, caching, and rate limiting
- M-PESA Daraja integration
- KRA eTIMS integration

## Local development
```bash
cp .env.example .env
pip install -r requirements-dev.txt
alembic -c alembic/alembic.ini -x profile=bootstrap upgrade head
uvicorn app.main:app --reload
```

## Production
1. Copy `.env.production.example` to `.env` and replace every `CHANGE_ME` value.
2. Build the API image.
3. Run migrations before the API starts.
4. Keep FastAPI docs disabled in production.
5. Verify `/health` before sending traffic.

## Useful commands
```bash
# Tests
pytest

# Lint + type check
ruff check app/ tests/
ruff format app/ tests/ --check
pyright app/

# Migrations
alembic -c alembic/alembic.ini -x profile=legacy upgrade head
# or (brand new empty DB)
alembic -c alembic/alembic.ini -x profile=bootstrap upgrade head
```

## Core endpoints
- `/api/v1/auth/*`
- `/api/v1/products/*`
- `/api/v1/transactions/*`
- `/api/v1/reports/*`
- `/api/v1/mpesa/*`
- `/api/v1/procurement/*`
- `/api/v1/accounting/*`
- `/api/v1/sync/*`

## Deployment notes
- Use `backend/docker-compose.prod.yml` for container deployments.
- Use production secrets for `SECRET_KEY`, `INTERNAL_API_KEY`, `SYNC_AGENT_API_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`.
- Set `FRONTEND_URL` and `ALLOWED_ORIGINS` to real live domains only.
- Test backup and restore before the first real client goes live.
