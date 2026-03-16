"""pytest configuration: in-memory SQLite async test database."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.base import Base
from database.models import Patient, Role, User, UserRole
from database.session import get_async_session
from api.security import hash_password


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    # Seed all roles once at session scope
    async with factory() as session:
        for role_name in ("PATIENT", "PROVIDER", "ADMIN"):
            existing = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
            if not existing:
                session.add(Role(id=_id(), name=role_name, description=role_name))
        await session.commit()
    return factory


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    from api.main import create_app

    app = create_app()

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _id():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


async def _create_user_with_role(session: AsyncSession, email: str, password: str, full_name: str, role_name: str) -> tuple[User, str]:
    """Create a user+role in the test DB and return (user, role_id)."""
    existing_role = (await session.execute(
        select(Role).where(Role.name == role_name)
    )).scalar_one_or_none()

    if not existing_role:
        existing_role = Role(id=_id(), name=role_name, description=role_name)
        session.add(existing_role)
        await session.flush()

    # Check if user already exists
    existing_user = (await session.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()
    if existing_user:
        return existing_user, existing_role.id

    user = User(
        id=_id(),
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(user)
    await session.flush()
    session.add(UserRole(id=_id(), user_id=user.id, role_id=existing_role.id, assigned_at=_now()))
    await session.commit()
    return user, existing_role.id


@pytest_asyncio.fixture
async def provider_token(client: AsyncClient, session_factory):
    async with session_factory() as session:
        await _create_user_with_role(session, "prov@test.com", "Password1!", "Dr Test", "PROVIDER")
    resp = await client.post("/auth/token", data={"username": "prov@test.com", "password": "Password1!"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient, session_factory):
    async with session_factory() as session:
        await _create_user_with_role(session, "admin@test.com", "Password1!", "Admin Test", "ADMIN")
    resp = await client.post("/auth/token", data={"username": "admin@test.com", "password": "Password1!"})
    assert resp.status_code == 200
    return resp.json()["access_token"]

