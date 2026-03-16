"""Activity routes — POST and GET with filtering and pagination."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from api.dal import ActivityRepository, PatientRepository
from api.dependencies import AsyncDB, CurrentUser, get_user_roles
from api.schemas import ActivityCreate, ActivityListOut, ActivityOut
from database.models import ActivityRecord

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


@router.post(
    "/{patient_id}/activity",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record an activity entry",
)
async def post_activity(
    patient_id: str,
    body: ActivityCreate,
    db: AsyncDB,
    current_user: CurrentUser,
) -> ActivityOut:
    await _assert_patient_access(patient_id, current_user, db)

    record = ActivityRecord(
        id=_id(),
        patient_id=patient_id,
        recorded_at=body.recorded_at,
        steps=body.steps,
        active_minutes=body.active_minutes,
        sleep_hours=body.sleep_hours,
        calories_burned=body.calories_burned,
        source=body.source,
        created_at=_now(),
    )
    repo = ActivityRepository(db)
    await repo.create(record)
    await db.commit()
    await db.refresh(record)
    return ActivityOut.model_validate(record)


@router.get(
    "/{patient_id}/activity",
    response_model=ActivityListOut,
    summary="List activity records for a patient (filterable by date range)",
)
async def list_activity(
    patient_id: str,
    db: AsyncDB,
    current_user: CurrentUser,
    start: Optional[datetime] = Query(None, description="ISO 8601 start datetime"),
    end: Optional[datetime] = Query(None, description="ISO 8601 end datetime"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ActivityListOut:
    await _assert_patient_access(patient_id, current_user, db)

    repo = ActivityRepository(db)
    total, items = await repo.list_for_patient(
        patient_id=patient_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
    return ActivityListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[ActivityOut.model_validate(r) for r in items],
    )
