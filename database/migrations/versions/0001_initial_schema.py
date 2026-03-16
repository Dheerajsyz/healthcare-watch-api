"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums ---
    vital_metric = postgresql.ENUM(
        "HR", "BP_SYS", "BP_DIA", "SPO2", "TEMP", "RESP_RATE", "WEIGHT", "GLUCOSE",
        name="vital_metric",
    )
    alert_severity = postgresql.ENUM("INFO", "WARNING", "CRITICAL", name="alert_severity")
    alert_status = postgresql.ENUM(
        "OPEN", "ACKNOWLEDGED", "RESOLVED", "SUPPRESSED", name="alert_status"
    )
    sex_enum = postgresql.ENUM("F", "M", "X", name="sex")
    role_name_enum = postgresql.ENUM("PATIENT", "PROVIDER", "ADMIN", name="role_name")
    notif_channel = postgresql.ENUM("EMAIL", "SMS", "PUSH", name="notification_channel")
    notif_status = postgresql.ENUM(
        "PENDING", "SENT", "FAILED", "RETRYING", name="notification_status"
    )
    risk_level_enum = postgresql.ENUM(
        "LOW", "MODERATE", "HIGH", "CRITICAL", name="risk_level"
    )

    for e in [vital_metric, alert_severity, alert_status, sex_enum, role_name_enum,
              notif_channel, notif_status, risk_level_enum]:
        e.create(op.get_bind(), checkfirst=True)

    # roles
    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "name",
            postgresql.ENUM("PATIENT", "PROVIDER", "ADMIN", name="role_name", create_type=False),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # user_roles
    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles"),
    )

    # patients
    op.create_table(
        "patients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("date_of_birth", sa.String(10), nullable=True),
        sa.Column("sex", postgresql.ENUM("F", "M", "X", name="sex", create_type=False), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("emergency_contact_name", sa.String(255), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(30), nullable=True),
        sa.Column("consent_given", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sex IN ('F','M','X')", name="ck_patients_sex"),
    )

    # providers
    op.create_table(
        "providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("specialty", sa.String(100), nullable=True),
        sa.Column("license_number", sa.String(50), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # patient_provider_assignments
    op.create_table(
        "patient_provider_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.UniqueConstraint("patient_id", "provider_id", name="uq_patient_provider"),
    )

    # vital_sign_records
    op.create_table(
        "vital_sign_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", postgresql.ENUM("HR", "BP_SYS", "BP_DIA", "SPO2", "TEMP", "RESP_RATE", "WEIGHT", "GLUCOSE", name="vital_metric", create_type=False), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("is_flagged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vitals_patient_recorded_at", "vital_sign_records", ["patient_id", "recorded_at"])
    op.create_index("ix_vitals_recorded_at", "vital_sign_records", ["recorded_at"])

    # activity_records
    op.create_table(
        "activity_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("steps", sa.Integer, nullable=True),
        sa.Column("active_minutes", sa.Integer, nullable=True),
        sa.Column("sleep_hours", sa.Float, nullable=True),
        sa.Column("calories_burned", sa.Float, nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("steps >= 0", name="ck_activity_steps_nonneg"),
        sa.CheckConstraint("active_minutes >= 0", name="ck_activity_active_minutes_nonneg"),
        sa.CheckConstraint("sleep_hours >= 0", name="ck_activity_sleep_nonneg"),
        sa.CheckConstraint("calories_burned >= 0", name="ck_activity_calories_nonneg"),
    )
    op.create_index("ix_activity_patient_recorded_at", "activity_records", ["patient_id", "recorded_at"])
    op.create_index("ix_activity_recorded_at", "activity_records", ["recorded_at"])

    # alert_rules
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("metric", postgresql.ENUM("HR", "BP_SYS", "BP_DIA", "SPO2", "TEMP", "RESP_RATE", "WEIGHT", "GLUCOSE", name="vital_metric", create_type=False), nullable=False),
        sa.Column("threshold_min", sa.Float, nullable=True),
        sa.Column("threshold_max", sa.Float, nullable=True),
        sa.Column("severity", postgresql.ENUM("INFO", "WARNING", "CRITICAL", name="alert_severity", create_type=False), nullable=False),
        sa.Column("suppression_window_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # alert_events
    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(36), sa.ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metric", postgresql.ENUM("HR", "BP_SYS", "BP_DIA", "SPO2", "TEMP", "RESP_RATE", "WEIGHT", "GLUCOSE", name="vital_metric", create_type=False), nullable=False),
        sa.Column("triggered_value", sa.Float, nullable=False),
        sa.Column("severity", postgresql.ENUM("INFO", "WARNING", "CRITICAL", name="alert_severity", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM("OPEN", "ACKNOWLEDGED", "RESOLVED", "SUPPRESSED", name="alert_status", create_type=False), nullable=False, server_default="OPEN"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alert_events_patient_created", "alert_events", ["patient_id", "created_at"])

    # alert_acknowledgments
    op.create_table(
        "alert_acknowledgments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_event_id", sa.String(36), sa.ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("action_taken", sa.String(255), nullable=True),
    )

    # notification_log
    op.create_table(
        "notification_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_event_id", sa.String(36), sa.ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", postgresql.ENUM("EMAIL", "SMS", "PUSH", name="notification_channel", create_type=False), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("status", postgresql.ENUM("PENDING", "SENT", "FAILED", "RETRYING", name="notification_status", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notification_log_alert_sent", "notification_log", ["alert_event_id", "sent_at"])

    # appointments
    op.create_table(
        "appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="30"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="SCHEDULED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_appointments_patient_scheduled", "appointments", ["patient_id", "scheduled_at"])

    # risk_scores
    op.create_table(
        "risk_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("risk_level", postgresql.ENUM("LOW", "MODERATE", "HIGH", "CRITICAL", name="risk_level", create_type=False), nullable=False),
        sa.Column("contributing_factors", sa.Text, nullable=True),
        sa.Column("recommendations", sa.Text, nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
    )
    op.create_index("ix_risk_scores_patient_scored", "risk_scores", ["patient_id", "scored_at"])

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_actor_created", "audit_log", ["actor_id", "created_at"])
    op.create_index("ix_audit_log_resource", "audit_log", ["resource_type", "resource_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("risk_scores")
    op.drop_table("appointments")
    op.drop_table("notification_log")
    op.drop_table("alert_acknowledgments")
    op.drop_table("alert_events")
    op.drop_table("alert_rules")
    op.drop_table("activity_records")
    op.drop_table("vital_sign_records")
    op.drop_table("patient_provider_assignments")
    op.drop_table("providers")
    op.drop_table("patients")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")

    for name in [
        "vital_metric", "alert_severity", "alert_status", "sex",
        "role_name", "notification_channel", "notification_status", "risk_level",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {name}")
