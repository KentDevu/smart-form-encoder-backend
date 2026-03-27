"""Celery application configuration for memory-efficient OCR processing."""

import logging
from celery import Celery
from celery.signals import worker_process_init

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

celery_app = Celery(
    "smartform_ocr",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.services.ocr_task"],
)

# Memory-efficient Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Manila",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Memory optimization settings
    task_soft_time_limit=300,  # 5 minutes max per task
    task_time_limit=360,       # 6 minutes hard limit
    worker_disable_rate_limits=True,  # Disable rate limiting
    task_compression="gzip",   # Compress task messages
    result_compression="gzip", # Compress results
    # Worker memory recycling: restart after N tasks to prevent memory leak accumulation
    # CELERY_MAX_TASKS_PER_CHILD is set to 50 for optimal performance (good tradeoff)
    worker_max_tasks_per_child=getattr(settings, "CELERY_MAX_TASKS_PER_CHILD", 50),
    # Result expiration: keep in Redis for 1 hour to avoid memory bloat
    result_expires=3600,
)


@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize Redis pool when Celery worker process starts."""
    try:
        from app.redis_pool import init_sync_redis_pool
        init_sync_redis_pool(settings.REDIS_URL)
        logger.info("[Celery] Sync Redis pool initialized in worker process")
        # Fix 6: Log model caching setting
        logger.info(f"[Celery][MEMORY CONFIG] OCR model caching: {'ENABLED (500MB RAM)' if settings.CACHE_OCR_MODEL else 'DISABLED (lower RAM, slower)'}")
        logger.info(f"[Celery][MEMORY CONFIG] Worker max tasks per child: {settings.CELERY_MAX_TASKS_PER_CHILD} (auto-restart after N tasks)")
    except Exception as e:
        logger.error(f"[Celery] Failed to initialize Redis pool: {e}", exc_info=True)
