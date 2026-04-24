from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from app.models.employee import Role


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username or email address")  # Changed from 'email'
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str          # NEW: long-lived refresh token
    token_type: str = "bearer"
    employee_id: int
    full_name: str
    role: Role
    terminal_id: Optional[str]
    store_name: Optional[str]
    store_location: Optional[str]


class EmployeeCreate(BaseModel):
    full_name: str
    username: str = Field(..., description="Unique username for login")  # NEW
    email: str
    phone: Optional[str] = None
    pin: Optional[str] = None
    password: str
    role: Role = Role.CASHIER
    terminal_id: Optional[str] = None


class PinSet(BaseModel):
    pin: str


class PinVerify(BaseModel):
    pin: str


class EmployeeOut(BaseModel):
    id: int
    full_name: str
    username: str  # NEW
    email: str
    phone: Optional[str]
    role: Role
    is_active: bool
    terminal_id: Optional[str]

    class Config:
        from_attributes = True