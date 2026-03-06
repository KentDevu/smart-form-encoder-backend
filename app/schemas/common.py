from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response shape."""
    success: bool = True
    data: T | None = None
    message: str = ""
    errors: list[str] = Field(default_factory=list)


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""
    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    items: list[T]
    total: int
    page: int
    per_page: int
    total_pages: int
