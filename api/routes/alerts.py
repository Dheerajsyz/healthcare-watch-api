"""Alert routes — list and update alert events for a patient."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dal import AlertEventRepository, PatientRepository
from api.dependencies import AsyncDB, CurrentUser, get_user_roles, require_roles
from api.schemas import AlertEventListOut, AlertEventOut, AlertStatusUpdate
from database.models import AlertEvent

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


async def _assert_patient_access(patient_id: str, current_user, db) -> None:
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
                detail={"error": {"code": "FORBIDDEN", "message": "Cannot access another patient's data.", "details": None}},
            )


# ---------------------------------------------------------------------------
# GET /patients/{patient_id}/alerts
# ---------------------------------------------------------------------------

@router.get(
    "/{patient_id}/alerts",
    response_model=AlertEventListOut,
    summary="List alert events for a patient (filterable by status/severity)",
)
async def list_alerts(
    patient_id: str,
    db: AsyncDB,
    current_user: CurrentUser,
    alert_status: Optional[str] = Query(None, alias="status", description="Filter: OPEN | ACKNOWLEDGED | RESOLVED | SUPPRESSED"),
    severity: Optional[str] = Query(None, description="Filter: INFO | WARNING | CRITICAL"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AlertEventListOut:
    await _assert_patient_access(patient_id, current_user, db)

    repo = AlertEventRepository(db)
    total, items = await repo.list_for_patient(
        patient_id=patient_id,
        status=alert_status,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return AlertEventListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[AlertEventOut.model_validate(e) for e in items],
    )


# ---------------------------------------------------------------------------
# PATCH /patients/{patient_id}/alerts/{alert_id}
# ---------------------------------------------------------------------------

@router.patch(
    "/{patient_id}/alerts/{alert_id}",
    response_model=AlertEventOut,
    summary="Acknowledge or resolve an alert event (PROVIDER or ADMIN)",
    dependencies=[Depends(require_roles("PROVIDER", "ADMIN"))],
)
async def update_alert_status(
    patient_id: str,
    alert_id: str,
    body: AlertStatusUpdate,
    db: AsyncDB,
    current_user: CurrentUser,
) -> AlertEventOut:
    await _assert_patient_access(patient_id, current_user, db)

    repo = AlertEventRepository(db)
    event = await repo.get_by_id(alert_id)
    if not event or event.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Alert event not found.", "details": None}},
        )
    if event.status in ("RESOLVED",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "CONFLICT", "message": "Alert is already resolved.", "details": None}},
        )

    event.status = body.status
    if body.status == "RESOLVED":
        event.resolved_at = _now()

    await db.commit()
    await db.refresh(event)
    return AlertEventOut.model_validate(event)
