"""Employee management endpoints for admin users."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.deps import get_db, get_current_employee, require_admin
from app.core.security import hash_password
from app.models.employee import Employee, Role
from app.schemas.registration import (
    EmployeeCreateRequest,
    EmployeeUpdateRequest,
    EmployeeOut,
    EmployeeListResponse,
    EmployeeCreateResponse,
)

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("", response_model=EmployeeListResponse)
def list_employees(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_admin),
):
    """
    List all employees in the current store.
    Admin only.
    """
    employees = db.query(Employee).filter(
        Employee.store_id == current.store_id
    ).order_by(Employee.created_at.desc()).all()

    return EmployeeListResponse(
        employees=[
            EmployeeOut.from_orm(emp) for emp in employees
        ],
        total=len(employees),
    )


@router.post("", response_model=EmployeeCreateResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreateRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_admin),
):
    """
    Create a new employee.
    Admin only.

    Restrictions:
    - Cannot create admin users (only during store registration)
    - Cannot create users with higher role than self
    """
    # Check email uniqueness globally
    existing = db.query(Employee).filter(Employee.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check username uniqueness
    existing = db.query(Employee).filter(Employee.user_name == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Cannot create admin (only during registration)
    if payload.role == Role.ADMIN:
        raise HTTPException(
            status_code=422,
            detail="Cannot create admin users. Admin role is only for store owners."
        )

    # Validate role hierarchy (cannot create higher role than self)
    if payload.role == Role.MANAGER and current.role != Role.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admins can create manager accounts"
        )

    try:
        employee = Employee(
            store_id=current.store_id,
            full_name=payload.full_name,
            email=payload.email,
            user_name=payload.username,  # Map username to user_name column
            phone=payload.phone,
            password=hash_password(payload.password),
            role=payload.role,
            is_active=True,
            terminal_id=payload.terminal_id,
            is_password_reset_required=False,
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

        return EmployeeCreateResponse(
            id=employee.id,
            full_name=employee.full_name,
            email=employee.email,
            username=employee.user_name,  # Include username in response
            role=employee.role.value,
            is_active=True,
            message="Employee created successfully."
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create employee: {str(e)}")


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_admin),
):
    """
    Update an existing employee.
    Admin only.

    Restrictions:
    - Cannot change role to higher than admin's own role
    - Cannot deactivate the last active admin
    """
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.store_id == current.store_id
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Cannot modify other admins unless you're the platform owner
    if employee.role == Role.ADMIN and current.role != Role.PLATFORM_OWNER:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify admin accounts"
        )

    # Validate role changes
    if payload.role is not None:
        if payload.role == Role.ADMIN and current.role != Role.PLATFORM_OWNER:
            raise HTTPException(
                status_code=422,
                detail="Cannot promote to admin role"
            )
        if payload.role == Role.MANAGER and current.role not in [Role.ADMIN, Role.PLATFORM_OWNER]:
            raise HTTPException(
                status_code=403,
                detail="Only admins can create manager accounts"
            )

    # Check if deactivating the last admin
    if payload.is_active is False and employee.role == Role.ADMIN:
        active_admins = db.query(Employee).filter(
            Employee.store_id == current.store_id,
            Employee.role == Role.ADMIN,
            Employee.is_active == True,
            Employee.id != employee_id
        ).count()
        if active_admins == 0:
            raise HTTPException(
                status_code=422,
                detail="Cannot deactivate the last active admin"
            )

    # Apply updates (handle username specially)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'username':
            # Check if username is being changed and if it's taken
            if value and value != employee.user_name:
                existing = db.query(Employee).filter(Employee.user_name == value).first()
                if existing:
                    raise HTTPException(status_code=400, detail="Username already taken")
                setattr(employee, 'user_name', value)
        else:
            setattr(employee, field, value)

    db.commit()
    db.refresh(employee)
    return EmployeeOut.from_orm(employee)


@router.delete("/{employee_id}")
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_admin),
):
    """
    Deactivate an employee (soft delete).
    Admin only.

    Restrictions:
    - Cannot deactivate the last active admin
    - Cannot deactivate other admins
    """
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.store_id == current.store_id
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Cannot deactivate other admins
    if employee.role == Role.ADMIN and current.role != Role.PLATFORM_OWNER:
        raise HTTPException(
            status_code=403,
            detail="Cannot deactivate admin accounts"
        )

    # Check if deactivating the last admin
    if employee.role == Role.ADMIN:
        active_admins = db.query(Employee).filter(
            Employee.store_id == current.store_id,
            Employee.role == Role.ADMIN,
            Employee.is_active == True,
            Employee.id != employee_id
        ).count()
        if active_admins == 0:
            raise HTTPException(
                status_code=422,
                detail="Cannot deactivate the last active admin"
            )

    employee.is_active = False
    db.commit()

    return {"message": "Employee deactivated"}


@router.post("/{employee_id}/reset-password")
def reset_employee_password(
    employee_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_admin),
):
    """
    Force password reset for an employee.
    Admin only.

    Generates a new temporary password and forces a password change on next login.
    """
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.store_id == current.store_id
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Generate new temporary password
    import secrets
    import string
    temp_password = ''.join([
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
        secrets.token_urlsafe(8)
    ])

    employee.password = hash_password(temp_password)
    employee.is_password_reset_required = True
    db.commit()

    return {
        "message": "Password reset successfully. The employee must use the Forgot Password flow to set a new password, or you can share a secure one-time link with them.",
        "password_reset_required": True,
    }


@router.get("/me", response_model=EmployeeOut)
def get_current_user(current: Employee = Depends(get_current_employee)):
    """Get current user information."""
    return EmployeeOut.from_orm(current)