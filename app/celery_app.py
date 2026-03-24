"""Celery application configuration for memory-efficient OCR processing."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

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
)

# In low-RAM mode, add aggressive memory recycling settings
if settings.LOW_RAM_MODE:
    celery_app.conf.update(
        # Restart worker after N tasks to free accumulated memory
        CELERYD_MAX_TASKS_PER_CHILD=getattr(settings, "CELERY_MAX_TASKS_PER_CHILD", 5),
        # Lower result expiration to free Redis memory
        result_expires=3600,  # 1 hour
        # Disable task result storage if not needed
        task_ignore_result=False,  # We need results for progress tracking
    )
