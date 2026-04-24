from pydantic_settings import BaseSettings
from typing import List
from decimal import Decimal

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Smartlynx"
    APP_VERSION: str = "4.5.1"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Deployment topology
    DEPLOYMENT_MODE: str = "single_store"  # single_store | multi_branch
    NODE_ROLE: str = "store_server"        # store_server | hq_cloud
    BRANCH_CODE: str = ""
    BRANCH_NAME: str = ""
    HQ_REGION: str = "kenya"
    ENABLE_HQ_SYNC: bool = False
    STORE_SERVER_HOST: str = "localhost"

    # CORS / frontend
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
    ALLOWED_ORIGIN_REGEX: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ALLOW_CREDENTIALS: bool = True

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    SECRET_ENCRYPTION_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_HOURS: int = 9
    WEB_AUTH_USE_COOKIES: bool = True
    REFRESH_COOKIE_NAME: str = "smartlynx_refresh"
    REFRESH_COOKIE_SECURE: bool = True
    REFRESH_COOKIE_SAMESITE: str = "lax"
    REFRESH_COOKIE_DOMAIN: str = ""
    AUTH_COOKIE_NAME: str = "smartlynx_refresh"
    AUTH_COOKIE_SECURE: bool = True
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_DOMAIN: str = ""

    # Internal API key (protects /health/deep and /metrics in production)
    INTERNAL_API_KEY: str = ""
    SYNC_AGENT_API_KEY: str | None = None

    # Redis (optional — enables multi-worker rate limiting, distributed auth, product cache, WS pub/sub)
    REDIS_URL: str = ""

    # Trusted proxy CIDRs — only these connecting IPs may set X-Forwarded-For.
    TRUSTED_PROXY_CIDRS: str = "127.0.0.1/32"

    # Rate limiting
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_API_PER_MINUTE: int = 300

    # Error tracking
    SENTRY_DSN: str = ""

    # M-PESA global fallbacks
    MPESA_CONSUMER_KEY: str = ""
    MPESA_CONSUMER_SECRET: str = ""
    MPESA_SHORTCODE: str = "174379"
    MPESA_PASSKEY: str = ""
    MPESA_CALLBACK_URL: str = ""
    MPESA_ENV: str = "sandbox"
    MPESA_WEBHOOK_SECRET: str = ""

    # KRA eTIMS
    ETIMS_URL: str = "https://etims-api.kra.go.ke/etims-api"
    ETIMS_PIN: str = ""
    ETIMS_BRANCH_ID: str = "00"
    ETIMS_DEVICE_SERIAL: str = ""

    # Email delivery
    MAIL_FROM: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    PASSWORD_RESET_URL: str = ""

    # Store
    STORE_NAME: str = "My Smartlynx Store"
    STORE_LOCATION: str = "Nairobi, Kenya"
    STORE_TIMEZONE: str = "Africa/Nairobi"
    VAT_RATE: float = 0.16
    CURRENCY: str = "KES"
    CASH_VARIANCE_THRESHOLD: Decimal = Decimal("1000.00")
    
    @property
    def origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def docs_url(self) -> str | None:
        return None if self.is_production else "/docs"

    @property
    def redoc_url(self) -> str | None:
        return None if self.is_production else "/redoc"

    @property
    def openapi_url(self) -> str | None:
        return None if self.is_production else "/openapi.json"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod"}

    @property
    def mail_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.MAIL_FROM)

    @property
    def frontend_is_local(self) -> bool:
        frontend = (self.FRONTEND_URL or "").lower()
        return "localhost" in frontend or "127.0.0.1" in frontend

    @property
    def is_multi_branch(self) -> bool:
        return self.DEPLOYMENT_MODE.lower() == "multi_branch"

    @property
    def deployment_label(self) -> str:
        branch = f" ({self.BRANCH_CODE})" if self.BRANCH_CODE else ""
        return f"{self.DEPLOYMENT_MODE}:{self.NODE_ROLE}{branch}"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
