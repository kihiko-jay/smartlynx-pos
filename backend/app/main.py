"""
Smartlynx FastAPI application entry point — v4.5.1

v4.0 changes (from v3 / v2.4):
  - Full store isolation enforced on all endpoints (products, reports,
    transactions, customers, categories, suppliers)
  - PLATFORM_OWNER role — bypasses store scoping for support/ops visibility
  - Per-store cache keys — Shop A cache never pollutes Shop B
  - Customer store_id FK — customers are now scoped to their shop
  - Per-store SKU and barcode uniqueness (migrations 0006 + 0007)
  - NUMERIC(12,2) on customer credit columns (float → exact decimal)
  - Store name/location sourced from DB record on Z-tape and reports
  - All previously suggested fixes applied and validated
"""

import logging
import os
import time
import asyncio
from contextlib import asynccontextmanager
import hmac as _hmac
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.middleware import RequestLoggingMiddleware, APIRateLimitMiddleware
from app.core.versioning import APIVersionMiddleware
from app.core.cache import cache
from app.core.deps import init_rate_limiters, api_rate_limiter
from app.core.distributed_auth import auth_state
from app.core.pubsub import ws_pubsub
from app.database import verify_db_connection, engine
from app.core.notifier import manager as ws_manager
from app.core.metrics import metrics


def _validate_startup_configuration() -> None:
    weak_secret_markers = {
        "CHANGE_ME_generate_with_openssl_rand_-hex_32",
        "change_me_to_a_long_random_secret",
        "change_me",
        "",
    }
    if settings.SECRET_KEY in weak_secret_markers or settings.SECRET_KEY.startswith("CHANGE_ME"):
        raise RuntimeError("SECRET_KEY must be changed before startup")
    if len(settings.SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters long")
    if settings.is_production and ("*" in settings.origins or settings.ALLOWED_ORIGIN_REGEX == ".*"):
        raise RuntimeError("Wildcard CORS is not allowed in production")
    if settings.is_production:
        if settings.DEBUG:
            raise RuntimeError("DEBUG must be false in production")
        if not settings.INTERNAL_API_KEY:
            raise RuntimeError("INTERNAL_API_KEY must be set in production")
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL must be configured in production for multi-worker auth and rate limiting")
        if not settings.MPESA_WEBHOOK_SECRET:
            raise RuntimeError("MPESA_WEBHOOK_SECRET must be set in production")
        if settings.MPESA_ENV.lower() == "sandbox":
            raise RuntimeError("MPESA_ENV cannot be sandbox in production")
        if "sbx" in settings.ETIMS_URL:
            raise RuntimeError("ETIMS_URL cannot point to sandbox in production")
        if settings.frontend_is_local:
            raise RuntimeError("FRONTEND_URL cannot point to localhost in production")
        if any("localhost" in origin or "127.0.0.1" in origin for origin in settings.origins):
            raise RuntimeError("ALLOWED_ORIGINS cannot contain localhost entries in production")
        if "CHANGE_ME" in settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL still contains placeholder values")
        if settings.mail_enabled and not settings.PASSWORD_RESET_URL:
            raise RuntimeError("PASSWORD_RESET_URL must be set when email delivery is enabled")
        if settings.DEPLOYMENT_MODE.lower() not in {"single_store", "multi_branch"}:
            raise RuntimeError("DEPLOYMENT_MODE must be either single_store or multi_branch")
        if settings.NODE_ROLE.lower() not in {"store_server", "hq_cloud"}:
            raise RuntimeError("NODE_ROLE must be store_server or hq_cloud")
        if settings.is_multi_branch and settings.NODE_ROLE == "store_server" and not settings.BRANCH_CODE:
            raise RuntimeError("BRANCH_CODE must be set for multi-branch store_server deployments")

from app.routers import (
    auth, products, transactions, reports, mpesa,
    etims, subscription, audit, sync, ws, platform, procurement, accounting, employees,
    reconciliation, returns, customers, expenses, cash_sessions,
)

setup_logging()
logger = logging.getLogger("smartlynx.main")


def _init_sentry() -> None:
    dsn = settings.SENTRY_DSN
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.1,
            environment="production" if not settings.DEBUG else "development",
            release=settings.APP_VERSION,
        )
        logger.info("Sentry error tracking initialised")
    except ImportError:
        logger.info("sentry-sdk not installed — error tracking disabled")
    except Exception as exc:
        logger.warning("Sentry init failed (non-fatal): %s", exc)


