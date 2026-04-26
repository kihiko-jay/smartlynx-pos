import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Enum,
    Numeric,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ────────────────────────────────────────────────────────────────
# ENUMS
# ────────────────────────────────────────────────────────────────

class Plan(str, enum.Enum):
    FREE    = "free"      # POS only — forever free
    STARTER = "starter"   # KES 1,500/mo — 1 store
    GROWTH  = "growth"    # KES 3,500/mo — up to 3 stores
    PRO     = "pro"       # KES 7,500/mo — unlimited + API


class SubStatus(str, enum.Enum):
    ACTIVE    = "active"
    TRIALING  = "trialing"
    EXPIRED   = "expired"
    CANCELLED = "cancelled"


# ────────────────────────────────────────────────────────────────
# STORE MODEL (TENANT)
# ────────────────────────────────────────────────────────────────

class Store(Base):
    __tablename__ = "stores"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(200), nullable=False)
    location      = Column(String(300), nullable=True)
    kra_pin       = Column(String(50), nullable=True)
    phone         = Column(String(20), nullable=True)
    email         = Column(String(200), nullable=True)

    # ── Subscription ─────────────────────────────────────────────
    plan          = Column(Enum(Plan), default=Plan.FREE, nullable=False)
    sub_status    = Column(Enum(SubStatus), default=SubStatus.TRIALING, nullable=False)

    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    sub_ends_at   = Column(DateTime(timezone=True), nullable=True)

    # Billing (M-PESA) — for subscription payments
    mpesa_phone   = Column(String(20), nullable=True)
    billing_ref   = Column(String(100), nullable=True)

    # M-PESA Configuration (per-store) — for customer payments
    mpesa_enabled         = Column(Boolean, default=False)
    mpesa_consumer_key    = Column(String(200), nullable=True)
    mpesa_consumer_secret = Column(String(200), nullable=True)
    mpesa_shortcode       = Column(String(20), nullable=True)   # Paybill
    mpesa_passkey         = Column(String(200), nullable=True)
    mpesa_callback_url    = Column(String(300), nullable=True)
    mpesa_till_number     = Column(String(20), nullable=True)   # Alternative to shortcode

    # eTIMS Configuration (per-store)
    etims_enabled       = Column(Boolean, default=False, nullable=False)
    etims_pin           = Column(String(200), nullable=True)   # encrypted at rest
    etims_branch_id     = Column(String(10),  nullable=True)   # e.g. "00"
    etims_device_serial = Column(String(200), nullable=True)   # encrypted at rest

    # Metadata
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    employees     = relationship("Employee", back_populates="store")
    payments      = relationship("SubPayment", back_populates="store")
    invitations   = relationship("StoreInvitation", back_populates="store")  # NOT YET IMPLEMENTED — no router exists for this relationship

    # ─────────────────────────────────────────────────────────────
    # BUSINESS LOGIC
    # ─────────────────────────────────────────────────────────────

    @property
    def is_premium(self) -> bool:
        """
        Determines if store has access to premium features.
        """
        now = datetime.now(timezone.utc)

        # Trial still valid
        if self.sub_status == SubStatus.TRIALING:
            return bool(self.trial_ends_at and self.trial_ends_at > now)

        # Active paid subscription
        if self.sub_status == SubStatus.ACTIVE:
            return self.sub_ends_at is None or self.sub_ends_at > now

        return False

    @property
    def has_etims_credentials(self) -> bool:
        """
        Check if this store has configured all required eTIMS credentials.
        
        Returns True only if etims_enabled is True AND both etims_pin and
        etims_device_serial are set (not None and not empty).
        """
        return bool(self.etims_enabled and self.etims_pin and self.etims_device_serial)

    @property
    def plan_label(self) -> str:
        return {
            Plan.FREE: "Free",
            Plan.STARTER: "Starter — KES 1,500/mo",
            Plan.GROWTH: "Growth — KES 3,500/mo",
            Plan.PRO: "Pro — KES 7,500/mo",
        }.get(self.plan, str(self.plan))


# ────────────────────────────────────────────────────────────────
# SUBSCRIPTION PAYMENTS
# ────────────────────────────────────────────────────────────────

class SubPayment(Base):
    __tablename__ = "sub_payments"

    id         = Column(Integer, primary_key=True, index=True)
    store_id   = Column(Integer, ForeignKey("stores.id"), nullable=False)

    amount     = Column(Numeric(12, 2), nullable=False)
    plan       = Column(Enum(Plan), nullable=False)

    mpesa_ref  = Column(String(100), nullable=True)
    months     = Column(Integer, default=1)
    status     = Column(String(20), default="pending")  # pending | confirmed

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    store      = relationship("Store", back_populates="payments")