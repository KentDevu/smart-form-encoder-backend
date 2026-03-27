import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.core.exceptions import AppException
from app.redis_pool import (
    init_async_redis_pool,
    init_sync_redis_pool,
    close_async_redis_pool,
    close_sync_redis_pool,
)

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    try:
        init_async_redis_pool(
            settings.REDIS_URL,
            pool_size=settings.REDIS_POOL_SIZE,
            timeout=settings.REDIS_POOL_TIMEOUT,
        )
        init_sync_redis_pool(
            settings.REDIS_URL,
            pool_size=settings.REDIS_POOL_SIZE,
            timeout=settings.REDIS_POOL_TIMEOUT,
        )
        logger.info("Redis connection pools initialized")
        # Fix 5 & 6: Log memory optimization settings
        logger.info(f"[MEMORY CONFIG] Redis pool size: {settings.REDIS_POOL_SIZE} (timeout: {settings.REDIS_POOL_TIMEOUT}s)")
        logger.info(f"[MEMORY CONFIG] OCR model caching: {'ENABLED (500MB RAM)' if settings.CACHE_OCR_MODEL else 'DISABLED (lower RAM, slower)'}")
        logger.info(f"[MEMORY CONFIG] Debug mode: {settings.DEBUG}")
    except Exception as e:
        logger.error(f"Failed to initialize Redis pools: {e}")
        raise
    
    yield
    
    # Shutdown
    await close_async_redis_pool()
    close_sync_redis_pool()
    logger.info("Redis connection pools closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    origin = request.headers.get("origin")
    headers = {}
    if origin in settings.CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "message": exc.message,
            "errors": exc.errors,
        },
        headers=headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other exceptions with CORS headers."""
    origin = request.headers.get("origin")
    headers = {}
    if origin in settings.CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "message": "Internal server error",
            "errors": [],
        },
        headers=headers,
    )


# Include API v1 routes
app.include_router(v1_router, prefix=settings.API_V1_PREFIX)


# Health check
@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "version": settings.APP_VERSION}
