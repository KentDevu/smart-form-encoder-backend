from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, TokenRefreshResponse
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LoginResponse]:
    """Authenticate user and return access token. Sets refresh token as httpOnly cookie."""
    service = AuthService(db)
    result = await service.login(body.email, body.password)

    # Set refresh token as httpOnly cookie
    # Use secure=True only for production (HTTPS)
    is_production = not settings.DEBUG
    response.set_cookie(
        key="refresh_token",
        value=result["refresh_token"],
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
        path="/api/v1/auth",
    )

    return ApiResponse(
        success=True,
        data=LoginResponse(access_token=result["access_token"]),
        message="Login successful",
    )


@router.post("/register", response_model=ApiResponse[UserResponse])
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserResponse]:
    """Register a new user (admin-created accounts)."""
    service = AuthService(db)
    user = await service.register(body.email, body.password, body.full_name, body.role)

    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user),
        message="User registered successfully",
    )


@router.post("/refresh", response_model=ApiResponse[TokenRefreshResponse])
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenRefreshResponse]:
    """Refresh access token using the httpOnly refresh token cookie."""
    # Get refresh token from cookie
    token = request.cookies.get("refresh_token")
    if not token:
        from app.core.exceptions import UnauthorizedException
        raise UnauthorizedException("Refresh token not found")

    service = AuthService(db)
    new_access_token = await service.refresh_access_token(token)

    return ApiResponse(
        success=True,
        data=TokenRefreshResponse(access_token=new_access_token),
        message="Token refreshed successfully",
    )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_me(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[UserResponse]:
    """Get the current authenticated user's profile."""
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(current_user),
    )


@router.post("/logout")
async def logout(response: Response) -> ApiResponse[None]:
    """Logout by clearing the refresh token cookie."""
    # Use same secure setting as login
    is_production = not settings.DEBUG
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        secure=is_production,
    )
    return ApiResponse(
        success=True,
        message="Logged out successfully",
    )
