"""SQLAlchemy engine and session factories.

Provides both async (AsyncSession) and sync (Session) factories:
- Async is used by the FastAPI API layer.
- Sync is used by Alembic migrations and seed scripts.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

ASYNC_DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://healthtrack:healthtrack@localhost:5432/healthtrack",
)
SYNC_DATABASE_URL: str = os.environ.get(
    "SYNC_DATABASE_URL",
    "postgresql://healthtrack:healthtrack@localhost:5432/healthtrack",
)

# ---------------------------------------------------------------------------
# Async engine (FastAPI)
# ---------------------------------------------------------------------------
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_async_session() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency that yields an AsyncSession."""
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Sync engine (Alembic / seed scripts)
# ---------------------------------------------------------------------------
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)
