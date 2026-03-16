"""FastAPI dependencies: DB session, current user, RBAC, HIPAA audit logging."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.security import decode_token
from database.models import AuditLog, User, UserRole
from database.session import get_async_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------

AsyncDB = Annotated[AsyncSession, Depends(get_async_session)]


# ---------------------------------------------------------------------------
# Current user dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncDB,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "UNAUTHORIZED", "message": "Could not validate credentials.", "details": None}},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_user_roles(user: User) -> list[str]:
    return [ur.role.name for ur in user.user_roles]


def require_roles(*roles: str):
    """Dependency factory: require the current user to have at least one of the given roles."""

    async def _checker(current_user: CurrentUser) -> User:
        user_roles = get_user_roles(current_user)
        if not any(r in user_roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "Insufficient permissions.", "details": None}},
            )
        return current_user

    return _checker


# ---------------------------------------------------------------------------
# HIPAA Audit Logging
# ---------------------------------------------------------------------------

def _write_audit_log(
    db_session_factory,
    actor_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> None:
    """Synchronous audit writer executed as a background task.

    Uses a separate session to avoid coupling with the request session lifetime.
    """
    # Import here to avoid circular imports
    import asyncio
    from database.session import AsyncSessionLocal

    async def _write():
        async with AsyncSessionLocal() as session:
            log = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=None,
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            await session.commit()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_write())
        else:
            loop.run_until_complete(_write())
    except Exception:
        pass  # Audit failures must never break the main request


def audit_phi_access(action: str, resource_type: str):
    """Dependency factory that schedules a HIPAA audit log entry as a background task.

    Usage::

        @router.get("/{patient_id}/vitals")
        async def list_vitals(
            patient_id: str,
            _audit=Depends(audit_phi_access("READ", "vital_sign_records")),
            ...
        ):
    """

    def _dep(
        request: Request,
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
    ):
        resource_id = request.path_params.get("patient_id")
        actor_id = current_user.id
        ip_addr = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

        background_tasks.add_task(
            _write_audit_log,
            None,  # session_factory not used (uses its own session)
            actor_id,
            action,
            resource_type,
            resource_id,
            ip_addr,
            ua,
        )

    return Depends(_dep)
