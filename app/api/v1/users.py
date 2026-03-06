from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=ApiResponse[list[UserResponse]])
async def list_users(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[UserResponse]]:
    """List all users (admin only)."""
    service = UserService(db)
    users = await service.list_users()

    return ApiResponse(
        success=True,
        data=[UserResponse.model_validate(u) for u in users],
    )


@router.post("", response_model=ApiResponse[UserResponse])
async def create_user(
    body: UserCreate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserResponse]:
    """Create a new user (admin only)."""
    service = UserService(db)
    user = await service.create_user(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=body.role,
    )

    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User created successfully",
    )


@router.put("/{user_id}", response_model=ApiResponse[UserResponse])
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserResponse]:
    """Update a user (admin only)."""
    service = UserService(db)
    user = await service.update_user(
        user_id=user_id,
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        is_active=body.is_active,
    )

    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User updated successfully",
    )


@router.delete("/{user_id}", response_model=ApiResponse[UserResponse])
async def delete_user(
    user_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserResponse]:
    """Deactivate a user (admin only)."""
    service = UserService(db)
    user = await service.deactivate_user(user_id)

    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User deactivated successfully",
    )
