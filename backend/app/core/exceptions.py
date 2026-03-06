from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""

    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        message: str = "An unexpected error occurred",
        errors: list | None = None,
    ):
        self.message = message
        self.errors = errors or []
        super().__init__(status_code=status_code, detail=message)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Not authenticated"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
        )


class ForbiddenException(AppException):
    def __init__(self, message: str = "Not enough permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
        )


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            message=message,
        )


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request", errors: list | None = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message,
            errors=errors,
        )


class ConflictException(AppException):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            message=message,
        )
