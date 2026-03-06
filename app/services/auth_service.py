from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole


class AuthService:
    """Handles authentication business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self, email: str, password: str, full_name: str, role: str = "encoder"
    ) -> User:
        """Register a new user."""
        # Check if email already exists
        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise ConflictException("A user with this email already exists")

        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole(role),
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def login(self, email: str, password: str) -> dict:
        """Authenticate user and return tokens."""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedException("User account is deactivated")

        access_token = create_access_token(user.id, user.role.value)
        refresh_token = create_refresh_token(user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user,
        }

    async def refresh_access_token(self, refresh_token: str) -> str:
        """Validate refresh token and issue a new access token."""
        payload = decode_token(refresh_token)
        if payload is None:
            raise UnauthorizedException("Invalid or expired refresh token")

        if payload.get("type") != "refresh":
            raise BadRequestException("Invalid token type")

        user_id = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException("Invalid token payload")

        result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
        user = result.scalar_one_or_none()

        if user is None:
            raise NotFoundException("User not found")

        if not user.is_active:
            raise UnauthorizedException("User account is deactivated")

        return create_access_token(user.id, user.role.value)
