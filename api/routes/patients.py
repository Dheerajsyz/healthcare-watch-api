"""Patient routes — CRUD with RBAC and HIPAA audit logging."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dal import PatientRepository, RoleRepository, UserRepository
from api.dependencies import AsyncDB, CurrentUser, audit_phi_access, get_user_roles, require_roles
from api.schemas import PatientCreate, PatientListOut, PatientOut, PatientUpdate
from api.security import hash_password
from database.models import Patient, User, UserRole

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


def _patient_out(patient: Patient) -> PatientOut:
    return PatientOut(
        id=patient.id,
        user_id=patient.user_id,
        full_name=patient.user.full_name,
        email=patient.user.email,
        date_of_birth=patient.date_of_birth,
        sex=patient.sex,
        phone=patient.phone,
        address=patient.address,
        emergency_contact_name=patient.emergency_contact_name,
        emergency_contact_phone=patient.emergency_contact_phone,
        consent_given=patient.consent_given,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


# ---------------------------------------------------------------------------
# POST /patients — PROVIDER or ADMIN creates a patient
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=PatientOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new patient (PROVIDER or ADMIN)",
    dependencies=[Depends(require_roles("PROVIDER", "ADMIN"))],
)
async def create_patient(
    body: PatientCreate,
    db: AsyncDB,
    current_user: CurrentUser,
) -> PatientOut:
    user_repo = UserRepository(db)
    role_repo = RoleRepository(db)
    patient_repo = PatientRepository(db)

    # Check email uniqueness
    existing = await user_repo.get_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "CONFLICT", "message": "Email already registered.", "details": None}},
        )

    role = await role_repo.get_by_name("PATIENT")
    if not role:
        raise HTTPException(status_code=500, detail={"error": {"code": "SETUP_ERROR", "message": "PATIENT role not found in DB. Run seed.py.", "details": None}})

    now = _now()
    new_user = User(
        id=_id(),
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    await user_repo.create(new_user)

    db.add(UserRole(id=_id(), user_id=new_user.id, role_id=role.id, assigned_at=now))

    patient = Patient(
        id=_id(),
        user_id=new_user.id,
        date_of_birth=body.date_of_birth,
        sex=body.sex,
        phone=body.phone,
        address=body.address,
        emergency_contact_name=body.emergency_contact_name,
        emergency_contact_phone=body.emergency_contact_phone,
        consent_given=body.consent_given,
        created_at=now,
        updated_at=now,
    )
    # Attach user for serialisation
    patient.user = new_user
    await patient_repo.create(patient)
    await db.commit()
    await db.refresh(patient)
    await db.refresh(new_user)
    patient.user = new_user
    return _patient_out(patient)


# ---------------------------------------------------------------------------
# GET /patients — list (PROVIDER / ADMIN only)
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PatientListOut,
    summary="List all patients (PROVIDER or ADMIN)",
    dependencies=[Depends(require_roles("PROVIDER", "ADMIN"))],
)
async def list_patients(
    db: AsyncDB,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PatientListOut:
    patient_repo = PatientRepository(db)
    total, patients = await patient_repo.list_all(limit=limit, offset=offset)
    return PatientListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[_patient_out(p) for p in patients],
    )


# ---------------------------------------------------------------------------
# GET /patients/{id}
# ---------------------------------------------------------------------------

@router.get(
    "/{patient_id}",
    response_model=PatientOut,
    summary="Get patient by ID",
    dependencies=[audit_phi_access("READ", "patients")],
)
async def get_patient(
    patient_id: str,
    db: AsyncDB,
    current_user: CurrentUser,
) -> PatientOut:
    patient_repo = PatientRepository(db)
    patient = await patient_repo.get_by_id(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Patient not found.", "details": None}},
        )

    roles = get_user_roles(current_user)
    # PATIENT can only see their own record
    if "PATIENT" in roles and "PROVIDER" not in roles and "ADMIN" not in roles:
        if patient.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You can only access your own record.", "details": None}},
            )

    return _patient_out(patient)


# ---------------------------------------------------------------------------
# PATCH /patients/{id}
# ---------------------------------------------------------------------------

@router.patch(
    "/{patient_id}",
    response_model=PatientOut,
    summary="Update patient demographics",
    dependencies=[audit_phi_access("UPDATE", "patients")],
)
async def update_patient(
    patient_id: str,
    body: PatientUpdate,
    db: AsyncDB,
    current_user: CurrentUser,
) -> PatientOut:
    patient_repo = PatientRepository(db)
    patient = await patient_repo.get_by_id(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Patient not found.", "details": None}},
        )

    roles = get_user_roles(current_user)
    if "PATIENT" in roles and "PROVIDER" not in roles and "ADMIN" not in roles:
        if patient.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "Cannot modify another patient's record.", "details": None}},
            )

    # Apply updates
    update_data = body.model_dump(exclude_unset=True)
    if "full_name" in update_data:
        patient.user.full_name = update_data.pop("full_name")
    for field, value in update_data.items():
        setattr(patient, field, value)
    patient.updated_at = _now()

    await patient_repo.update(patient)
    await db.commit()
    await db.refresh(patient)
    return _patient_out(patient)
