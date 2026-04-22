"""
Auth router.

Changes vs original:
  - /login now returns access_token + refresh_token (short + long lived)
  - /token/refresh endpoint added — swaps a valid refresh token for a new access token
  - login_rate_limiter dependency applied to /login to prevent brute force
  - /login no longer returns 401 with distinct messages for "no user" vs "bad password"
    (both return the same message to prevent user enumeration)
  - All DB writes are inside explicit transactions
"""

import re
import uuid as _uuid
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response
from sqlalchemy.orm import Session

from app.core.deps import (
    get_db, get_current_employee, require_admin, require_premium,
    login_rate_limiter, get_client_ip,
)
from app.core.security import (
    verify_password, hash_password,
    create_access_token, create_refresh_token, decode_refresh_token,
    revoke_token, generate_password_reset_token, hash_token, verify_token,
    encrypt_sensitive_value, fingerprint_token,
)
from app.core.distributed_auth import auth_state
from app.core.config import settings
from app.core.datetime_utils import ensure_utc_datetime
from app.services.email import send_password_reset_email
from app.services.registration import create_store_with_admin, TRIAL_DAYS

from app.models.employee import Employee, Role
from app.models.subscription import Store, Plan, SubStatus
from app.models.registration import PasswordResetToken
from app.models.auth_session import RefreshSession
from app.schemas.auth import LoginRequest, TokenOut, EmployeeCreate, EmployeeOut, PinSet, PinVerify
from app.schemas.registration import (
    StoreRegistrationRequest,
    StoreRegistrationResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    max_age = settings.REFRESH_TOKEN_EXPIRE_HOURS * 3600
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        max_age=max_age,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        path="/",
    )

# ── WS Ticket store ───────────────────────────────────────────────────────────
_WS_TICKET_TTL = 30  # seconds


def _issue_ws_ticket(employee_id: int) -> str:
    ticket = str(_uuid.uuid4())
    auth_state.issue_ws_ticket(ticket, employee_id, _WS_TICKET_TTL)
    return ticket


def consume_ws_ticket(ticket: str) -> int | None:
    """Validate and consume a one-time WS ticket. Returns employee_id or None."""
    return auth_state.consume_ws_ticket(ticket)


# ── Session helpers ───────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str | None:
    # Reuse trusted-proxy-aware resolution to prevent spoofed X-Forwarded-For.
    return get_client_ip(request)


def _build_device_label(request: Request, employee: Employee) -> str | None:
    parts = []
    if employee.terminal_id:
        parts.append(f"terminal:{employee.terminal_id}")
    ua = request.headers.get("user-agent", "").strip()
    if ua:
        parts.append(ua[:80])
    return " | ".join(parts)[:120] if parts else None


