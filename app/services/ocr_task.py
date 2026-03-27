"""Celery task for OCR processing pipeline."""

import gc
import json
import logging
from typing import Any, TypedDict

from pydantic import BaseModel, Field, validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload, Session
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from app.celery_app import celery_app
from app.config import get_settings
from app.models.form_entry import FormEntry, FormEntryStatus
from app.models.form_field import FormField
from app.models.form_template import FormTemplate
from app.services.ocr_service import (
    enhance_with_vision,
    extract_text_from_image,
    extract_text_from_image_with_template,
)
from app.services.ocr_unified import extract_fields_unified
from app.services.forms.dti_bnr_rules import apply_dti_bnr_corrections
from app.services.forms.template_schema import normalize_template_schema
from app.services.forms.template_field_extractor import extract_fields_with_template_map
from app.services.error_classifier import classify_error, should_retry_stage, get_retry_delay, log_error_classification
from app.services.redis_cache import (
    get_cached_ocr_result,
    cache_ocr_result,
    get_cached_field_extraction,
    cache_field_extraction,
)
from app.services.parallel_ops import parallel_cache_check, parallel_caching
from app.services.storage_service import _get_r2_client

logger = logging.getLogger(__name__)
settings = get_settings()

LOW_CONFIDENCE_THRESHOLD = 0.7

# Memory optimization: max image size to keep in memory before streaming processing
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB


# Type definitions for OCR data structures
class OCRResultFresh(TypedDict):
    """Fresh OCR result from extract_text_from_image (with raw_lines array)."""
    raw_lines: list[dict[str, Any]]
    full_text: str
    avg_confidence: float
    processing_time: float


class OCRResultCached(TypedDict):
    """Cached OCR result from Redis (raw_lines excluded to save memory)."""
    line_count: int
    full_text: str
    avg_confidence: float
    processing_time: float


