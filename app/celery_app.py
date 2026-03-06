"""Celery application configuration."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "smartform_ocr",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.services.ocr_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Manila",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
