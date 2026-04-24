
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class CashSession(Base):
    __tablename__ = "cash_sessions"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    cashier_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    terminal_id = Column(String(50), nullable=True, index=True)
    session_number = Column(String(30), nullable=False, unique=True, index=True)
    opening_float = Column(Numeric(12, 2), nullable=False, default=0)
    expected_cash = Column(Numeric(12, 2), nullable=False, default=0)
    counted_cash = Column(Numeric(12, 2), nullable=True)
    counted_mpesa = Column(Numeric(12, 2), nullable=True, default=0)
    counted_card = Column(Numeric(12, 2), nullable=True, default=0)
    counted_credit = Column(Numeric(12, 2), nullable=True, default=0)
    counted_store_credit = Column(Numeric(12, 2), nullable=True, default=0)
    total_counted = Column(Numeric(12, 2), nullable=True)
    variance = Column(Numeric(12, 2), nullable=True)
    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    opened_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    notes = Column(Text, nullable=True)

    cashier = relationship("Employee", foreign_keys=[cashier_id])
    opener = relationship("Employee", foreign_keys=[opened_by])
    closer = relationship("Employee", foreign_keys=[closed_by])
