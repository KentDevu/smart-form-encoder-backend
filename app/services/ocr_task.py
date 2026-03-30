"""
OCR Task Module - Now using GLM-OCR backend

This module has been refactored to use GLM-OCR (single-pass vision-language model)
instead of the previous Paddle+Groq multi-stage pipeline.

For full implementation details, see glm_ocr_task.py
"""

# Re-export the GLM-based task for backward compatibility
from app.services.glm_ocr_task import (
    process_ocr_task,
    _sync_publish_progress,
    _download_image_from_r2,
    celery_app,
)

__all__ = ["process_ocr_task", "celery_app"]
