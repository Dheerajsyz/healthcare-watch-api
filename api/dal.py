"""Data Access Layer — repository classes using SQLAlchemy select() queries."""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    ActivityRecord,
    AlertEvent,
    AlertRule,
    AuditLog,
    NotificationLog,
    Patient,
    Role,
    RiskScore,
    User,
    UserRole,
    VitalSignRecord,
)


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        return user


# ---------------------------------------------------------------------------
# RoleRepository
# ---------------------------------------------------------------------------

class RoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_name(self, name: str) -> Optional[Role]:
        result = await self.db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# PatientRepository
# ---------------------------------------------------------------------------

class PatientRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, patient_id: str) -> Optional[Patient]:
        result = await self.db.execute(
            select(Patient)
            .where(Patient.id == patient_id)
            .options(selectinload(Patient.user))
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: str) -> Optional[Patient]:
        result = await self.db.execute(
            select(Patient)
            .where(Patient.user_id == user_id)
            .options(selectinload(Patient.user))
        )
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 20, offset: int = 0) -> tuple[int, Sequence[Patient]]:
        count_q = select(func.count()).select_from(Patient)
        total = (await self.db.execute(count_q)).scalar_one()
        rows = (
            await self.db.execute(
                select(Patient)
                .options(selectinload(Patient.user))
                .order_by(Patient.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return total, rows

    async def create(self, patient: Patient) -> Patient:
        self.db.add(patient)
        await self.db.flush()
        return patient

    async def update(self, patient: Patient) -> Patient:
        await self.db.flush()
        return patient


# ---------------------------------------------------------------------------
# VitalSignRepository
# ---------------------------------------------------------------------------

class VitalSignRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, record: VitalSignRecord) -> VitalSignRecord:
        self.db.add(record)
        await self.db.flush()
        return record

    async def list_for_patient(
        self,
        patient_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        metric: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, Sequence[VitalSignRecord]]:
        base = select(VitalSignRecord).where(VitalSignRecord.patient_id == patient_id)
        if start:
            base = base.where(VitalSignRecord.recorded_at >= start)
        if end:
            base = base.where(VitalSignRecord.recorded_at <= end)
        if metric:
            base = base.where(VitalSignRecord.metric == metric)

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        rows = (
            await self.db.execute(
                base.order_by(VitalSignRecord.recorded_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return total, rows

    async def list_recent_for_risk(
        self, patient_id: str, since: datetime
    ) -> Sequence[VitalSignRecord]:
        result = await self.db.execute(
            select(VitalSignRecord)
            .where(
                VitalSignRecord.patient_id == patient_id,
                VitalSignRecord.recorded_at >= since,
            )
        )
        return result.scalars().all()


# ---------------------------------------------------------------------------
# ActivityRepository
# ---------------------------------------------------------------------------

class ActivityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, record: ActivityRecord) -> ActivityRecord:
        self.db.add(record)
        await self.db.flush()
        return record

    async def list_for_patient(
        self,
        patient_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, Sequence[ActivityRecord]]:
        base = select(ActivityRecord).where(ActivityRecord.patient_id == patient_id)
        if start:
            base = base.where(ActivityRecord.recorded_at >= start)
        if end:
            base = base.where(ActivityRecord.recorded_at <= end)

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        rows = (
            await self.db.execute(
                base.order_by(ActivityRecord.recorded_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return total, rows

    async def list_recent_for_risk(
        self, patient_id: str, since: datetime
    ) -> Sequence[ActivityRecord]:
        result = await self.db.execute(
            select(ActivityRecord)
            .where(
                ActivityRecord.patient_id == patient_id,
                ActivityRecord.recorded_at >= since,
            )
        )
        return result.scalars().all()


# ---------------------------------------------------------------------------
# AlertRuleRepository
# ---------------------------------------------------------------------------

class AlertRuleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_for_patient_metric(
        self, patient_id: str, metric: str
    ) -> Sequence[AlertRule]:
        """Return patient-specific rules first, then fall back to system-wide (patient_id IS NULL)."""
        result = await self.db.execute(
            select(AlertRule)
            .where(
                AlertRule.is_active == True,
                AlertRule.metric == metric,
                (AlertRule.patient_id == patient_id) | (AlertRule.patient_id == None),
            )
        )
        return result.scalars().all()


# ---------------------------------------------------------------------------
# AlertEventRepository
# ---------------------------------------------------------------------------

class AlertEventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, event: AlertEvent) -> AlertEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_by_id(self, alert_id: str) -> Optional[AlertEvent]:
        result = await self.db.execute(
            select(AlertEvent).where(AlertEvent.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_open_for_rule(
        self, patient_id: str, rule_id: str
    ) -> Optional[AlertEvent]:
        result = await self.db.execute(
            select(AlertEvent)
            .where(
                AlertEvent.patient_id == patient_id,
                AlertEvent.rule_id == rule_id,
                AlertEvent.status.in_(["OPEN", "ACKNOWLEDGED"]),
            )
            .order_by(AlertEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_patient(
        self,
        patient_id: str,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, Sequence[AlertEvent]]:
        base = select(AlertEvent).where(AlertEvent.patient_id == patient_id)
        if status:
            base = base.where(AlertEvent.status == status)
        if severity:
            base = base.where(AlertEvent.severity == severity)

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        rows = (
            await self.db.execute(
                base.order_by(AlertEvent.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return total, rows

    async def count_recent_for_patient(
        self, patient_id: str, since: datetime
    ) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(AlertEvent)
            .where(
                AlertEvent.patient_id == patient_id,
                AlertEvent.created_at >= since,
                AlertEvent.severity.in_(["WARNING", "CRITICAL"]),
            )
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# RiskScoreRepository
# ---------------------------------------------------------------------------

class RiskScoreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, score: RiskScore) -> RiskScore:
        self.db.add(score)
        await self.db.flush()
        return score

    async def get_latest_for_patient(self, patient_id: str) -> Optional[RiskScore]:
        result = await self.db.execute(
            select(RiskScore)
            .where(RiskScore.patient_id == patient_id)
            .order_by(RiskScore.scored_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# AuditLogRepository
# ---------------------------------------------------------------------------

class AuditLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, log: AuditLog) -> AuditLog:
        self.db.add(log)
        await self.db.flush()
        return log


# ---------------------------------------------------------------------------
# NotificationLogRepository
# ---------------------------------------------------------------------------

class NotificationLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, log: NotificationLog) -> NotificationLog:
        self.db.add(log)
        await self.db.flush()
        return log
