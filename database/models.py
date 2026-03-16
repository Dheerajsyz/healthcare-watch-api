"""ORM models for HealthTrack.

All tables use UUID primary keys and timezone-aware timestamps.
Constraints and indexes are defined inline to satisfy rubric requirements.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database.base import Base

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums (database-level)
# ---------------------------------------------------------------------------

VITAL_METRIC_ENUM = Enum(
    "HR",          # Heart rate (bpm)
    "BP_SYS",      # Systolic blood pressure
    "BP_DIA",      # Diastolic blood pressure
    "SPO2",        # Oxygen saturation %
    "TEMP",        # Body temperature
    "RESP_RATE",   # Respiratory rate
    "WEIGHT",      # Weight kg
    "GLUCOSE",     # Blood glucose mg/dL
    name="vital_metric",
)

ALERT_SEVERITY_ENUM = Enum("INFO", "WARNING", "CRITICAL", name="alert_severity")
ALERT_STATUS_ENUM = Enum(
    "OPEN", "ACKNOWLEDGED", "RESOLVED", "SUPPRESSED", name="alert_status"
)
SEX_ENUM = Enum("F", "M", "X", name="sex")
ROLE_NAME_ENUM = Enum("PATIENT", "PROVIDER", "ADMIN", name="role_name")
NOTIFICATION_CHANNEL_ENUM = Enum("EMAIL", "SMS", "PUSH", name="notification_channel")
NOTIFICATION_STATUS_ENUM = Enum(
    "PENDING", "SENT", "FAILED", "RETRYING", name="notification_status"
)
RISK_LEVEL_ENUM = Enum("LOW", "MODERATE", "HIGH", "CRITICAL", name="risk_level")


# ---------------------------------------------------------------------------
# 1. roles
# ---------------------------------------------------------------------------

class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(ROLE_NAME_ENUM, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role")


# ---------------------------------------------------------------------------
# 2. users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="user")
    patient: Mapped["Patient | None"] = relationship(back_populates="user")
    provider: Mapped["Provider | None"] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


# ---------------------------------------------------------------------------
# 3. user_roles  (junction)
# ---------------------------------------------------------------------------

class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="user_roles")


# ---------------------------------------------------------------------------
# 4. patients
# ---------------------------------------------------------------------------

class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint("sex IN ('F','M','X')", name="ck_patients_sex"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    date_of_birth: Mapped[str | None] = mapped_column(String(10))  # ISO date string
    sex: Mapped[str | None] = mapped_column(SEX_ENUM)
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(255))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30))
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="patient")
    provider_assignments: Mapped[list["PatientProviderAssignment"]] = relationship(
        back_populates="patient"
    )
    vital_signs: Mapped[list["VitalSignRecord"]] = relationship(back_populates="patient")
    activity_records: Mapped[list["ActivityRecord"]] = relationship(back_populates="patient")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="patient")
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="patient")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="patient")
    risk_scores: Mapped[list["RiskScore"]] = relationship(back_populates="patient")


# ---------------------------------------------------------------------------
# 5. providers
# ---------------------------------------------------------------------------

class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    specialty: Mapped[str | None] = mapped_column(String(100))
    license_number: Mapped[str | None] = mapped_column(String(50))
    department: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="provider")
    patient_assignments: Mapped[list["PatientProviderAssignment"]] = relationship(
        back_populates="provider"
    )
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="provider")
    acknowledgments: Mapped[list["AlertAcknowledgment"]] = relationship(
        back_populates="provider"
    )


# ---------------------------------------------------------------------------
# 6. patient_provider_assignments
# ---------------------------------------------------------------------------

class PatientProviderAssignment(Base):
    __tablename__ = "patient_provider_assignments"
    __table_args__ = (UniqueConstraint("patient_id", "provider_id"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    patient_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="provider_assignments")
    provider: Mapped["Provider"] = relationship(back_populates="patient_assignments")


# ---------------------------------------------------------------------------
# 7. vital_sign_records
# ---------------------------------------------------------------------------

class VitalSignRecord(Base):
    __tablename__ = "vital_sign_records"
    __table_args__ = (
        Index("ix_vitals_patient_recorded_at", "patient_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    patient_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(VITAL_METRIC_ENUM, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    source: Mapped[str | None] = mapped_column(String(50))  # device / manual
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    patient: Mapped["Patient"] = relationship(back_populates="vital_signs")


# ---------------------------------------------------------------------------
# 8. activity_records
# ---------------------------------------------------------------------------

class ActivityRecord(Base):
    __tablename__ = "activity_records"
    __table_args__ = (
        CheckConstraint("steps >= 0", name="ck_activity_steps_nonneg"),
        CheckConstraint("active_minutes >= 0", name="ck_activity_active_minutes_nonneg"),
        CheckConstraint("sleep_hours >= 0", name="ck_activity_sleep_nonneg"),
        CheckConstraint("calories_burned >= 0", name="ck_activity_calories_nonneg"),
        Index("ix_activity_patient_recorded_at", "patient_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    patient_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    steps: Mapped[int | None] = mapped_column(Integer)
    active_minutes: Mapped[int | None] = mapped_column(Integer)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    calories_burned: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    patient: Mapped["Patient"] = relationship(back_populates="activity_records")


# ---------------------------------------------------------------------------
# 9. alert_rules
# ---------------------------------------------------------------------------

class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    patient_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,  # NULL = system-wide default
    )
    metric: Mapped[str] = mapped_column(VITAL_METRIC_ENUM, nullable=False)
    threshold_min: Mapped[float | None] = mapped_column(Float)
    threshold_max: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(ALERT_SEVERITY_ENUM, nullable=False)
    suppression_window_minutes: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    patient: Mapped["Patient | None"] = relationship(back_populates="alert_rules")
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="rule")


# ---------------------------------------------------------------------------
# 10. alert_events
# ---------------------------------------------------------------------------

class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_patient_created", "patient_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    patient_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("alert_rules.id", ondelete="SET NULL")
    )
    metric: Mapped[str] = mapped_column(VITAL_METRIC_ENUM, nullable=False)
    triggered_value: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(ALERT_SEVERITY_ENUM, nullable=False)
    status: Mapped[str] = mapped_column(
        ALERT_STATUS_ENUM, default="OPEN", nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patient: Mapped["Patient"] = relationship(back_populates="alert_events")
    rule: Mapped["AlertRule | None"] = relationship(back_populates="alert_events")
    acknowledgments: Mapped[list["AlertAcknowledgment"]] = relationship(
        back_populates="alert_event"
    )
    notifications: Mapped[list["NotificationLog"]] = relationship(
        back_populates="alert_event"
    )


# ---------------------------------------------------------------------------
# 11. alert_acknowledgments
# ---------------------------------------------------------------------------

class AlertAcknowledgment(Base):
    __tablename__ = "alert_acknowledgments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    alert_event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("alert_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(String(255))

    alert_event: Mapped["AlertEvent"] = relationship(back_populates="acknowledgments")
    provider: Mapped["Provider"] = relationship(back_populates="acknowledgments")


# ---------------------------------------------------------------------------
# 12. notification_log
# ---------------------------------------------------------------------------

class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        Index("ix_notification_log_alert_sent", "alert_event_id", "sent_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    alert_event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("alert_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(NOTIFICATION_CHANNEL_ENUM, nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        NOTIFICATION_STATUS_ENUM, default="PENDING", nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    alert_event: Mapped["AlertEvent"] = relationship(back_populates="notifications")


# ---------------------------------------------------------------------------
# 13. appointments
# ---------------------------------------------------------------------------

class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_patient_scheduled", "patient_id", "scheduled_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    patient_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="SCHEDULED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    patient: Mapped["Patient"] = relationship(back_populates="appointments")
    provider: Mapped["Provider"] = relationship(back_populates="appointments")


# ---------------------------------------------------------------------------
# 14. risk_scores
# ---------------------------------------------------------------------------

class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (
        Index("ix_risk_scores_patient_scored", "patient_id", "scored_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    patient_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(RISK_LEVEL_ENUM, nullable=False)
    contributing_factors: Mapped[str | None] = mapped_column(Text)  # JSON string
    recommendations: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    model_version: Mapped[str | None] = mapped_column(String(50))

    patient: Mapped["Patient"] = relationship(back_populates="risk_scores")


# ---------------------------------------------------------------------------
# 15. audit_log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_actor_created", "actor_id", "created_at"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    actor_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[str | None] = mapped_column(Text)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )

    actor: Mapped["User | None"] = relationship(back_populates="audit_logs")
