"""Pydantic schemas for HealthTrack API."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    roles: list[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------

SexType = Literal["F", "M", "X"]


class PatientCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Min 8 chars")
    full_name: str = Field(min_length=1, max_length=255)
    date_of_birth: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sex: Optional[SexType] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    consent_given: bool = False


class PatientUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    date_of_birth: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sex: Optional[SexType] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    consent_given: Optional[bool] = None


class PatientOut(BaseModel):
    id: str
    user_id: str
    full_name: str
    email: str
    date_of_birth: Optional[str]
    sex: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    emergency_contact_name: Optional[str]
    emergency_contact_phone: Optional[str]
    consent_given: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PatientOut]


# ---------------------------------------------------------------------------
# Vitals
# ---------------------------------------------------------------------------

VitalMetricType = Literal["HR", "BP_SYS", "BP_DIA", "SPO2", "TEMP", "RESP_RATE", "WEIGHT", "GLUCOSE"]


class VitalSignCreate(BaseModel):
    metric: VitalMetricType
    value: float
    unit: Optional[str] = None
    recorded_at: datetime
    source: Optional[str] = None


class VitalSignOut(BaseModel):
    id: str
    patient_id: str
    metric: str
    value: float
    unit: Optional[str]
    recorded_at: datetime
    source: Optional[str]
    is_flagged: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class VitalSignListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[VitalSignOut]


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

class ActivityCreate(BaseModel):
    recorded_at: datetime
    steps: Optional[int] = Field(None, ge=0)
    active_minutes: Optional[int] = Field(None, ge=0)
    sleep_hours: Optional[float] = Field(None, ge=0)
    calories_burned: Optional[float] = Field(None, ge=0)
    source: Optional[str] = None


class ActivityOut(BaseModel):
    id: str
    patient_id: str
    recorded_at: datetime
    steps: Optional[int]
    active_minutes: Optional[int]
    sleep_hours: Optional[float]
    calories_burned: Optional[float]
    source: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ActivityOut]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertEventOut(BaseModel):
    id: str
    patient_id: str
    rule_id: Optional[str]
    metric: str
    triggered_value: float
    severity: str
    status: str
    message: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AlertEventListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AlertEventOut]


class AlertStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        pattern="^(ACKNOWLEDGED|RESOLVED)$",
        description="New status: ACKNOWLEDGED or RESOLVED",
    )
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------

class RiskScoreOut(BaseModel):
    id: str
    patient_id: str
    score: float
    risk_level: str
    contributing_factors: Optional[str]
    recommendations: Optional[str]
    scored_at: datetime
    model_version: Optional[str]

    model_config = {"from_attributes": True}
