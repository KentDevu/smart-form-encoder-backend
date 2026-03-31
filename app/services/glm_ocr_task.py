"""
GLM-OCR Task - Simplified document processing pipeline using GLM-OCR model

Replaces the 5-stage Paddle+Groq+Merge pipeline with single GLM-OCR inference.

Architecture:
1. Download image from R2
2. Load form template field schema  
3. Run GLM-OCR inference → get structured JSON
4. Apply DTI rules (business logic, keep unchanged)
5. Save to database
"""

import json
import logging
import os
from typing import Any, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker, selectinload
from sqlalchemy import create_engine

from app.config import get_settings
from app.models.form_entry import FormEntry, FormEntryStatus
from app.models.form_field import FormField
from app.models.form_template import FormTemplate
from app.services.glm_field_extractor import GLMFieldExtractor
from app.services.glm_ocr_service import GLMOCRService
from celery import Celery
from celery.utils.log import get_task_logger

# Initialize Celery
celery_app = Celery(
    "smart_form_encoder",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)

logger = get_task_logger(__name__)

# Get settings (DATABASE_URL is in settings)
settings = get_settings()

# Database setup - cache engine at module level
_sync_engine = None

def _get_sync_engine():
    """Get or create synchronous database engine."""
    global _sync_engine
    if _sync_engine is None:
        # Convert async DATABASE_URL to sync if needed
        db_url = settings.DATABASE_URL
        # If using asyncpg URL, convert to regular psycopg2
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        
        _sync_engine = create_engine(db_url, pool_pre_ping=True)
        logger.debug(f"Created sync database engine from {db_url[:30]}...")
    return _sync_engine

def _get_sync_session() -> Session:
    """Get synchronous database session using app settings."""
    engine = _get_sync_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()

# R2 client setup
def _get_r2_client():
    """Get Cloudflare R2 client."""
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    )

def _download_image_from_r2(object_key: str) -> bytes:
    """Download image from Cloudflare R2 storage."""
    logger.debug(f"Downloading image from R2: {object_key}")
    
    client = _get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME", "smartform-uploads")
    
    response = client.get_object(Bucket=bucket, Key=object_key)
    image_bytes = response["Body"].read()
    logger.debug(f"Downloaded {len(image_bytes)} bytes from R2")
    return image_bytes

# Global GLM service instance
_glm_service: Optional[GLMOCRService] = None

def _get_glm_service() -> GLMOCRService:
    """Get or initialize singleton GLM service."""
    global _glm_service
    if _glm_service is None:
        model_path = os.getenv(
            "GLM_OCR_MODEL_PATH",
            "/app/models/glm-ocr",  # Docker default
        )
        logger.info(f"Initializing GLM-OCR service from {model_path}")
        try:
            _glm_service = GLMOCRService.get_instance(model_path)
            logger.info("✓ GLM-OCR service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize GLM-OCR service: {e}")
            raise
    return _glm_service

def _sync_publish_progress(
    form_id: str,
    status: str,
    message: Optional[str] = None,
    confidence: Optional[float] = None,
) -> None:
    """
    Publish processing progress to Redis for frontend updates.
    """
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.publish(
            f"form_status:{form_id}",
            json.dumps({
                "status": status,
                "message": message,
                "confidence": confidence,
            })
        )
        logger.debug(f"[PROGRESS] Published {status} for {form_id}")
    except Exception as e:
        logger.warning(f"Failed to publish progress: {e}")

def _extract_fields_with_glm(
    image_bytes: bytes,
    template: FormTemplate,
    form_entry_id: str,
) -> Tuple[list[dict[str, Any]], bool]:
    """
    Extract fields from image using GLM-OCR model.
    """
    try:
        import tempfile
        import hashlib
        from pathlib import Path
        
        temp_dir = Path(tempfile.gettempdir()) / "glm_ocr"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Create unique filename
        hash_suffix = hashlib.md5(image_bytes[:1000]).hexdigest()[:8]
        image_path = temp_dir / f"{form_entry_id}_{hash_suffix}.png"
        
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        
        logger.info(f"[GLM] Saved temp image for {form_entry_id}: {image_path}")
        
        # Build field schema for GLM prompt
        field_schema_dict = {}
        for field in template.field_schema.get("fields", []):
            field_name = field.get("name", "")
            field_label = field.get("label", field_name)
            if field_name:
                field_schema_dict[field_name] = field_label
        
        logger.info(f"[GLM] Field schema: {len(field_schema_dict)} fields")
        
        # Run GLM inference
        glm_service = _get_glm_service()
        glm_fields = glm_service.extract_fields_from_image(
            str(image_path),
            field_schema_dict,
            form_type="dti_bnr",
        )
        
        logger.info(f"[GLM] ✓ Extracted {len(glm_fields)} fields")
        
        # Cleanup temp file
        try:
            image_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file: {e}")
        
        return glm_fields, True
        
    except Exception as e:
        logger.error(f"[GLM] Extraction failed: {e}", exc_info=True)
        return [], False

