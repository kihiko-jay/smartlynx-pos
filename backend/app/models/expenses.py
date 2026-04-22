
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Date, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ExpenseVoucher(Base):
    __tablename__ = "expense_vouchers"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    voucher_number = Column(String(30), nullable=False, unique=True, index=True)
    expense_date = Column(Date, nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String(20), nullable=False)
    payee = Column(String(200), nullable=True)
    reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_void = Column(Boolean, nullable=False, default=False)
    void_reason = Column(Text, nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    voided_by = Column(Integer, ForeignKey("employees.id"), nullable=True)

    account = relationship("Account")
    creator = relationship("Employee", foreign_keys=[created_by])
    voider = relationship("Employee", foreign_keys=[voided_by])
