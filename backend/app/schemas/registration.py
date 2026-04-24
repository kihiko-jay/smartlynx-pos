"""Pydantic schemas for store registration, password reset, and employee management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.employee import Role


class StoreRegistrationRequest(BaseModel):
    store_name: str = Field(..., min_length=1, max_length=200)
    store_location: Optional[str] = Field(None, max_length=300)
    store_email: Optional[EmailStr] = None
    store_phone: Optional[str] = Field(None, max_length=20)
    store_kra_pin: Optional[str] = Field(None, max_length=50)
    admin_full_name: str = Field(..., min_length=1, max_length=150)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8, max_length=200)
    mpesa_enabled: Optional[bool] = Field(False)
    mpesa_consumer_key: Optional[str] = Field(None, max_length=200)
    mpesa_consumer_secret: Optional[str] = Field(None, max_length=200)
    mpesa_shortcode: Optional[str] = Field(None, max_length=20)
    mpesa_passkey: Optional[str] = Field(None, max_length=200)
    mpesa_callback_url: Optional[str] = Field(None, max_length=300)
    mpesa_till_number: Optional[str] = Field(None, max_length=20)


class StoreRegistrationResponse(BaseModel):
    store_id: int
    store_name: str
    admin_id: int
    admin_email: str
    message: str
    trial_ends_at: datetime


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    token: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=200)


class EmployeeCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=150)
    username: str = Field(..., min_length=3, max_length=50, description="Unique username for login")
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8, max_length=200)
    role: Role
    terminal_id: Optional[str] = Field(None, max_length=20)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        has_upper = any(ch.isupper() for ch in value)
        has_lower = any(ch.islower() for ch in value)
        has_digit = any(ch.isdigit() for ch in value)
        has_symbol = any(not ch.isalnum() for ch in value)
        if not (has_upper and has_lower and has_digit and has_symbol):
            raise ValueError(
                "Password must include at least one uppercase letter, one lowercase letter, one number, and one symbol."
            )
        return value

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not value.isalnum() and not all(c.isalnum() or c == '_' for c in value):
            raise ValueError("Username can only contain letters, numbers, and underscores")
        return value.lower()


class EmployeeUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=150)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    role: Optional[Role] = None
    terminal_id: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: Optional[str]) -> Optional[str]:
        if value:
            if not value.isalnum() and not all(c.isalnum() or c == '_' for c in value):
                raise ValueError("Username can only contain letters, numbers, and underscores")
            return value.lower()
        return value


class EmployeeOut(BaseModel):
    id: int
    store_id: Optional[int] = None
    full_name: str
    email: str
    username: Optional[str] = None
    phone: Optional[str]
    role: str
    terminal_id: Optional[str]
    is_active: bool
    last_login_at: Optional[datetime] = None
    clocked_in_at: Optional[datetime] = None
    clocked_out_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime]

    @classmethod
    def from_orm(cls, employee):
        return cls(
            id=employee.id,
            store_id=employee.store_id,
            full_name=employee.full_name,
            email=employee.email,
            username=employee.user_name,
            phone=employee.phone,
            role=employee.role.value,
            terminal_id=employee.terminal_id,
            is_active=employee.is_active,
            last_login_at=employee.last_login_at,
            clocked_in_at=employee.clocked_in_at,
            clocked_out_at=employee.clocked_out_at,
            created_at=employee.created_at,
            updated_at=employee.updated_at,
        )

    class Config:
        from_attributes = True


class EmployeeListResponse(BaseModel):
    employees: list[EmployeeOut]
    total: int


class EmployeeCreateResponse(BaseModel):
    id: int
    full_name: str
    email: str
    username: Optional[str] = None
    role: str
    is_active: bool
    message: str


class CurrentUserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    store_id: Optional[int]
    store_name: Optional[str]


class StoreMpesaConfigUpdateRequest(BaseModel):
    mpesa_enabled: Optional[bool] = None
    mpesa_consumer_key: Optional[str] = Field(None, max_length=200)
    mpesa_consumer_secret: Optional[str] = Field(None, max_length=200)
    mpesa_shortcode: Optional[str] = Field(None, max_length=20)
    mpesa_passkey: Optional[str] = Field(None, max_length=200)
    mpesa_callback_url: Optional[str] = Field(None, max_length=300)
    mpesa_till_number: Optional[str] = Field(None, max_length=20)