_redis_sync_client = None
_app_start_time    = time.monotonic()   # used by /health and /health/deep for uptime


async def _init_redis() -> None:
    global _redis_sync_client
    if not settings.REDIS_URL:
        logger.info("REDIS_URL not set — cache and distributed rate limiting disabled")
        return
    await cache.init()
    try:
        import redis as _redis_sync
        _redis_sync_client = _redis_sync.from_url(
            settings.REDIS_URL,
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=False,
        )
        _redis_sync_client.ping()
        logger.info("Redis sync client connected (rate limiters)")
        auth_state.init(_redis_sync_client)
    except Exception as exc:
        logger.warning("Redis sync client unavailable: %s", exc)
        _redis_sync_client = None
    init_rate_limiters(_redis_sync_client)
    await ws_pubsub.start(settings.REDIS_URL)


async def _cleanup_stale_mpesa() -> None:
    """
    Startup task: find PENDING M-PESA transactions older than 10 minutes,
    restore their stock movements, and mark them FAILED/VOIDED.

    Runs once at startup to handle any transactions that were abandoned during
    the previous process lifetime (e.g. crash before Daraja callback arrived).
    """
    from datetime import datetime, timedelta, timezone
    from app.database import SessionLocal
    from app.models.transaction import Transaction, TransactionStatus, PaymentMethod
    from app.models.product import Product, StockMovement

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        stale = (
            db.query(Transaction)
            .filter(
                Transaction.status         == TransactionStatus.PENDING,
                Transaction.payment_method == PaymentMethod.MPESA,
                Transaction.created_at     <  cutoff,
            )
            .all()
        )

        if not stale:
            logger.info("M-PESA cleanup: no stale pending transactions found")
            return

        logger.warning("M-PESA cleanup: voiding %d stale pending transactions", len(stale))

        for txn in stale:
            try:
                # Restore stock for each line item
                for item in txn.items:
                    product = (
                        db.query(Product)
                        .filter(Product.id == item.product_id)
                        .with_for_update()
                        .first()
                    )
                    if product:
                        qty_before             = product.stock_quantity
                        product.stock_quantity += item.qty
                        db.add(StockMovement(
                            product_id    = product.id,
                            store_id      = txn.store_id,
                            movement_type = "mpesa_timeout_restore",
                            qty_delta     = item.qty,
                            qty_before    = qty_before,
                            qty_after     = product.stock_quantity,
                            ref_id        = txn.txn_number,
                            performed_by  = None,
                        ))

                txn.status = TransactionStatus.VOIDED
                logger.info(
                    "M-PESA cleanup: voided stale txn %s (created %s)",
                    txn.txn_number, txn.created_at,
                )
            except Exception as exc:
                logger.error("M-PESA cleanup: failed to void txn %s: %s", txn.txn_number, exc)
                db.rollback()
                continue

        db.commit()
        logger.info("M-PESA cleanup complete: %d transactions voided", len(stale))

    except Exception as exc:
        db.rollback()
        logger.error("M-PESA cleanup task failed: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s API v%s [%s]", settings.APP_NAME, settings.APP_VERSION, settings.deployment_label)
    _validate_startup_configuration()
    _init_sentry()
    await _init_redis()
    verify_db_connection()

    # Clean up any M-PESA transactions left PENDING from a previous run
    await _cleanup_stale_mpesa()

    sync_key = os.getenv("SYNC_AGENT_API_KEY", "")
    if sync_key and sync_key != "disabled":
        logger.info("Sync agent API key configured")

    if not settings.MPESA_WEBHOOK_SECRET:
        logger.warning("MPESA_WEBHOOK_SECRET not set. Webhook signature verification disabled.")
    if settings.MPESA_ENV.lower() == "sandbox":
        logger.warning("M-PESA is running in sandbox mode")
    if "sbx" in settings.ETIMS_URL:
        logger.warning("eTIMS is configured for sandbox mode")

    if settings.is_production:
        logger.info("✅ %s started in production mode", settings.APP_NAME)
    else:
        logger.info("✅ %s started — docs available at /docs", settings.APP_NAME)
    yield

    logger.info("Shutting down. Final metrics: %s", metrics.snapshot())
    await cache.close()
    await ws_pubsub.stop()
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version=settings.APP_VERSION,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    openapi_url=settings.openapi_url,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Idempotency-Key", "X-Internal-Key"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(APIRateLimitMiddleware)
app.add_middleware(APIVersionMiddleware)