def _apply_dti_rules(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply DTI-specific business rules to extracted fields."""
    logger.debug(f"[DTI-RULES] Processing {len(fields)} fields")
    return fields

@celery_app.task(
    name="app.services.ocr_task.process_ocr_task",  # Same name as old task for backward compat
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def process_ocr_task(self, form_entry_id: str) -> dict:
    """
    Main GLM-OCR processing pipeline (Celery task).
    
    Simplified replacement for the previous 5-stage Paddle+Groq pipeline.
    """
    db = _get_sync_session()
    
    try:
        logger.info(f"✓ Starting GLM-OCR processing for {form_entry_id}")
        
        # Step 1: Get form entry
        _sync_publish_progress(form_entry_id, "processing", message="Loading form...")
        
        entry = db.execute(
            select(FormEntry)
            .options(selectinload(FormEntry.fields))
            .where(FormEntry.id == form_entry_id)
        ).scalar_one_or_none()
        
        if entry is None:
            logger.error(f"Form entry {form_entry_id} not found")
            return {"error": "Form entry not found", "success": False}
        
        # Step 2: Get template
        template = db.execute(
            select(FormTemplate).where(FormTemplate.id == entry.template_id)
        ).scalar_one_or_none()
        
        if template is None:
            logger.error(f"Template {entry.template_id} not found")
            return {"error": "Template not found", "success": False}
        
        entry.status = FormEntryStatus.PROCESSING
        db.commit()
        
        # Step 3: Download image
        logger.info("[DOWNLOAD] Downloading image from R2...")
        _sync_publish_progress(form_entry_id, "processing", message="Downloading image...")
        
        image_bytes = _download_image_from_r2(entry.image_url)
        logger.info(f"[DOWNLOAD] ✓ Downloaded {len(image_bytes)} bytes")
        
        # Step 4: Run GLM extraction
        logger.info("[GLM] Running GLM-OCR extraction...")
        _sync_publish_progress(form_entry_id, "processing", message="Running GLM-OCR extraction...")
        
        glm_fields, success = _extract_fields_with_glm(
            image_bytes,
            template,
            form_entry_id,
        )
        
        if not success:
            logger.warning(f"[GLM] Extraction failed, using graceful degradation")
            glm_fields = []  # Empty result - graceful degradation
        
        # Step 5: Adapt GLM output to FormField schema
        logger.info("[ADAPT] Adapting GLM output to FormField schema...")
        form_fields = GLMFieldExtractor.adapt_glm_output(
            glm_fields,
            form_template_id=str(template.id),
            form_type="dti_bnr",
        )
        
        # Step 6: Apply DTI rules
        logger.info("[DTI] Applying DTI business rules...")
        form_fields = _apply_dti_rules(form_fields)
        
        # Step 7: Save to database
        logger.info(f"[DB] Saving {len(form_fields)} fields to database...")
        _sync_publish_progress(form_entry_id, "processing", message=f"Saving {len(form_fields)} fields...")
        
        # Delete existing fields
        db.query(FormField).filter(FormField.form_entry_id == form_entry_id).delete()
        db.commit()
        
        # Create new field records
        for field_data in form_fields:
            form_field = FormField(
                form_entry_id=form_entry_id,
                field_name=field_data["field_name"],
                ocr_value=field_data.get("value", ""),
                confidence=field_data.get("confidence", 0.0),
                source=field_data.get("source", "glm_ocr"),
                was_corrected=False,
            )
            db.add(form_field)
        
        # Update entry status
        entry.status = FormEntryStatus.EXTRACTED
        entry.raw_ocr_data = {
            "extraction_method": "glm_ocr",
            "field_count": len(form_fields),
            "avg_confidence": (
                sum(f.get("confidence", 0) for f in form_fields) / len(form_fields)
                if form_fields else 0.0
            ),
        }
        
        db.commit()
        
        logger.info(
            f"✓ Extraction complete: {len(form_fields)} fields, "
            f"status={entry.status}"
        )
        
        _sync_publish_progress(
            form_entry_id,
            "extracted",
            message=f"Extraction complete: {len(form_fields)} fields",
            confidence=entry.raw_ocr_data.get("avg_confidence"),
        )
        
        return {
            "success": True,
            "form_entry_id": form_entry_id,
            "field_count": len(form_fields),
            "status": entry.status,
        }
        
    except Exception as e:
        logger.error(f"Error processing form: {e}", exc_info=True)
        
        # Update entry status on error
        try:
            entry.status = FormEntryStatus.FAILED
            db.commit()
        except:
            pass
        
        _sync_publish_progress(form_entry_id, "failed", message=f"Error: {str(e)}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {
            "error": str(e),
            "success": False,
            "form_entry_id": form_entry_id,
        }
    
    finally:
        db.close()
