"""Risk assessment route — compute and retrieve patient risk scores."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from api.dal import (
    ActivityRepository,
    AlertEventRepository,
    PatientRepository,
    RiskScoreRepository,
    VitalSignRepository,
)
from api.dependencies import AsyncDB, CurrentUser, get_user_roles
from api.schemas import RiskScoreOut
from database.models import RiskScore

router = APIRouter()

RISK_MODEL_VERSION = "1.0"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Risk scoring algorithm
# Score range: 0–100. Levels: LOW 0-25, MODERATE 26-50, HIGH 51-75, CRITICAL 76-100
# ---------------------------------------------------------------------------

# Normal range thresholds: (metric, low_critical, low_warn, high_warn, high_critical, crit_pts, warn_pts)
_VITAL_THRESHOLDS = [
    # (metric,  low_crit, low_warn, high_warn, high_crit, crit_pts, warn_pts)
    ("SPO2",     None,    95,       None,      92,         30,       15),
    ("HR",       None,    None,     100,       120,        25,       10),
    ("BP_SYS",   None,    None,     130,       140,        20,       10),
    ("GLUCOSE",  None,    None,     180,       200,        25,       10),
    ("TEMP",     None,    None,     38.0,      38.5,       15,        8),
    ("RESP_RATE",None,    None,     18,        22,         10,        5),
]


def _score_vitals(vitals) -> tuple[float, list[str]]:
    """Aggregate worst-case vital sign deviation score (0–60 max)."""
    if not vitals:
        return 0.0, []

    # Collect per-metric worst values
    worst: dict[str, float] = {}
    for v in vitals:
        metric = v.metric
        val = v.value
        if metric not in worst:
            worst[metric] = val
        # keep the most extreme value based on deviation
    # re-scan to find actual abnormal extremes
    extremes: dict[str, float] = {}
    for v in vitals:
        m = v.metric
        extremes.setdefault(m, v.value)
        # For SPO2 pick lowest; for others pick highest
        if m == "SPO2":
            if v.value < extremes[m]:
                extremes[m] = v.value
        else:
            if v.value > extremes[m]:
                extremes[m] = v.value

    points = 0.0
    factors = []
    for metric, low_crit, low_warn, high_warn, high_crit, crit_pts, warn_pts in _VITAL_THRESHOLDS:
        val = extremes.get(metric)
        if val is None:
            continue
        # Check critical threshold first
        if low_crit is not None and val <= low_crit:
            points += crit_pts
            factors.append(f"{metric}={val} (critically low)")
        elif high_crit is not None and val >= high_crit:
            points += crit_pts
            factors.append(f"{metric}={val} (critically high)")
        elif low_warn is not None and val <= low_warn:
            points += warn_pts
            factors.append(f"{metric}={val} (borderline low)")
        elif high_warn is not None and val >= high_warn:
            points += warn_pts
            factors.append(f"{metric}={val} (borderline high)")

    return min(points, 60.0), factors


def _score_alerts(alert_count: int) -> tuple[float, list[str]]:
    """Up to 25 points from recent WARNING/CRITICAL alert count (7 days)."""
    pts = min(alert_count * 5.0, 25.0)
    factors = []
    if alert_count > 0:
        factors.append(f"{alert_count} warning/critical alert(s) in last 7 days")
    return pts, factors


def _score_activity(activity_records) -> tuple[float, list[str]]:
    """Up to 15 points for low activity (< 1000 steps/day average)."""
    if not activity_records:
        return 0.0, []
    steps_records = [r.steps for r in activity_records if r.steps is not None]
    if not steps_records:
        return 0.0, []
    avg_steps = sum(steps_records) / len(steps_records)
    if avg_steps < 500:
        return 15.0, [f"Very low activity: avg {avg_steps:.0f} steps/day"]
    if avg_steps < 1000:
        return 8.0, [f"Low activity: avg {avg_steps:.0f} steps/day"]
    return 0.0, []


def _determine_level(score: float) -> str:
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MODERATE"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def _build_recommendations(level: str, factors: list[str]) -> str:
    recs = []
    if level == "CRITICAL":
        recs.append("Immediate clinical review required.")
    elif level == "HIGH":
        recs.append("Schedule urgent follow-up within 24 hours.")
    elif level == "MODERATE":
        recs.append("Monitor closely. Schedule routine follow-up.")
    else:
        recs.append("Continue current care plan.")

    if any("SPO2" in f for f in factors):
        recs.append("Evaluate oxygen therapy.")
    if any("BP_SYS" in f for f in factors):
        recs.append("Review antihypertensive medication.")
    if any("GLUCOSE" in f for f in factors):
        recs.append("Adjust glycemic management.")
    if any("activity" in f.lower() or "steps" in f.lower() for f in factors):
        recs.append("Encourage physical activity per care plan.")
    return " ".join(recs)


async def _calculate_risk(patient_id: str, db) -> RiskScore:
    since = _now() - timedelta(days=7)
    vitals = await VitalSignRepository(db).list_recent_for_risk(patient_id, since)
    alert_count = await AlertEventRepository(db).count_recent_for_patient(patient_id, since)
    activity = await ActivityRepository(db).list_recent_for_risk(patient_id, since)

    v_pts, v_factors = _score_vitals(vitals)
    a_pts, a_factors = _score_alerts(alert_count)
    act_pts, act_factors = _score_activity(activity)

    total_score = min(v_pts + a_pts + act_pts, 100.0)
    all_factors = v_factors + a_factors + act_factors
    level = _determine_level(total_score)

    score = RiskScore(
        id=_id(),
        patient_id=patient_id,
        score=round(total_score, 2),
        risk_level=level,
        contributing_factors=json.dumps(all_factors),
        recommendations=_build_recommendations(level, all_factors),
        scored_at=_now(),
        model_version=RISK_MODEL_VERSION,
    )
    await RiskScoreRepository(db).create(score)
    return score


# ---------------------------------------------------------------------------
# GET /patients/{patient_id}/risk
# ---------------------------------------------------------------------------

async def _assert_patient_access(patient_id: str, current_user, db) -> None:
    patient = await PatientRepository(db).get_by_id(patient_id)
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


router = APIRouter()


@router.get(
    "/{patient_id}/risk",
    response_model=RiskScoreOut,
    summary="Get the latest risk score for a patient",
)
async def get_risk_score(
    patient_id: str,
    db: AsyncDB,
    current_user: CurrentUser,
) -> RiskScoreOut:
    await _assert_patient_access(patient_id, current_user, db)

    latest = await RiskScoreRepository(db).get_latest_for_patient(patient_id)
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "No risk score calculated yet. POST to /risk/calculate.", "details": None}},
        )
    return RiskScoreOut.model_validate(latest)


# ---------------------------------------------------------------------------
# POST /patients/{patient_id}/risk/calculate
# ---------------------------------------------------------------------------

@router.post(
    "/{patient_id}/risk/calculate",
    response_model=RiskScoreOut,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger risk score recalculation for a patient",
)
async def calculate_risk_score(
    patient_id: str,
    db: AsyncDB,
    current_user: CurrentUser,
) -> RiskScoreOut:
    await _assert_patient_access(patient_id, current_user, db)
    score = await _calculate_risk(patient_id, db)
    await db.commit()
    await db.refresh(score)
    return RiskScoreOut.model_validate(score)