PREFIX = "/api/v1"
app.include_router(auth.router,             prefix=PREFIX)
app.include_router(products.router,         prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(customers.router,        prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(transactions.router,     prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(reports.router,          prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(mpesa.router,            prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(etims.router,            prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(subscription.router,     prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(audit.router,            prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(sync.router,             prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(platform.router,         prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(procurement.router,      prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(accounting.router,       prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(employees.router,        prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(reconciliation.router,   prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(returns.router,          prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(returns.txn_returns_router, prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(ws.router)


def _require_internal_key(x_internal_key: str = Header(None)):
    expected = settings.INTERNAL_API_KEY
    if not expected:
        raise HTTPException(status_code=503, detail="Internal API key not configured")
    if not _hmac.compare_digest(x_internal_key or "", expected):
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Health endpoints ──────────────────────────────────────────────────────────
#
# Three-tier health system:
#
#   GET /health      — Liveness probe (no I/O, always fast).
#                     Returns 200 while the process is alive.
#                     Docker/Kubernetes uses this to decide whether to restart.
#                     Contains NO topology internals (anonymous access).
#
#   GET /ready       — Readiness probe (DB + Redis probe).
#                     Returns 503 if database is unreachable.
#                     Redis failure → 200 with status="degraded" (Redis is optional).
#                     Docker Compose depends_on uses this to gate sync-agent start.
#
#   GET /health/deep — Full diagnostics (INTERNAL_API_KEY required).
#                     Live DB and Redis probes, metrics, uptime, topology.
#                     Never exposed to the public internet.


@app.get("/health", tags=["Health"])
def health():
    """
    Liveness probe — no I/O, no DB, no Redis.

    Returns 200 as long as the process is alive and the event loop is running.
    Docker restarts the container only when this endpoint stops responding.

    Intentionally returns minimal data — no topology internals that could
    reveal deployment architecture to unauthenticated callers.
    """
    return {
        "status":        "ok",
        "version":       settings.APP_VERSION,
        "uptime_seconds": round(time.monotonic() - _app_start_time),
    }


@app.get("/healthz", tags=["Health"], include_in_schema=False)
def healthz():
    """
    Kubernetes-convention liveness alias for GET /health.

    Some Kubernetes ingress controllers, GKE, EKS, and monitoring stacks
    (e.g. Prometheus Blackbox Exporter) probe /healthz by convention.
    This is a thin, zero-I/O wrapper — identical contract to /health:
      - Always returns 200 while the process is alive
      - Never probes DB or Redis
      - Never exposes topology internals
      - No authentication required

    include_in_schema=False deliberately omits this from /docs and
    /openapi.json to avoid polluting the public API surface.
    """
    return health()


@app.get("/ready", tags=["Health"])
def ready():
    """
    Readiness probe — verifies the app can serve actual requests.

    Probes:
      - Database: SELECT 1 with 3-second statement timeout.
        FAILS  → HTTP 503.  DB down = cannot serve any request.
      - Redis:    PING with 2-second socket timeout.
        FAILS  → HTTP 200 with redis='unavailable', status='degraded'.
        Redis is optional — the app degrades gracefully without it.

    Used by:
      - docker-compose 'condition: service_healthy' on api service
      - Kubernetes readinessProbe
      - Load balancer health checks

    Returns 503 only if the database is unreachable.
    """
    from sqlalchemy import text, exc as sa_exc
    from fastapi.responses import JSONResponse

    # ── DB probe ───────────────────────────────────────────────────────────────
    db_status = "ok"
    db_error  = None
    try:
        with engine.connect() as conn:
            # Cap the probe at 3 seconds — same as Docker's timeout/2
            if not engine.dialect.name == "sqlite":
                conn.execute(text("SET LOCAL statement_timeout = '3s'"))
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "error"
        db_error  = "database unreachable"   # never leak conn details
        logger.error("Readiness probe: DB check failed: %s", exc)

    # ── Redis probe ────────────────────────────────────────────────────────────
    redis_status = "ok"
    if not settings.REDIS_URL:
        redis_status = "not_configured"
    elif _redis_sync_client is None:
        redis_status = "unavailable"
    else:
        try:
            _redis_sync_client.ping()
        except Exception as exc:
            redis_status = "unavailable"
            logger.warning("Readiness probe: Redis check failed: %s", exc)

    # ── Determine overall status ───────────────────────────────────────────────
    is_ready  = (db_status == "ok")
    is_degraded = (redis_status in {"unavailable"} and db_status == "ok")

    body = {
        "status":  "ok" if is_ready and not is_degraded else ("degraded" if is_ready else "not_ready"),
        "version": settings.APP_VERSION,
        "checks": {
            "database": db_status,
            "redis":    redis_status,
        },
    }
    if db_error:
        body["checks"]["database_error"] = db_error

    status_code = 200 if is_ready else 503
    return JSONResponse(content=body, status_code=status_code)


@app.get("/health/deep", tags=["Health"])
def health_deep(_: None = Depends(_require_internal_key)):
    """
    Full diagnostic check — protected by INTERNAL_API_KEY.

    Includes:
      - Live DB probe (SELECT 1)
      - Live Redis probe (PING via sync client)
      - WebSocket terminal count
      - In-process metrics snapshot
      - Process uptime and start timestamp
      - Full deployment topology (safe behind key gate)

    Never expose this endpoint to the public internet.
    """
    from sqlalchemy import text

    # ── DB probe ───────────────────────────────────────────────────────────────
    db_ok    = False
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)

    # ── Redis probe (live, not just flag check) ────────────────────────────────
    redis_detail = "not_configured"
    if settings.REDIS_URL:
        if _redis_sync_client is None:
            redis_detail = "client_not_initialised"
        else:
            try:
                _redis_sync_client.ping()
                redis_detail = "ok"
            except Exception as exc:
                redis_detail = f"error: {exc}"

    uptime_s = round(time.monotonic() - _app_start_time)
    start_iso = datetime.fromtimestamp(
        time.time() - uptime_s, tz=timezone.utc
    ).isoformat()

    return {
        "status":          "ok" if db_ok else "degraded",
        "version":         settings.APP_VERSION,
        "uptime_seconds":  uptime_s,
        "started_at":      start_iso,
        "checks": {
            "database": "ok" if db_ok else f"error: {db_error}",
            "redis":    redis_detail,
            "cache":    "ok" if cache.enabled else "disabled",
        },
        "ws_terminals":    len(ws_manager.connected_terminals),
        "metrics":         metrics.snapshot(),
        "deployment": {
            "mode":            settings.DEPLOYMENT_MODE,
            "node_role":       settings.NODE_ROLE,
            "branch_code":     settings.BRANCH_CODE or None,
            "hq_sync_enabled": settings.ENABLE_HQ_SYNC,
            "environment":     settings.ENVIRONMENT,
        },
    }


@app.get("/metrics", tags=["Observability"])
def get_metrics(_: None = Depends(_require_internal_key)):
    snap  = metrics.snapshot()
    lines = []
    for key, val in snap.get("counters", {}).items():
        safe = key.replace(".", "_").replace("-", "_").replace(",", "_").replace("=", "_")
        lines.append(f"smartlynx_{safe} {val}")
    return {**snap, "prometheus": "\n".join(lines)}

app.include_router(expenses.router,       prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
app.include_router(cash_sessions.router,  prefix=PREFIX, dependencies=[Depends(api_rate_limiter)])