# Pydantic schema for validated field data from OCR extraction
class ValidatedExtractedField(BaseModel):
    """Validated field extracted by OCR and AI processing."""
    field_name: str = Field(..., min_length=1, max_length=255, description="Field name from template")
    ocr_value: str = Field(default="", max_length=5000, description="OCR-extracted value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    
    class Config:
        """Enforce strict validation: reject implicit type coercion."""
        strict = True
    
    @validator('field_name', pre=True)
    def validate_field_name(cls, v):
        """Ensure field_name is non-empty string."""
        if not isinstance(v, str):
            raise ValueError("field_name must be string")
        if not v.strip():
            raise ValueError("field_name cannot be empty")
        return v.strip()
    
    @validator('ocr_value', pre=True)
    def validate_ocr_value(cls, v):
        """Ensure ocr_value is string, default to empty."""
        if v is None:
            return ""
        if not isinstance(v, str):
            return str(v)
        return v
    
    @validator('confidence', pre=True)
    def validate_confidence(cls, v):
        """Ensure confidence is float between 0 and 1."""
        if not isinstance(v, (int, float)):
            try:
                v = float(v)
            except (ValueError, TypeError):
                raise ValueError(f"confidence must be numeric, got {type(v)}")
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be 0.0-1.0, got {v}")
        return float(v)


def _validate_extracted_fields(fields: list[dict]) -> list[ValidatedExtractedField]:
    """
    Validate and normalize extracted fields using Pydantic schema.
    Raises ValueError if any field is invalid.
    """
    try:
        validated = [ValidatedExtractedField(**f) for f in fields]
        return validated
    except Exception as e:
        logger.error(f"Field validation failed: {e}")
        raise ValueError(f"Invalid field structure from OCR: {e}") from e


def _merge_extraction_results(
    primary: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge primary and fallback extraction results.
    
    Strategy: For each field, use the result with higher confidence.
    If primary has no value, use fallback value instead.
    
    Args:
        primary: Results from unified AI extraction {field_name: {value, confidence}}
        fallback: Results from positional mapping {field_name: {value, confidence}}
        
    Returns:
        Merged {field_name: {value, confidence}} dictionary
    """
    merged: dict[str, Any] = {}
    
    # Collect all field names from both sources
    all_field_names = set(primary.keys()) | set(fallback.keys())
    
    for field_name in all_field_names:
        primary_result = primary.get(field_name, {})
        fallback_result = fallback.get(field_name, {})
        
        primary_conf = primary_result.get("confidence", 0.0)
        fallback_conf = fallback_result.get("confidence", 0.0)
        primary_value = primary_result.get("value", "")
        fallback_value = fallback_result.get("value", "")
        
        # Selection logic:
        # 1. If primary has value and confidence >= fallback → use primary
        # 2. If fallback has value and confidence > primary → use fallback
        # 3. Otherwise use whichever has higher confidence
        if primary_value and primary_conf >= fallback_conf:
            merged[field_name] = primary_result
        elif fallback_value and fallback_conf > primary_conf:
            merged[field_name] = fallback_result
        elif primary_conf >= fallback_conf:
            merged[field_name] = primary_result
        else:
            merged[field_name] = fallback_result
    
    return merged


def _validate_and_fallback_confidence(
    field_data: dict[str, Any],
    field_name: str,
    raw_lines: list[dict[str, Any]] | None = None,
) -> float:
    """
    Validate confidence exists in field_data. If missing or invalid, calculate from raw_lines.
    
    Args:
        field_data: Field data dict from AI response (should have 'confidence' key)
        field_name: Name of field (for logging)
        raw_lines: List of raw OCR lines with text and confidence scores (optional)
    
    Returns:
        Valid confidence float 0.0-1.0
        
    Logic:
        1. If 'confidence' key exists and is valid (0.0-1.0) → return it
        2. If invalid range (e.g., 1.5), clamp to [0.0, 1.0] with warning
        3. If 'confidence' missing and field has value + raw_lines available → calculate from raw_lines
        4. Otherwise → return 0.5 with warning and log field name
    """
    # Check if confidence exists
    if "confidence" in field_data:
        conf_value = field_data.get("confidence")
        if isinstance(conf_value, (int, float)):
            try:
                conf = float(conf_value)
                # Validate range, clamp if needed
                if 0.0 <= conf <= 1.0:
                    return conf  # Valid confidence in range
                else:
                    # Out of range - clamp and warn
                    clamped = max(0.0, min(1.0, conf))
                    logger.warning(
                        f"[CONFIDENCE-OUT-OF-RANGE] Field '{field_name}' confidence {conf} "
                        f"out of range [0.0-1.0], clamped to {clamped}"
                    )
                    return clamped
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"[CONFIDENCE-INVALID-TYPE] Field '{field_name}' confidence {conf_value} "
                    f"invalid: {e}"
                )
                pass  # Fall through to fallback logic
        else:
            # Not numeric
            logger.warning(
                f"[CONFIDENCE-NOT-NUMERIC] Field '{field_name}' confidence is "
                f"{type(conf_value).__name__}, expected float/int"
            )
    
    # Fallback: Try to calculate confidence from raw OCR lines
    field_value = field_data.get("value", "").strip()
    if field_value and raw_lines and len(field_value) > 1:  # Skip single-char fields to avoid over-matching
        # Import regex for word-boundary matching (more precise than substring)
        import re
        try:
            # Use word boundary match to avoid matching substrings
            # For short or special chars, still use substring as fallback
            if len(field_value) > 2:  # Word boundary matching for 3+ char values
                escaped_value = re.escape(field_value)
                pattern = r'\b' + escaped_value + r'\b'
                matching_lines = [
                    l for l in raw_lines
                    if re.search(pattern, l.get("text", ""), re.IGNORECASE)
                ]
            else:  # For shorter values, use exact but case-insensitive match
                matching_lines = [
                    l for l in raw_lines
                    if field_value.lower() == l.get("text", "").lower()
                ]
            
            if matching_lines:
                # Use average confidence of matching lines
                avg_conf = sum(
                    max(0.0, min(1.0, float(l.get("confidence", 0.5))))
                    for l in matching_lines
                ) / len(matching_lines)
                
                logger.warning(
                    f"[CONFIDENCE-FALLBACK] Field '{field_name}' missing confidence key, "
                    f"calculated from {len(matching_lines)} matching OCR line(s): {avg_conf:.2f}"
                )
                return float(avg_conf)
        except Exception as e:
            logger.debug(
                f"[CONFIDENCE-FALLBACK-ERROR] Field '{field_name}' fallback calculation failed: {e}"
            )
    
    # Last resort: default to 0.5 with warning
    logger.warning(
        f"[CONFIDENCE-MISSING] Field '{field_name}' missing confidence key and no matching OCR lines found. "
        f"Using default confidence 0.5 (indicates potential extraction quality issue)"
    )
    return 0.5


def _sync_publish_progress(form_id: str, status: str, confidence: float | None = None,
                           message: str | None = None) -> None:
    """
    Synchronous wrapper to publish OCR progress via Redis.
    Celery tasks run synchronously so we can't use async functions directly.

    This publishes to Redis which then forwards to WebSocket connections.
    Uses pooled Redis connection instead of creating new one per call.
    """
    try:
        from app.redis_pool import get_sync_redis_client
        
        # Get client from pool (connects to existing pool, doesn't create new socket)
        r = get_sync_redis_client()
        data = {
            "status": status,
            "confidence_score": float(confidence) if confidence else None,
            "message": message or f"OCR status: {status}"
        }
        channel = f"form:progress:{form_id}"
        payload = json.dumps(data)
        result = r.publish(channel, payload)
        logger.debug(f"[OCR-Redis] Published to {channel}: status={status}, receivers={result}")
    except Exception as e:
        logger.error(f"Failed to publish progress for {form_id}: {e}", exc_info=True)


# Module-level engine pool to avoid connection leak from creating engines per task
_sync_engine = None
_sync_session_factory = None


def _get_or_create_engine():
    """Get or create a shared database engine with pooling."""
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        _sync_engine = create_engine(
            settings.DATABASE_SYNC_URL,
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before reuse
            pool_recycle=3600,   # Recycle connections every hour
        )
        logger.info("[DB] Initialized shared connection pool (pool_size=20, max_overflow=10)")
    return _sync_engine


def _get_sync_session() -> Session:
    """Create a synchronous DB session for Celery tasks (reuses pooled engine)."""
    global _sync_session_factory
    if _sync_session_factory is None:
        from sqlalchemy.orm import sessionmaker
        engine = _get_or_create_engine()
        _sync_session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _sync_session_factory()


def _download_image_from_r2(object_key: str) -> bytes:
    """Download an image from R2 and return bytes."""
    client = _get_r2_client()
    response = client.get_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=object_key,
    )
    return response["Body"].read()


def _should_use_image_for_field_mapping(field_schema: dict) -> bool:
    """
    Determine if image should be passed to field mapping.
    
    Returns True if:
    - Consensus extraction is enabled (needs image for multi-AI agreement)
    - Form has checkbox/radio fields (needs image for button detection)
    - Otherwise False (text-only extraction can use OCR text alone)
    """
    from app.config import get_settings
    settings = get_settings()
    
    # Consensus needs image
    if settings.AI_CONSENSUS_ENABLED:
        api_keys = settings.ai_api_keys
        if len(api_keys) >= 4:
            return True
    
    # Check if form has checkbox/radio fields
    fields = field_schema.get("fields", [])
    checkbox_types = {"checkbox", "checkbox-group", "radio"}
    has_checkboxes = any(f.get("type") in checkbox_types for f in fields)
    
    return has_checkboxes


@celery_app.task(
    name="app.services.ocr_task.process_ocr_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,  # P1: Overridden by error classification logic in exception handler
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

        # Redis batching: Track state changes to minimize publish calls (target: 2-3 per task instead of 7-10)
        last_published_state = None
        
        def _publish_if_state_changed(status: str, confidence: float | None = None, message: str | None = None) -> None:
            """Only publish to Redis if status has meaningfully changed."""
            nonlocal last_published_state
            current_state = (status, confidence)
            if current_state != last_published_state:
                _sync_publish_progress(form_entry_id, status, confidence, message)
                last_published_state = current_state
                logger.debug(f"[OCR-Batch] Published state change: {status} (confidence={confidence})")
            else:
                logger.debug(f"[OCR-Batch] Skipped redundant publish: {status} unchanged")

        # Publish initial processing status
        _publish_if_state_changed("processing", message="Form processing started")

        # Step 1: Download image
        image_bytes = _download_image_from_r2(entry.image_url)
        logger.info(f"Downloaded image: {len(image_bytes)} bytes")

        # Step 2: Run PaddleOCR (Cache disabled - always fresh extraction)
        # DISABLED: cached_ocr = get_cached_ocr_result(form_entry_id, template.id, image_bytes)
        # Always do fresh extraction to ensure confidence scores are recalculated
        # Use template-specific preprocessing based on form type
        ocr_result = extract_text_from_image_with_template(image_bytes, template)
        logger.info(f"[OCR] Fresh extraction (cache disabled) for {form_entry_id}")
        
        logger.info(
            f"OCR complete: {len(ocr_result.get('raw_lines', []))} lines, "
            f"avg confidence: {ocr_result.get('avg_confidence', 0.0):.2f}"
        )

        # Redis batching: Publish OCR milestone with confidence score
        _publish_if_state_changed("processing",
                                 confidence=ocr_result.get('avg_confidence', 0.0),
                                 message="OCR text extraction complete, analyzing fields...")

        # Step 3: Template-first deterministic extraction
        normalized_schema = normalize_template_schema(template.field_schema)
        deterministic_results = extract_fields_with_template_map(
            raw_lines=ocr_result.get("raw_lines", []),
            field_schema=normalized_schema,
        )
        unresolved_names = [
            name for name, payload in deterministic_results.items() if payload.get("unresolved")
        ]

        # Step 4: Targeted AI resolution for unresolved fields only
        from app.services.ai_client_factory import get_ai_client
        ai_client = get_ai_client()

        ai_fields = extract_fields_unified(
            client=ai_client,
            field_schema=normalized_schema,
            ocr_result=ocr_result,
            unresolved_field_names=unresolved_names,
            deterministic_results=deterministic_results,
        )

        merged_fields: dict[str, dict[str, Any]] = dict(deterministic_results)
        if isinstance(ai_fields, dict):
            for field_name, ai_payload in ai_fields.items():
                ai_value = str(ai_payload.get("value", "")).strip()
                ai_confidence = float(ai_payload.get("confidence", 0.0) or 0.0)
                if not ai_value:
                    continue
                current = merged_fields.get(field_name, {})
                current_value = str(current.get("value", "")).strip()
                current_conf = float(current.get("confidence", 0.0) or 0.0)
                if (not current_value) or ai_confidence >= current_conf:
                    merged_fields[field_name] = {
                        **current,
                        "value": ai_value,
                        "confidence": max(0.0, min(1.0, ai_confidence)),
                        "source": "ai",
                        "unresolved": False,
                    }

        mapped_fields = []
        raw_lines = ocr_result.get("raw_lines", []) if ocr_result else []
        for field_name, field_data in merged_fields.items():
            confidence = _validate_and_fallback_confidence(
                field_data=field_data,
                field_name=field_name,
                raw_lines=raw_lines,
            )
            mapped_fields.append({
                "field_name": field_name,
                "ocr_value": field_data.get("value", ""),
                "confidence": confidence,
                "source": field_data.get("source", "deterministic"),
            })
        
        # Apply form-specific rules (P2 strategy) for DTI BNR
        if template and "dti" in template.name.lower():
            try:
                pre_rules_filled_count = sum(1 for f in mapped_fields if f.get("ocr_value"))
                pre_rules_avg_confidence = (
                    sum(f["confidence"] for f in mapped_fields) / len(mapped_fields)
                    if mapped_fields else 0.0
                )
                # Convert list format to dict for rules processing
                fields_dict = {
                    f["field_name"]: {
                        "value": f.get("ocr_value", ""),
                        "confidence": f.get("confidence", 0.0),
                    }
                    for f in mapped_fields
                }
                
                # Apply DTI BNR specific rules
                corrected_fields = apply_dti_bnr_corrections(fields_dict)
                
                # Convert back to list format
                mapped_fields = [
                    {
                        "field_name": field_name,
                        "ocr_value": field_data.get("value", ""),
                        "confidence": field_data.get("confidence", 0.0),
                        "source": "rules",
                    }
                    for field_name, field_data in corrected_fields.items()
                ]
                
                # Log improvement
                new_filled_count = sum(1 for f in mapped_fields if f.get("ocr_value"))
                new_avg_confidence = (
                    sum(f["confidence"] for f in mapped_fields) / len(mapped_fields)
                    if mapped_fields else 0.0
                )
                logger.info(
                    f"[OCR-RULES-P2] DTI BNR rules applied: "
                    f"filled {pre_rules_filled_count}→{new_filled_count}, "
                    f"confidence {pre_rules_avg_confidence:.2f}→{new_avg_confidence:.2f}"
                )
            except Exception as e:
                logger.error(
                    f"[OCR-RULES-P2] DTI BNR rules failed: {e}",
                    exc_info=True,
                )
                # Continue with pre-correction fields on rules failure
        
        # Release image_bytes after extraction (no longer needed for field mapping)
        del image_bytes
        gc.collect()
        logger.debug("[OCR] Released image_bytes after extraction")

        # Step 4: Optional enhancement of low-confidence fields with targeted vision
        # (Skipped in P0 to reduce API calls; can enable if needed)
        # low_conf_fields = [
        #     f["field_name"] for f in mapped_fields
        #     if f["confidence"] < LOW_CONFIDENCE_THRESHOLD and f["field_name"]
        # ]
        # if low_conf_fields:
        #     logger.info(f"Enhancing {len(low_conf_fields)} low-confidence fields with AI Vision")
        
        # For P0, skip enhancement to save cost
        logger.debug("[P0] Skipping low-confidence field enhancement to reduce API calls")

        # Step 4.5: Apply field validators (Phase C - Validation & Hardening)
        # Normalize values based on field types (date, phone, checkbox, amount)
        # Adjust confidence based on validation results
        from app.services.ocr_service import _apply_field_validators
        
        mapped_fields_before_validation = [dict(f) for f in mapped_fields]  # Copy for comparison
        source_by_field_name = {
            field.get("field_name"): field.get("source", "deterministic")
            for field in mapped_fields
        }
        try:
            mapped_fields = _apply_field_validators(
                fields=mapped_fields,
                field_schema=normalized_schema,
            )
            for field in mapped_fields:
                field["source"] = source_by_field_name.get(field.get("field_name"), "deterministic")
            logger.info(f"[OCR-VALIDATORS] Field validators applied successfully")
        except Exception as e:
            logger.error(
                f"[OCR-VALIDATORS] Field validation failed: {e}",
                exc_info=True,
            )
            # Continue with unvalidated fields on validator failure
            mapped_fields = mapped_fields_before_validation

        # Step 5: Save results to DB
        # Clear existing fields
        for existing_field in entry.fields:
            db.delete(existing_field)

        # Validate and normalize extracted fields using Pydantic schema
        logger.debug(f"Validating {len(mapped_fields)} extracted fields")
        try:
            validated_fields = _validate_extracted_fields(list(mapped_fields.values()) if isinstance(mapped_fields, dict) else mapped_fields)
        except ValueError as e:
            logger.error(f"Field validation failed: {e}")
            return {"error": f"Invalid field extraction: {e}"}

        # Create new fields
        total_confidence = 0.0
        for validated_field in validated_fields:
            form_field = FormField(
                entry_id=entry.id,
                field_name=validated_field.field_name,
                ocr_value=validated_field.ocr_value,
                confidence=validated_field.confidence,
            )
            db.add(form_field)
            total_confidence += validated_field.confidence

        # Update entry
        avg_confidence = (
            total_confidence / len(mapped_fields)
            if mapped_fields else 0.0
        )
        # Memory optimization: Exclude raw_lines (300-500KB per entry)
        # Only store full_text summary and field_count
        # NOTE: ocr_result has two possible structures:
        # - Fresh: {"raw_lines": [...], "full_text": str, "avg_confidence": float, "processing_time": float}
        # - Cached: {"line_count": N, "full_text": str, "avg_confidence": float, "processing_time": float}
        # (raw_lines excluded from cache to save ~300KB per entry)
        if "line_count" in ocr_result:
            # Cached result: line_count is pre-computed
            raw_lines_count = ocr_result["line_count"]
        elif "raw_lines" in ocr_result:
            # Fresh result: compute from array
            raw_lines_count = len(ocr_result["raw_lines"])
        else:
            # Data pipeline error: both keys missing (should never happen)
            # This indicates corrupted OCR result, likely from caching or extraction failure
            logger.error(
                f"OCR data integrity error for entry {form_entry_id}: "
                f"missing both 'line_count' (cached) and 'raw_lines' (fresh). "
                f"OCR result may be corrupted. Marking entry with 0 lines as fallback."
            )
            raw_lines_count = 0
        
        # Validate ocr_result has required fields before accessing
        required_keys = {"full_text", "processing_time"}
        missing_keys = required_keys - set(ocr_result.keys())
        if missing_keys:
            logger.error(f"OCR result missing required keys: {missing_keys}. Got: {set(ocr_result.keys())}")
            raise ValueError(f"OCR pipeline returned incomplete data: missing {missing_keys}")
        
        field_sources = {
            field["field_name"]: field.get("source", "unknown")
            for field in mapped_fields
        }
        entry.raw_ocr_data = {
            "full_text": ocr_result.get("full_text", ""),
            "raw_lines_count": raw_lines_count,
            "field_count": len(mapped_fields),
            "field_sources": field_sources,
            "template_first_enabled": True,
        }
        entry.confidence_score = avg_confidence
        entry.processing_time = ocr_result.get("processing_time", 0.0)
        entry.status = FormEntryStatus.EXTRACTED

        db.commit()

        logger.info(
            f"OCR pipeline complete for entry {form_entry_id}: "
            f"{len(mapped_fields)} fields, avg confidence: {avg_confidence:.2f}"
        )

        # Force garbage collection before finalizing
        gc.collect()
        
        # Redis batching: Publish final completion status
        logger.debug(f"[OCR] Publishing final status to Redis: form_id={form_entry_id}, status=extracted, confidence={avg_confidence:.2f}")
        _publish_if_state_changed("extracted",
                                 confidence=avg_confidence,
                                 message="OCR processing complete")
        logger.info(f"[OCR] Pipeline complete for {form_entry_id}")

        return {
            "entry_id": form_entry_id,
            "status": "extracted",
            "fields_count": len(mapped_fields),
            "avg_confidence": avg_confidence,
            "processing_time": ocr_result.get("processing_time", 0.0),
        }

    except Exception as exc:
        logger.exception(f"OCR processing failed for entry {form_entry_id}")
        
        # P1: Classify the error to determine retry strategy
        classified = classify_error(exc, stage="ocr_pipeline")
        log_error_classification(form_entry_id, classified, attempt=self.request.retries)
        
        # Update status based on error category
        try:
            entry = db.execute(
                select(FormEntry).where(FormEntry.id == form_entry_id)
            ).scalar_one_or_none()
            if entry:
                # PERMANENT errors → mark as failed (don't retry)
                # TRANSIENT errors → mark as uploaded (retry)
                # PARTIAL errors → mark as extracted (some data saved)
                if classified.category.value == "permanent":
                    entry.status = FormEntryStatus.UPLOADED  # Signal failure (could use new FAILED status)
                    logger.error(f"[P1] PERMANENT error for {form_entry_id} - not retrying")
                elif classified.category.value == "partial":
                    entry.status = FormEntryStatus.EXTRACTED  # Partial success - keep data
                    logger.warning(f"[P1] PARTIAL error for {form_entry_id} - keeping partial data")
                else:
                    entry.status = FormEntryStatus.UPLOADED  # Transient - will retry
                
                db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update entry status: {db_err}")
            db.rollback()
        
        # Smart retry: Only retry if error is transient
        if should_retry_stage(classified) and self.request.retries < self.max_retries:
            retry_delay = get_retry_delay(self.request.retries, classified)
            logger.info(f"[P1] Retrying in {retry_delay}s (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=exc, countdown=retry_delay)
        else:
            # Permanent error or max retries exceeded
            logger.error(f"[P1] NOT retrying: category={classified.category}, retries={self.request.retries}attempts >= {self.max_retries}")
            raise exc

    finally:
        db.close()


# ============================================================================
# STEP 4.4: FIELD-LEVEL VALIDATION FUNCTIONS
# ============================================================================
# Validation functions for normalizing and validating OCR-extracted field values.
# Each validator:
# - Takes (value, confidence) as input
# - Returns (normalized_value, confidence_adjustment)
# - Adjustments ∈ [-0.25, +0.10]
# - Never raises exceptions (returns original + penalty on error)
# - Logs validation outcomes
# ============================================================================

from datetime import datetime
from typing import Tuple
import re

# Input length safety limit (prevent DoS via extremely long strings)
MAX_INPUT_LENGTH = 1000


def _validate_date(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and normalize date fields to DD/MM/YYYY format.
    
    Accepts multiple date formats:
    - DD/MM/YYYY, DD-MM-YYYY (European format)
    - MM/DD/YYYY (American format, auto-detected)
    - YYYY-MM-DD, YYYY/MM/DD (ISO format)
    - Spelled out (e.g., "March 15, 2020", "Mar 15 2020")
    
    Validation:
    - Day: 1-31 (accounting for month lengths, leap years)
    - Month: 1-12
    - Year: 1950-2030
    
    Args:
        value: Raw date string from OCR
        confidence: Current field confidence score (0.0-1.0)
    
    Returns:
        Tuple of (normalized_date, confidence_adjustment)
        - normalized_date: Formatted as "DD/MM/YYYY" or "" if invalid
        - confidence_adjustment: ∈ [-0.25, +0.10]
            - Valid date recognized: +0.10
            - Invalid/out-of-range: -0.25
    """
    if not value or (isinstance(value, str) and not value.strip()):
        logger.warning("[Validation] Date: Empty value")
        return ("", -0.25)
    
    value_clean = value.strip()
    if len(value_clean) > MAX_INPUT_LENGTH:
        logger.warning(f"[Validation] Date: Input too long ({len(value_clean)} chars)")
        return ("", -0.25)
    day: int | None = None
    month: int | None = None
    year: int | None = None
    
    # Try ISO format: YYYY-MM-DD or YYYY/MM/DD
    iso_match = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', value_clean)
    if iso_match:
        year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
    else:
        # Try DD/MM/YYYY or DD-MM-YYYY format
        dmy_match = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$', value_clean)
        if dmy_match:
            first_num, second_num, year_cand = int(dmy_match.group(1)), int(dmy_match.group(2)), int(dmy_match.group(3))
            # Smart format detection:
            # - If first > 12 and second <= 12: must be DD/MM/YYYY
            # - If second > 12 and first <= 12: must be MM/DD/YYYY  
            # - If both <= 12: assume MM/DD/YYYY (American format, most common)
            if first_num > 12:
                # First must be day
                day, month, year = first_num, second_num, year_cand
            elif second_num > 12:
                # Second must be day, first is month
                day, month, year = second_num, first_num, year_cand
            elif first_num <= 12 and second_num <= 12:
                # Ambiguous: assume MM/DD/YYYY (American format)
                day, month, year = second_num, first_num, year_cand
            else:
                # This shouldn't happen given the regex, but just in case
                logger.warning(f"[Validation] Date: Invalid numeric format '{value_clean}'")
                return ("", -0.25)
    
    # Try spelled-out month format: "March 15, 2020", "Mar 15 2020", "15 March 2020"
    if day is None:
        months_map = {
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12,
        }
        for month_name, month_num in months_map.items():
            # Pattern: "March 15, 2020" or "Mar 15 2020" or "15 March 2020"
            patterns = [
                rf'^({month_name})\s+(\d{{1,2}})[,\s]+(\d{{4}})$',  # "March 15, 2020"
                rf'^(\d{{1,2}})\s+({month_name})[,\s]+(\d{{4}})$',  # "15 March 2020"
            ]
            for pattern in patterns:
                match = re.match(pattern, value_clean, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    # Determine which is day based on position
                    if month_name in groups[0].lower():
                        # "March 15, 2020" format
                        day, year = int(groups[1]), int(groups[2])
                    else:
                        # "15 March 2020" format
                        day, year = int(groups[0]), int(groups[2])
                    month = month_num
                    break
            if day is not None:
                break
    
    # Validate extracted components
    if day is None or month is None or year is None:
        logger.warning(f"[Validation] Date: Could not parse '{value_clean}'")
        return ("", -0.25)
    
    # Range checks
    if not (1 <= month <= 12):
        logger.warning(f"[Validation] Date: Invalid month {month} in '{value_clean}'")
        return ("", -0.25)
    
    if not (1950 <= year <= 2030):
        logger.warning(f"[Validation] Date: Year {year} outside range [1950, 2030] in '{value_clean}'")
        return ("", -0.25)
    
    # Day validation (accounting for month lengths and leap years)
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        days_in_month[1] = 29  # Leap year February
    
    max_day = days_in_month[month - 1]
    if not (1 <= day <= max_day):
        logger.warning(f"[Validation] Date: Invalid day {day} for month {month} in '{value_clean}'")
        return ("", -0.25)
    
    # Valid date: normalize to DD/MM/YYYY
    normalized = f"{day:02d}/{month:02d}/{year:04d}"
    logger.info(f"[Validation] Date: '{value_clean}' → '{normalized}' (+0.10)")
    return (normalized, 0.10)


def _validate_phone(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and standardize Philippine phone numbers.
    
    Accepts formats:
    - +639XXXXXXXXX (international, 12 digits)
    - 09XXXXXXXXX (local with 0, 11 digits)
    - 9XXXXXXXXX (local without 0, 10 digits)
    - With separators: spaces, hyphens, parentheses
    
    Standardizes to: +639XXXXXXXXX
    
    Validation:
    - 10-11 numeric digits after cleanup
    - Valid mobile prefixes: 917, 918, 920, 921, 928 (PH mobile networks)
    - Rejects landlines (prefix 032, 033, etc.)
    
    Args:
        value: Phone number string from OCR
        confidence: Current field confidence score (0.0-1.0)
    
    Returns:
        Tuple of (standardized_phone, confidence_adjustment)
        - standardized_phone: "+639XXXXXXXXX" or "" if invalid
        - confidence_adjustment: ∈ [-0.20, +0.05]
            - Valid PH phone: +0.05
            - Invalid: -0.20
    """
    if not value or (isinstance(value, str) and not value.strip()):
        logger.warning("[Validation] Phone: Empty value")
        return ("", -0.20)
    
    value_clean = value.strip()
    
    # Remove separators: spaces, hyphens, parentheses
    # +63 917 123 4567 → +639171234567
    # (09) 17-1234567 → 09171234567
    cleaned = re.sub(r'[\s\-\(\)]+', '', value_clean)
    
    # Extract numeric and leading + sign only
    digits_only = re.sub(r'[^\d\+]', '', cleaned)
    
    # Normalize format
    if digits_only.startswith('+63'):
        # Already international: +639171234567
        phone_digits = digits_only[1:]  # Remove leading +
    elif digits_only.startswith('63'):
        # Alternative international without +: 639171234567
        phone_digits = digits_only
    elif digits_only.startswith('09'):
        # Local format with 0: 09171234567 → 639171234567
        phone_digits = '63' + digits_only[1:]
    elif digits_only.startswith('9') and len(digits_only) >= 10:
        # Local without 0: 9171234567 → 639171234567
        phone_digits = '63' + digits_only
    else:
        logger.warning(f"[Validation] Phone: Invalid format '{value_clean}'")
        return ("", -0.20)
    
    # Validate length
    if len(phone_digits) != 12:
        logger.warning(f"[Validation] Phone: Invalid length {len(phone_digits)} (expected 12) in '{value_clean}'")
        return ("", -0.20)
    
    # Validate PH country code
    if not phone_digits.startswith('63'):
        logger.warning(f"[Validation] Phone: Not a PH number '{value_clean}'")
        return ("", -0.20)
    
    # Validate mobile prefix (3rd-4th digits after country code)
    # Valid: 917, 918, 920, 921, 928 (Globe, Smart, etc.)
    mobile_prefix = phone_digits[2:4]
    valid_prefixes = ['91', '92']  # 91X and 92X are mobile networks
    if mobile_prefix not in valid_prefixes:
        logger.warning(f"[Validation] Phone: Invalid PH mobile prefix '{mobile_prefix}' in '{value_clean}'")
        return ("", -0.20)
    
    standardized = f"+{phone_digits}"
    logger.info(f"[Validation] Phone: '{value_clean}' → '{standardized}' (+0.05)")
    return (standardized, 0.05)


def _validate_checkbox(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and normalize checkbox fields to 'Yes', 'No', or empty string.
    
    Handles 12+ variations:
    - Yes variations: "Yes", "YES", "yes", "Y", "True", "true", "1", "✓", "✔", "Checked"
    - No variations: "No", "NO", "no", "N", "False", "false", "0", "☐", "Unchecked"
    - Ambiguous: "maybe", "unknown", "?", "unclear" → empty (with penalty)
    - Already empty: "" → "" (no penalty for empty optional field)
    
    Args:
        value: Checkbox value from OCR
        confidence: Current field confidence score (0.0-1.0)
    
    Returns:
        Tuple of (normalized_value, confidence_adjustment)
        - normalized_value: "Yes", "No", or "" (ambiguous/empty)
        - confidence_adjustment: ∈ [-0.05, +0.05]
            - Clear Yes/No: +0.05
            - Ambiguous: -0.05
            - Empty recognized: 0.0
    """
    if not value or (isinstance(value, str) and not value.strip()):
        logger.info("[Validation] Checkbox: Empty value (allowed, no adjustment)")
        return ("", 0.0)
    
    value_clean = value.strip().lower()
    
    # Yes variations
    yes_patterns = ['yes', 'y', 'true', '1', '✓', '✔', 'checked', 'x']
    if value_clean in yes_patterns:
        logger.info(f"[Validation] Checkbox: '{value}' → 'Yes' (+0.05)")
        return ("Yes", 0.05)
    
    # No variations
    no_patterns = ['no', 'n', 'false', '0', '☐', 'unchecked', 'empty']
    if value_clean in no_patterns:
        logger.info(f"[Validation] Checkbox: '{value}' → 'No' (+0.05)")
        return ("No", 0.05)
    
    # Ambiguous values
    ambiguous_patterns = ['maybe', 'unknown', '?', 'unclear', 'n/a', 'na', 'unclear']
    if value_clean in ambiguous_patterns:
        logger.warning(f"[Validation] Checkbox: Ambiguous value '{value}' → empty (-0.05)")
        return ("", -0.05)
    
    # Unrecognized value: treat as ambiguous
    logger.warning(f"[Validation] Checkbox: Unrecognized value '{value}' → empty (-0.05)")
    return ("", -0.05)


def _validate_amount(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and normalize currency amounts to X,XXX.XX format.
    
    Accepts formats:
    - Plain numbers: "5000", "5000.50", "5000.99"
    - With thousands: "5,000", "5,000.50"
    - With currency: "₱5000", "P5000", "$5000", "€5000"
    - Negative: "-5000", "₱-5000", "-5,000.50"
    
    Normalizes to: X,XXX.XX (thousands comma, 2 decimal places)
    Preserves negative sign for refunds/deductions.
    
    Args:
        value: Currency amount string from OCR
        confidence: Current field confidence score (0.0-1.0)
    
    Returns:
        Tuple of (formatted_amount, confidence_adjustment)
        - formatted_amount: "X,XXX.XX" or "" if invalid
        - confidence_adjustment: ∈ [-0.20, +0.08]
            - Valid amount: +0.08
            - Non-numeric/invalid: -0.20
    """
    if not value or (isinstance(value, str) and not value.strip()):
        logger.warning("[Validation] Amount: Empty value")
        return ("", -0.20)
    
    value_clean = value.strip()
    if len(value_clean) > MAX_INPUT_LENGTH:
        logger.warning(f"[Validation] Amount: Input too long ({len(value_clean)} chars)")
        return ("", -0.25)
    # Validate: at most one currency symbol (₱, P, $, €, £, ¥)
    # Count all currency symbols - must be <= 1 for valid input
    currency_symbols = ['₱', '$', '€', '£', '¥']  # Don't count 'P' alone as it could be a letter
    symbol_count = sum(value_clean.count(sym) for sym in currency_symbols)
    
    # Special handling for 'P': only count as currency if standalone or with space/digit
    if 'P' in value_clean:
        # P followed by digit is likely currency (e.g., "P5000")
        # P followed by letter or at word boundary might be normal letter
        p_as_currency = len(re.findall(r'P(?=[\d\s])', value_clean))
        symbol_count += p_as_currency
    
    if symbol_count > 1:
        logger.warning(f"[Validation] Amount: Multiple currency symbols in '{value_clean}'")
        return ("", -0.20)
    
    # Remove currency symbols: ₱, P, $, €, £, ¥
    no_currency = re.sub(r'[₱P$€£¥]', '', value_clean)
    
    # Remove spaces
    no_spaces = no_currency.replace(' ', '')
    
    # Extract numeric part (including - for negative, . for decimal)
    # Pattern: optional -, digits, optional comma separators, optional .XX
    numeric_match = re.match(r'^(-?)(\d{1,3}(?:,?\d{3})*\.?\d{0,2})$', no_spaces)
    if not numeric_match:
        logger.warning(f"[Validation] Amount: Non-numeric format '{value_clean}'")
        return ("", -0.20)
    
    is_negative = numeric_match.group(1) == '-'
    digits_part = numeric_match.group(2)
    
    # Remove commas and convert to float
    try:
        amount_value = float(digits_part.replace(',', ''))
    except ValueError:
        logger.warning(f"[Validation] Amount: Failed to parse '{value_clean}'")
        return ("", -0.20)
    
    # Format: X,XXX.XX
    if is_negative:
        formatted = f"-{abs(amount_value):,.2f}"
    else:
        formatted = f"{amount_value:,.2f}"
    
    logger.info(f"[Validation] Amount: '{value_clean}' → '{formatted}' (+0.08)")
    return (formatted, 0.08)


def _validate_required(value: str, is_required: bool, confidence: float) -> Tuple[str, float]:
    """Validate required fields are not empty.
    
    Adjusts confidence based on whether required field is populated:
    - Required field empty: -0.25 (high penalty, needs human review)
    - Required field filled: +0.05 (verified field present)
    - Optional field: 0.0 (no adjustment)
    
    Args:
        value: Field value (unchanged if valid)
        is_required: Whether field is marked required
        confidence: Current field confidence score (0.0-1.0)
    
    Returns:
        Tuple of (value_unchanged, confidence_adjustment)
        - value_unchanged: Original value (never modified)
        - confidence_adjustment: ∈ [-0.25, +0.05]
            - Required empty: -0.25
            - Required filled: +0.05
            - Optional: 0.0
    """
    if not is_required:
        # Optional field: no adjustment
        return (value, 0.0)
    
    # Check if empty or whitespace-only
    is_empty = not value or (isinstance(value, str) and not value.strip())
    
    if is_empty:
        logger.warning(f"[Validation] Required: Empty required field (-0.25)")
        return (value, -0.25)
    else:
        logger.info(f"[Validation] Required: Filled required field '{value}' (+0.05)")
        return (value, 0.05)
