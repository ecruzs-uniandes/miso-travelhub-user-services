from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_chain import get_current_user_id
from app.schemas.user import (
    MessageResponse,
    MFASetupResponse,
    MFAVerifyRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.services import auth_service

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(request: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.register_user(request, db)


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.login_user(
        request.email, request.password, request.totp_code, db
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.refresh_tokens(request.refresh_token, db)


@router.get("/me", response_model=UserResponse)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.get_current_user(user_id, db)


@router.put("/me", response_model=UserResponse)
async def update_me(
    request: UserUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.update_user(user_id, request, db)


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.setup_mfa(user_id, db)


@router.post("/mfa/verify", response_model=MessageResponse)
async def mfa_verify(
    request: MFAVerifyRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.verify_mfa(user_id, request.totp_code, db)
