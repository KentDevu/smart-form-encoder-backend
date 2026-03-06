from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import hash_password
from app.models.user import User, UserRole


class UserService:
    """Handles user management business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(self) -> list[User]:
        """List all users (admin only)."""
        result = await self.db.execute(
            select(User).order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_user(self, user_id: UUID) -> User:
        """Get a user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundException("User not found")
        return user

    async def create_user(
        self, email: str, password: str, full_name: str, role: str = "encoder"
    ) -> User:
        """Create a new user (admin only)."""
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

    async def update_user(
        self,
        user_id: UUID,
        email: str | None = None,
        full_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Update user details (admin only)."""
        user = await self.get_user(user_id)

        if email and email != user.email:
            result = await self.db.execute(select(User).where(User.email == email))
            if result.scalar_one_or_none():
                raise ConflictException("A user with this email already exists")
            user.email = email

        if full_name is not None:
            user.full_name = full_name
        if role is not None:
            user.role = UserRole(role)
        if is_active is not None:
            user.is_active = is_active

        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def deactivate_user(self, user_id: UUID) -> User:
        """Deactivate a user (admin only)."""
        user = await self.get_user(user_id)
        user.is_active = False
        await self.db.flush()
        await self.db.refresh(user)
        return user
