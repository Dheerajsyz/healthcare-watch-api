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

# Database connection strings.
# Prefer a fully specified DATABASE_URL/SYNC_DATABASE_URL, but fall back to
# component-based construction (so we can inject secrets like DB_PASSWORD safely).
DATABASE_URL: str = os.environ.get("DATABASE_URL")
SYNC_DATABASE_URL: str = os.environ.get("SYNC_DATABASE_URL")

if not DATABASE_URL or not SYNC_DATABASE_URL:
    db_user = os.environ.get("DB_USER", "postgres")
    db_pass = os.environ.get("DB_PASSWORD", "healthtrack")
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME", "healthtrack")

    if not DATABASE_URL:
        DATABASE_URL = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    if not SYNC_DATABASE_URL:
        SYNC_DATABASE_URL = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

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
