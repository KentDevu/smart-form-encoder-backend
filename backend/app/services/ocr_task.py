"""Celery task for OCR processing pipeline."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload, Session
from sqlalchemy import create_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.models.form_entry import FormEntry, FormEntryStatus
from app.models.form_field import FormField
from app.models.form_template import FormTemplate
from app.services.ocr_service import (
    enhance_with_vision,
    extract_text_from_image,
    map_ocr_to_fields,
)
from app.services.storage_service import _get_r2_client

logger = logging.getLogger(__name__)
settings = get_settings()

LOW_CONFIDENCE_THRESHOLD = 0.7


def _get_sync_session() -> Session:
    """Create a synchronous DB session for Celery tasks."""
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(settings.DATABASE_SYNC_URL)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _download_image_from_r2(object_key: str) -> bytes:
    """Download an image from R2 and return bytes."""
    client = _get_r2_client()
    response = client.get_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=object_key,
    )
    return response["Body"].read()


@celery_app.task(
    name="app.services.ocr_task.process_ocr_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def process_ocr_task(self, form_entry_id: str) -> dict:
    """
    Main OCR processing pipeline:
    1. Download image from R2
    2. Run PaddleOCR
    3. Map text to form fields
    4. Enhance low-confidence fields with AI Vision
    5. Save results to DB
    """
    db = _get_sync_session()

    try:
        # Get the form entry with template
        entry = db.execute(
            select(FormEntry)
            .options(selectinload(FormEntry.fields))
            .where(FormEntry.id == form_entry_id)
        ).scalar_one_or_none()

        if entry is None:
            logger.error(f"Form entry {form_entry_id} not found")
            return {"error": "Form entry not found"}

        # Get template for field schema
        template = db.execute(
            select(FormTemplate).where(FormTemplate.id == entry.template_id)
        ).scalar_one_or_none()

        if template is None:
            logger.error(f"Template {entry.template_id} not found")
            return {"error": "Template not found"}

        # Update status to processing
        entry.status = FormEntryStatus.PROCESSING
        db.commit()

        logger.info(f"Starting OCR for entry {form_entry_id}")

        # Step 1: Download image
        image_bytes = _download_image_from_r2(entry.image_url)
        logger.info(f"Downloaded image: {len(image_bytes)} bytes")

        # Step 2: Run PaddleOCR
        ocr_result = extract_text_from_image(image_bytes)
        logger.info(
            f"OCR complete: {len(ocr_result['raw_lines'])} lines, "
            f"avg confidence: {ocr_result['avg_confidence']:.2f}"
        )

        # Step 3: Map to form fields (AI-powered with PaddleOCR text + image)
        mapped_fields = map_ocr_to_fields(ocr_result, template.field_schema, image_bytes)

        # Step 4: Enhance any remaining low-confidence fields with targeted vision
        low_conf_fields = [
            f["field_name"] for f in mapped_fields
            if f["confidence"] < LOW_CONFIDENCE_THRESHOLD and f["field_name"]
        ]

        if low_conf_fields:
            logger.info(f"Enhancing {len(low_conf_fields)} low-confidence fields with AI Vision")
            enhanced = enhance_with_vision(
                image_bytes, template.field_schema, low_conf_fields
            )

            # Merge enhanced results
            for field in mapped_fields:
                if field["field_name"] in enhanced:
                    enh = enhanced[field["field_name"]]
                    field["ocr_value"] = enh["value"]
                    field["confidence"] = enh["confidence"]

        # Step 5: Save results to DB
        # Clear existing fields
        for existing_field in entry.fields:
            db.delete(existing_field)

        # Create new fields
        total_confidence = 0.0
        for field_data in mapped_fields:
            form_field = FormField(
                entry_id=entry.id,
                field_name=field_data["field_name"],
                ocr_value=field_data["ocr_value"],
                confidence=field_data["confidence"],
            )
            db.add(form_field)
            total_confidence += field_data["confidence"]

        # Update entry
        avg_confidence = (
            total_confidence / len(mapped_fields)
            if mapped_fields else 0.0
        )
        entry.raw_ocr_data = {
            "full_text": ocr_result["full_text"],
            "raw_lines": ocr_result["raw_lines"],
            "field_count": len(mapped_fields),
        }
        entry.confidence_score = avg_confidence
        entry.processing_time = ocr_result["processing_time"]
        entry.status = FormEntryStatus.EXTRACTED

        db.commit()

        logger.info(
            f"OCR pipeline complete for entry {form_entry_id}: "
            f"{len(mapped_fields)} fields, avg confidence: {avg_confidence:.2f}"
        )

        return {
            "entry_id": form_entry_id,
            "status": "extracted",
            "fields_count": len(mapped_fields),
            "avg_confidence": avg_confidence,
            "processing_time": ocr_result["processing_time"],
        }

    except Exception as exc:
        logger.exception(f"OCR processing failed for entry {form_entry_id}")
        # Update status back to uploaded on failure
        try:
            entry = db.execute(
                select(FormEntry).where(FormEntry.id == form_entry_id)
            ).scalar_one_or_none()
            if entry:
                entry.status = FormEntryStatus.UPLOADED
                db.commit()
        except Exception:
            db.rollback()

        # Retry
        raise self.retry(exc=exc)

    finally:
        db.close()
