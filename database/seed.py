"""Seed script — inserts roles and sample users (admin, provider, patient).

Usage:
    SYNC_DATABASE_URL=postgresql://... python -m database.seed
    # or via docker compose:
    docker compose run --rm api python -m database.seed
"""

import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# Must set SYNC_DATABASE_URL before importing session
from database.session import SyncSessionLocal  # noqa: E402
from database.models import (  # noqa: E402
    Role,
    User,
    UserRole,
    Patient,
    Provider,
    PatientProviderAssignment,
    AlertRule,
)
from passlib.context import CryptContext  # noqa: E402

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


def _hash(plain: str) -> str:
    return _pwd_context.hash(plain)


ADMIN_HASH = _hash("Admin1!")
PROVIDER_HASH = _hash("Provider1!")
PATIENT_HASH = _hash("Patient1!")


def seed() -> None:
    session = SyncSessionLocal()
    try:
        # --- Roles ---
        roles: dict[str, Role] = {}
        for role_name in ("PATIENT", "PROVIDER", "ADMIN"):
            existing = session.query(Role).filter_by(name=role_name).first()
            if existing:
                roles[role_name] = existing
            else:
                role = Role(id=_id(), name=role_name, description=f"{role_name} role")
                session.add(role)
                roles[role_name] = role
        session.flush()

        # --- Admin user ---
        admin_user = session.query(User).filter_by(email="admin@healthtrack.local").first()
        if not admin_user:
            admin_user = User(
                id=_id(),
                email="admin@healthtrack.local",
                password_hash=ADMIN_HASH,
                full_name="System Admin",
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(admin_user)
            session.flush()
            session.add(UserRole(id=_id(), user_id=admin_user.id, role_id=roles["ADMIN"].id, assigned_at=_now()))

        # --- Provider user ---
        provider_user = session.query(User).filter_by(email="provider@healthtrack.local").first()
        if not provider_user:
            provider_user = User(
                id=_id(),
                email="provider@healthtrack.local",
                password_hash=PROVIDER_HASH,
                full_name="Dr. Jane Smith",
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(provider_user)
            session.flush()
            session.add(UserRole(id=_id(), user_id=provider_user.id, role_id=roles["PROVIDER"].id, assigned_at=_now()))

            provider = Provider(
                id=_id(),
                user_id=provider_user.id,
                specialty="Cardiology",
                license_number="MD-12345",
                department="Internal Medicine",
                created_at=_now(),
            )
            session.add(provider)
        else:
            provider = session.query(Provider).filter_by(user_id=provider_user.id).first()
        session.flush()

        # --- Patient user ---
        patient_user = session.query(User).filter_by(email="patient@healthtrack.local").first()
        if not patient_user:
            patient_user = User(
                id=_id(),
                email="patient@healthtrack.local",
                password_hash=PATIENT_HASH,
                full_name="John Doe",
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(patient_user)
            session.flush()
            session.add(UserRole(id=_id(), user_id=patient_user.id, role_id=roles["PATIENT"].id, assigned_at=_now()))

            patient = Patient(
                id=_id(),
                user_id=patient_user.id,
                date_of_birth="1980-05-15",
                sex="M",
                phone="+1-555-0100",
                consent_given=True,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(patient)
            session.flush()

            # Assign provider → patient
            if provider:
                session.add(
                    PatientProviderAssignment(
                        id=_id(),
                        patient_id=patient.id,
                        provider_id=provider.id,
                        assigned_at=_now(),
                        active=True,
                    )
                )

            # Default alert rules (system-wide, patient_id=None)
            default_rules = [
                AlertRule(id=_id(), patient_id=None, metric="SPO2",    threshold_min=92,  threshold_max=None, severity="CRITICAL", suppression_window_minutes=5,  is_active=True, created_at=_now(), updated_at=_now()),
                AlertRule(id=_id(), patient_id=None, metric="HR",      threshold_min=None, threshold_max=120, severity="WARNING",  suppression_window_minutes=5,  is_active=True, created_at=_now(), updated_at=_now()),
                AlertRule(id=_id(), patient_id=None, metric="BP_SYS",  threshold_min=None, threshold_max=140, severity="WARNING",  suppression_window_minutes=10, is_active=True, created_at=_now(), updated_at=_now()),
                AlertRule(id=_id(), patient_id=None, metric="GLUCOSE", threshold_min=None, threshold_max=200, severity="WARNING",  suppression_window_minutes=15, is_active=True, created_at=_now(), updated_at=_now()),
            ]
            session.add_all(default_rules)

        session.commit()
        print("✅ Seed complete.")
        print("   admin@healthtrack.local     / Admin1!")
        print("   provider@healthtrack.local  / Provider1!")
        print("   patient@healthtrack.local   / Patient1!")

    except Exception as exc:
        session.rollback()
        print(f"❌ Seed failed: {exc}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
