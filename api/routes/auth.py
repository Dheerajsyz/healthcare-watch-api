"""Auth routes — OAuth2 password flow (POST /auth/token)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from api.dal import UserRepository
from api.dependencies import AsyncDB
from api.schemas import TokenResponse
from api.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_password

router = APIRouter()


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Obtain a JWT access token (OAuth2 password flow)",
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncDB = None,
) -> TokenResponse:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(form.username)

    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password.", "details": None}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "ACCOUNT_DISABLED", "message": "Account is disabled.", "details": None}},
        )

    roles = [ur.role.name for ur in user.user_roles]
    token = create_access_token(
        data={"sub": user.id, "roles": roles},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=token)


    roles = [ur.role.name for ur in user.user_roles]
    token = create_access_token(
        data={"sub": user.id, "roles": roles},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=token)
