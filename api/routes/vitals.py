"""Vital sign routes — POST and GET with filtering and pagination."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from api.dal import (
    AlertEventRepository,
    AlertRuleRepository,
    NotificationLogRepository,
    PatientRepository,
    VitalSignRepository,
)
from api.dependencies import AsyncDB, CurrentUser, audit_phi_access, get_user_roles
from api.schemas import VitalSignCreate, VitalSignListOut, VitalSignOut
from database.models import AlertEvent, NotificationLog, VitalSignRecord

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


# Simple abnormal thresholds for auto-flagging at ingestion time
_ABNORMAL_RULES: dict[str, dict] = {
    "SPO2":   {"min": 92},
    "HR":     {"max": 120},
    "BP_SYS": {"max": 140},
    "GLUCOSE":{"max": 200},
}


def _is_flagged(metric: str, value: float) -> bool:
    rule = _ABNORMAL_RULES.get(metric)
    if not rule:
        return False
    if "min" in rule and value < rule["min"]:
        return True
    if "max" in rule and value > rule["max"]:
        return True
    return False


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


async def _evaluate_alert_rules(
    patient_id: str, metric: str, value: float, db
) -> None:
    """Evaluate alert rules for the ingested vital and create AlertEvent if triggered.

    Suppression: skip if an OPEN/ACKNOWLEDGED event from the same rule exists
    within suppression_window_minutes.
    """
    rule_repo = AlertRuleRepository(db)
    event_repo = AlertEventRepository(db)
    notif_repo = NotificationLogRepository(db)

    rules = await rule_repo.get_active_for_patient_metric(patient_id, metric)
    now = _now()

    for rule in rules:
        triggered = False
        if rule.threshold_min is not None and value < rule.threshold_min:
            triggered = True
        if rule.threshold_max is not None and value > rule.threshold_max:
            triggered = True

        if not triggered:
            continue

        # Suppression check
        if rule.suppression_window_minutes > 0:
            existing = await event_repo.get_latest_open_for_rule(patient_id, rule.id)
            if existing:
                window = timedelta(minutes=rule.suppression_window_minutes)
                if existing.created_at.tzinfo is None:
                    existing_created = existing.created_at.replace(tzinfo=timezone.utc)
                else:
                    existing_created = existing.created_at
                if (now - existing_created) < window:
                    continue  # suppressed

        # Build message
        if rule.threshold_min is not None and value < rule.threshold_min:
            msg = f"{metric} {value} is below minimum threshold {rule.threshold_min}"
        else:
            msg = f"{metric} {value} exceeds maximum threshold {rule.threshold_max}"

        event = AlertEvent(
            id=_id(),
            patient_id=patient_id,
            rule_id=rule.id,
            metric=metric,
            triggered_value=value,
            severity=rule.severity,
            status="OPEN",
            message=msg,
            created_at=now,
        )
        await event_repo.create(event)

        # Create a PENDING in-app notification
        notif = NotificationLog(
            id=_id(),
            alert_event_id=event.id,
            channel="PUSH",
            recipient=patient_id,
            status="PENDING",
            created_at=now,
        )
        await notif_repo.create(notif)


@router.post(
    "/{patient_id}/vitals",
    response_model=VitalSignOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a vital sign measurement",
)
async def post_vital(
    patient_id: str,
    body: VitalSignCreate,
    db: AsyncDB,
    current_user: CurrentUser,
) -> VitalSignOut:
    await _assert_patient_access(patient_id, current_user, db)

    record = VitalSignRecord(
        id=_id(),
        patient_id=patient_id,
        metric=body.metric,
        value=body.value,
        unit=body.unit,
        recorded_at=body.recorded_at,
        source=body.source,
        is_flagged=_is_flagged(body.metric, body.value),
        created_at=_now(),
    )
    repo = VitalSignRepository(db)
    await repo.create(record)

    # Evaluate alert rules for this vital reading
    await _evaluate_alert_rules(patient_id, body.metric, body.value, db)

    await db.commit()
    await db.refresh(record)
    return VitalSignOut.model_validate(record)


@router.get(
    "/{patient_id}/vitals",
    response_model=VitalSignListOut,
    summary="List vital signs for a patient (filterable by date range and metric)",
    dependencies=[audit_phi_access("READ", "vital_sign_records")],
)
async def list_vitals(
    patient_id: str,
    db: AsyncDB,
    current_user: CurrentUser,
    start: Optional[datetime] = Query(None, description="ISO 8601 start datetime"),
    end: Optional[datetime] = Query(None, description="ISO 8601 end datetime"),
    metric: Optional[str] = Query(None, description="Filter by metric, e.g. HR"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> VitalSignListOut:
    await _assert_patient_access(patient_id, current_user, db)

    repo = VitalSignRepository(db)
    total, items = await repo.list_for_patient(
        patient_id=patient_id,
        start=start,
        end=end,
        metric=metric,
        limit=limit,
        offset=offset,
    )
    return VitalSignListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[VitalSignOut.model_validate(r) for r in items],
    )