def _persist_refresh_session(
    db: Session,
    employee: Employee,
    refresh_token: str,
    payload: dict,
    request: Request,
) -> RefreshSession:
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    session = RefreshSession(
        employee_id=employee.id,
        session_id=str(payload["sid"]),
        token_hash=fingerprint_token(refresh_token),
        token_family=str(payload.get("family") or payload["sid"]),
        device_label=_build_device_label(request, employee),
        ip_address=_client_ip(request),
        user_agent=(request.headers.get("user-agent", "") or None),
        expires_at=expires_at,
        last_used_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(session)
    return session


def _revoke_session(db: Session, session: RefreshSession | None) -> None:
    if not session:
        return
    session.is_active = False
    session.revoked_at = datetime.now(timezone.utc)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _rate: None = Depends(login_rate_limiter),
):
    employee = db.query(Employee).filter(Employee.email == payload.email).first()

    dummy_hash = "$2b$12$KIX/9f3sWWZD3zMgXeF0DOCKTiOGl3YC5Dy4a8ZlqG5v5tQXiKrpy"
    password_ok = verify_password(payload.password, employee.password if employee else dummy_hash)

    if not employee or not password_ok:
        logger.warning("Failed login attempt for email=%s", _mask_email(payload.email))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token_data = {"sub": str(employee.id), "role": employee.role.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    refresh_payload = decode_refresh_token(refresh_token)
    if not refresh_payload:
        raise HTTPException(status_code=500, detail="Could not create refresh session")

    store_name = None
    store_location = None
    if employee.store_id:
        store = db.query(Store).filter(Store.id == employee.store_id).first()
        if store:
            store_name = store.name
            store_location = store.location

    employee.last_login_at = datetime.now(timezone.utc)
    _persist_refresh_session(db, employee, refresh_token, refresh_payload, request)
    db.commit()
    _set_refresh_cookie(response, refresh_token)

    logger.info("Employee %s logged in (role=%s)", employee.id, employee.role)

    return TokenOut(
        access_token=access_token,
        refresh_token=refresh_token,
        employee_id=employee.id,
        full_name=employee.full_name,
        role=employee.role,
        terminal_id=employee.terminal_id,
        store_name=store_name,
        store_location=store_location,
    )


# ── WS Ticket ─────────────────────────────────────────────────────────────────

@router.post("/ws-ticket")
def issue_ws_ticket(current: Employee = Depends(get_current_employee)):
    ticket = _issue_ws_ticket(current.id)
    return {"ticket": ticket, "expires_in": _WS_TICKET_TTL}


# ── Token refresh ─────────────────────────────────────────────────────────────

@router.post("/token/refresh")
def refresh_token(body: dict, request: Request, response: Response, db: Session = Depends(get_db)):
    token = body.get("refresh_token", "") or request.cookies.get(settings.AUTH_COOKIE_NAME, "")
    if not token:
        raise HTTPException(status_code=400, detail="refresh_token is required")

    payload = decode_refresh_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    try:
        employee_id = int(payload["sub"])
        session_id = str(payload["sid"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Malformed token")

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee or not employee.is_active:
        raise HTTPException(status_code=401, detail="Employee not found or deactivated")

    session = (
        db.query(RefreshSession)
        .filter(RefreshSession.session_id == session_id)
        .first()
    )
    if not session or not session.is_active:
        raise HTTPException(status_code=401, detail="Refresh session revoked")
    if session.employee_id != employee.id:
        raise HTTPException(status_code=401, detail="Refresh session mismatch")
    expires_at_utc = ensure_utc_datetime(session.expires_at)
    if expires_at_utc is None:
        logger.error(
            "Refresh session missing expiry timestamp",
            extra={"employee_id": employee.id, "session_id": session.session_id},
        )
        raise HTTPException(status_code=401, detail="Refresh session invalid")
    if expires_at_utc <= datetime.now(timezone.utc):
        _revoke_session(db, session)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh session expired")
    if session.token_hash != fingerprint_token(token):
        # Replay or token theft attempt: revoke the whole family.
        (
            db.query(RefreshSession)
            .filter(RefreshSession.token_family == session.token_family, RefreshSession.is_active == True)
            .update({
                "is_active": False,
                "revoked_at": datetime.now(timezone.utc),
            }, synchronize_session=False)
        )
        revoke_token(payload)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token replay detected")

    token_data = {
        "sub": str(employee.id),
        "role": employee.role.value,
        "family": session.token_family,
    }
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)
    new_payload = decode_refresh_token(new_refresh)
    if not new_payload:
        raise HTTPException(status_code=500, detail="Could not rotate refresh session")

    revoke_token(payload)
    _revoke_session(db, session)
    _persist_refresh_session(db, employee, new_refresh, new_payload, request)
    db.commit()
    _set_refresh_cookie(response, new_refresh)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout")
def logout(body: dict, response: Response, request: Request, db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    token = body.get("refresh_token", "") or request.cookies.get(settings.AUTH_COOKIE_NAME, "")
    if token:
        payload = decode_refresh_token(token)
        if payload and payload.get("sub") == str(current.id):
            revoke_token(payload)
            session = db.query(RefreshSession).filter(RefreshSession.session_id == str(payload.get("sid"))).first()
            _revoke_session(db, session)
            db.commit()
    _clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
def logout_all_sessions(db: Session = Depends(get_db), current: Employee = Depends(get_current_employee)):
    now = datetime.now(timezone.utc)
    (
        db.query(RefreshSession)
        .filter(RefreshSession.employee_id == current.id, RefreshSession.is_active == True)
        .update({"is_active": False, "revoked_at": now}, synchronize_session=False)
    )
    db.commit()
    return {"message": "All sessions revoked successfully"}


# ── Employee management ───────────────────────────────────────────────────────

@router.post("/employees", response_model=EmployeeOut, dependencies=[Depends(require_premium)])
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)):
    if db.query(Employee).filter(Employee.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    emp = Employee(
        **payload.model_dump(exclude={"password"}),
        password=hash_password(payload.password),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp

@router.post("/register", response_model=StoreRegistrationResponse, status_code=status.HTTP_201_CREATED)
def register_store(
    payload: StoreRegistrationRequest,
    db: Session = Depends(get_db),
):
    store, admin, trial_end = create_store_with_admin(
        db=db,
        store_name=payload.store_name,
        store_location=payload.store_location,
        store_email=payload.store_email,
        store_phone=payload.store_phone,
        store_kra_pin=payload.store_kra_pin,
        admin_full_name=payload.admin_full_name,
        admin_email=payload.admin_email,
        admin_password=payload.admin_password,
        mpesa_enabled=payload.mpesa_enabled or False,
        mpesa_consumer_key=payload.mpesa_consumer_key,
        mpesa_consumer_secret=payload.mpesa_consumer_secret,
        mpesa_shortcode=payload.mpesa_shortcode,
        mpesa_passkey=payload.mpesa_passkey,
        mpesa_callback_url=payload.mpesa_callback_url,
        mpesa_till_number=payload.mpesa_till_number,
    )

    return StoreRegistrationResponse(
        store_id=store.id,
        store_name=store.name,
        admin_id=admin.id,
        admin_email=admin.email,
        message=f"Store registered. {TRIAL_DAYS}-day free trial started.",
        trial_ends_at=trial_end,
    )

@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate: None = Depends(login_rate_limiter),
):
    """Generate a secure password reset token and deliver it by email."""
    employee = db.query(Employee).filter(Employee.email == payload.email).first()
    if not employee:
        return {"message": "If an account with that email exists, a password reset link will be sent."}

    db.query(PasswordResetToken).filter(
        PasswordResetToken.employee_id == employee.id,
        PasswordResetToken.is_used == False,
    ).update({"is_used": True, "used_at": datetime.now(timezone.utc)})

    raw_token = generate_password_reset_token()
    reset_record = PasswordResetToken(
        employee_id=employee.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        is_used=False,
    )
    db.add(reset_record)
    db.commit()

    background_tasks.add_task(
        send_password_reset_email,
        to_email=employee.email,
        recipient_name=employee.full_name,
        reset_token=raw_token,
    )

    logger.info("Password reset email queued for %s", payload.email)
    return {"message": "If an account with that email exists, a password reset link will be sent."}


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """Validate a reset token for the supplied email and set a new password."""
    employee = db.query(Employee).filter(Employee.email == payload.email).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    matching_record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.employee_id == employee.id,
            PasswordResetToken.is_used == False,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .order_by(PasswordResetToken.expires_at.desc())
        .first()
    )

    if not matching_record or not verify_token(payload.token, matching_record.token_hash):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    employee.password = hash_password(payload.new_password)
    if hasattr(employee, "password_changed_at"):
        employee.password_changed_at = datetime.now(timezone.utc)
    if hasattr(employee, "is_password_reset_required"):
        employee.is_password_reset_required = False
    matching_record.is_used = True
    matching_record.used_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Password reset successfully. Please log in with your new password."}

# ── Clock in / out ────────────────────────────────────────────────────────────

@router.post("/clock-in")
def clock_in(
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    current.clocked_in_at  = datetime.now(timezone.utc)
    current.clocked_out_at = None
    db.commit()
    return {"message": f"Clocked in at {current.clocked_in_at.strftime('%H:%M')}"}


@router.post("/clock-out")
def clock_out(
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    current.clocked_out_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": f"Clocked out at {current.clocked_out_at.strftime('%H:%M')}"}


# ── PIN management ────────────────────────────────────────────────────────────

@router.post("/set-pin")
def set_pin(
    payload: PinSet,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """Set the current employee's quick-access PIN (4–8 digits)."""
    if not re.fullmatch(r"\d{4,8}", payload.pin):
        raise HTTPException(status_code=422, detail="PIN must be 4–8 numeric digits only")
    current.pin = hash_password(payload.pin)
    db.commit()
    return {"message": "PIN updated"}


@router.post("/verify-pin")
def verify_pin(
    payload: PinVerify,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """Verify the current employee's PIN (POS quick-lock screen)."""
    if current.pin is None:
        return {"valid": False, "reason": "PIN not set"}
    return {"valid": verify_password(payload.pin, current.pin)}


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=EmployeeOut)
def me(current: Employee = Depends(get_current_employee)):
    return current
