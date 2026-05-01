from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_chain import require_roles
from app.schemas.user import (
    PromoteUserRequest,
    PromotionRequestResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter()

require_platform_admin = require_roles(["platform_admin"])


@router.get("/promotion-requests", response_model=list[PromotionRequestResponse])
async def list_promotion_requests(
    admin_id: str = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.list_promotion_requests(db)


@router.post("/users/promote", response_model=UserResponse)
async def promote_user(
    request: PromoteUserRequest,
    admin_id: str = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.promote_user(request, admin_id, db)
