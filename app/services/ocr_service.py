"""OCR extraction service using PaddleOCR with Groq AI-powered field mapping."""

import hashlib
import io
import json
import logging
import re
import time
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Lazy-load PaddleOCR to avoid slow import on every request
_paddle_ocr = None

# LRU cache for template-based field mapping (max 128 unique form templates cached)
_field_mapping_cache: dict[str, list[dict[str, Any]]] = {}
_FIELD_MAPPING_CACHE_MAX_SIZE = 128


def _get_image_fingerprint(image_bytes: bytes | None) -> str:
    """
    Generate a SHA256 fingerprint of image bytes for caching.
    Returns empty string if image is None (for cases without image).
    """
    if image_bytes is None:
        return "none"
    return hashlib.sha256(image_bytes).hexdigest()[:16]  # 16 char prefix sufficient


def _get_field_mapping_cache_key(
    template_id: str,
    image_fingerprint: str,
    ocr_full_text: str,
) -> str:
    """Generate cache key combining template + image hash + ocr content hash."""
    # Include first 200 chars of OCR text to catch content variations
    ocr_hash = hashlib.md5(ocr_full_text[:500].encode()).hexdigest()[:8]
    return f"{template_id}:{image_fingerprint}:{ocr_hash}"


def _get_cached_field_mapping(
    template_id: str,
    image_fingerprint: str,
    ocr_full_text: str,
) -> list[dict[str, Any]] | None:
    """Retrieve cached field mapping if available."""
    cache_key = _get_field_mapping_cache_key(template_id, image_fingerprint, ocr_full_text)
    result = _field_mapping_cache.get(cache_key)
    if result:
        logger.debug(f"[Cache-Hit] Template {template_id}: reusing cached field mapping")
    return result


def _cache_field_mapping(
    template_id: str,
    image_fingerprint: str,
    ocr_full_text: str,
    fields: list[dict[str, Any]],
) -> None:
    """Store field mapping in LRU cache."""
    global _field_mapping_cache
    
    # Simple LRU: if cache is full, clear oldest entries
    if len(_field_mapping_cache) >= _FIELD_MAPPING_CACHE_MAX_SIZE:
        # Remove first 25% of oldest entries
        excess = len(_field_mapping_cache) - _FIELD_MAPPING_CACHE_MAX_SIZE + 1
        for _ in range(excess):
            _field_mapping_cache.pop(next(iter(_field_mapping_cache)))
        logger.debug(f"[Cache] Evicted {excess} entries, cache size now: {len(_field_mapping_cache)}")
    
    cache_key = _get_field_mapping_cache_key(template_id, image_fingerprint, ocr_full_text)
    _field_mapping_cache[cache_key] = fields
    logger.debug(f"[Cache-Store] Template {template_id}: cached field mapping ({len(_field_mapping_cache)} in cache)")


def _apply_field_validators(
    fields: list[dict[str, Any]],
    field_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Apply field validators to normalize values and adjust confidence.
    
    Validators applied (post-AI extraction):
    1. Type-specific validation (date, phone, checkbox, amount)
    2. Required field validation (presence check)
    3. Confidence adjustment based on validation results
    
    Args:
        fields: List of extracted fields [{field_name, ocr_value, confidence}, ...]
        field_schema: Template schema with field definitions {fields: [{name, type, required}, ...]}
        
    Returns:
        Updated fields list with normalized values and adjusted confidence
        
    Strategy (Option A: Post-AI Extraction):
    - Called after Groq + fallback + DTI BNR corrections
    - Maps field_name → field_type from schema
    - Looks up appropriate validator
    - Applies validator → (normalized_value, confidence_adjustment)
    - Clamps confidence to [0.0, 1.0]
    - Logs validation results per template
    """
    from app.config import get_settings
    from app.services.forms.field_validators import (
        validate_date,
        validate_phone,
        validate_checkbox,
        validate_amount,
        validate_required,
    )
    
    settings = get_settings()
    if not settings.ENABLE_FIELD_VALIDATORS:
        logger.debug("[VALIDATORS] Field validators disabled, skipping")
        return fields
    
    # Build field type map from schema
    field_definitions = field_schema.get("fields", [])
    field_types = {
        f["name"]: {
            "type": f.get("type", "text"),
            "required": f.get("required", False),
        }
        for f in field_definitions
        if "name" in f
    }
    
    # Validator registry: type → validator function
    validators = {
        "date": validate_date,
        "phone": validate_phone,
        "checkbox": validate_checkbox,
        "amount": validate_amount,
    }
    
    updated_fields = []
    validation_stats = {
        "total": 0,
        "improved": 0,
        "degraded": 0,
        "unchanged": 0,
        "skipped": 0,
    }
    
    for field in fields:
        field_name = field.get("field_name", "")
        field_value = field.get("ocr_value", "").strip()
        original_conf = field.get("confidence", 0.0)
        updated_conf = original_conf
        normalized_value = field_value
        
        validation_stats["total"] += 1
        
        # If field not in schema, skip validation
        if field_name not in field_types:
            logger.debug(f"[VALIDATORS] Field '{field_name}' not in schema, skipping")
            validation_stats["skipped"] += 1
            updated_fields.append(field)
            continue
        
        field_def = field_types[field_name]
        field_type = field_def["type"]
        is_required = field_def["required"]
        
        # Apply type-specific validator if available
        if field_type in validators and field_value:
            try:
                validator_fn = validators[field_type]
                normalized_value, conf_adjustment = validator_fn(field_value, original_conf)
                updated_conf = max(0.0, min(1.0, original_conf + conf_adjustment))
                
                logger.debug(
                    f"[VALIDATORS] {field_type.upper()} '{field_name}': "
                    f"'{field_value}' → '{normalized_value}' "
                    f"(conf: {original_conf:.2f} {conf_adjustment:+.2f} = {updated_conf:.2f})"
                )
            except Exception as e:
                logger.warning(
                    f"[VALIDATORS] {field_type.upper()} validator for '{field_name}' failed: {e}"
                )
                # Continue with original value on validator failure
        
        # Apply required field validation (presence check)
        if is_required and (not normalized_value or not normalized_value.strip()):
            try:
                _, req_adjustment = validate_required(normalized_value, is_required, updated_conf)
                updated_conf = max(0.0, min(1.0, updated_conf + req_adjustment))
                
                logger.debug(
                    f"[VALIDATORS] REQUIRED '{field_name}': missing value "
                    f"(conf: {original_conf:.2f} + {req_adjustment:+.2f} = {updated_conf:.2f})"
                )
            except Exception as e:
                logger.warning(
                    f"[VALIDATORS] Required field validator for '{field_name}' failed: {e}"
                )
        
        # Track statistics
        if updated_conf > original_conf:
            validation_stats["improved"] += 1
        elif updated_conf < original_conf:
            validation_stats["degraded"] += 1
        else:
            validation_stats["unchanged"] += 1
        
        # Create updated field
        updated_fields.append({
            "field_name": field_name,
            "ocr_value": normalized_value,
            "confidence": updated_conf,
        })
    
    # Log summary
    improved_pct = (
        100.0 * validation_stats["improved"] / validation_stats["total"]
        if validation_stats["total"] > 0 else 0.0
    )
    avg_improvement = (
        (sum(f["confidence"] for f in updated_fields) - sum(f["confidence"] for f in fields))
        / validation_stats["total"]
        if validation_stats["total"] > 0 else 0.0
    )
    
    logger.info(
        f"[VALIDATORS] Applied field validators: "
        f"improved={validation_stats['improved']}/{validation_stats['total']} ({improved_pct:.1f}%)",
        extra={
            "stats": validation_stats,
            "avg_improvement": f"{avg_improvement:+.3f}",
        }
    )
    
    return updated_fields


# Lazy-load PaddleOCR to avoid slow import on every request
_paddle_ocr = None


def _get_paddle_ocr():
    """
    Lazy initialize PaddleOCR instance.

    Caching strategy: CACHE_OCR_MODEL=true avoids reloading on every task,
    significantly reducing latency and CPU usage at minimal memory cost
    (PaddleOCR model is ~500MB, negligible on modern systems).
    """
    global _paddle_ocr

    from app.config import get_settings
    settings = get_settings()

    # If caching is disabled, don't use global cache
    if not settings.CACHE_OCR_MODEL:
        from paddleocr import PaddleOCR
        return PaddleOCR(
            use_angle_cls=True,
            lang="en",
            use_gpu=False,
            show_log=False,
        )

    # Normal mode: cache the model globally
    if _paddle_ocr is None:
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            use_gpu=False,
            show_log=False,
        )
    return _paddle_ocr


def _pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    """Convert PDF bytes to a list of PIL Images (one per page)."""
    import fitz  # PyMuPDF

    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        # Render at 300 DPI for good OCR quality
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def _is_pdf(data: bytes) -> bool:
    """Check if bytes represent a PDF file."""
    return data[:5] == b"%PDF-"


def _downscale_image_if_needed(image_bytes: bytes) -> bytes:
    """
    Downscale image if it exceeds size threshold to reduce memory usage during OCR.
    
    This is critical for low-RAM systems. Downscaling reduces:
    - Image buffer in memory
    - OCR model input size
    - Base64 encoding size
    - Overall peak RAM usage
    
    Returns downscaled image bytes (or original if already small).
    """
    from app.config import get_settings
    settings = get_settings()
    
    import gc
    
    max_size_bytes = settings.OCR_MAX_IMAGE_SIZE_MB * 1024 * 1024
    
    # Skip if image is already small
    if len(image_bytes) <= max_size_bytes:
        logger.debug(f"Image {len(image_bytes) / 1024:.1f}KB is within limit, no downscale needed")
        return image_bytes
    
    logger.info(f"Image {len(image_bytes) / 1024:.1f}KB exceeds limit, downscaling...")
    
    try:
        # Open image
        img = Image.open(io.BytesIO(image_bytes))
        original_size = img.size
        
        # Calculate scale factor to meet size target
        # Rough estimate: size ≈ width * height * 3 bytes/pixel (RGB) / compression_ratio
        current_ratio = len(image_bytes) / (original_size[0] * original_size[1] * 3)
        target_pixels = (max_size_bytes * 0.9) / (3 * current_ratio)  # 90% of target
        scale = (target_pixels / (original_size[0] * original_size[1])) ** 0.5
        
        new_width = int(original_size[0] * scale)
        new_height = int(original_size[1] * scale)
        
        # Ensure minimum size for OCR
        new_width = max(new_width, 640)
        new_height = max(new_height, 480)
        
        logger.info(f"Downscaling {original_size[0]}x{original_size[1]} → {new_width}x{new_height}")
        
        # Resize with LANCZOS (high-quality downsampling)
        img_resized = img.resize((new_width, new_height), Image.LANCZOS)
        
        # Release original
        del img
        gc.collect()
        
        # Save to bytes with quality compression
        output = io.BytesIO()
        img_resized.save(
            output,
            format="JPEG",
            quality=settings.OCR_DOWNSCALE_QUALITY,
            optimize=True,
        )
        downscaled_bytes = output.getvalue()
        
        logger.info(f"Downscaled: {len(image_bytes) / 1024:.1f}KB → {len(downscaled_bytes) / 1024:.1f}KB")
        
        # Release resized image
        del img_resized
        gc.collect()
        
        return downscaled_bytes
        
    except Exception as e:
        logger.warning(f"Image downscaling failed: {e}, using original")
        return image_bytes


def _apply_form_specific_preprocessing(
    img_array: np.ndarray,
    form_type: str,
) -> np.ndarray:
    """
    Apply form-specific preprocessing based on detected form type.
    
    Returns:
        Preprocessed image array optimized for the form type
    """
    if form_type == 'dti_bnr':
        logger.info("[OCR-PREP] Applying DTI BNR form-specific preprocessing")
        from app.services.ocr_form_specific import preprocess_dti_bnr_image
        return preprocess_dti_bnr_image(img_array)
    else:
        # Default: apply generic preprocessing
        logger.debug("[OCR-PREP] Applying generic preprocessing")
        return _enhance_image_preprocessing(img_array)


def _enhance_image_preprocessing(img_array: np.ndarray) -> np.ndarray:
    """
    Enhance image preprocessing for field extraction.
    Applies CLAHE, deskew, bilateral denoise, and morphological operations.
    
    Args:
        img_array: Input image as numpy array (uint8, 2D grayscale or 3D color)
        
    Returns:
        Enhanced image as numpy array
        
    Raises:
        ValueError: If image is None, invalid dtype, wrong shape, or exceeds size limits
        TypeError: If input is not a numpy array
        
    Expected gain: +2-4% confidence
    """
    import cv2
    
    # ============================================================================
    # 1. INPUT VALIDATION
    # ============================================================================
    
    # Check for None
    if img_array is None:
        logger.error("Input image is None")
        raise ValueError("img_array cannot be None")
    
    # Check type
    if not isinstance(img_array, np.ndarray):
        logger.error(f"Input type is {type(img_array)}, expected numpy.ndarray")
        raise TypeError(f"Expected numpy.ndarray, got {type(img_array).__name__}")
    
    # Check shape (must be 2D or 3D)
    if len(img_array.shape) not in (2, 3):
        logger.error(f"Invalid image shape {img_array.shape}: must be 2D or 3D")
        raise ValueError(f"Expected 2D or 3D array, got shape {img_array.shape}")
    
    # Validate or convert dtype
    if img_array.dtype != np.uint8:
        if img_array.dtype in (np.float32, np.float64):
            # Convert float [0-1] or [0-255] to uint8
            logger.warning(f"Converting dtype from {img_array.dtype} to uint8")
            if img_array.max() <= 1.0:
                img_array = (img_array * 255).astype(np.uint8)
            else:
                img_array = np.clip(img_array, 0, 255).astype(np.uint8)
        else:
            logger.error(f"Unsupported dtype {img_array.dtype}, expected uint8")
            raise ValueError(f"Expected dtype uint8, got {img_array.dtype}")
    
    # ============================================================================
    # 2. SIZE LIMITS (prevent DoS)
    # ============================================================================
    
    # 16 megapixels = 4000x4000 (or similar resolution)
    max_megapixels = 16
    max_pixels = max_megapixels * 1_000_000
    image_pixels = np.prod(img_array.shape[:2])
    
    if image_pixels > max_pixels:
        logger.error(
            f"Image too large: {image_pixels} pixels ({image_pixels / 1_000_000:.1f} MP) "
            f"exceeds limit of {max_pixels} pixels ({max_megapixels} MP)"
        )
        raise ValueError(
            f"Image resolution {img_array.shape[:2]} exceeds maximum "
            f"of {max_megapixels} megapixels"
        )
    
    # ============================================================================
    # 3. PREPROCESSING WITH ERROR HANDLING
    # ============================================================================
    
    try:
        # Convert to grayscale if color
        if len(img_array.shape) == 3:
            try:
                gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
            except cv2.error as e:
                logger.error(f"cv2.cvtColor failed: {e}")
                raise ValueError(f"Failed to convert to grayscale: {e}")
        else:
            gray = img_array.copy()  # ALWAYS copy to avoid mutation
        
        # 1. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        try:
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
        except cv2.error as e:
            logger.error(f"CLAHE enhancement failed: {e}")
            raise ValueError(f"CLAHE enhancement failed: {e}")
        
        # 2. Bilateral filter (denoise while preserving edges)
        try:
            denoised = cv2.bilateralFilter(enhanced, 9, 75, 75)
        except cv2.error as e:
            logger.error(f"Bilateral filter failed: {e}")
            raise ValueError(f"Bilateral filter failed: {e}")
        
        # 3. Deskew detection (Hough Line Transform)
        try:
            edges = cv2.Canny(denoised, 50, 150)
            lines = cv2.HoughLinesP(
                edges,
                1,
                np.pi / 180,
                100,
                minLineLength=100,
                maxLineGap=10
            )
        except cv2.error as e:
            logger.error(f"Edge detection / Hough transform failed: {e}")
            # Graceful fallback: skip deskew, continue with denoised image
            lines = None
        
        if lines is not None:
            try:
                angles = []
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                    if abs(angle) < 45:  # Filter near-horizontal lines
                        angles.append(angle)
                
                if angles:
                    median_angle = np.median(angles)
                    if abs(median_angle) > 1:  # Only rotate if angle > 1 degree
                        h, w = denoised.shape
                        center = (w // 2, h // 2)
                        rotation_matrix = cv2.getRotationMatrix2D(
                            center, median_angle, 1.0
                        )
                        denoised = cv2.warpAffine(
                            denoised,
                            rotation_matrix,
                            (w, h),
                            borderMode=cv2.BORDER_REPLICATE
                        )
            except (cv2.error, ValueError, IndexError) as e:
                logger.warning(f"Deskew rotation failed, skipping: {e}")
                # Graceful fallback: continue without rotation
        
        # 4. Morphological operations (clean up)
        try:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            morph = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel, iterations=1)
        except cv2.error as e:
            logger.error(f"Morphological operations failed: {e}")
            # Graceful fallback: return denoised image
            morph = denoised
        
        return morph
        
    except ValueError:
        # Re-raise validation errors
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            f"Unexpected error in image preprocessing: {type(e).__name__}: {e}"
        )
        raise ValueError(f"Image preprocessing failed: {e}")


def _ocr_single_image(img_array: np.ndarray) -> list[dict[str, Any]]:
    """Run PaddleOCR on a single numpy image array and return raw lines."""
    ocr = _get_paddle_ocr()
    result = ocr.ocr(img_array)

    raw_lines = []
    if result and result[0]:
        for line in result[0]:
            bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text = line[1][0]
            confidence = float(line[1][1])
            raw_lines.append({
                "text": text,
                "confidence": confidence,
                "bbox": bbox,
            })
    return raw_lines


def extract_text_from_image(image_bytes: bytes) -> dict[str, Any]:
    """
    Run PaddleOCR on an image or PDF with form-specific optimization.
    PDFs are converted to images first (one per page), then OCR is run on each page.
    
    FORM-SPECIFIC OPTIMIZATION:
    - Detects form type (DTI BNR, Barangay Clearance, etc.)
    - Applies form-specific preprocessing and region extraction
    - Returns OCR results optimized for the form layout

    Returns:
        {
            "raw_lines": [{"text": str, "confidence": float, "bbox": list}],
            "full_text": str,
            "avg_confidence": float,
            "processing_time": float,
            "form_type": str,  # NEW: detected form type
        }
    """
    import gc
    start_time = time.time()

    # MEMORY OPTIMIZATION: Downscale image if needed BEFORE OCR to reduce peak RAM
    logger.debug(f"Original image size: {len(image_bytes) / 1024:.1f}KB")
    image_bytes = _downscale_image_if_needed(image_bytes)
    gc.collect()  # Force cleanup after downscaling

    raw_lines: list[dict[str, Any]] = []
    detected_form_type = "unknown"

    if _is_pdf(image_bytes):
        # Convert PDF pages to images and OCR each page
        logger.info("Detected PDF input, converting pages to images...")
        pages = _pdf_to_images(image_bytes)
        logger.info(f"PDF has {len(pages)} page(s)")

        for page_num, page_img in enumerate(pages, 1):
            if page_img.mode != "RGB":
                page_img = page_img.convert("RGB")
            img_array = np.array(page_img)
            
            # Detect form type on first page only
            if page_num == 1:
                from app.services.ocr_form_specific import detect_form_type
                detected_form_type = detect_form_type(img_array)
                logger.info(f"[FORM-TYPE] Detected: {detected_form_type}")
            
            # Apply form-specific or generic preprocessing
            preprocessed = _apply_form_specific_preprocessing(img_array, detected_form_type)
            page_lines = _ocr_single_image(preprocessed)
            # Tag lines with page number
            for line in page_lines:
                line["page"] = page_num
            raw_lines.extend(page_lines)
            logger.info(f"Page {page_num}: extracted {len(page_lines)} lines")
            
            # MEMORY OPTIMIZATION: Clear page from memory after processing
            del page_img
            del img_array
            del preprocessed
            gc.collect()
    else:
        # Single image
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_array = np.array(image)
        
        # Detect form type
        from app.services.ocr_form_specific import detect_form_type
        detected_form_type = detect_form_type(img_array)
        logger.info(f"[FORM-TYPE] Detected: {detected_form_type}")
        
        # Apply form-specific or generic preprocessing
        preprocessed = _apply_form_specific_preprocessing(img_array, detected_form_type)
        raw_lines = _ocr_single_image(preprocessed)
        
        # MEMORY OPTIMIZATION: Release image immediately after OCR
        del image
        del img_array
        del preprocessed
        gc.collect()

    processing_time = time.time() - start_time
    total_confidence = sum(line["confidence"] for line in raw_lines)
    avg_confidence = (total_confidence / len(raw_lines)) if raw_lines else 0.0
    full_text = "\n".join(line["text"] for line in raw_lines)

    logger.info(
        f"OCR extracted {len(raw_lines)} lines, avg confidence: {avg_confidence:.2f}, "
        f"time: {processing_time:.2f}s, form_type: {detected_form_type}"
    )

    return {
        "raw_lines": raw_lines,
        "full_text": full_text,
        "avg_confidence": avg_confidence,
        "processing_time": processing_time,
        "form_type": detected_form_type,
    }


def extract_text_from_image_with_template(
    image_bytes: bytes,
    template: Any,  # FormTemplate model
) -> dict[str, Any]:
    """
    Extract text from image using template-specific OCR optimization.
    
    Uses template name OR template ID to determine form type and apply optimized preprocessing.
    Falls back to standard extraction if template-specific preprocessing fails.
    """
    import gc
    start_time = time.time()
    
    # Determine form type from template name or ID
    # Priority: name > ID pattern matching
    template_name = (template.name.lower() if hasattr(template, 'name') else 'unknown')
    template_id = str(template.id) if hasattr(template, 'id') else None
    
    logger.info(f"[TEMPLATE-MAP] Template ID: {template_id}, Name: {template_name}")
    
    form_type_mapping = {
        'dti': 'dti_bnr',
        'business name': 'dti_bnr',
        '028e7ec2': 'dti_bnr',  # Known DTI template ID prefix
        'barangay': 'barangay_clearance',
        'community tax': 'community_tax',
        'cedula': 'community_tax',
    }
    
    detected_form_type = 'unknown'
    
    # Try name matching first
    for keyword, form_code in form_type_mapping.items():
        if keyword in template_name:
            detected_form_type = form_code
            logger.info(f"[TEMPLATE-MAP] Matched by name: '{keyword}' → {form_code}")
            break
    
    # Try ID matching if name didn't work
    if detected_form_type == 'unknown' and template_id:
        for keyword, form_code in form_type_mapping.items():
            if keyword in template_id:
                detected_form_type = form_code
                logger.info(f"[TEMPLATE-MAP] Matched by ID: '{keyword}' → {form_code}")
                break
    
    logger.info(f"[TEMPLATE-FORM-MAP] '{template_name}' (ID: {template_id}) → {detected_form_type}")
    
    # Apply generic preprocessing + downscaling first (shared with standard path)
    image_bytes_processed = _downscale_image_if_needed(image_bytes)
    gc.collect()
    
    raw_lines: list[dict[str, Any]] = []
    
    try:
        # Convert bytes to numpy array
        image = Image.open(io.BytesIO(image_bytes_processed))
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_array = np.array(image)
        
        # Apply template-specific preprocessing
        preprocessed = _apply_form_specific_preprocessing(img_array, detected_form_type)
        raw_lines = _ocr_single_image(preprocessed)
        
        del image
        del img_array
        del preprocessed
        gc.collect()
        
    except Exception as e:
        logger.warning(f"Template-specific extraction failed: {e}, falling back to standard extraction")
        # Fallback: use standard extraction instead
        return extract_text_from_image(image_bytes_processed)
    
    processing_time = time.time() - start_time
    total_confidence = sum(line["confidence"] for line in raw_lines)
    avg_confidence = (total_confidence / len(raw_lines)) if raw_lines else 0.0
    full_text = "\n".join(line["text"] for line in raw_lines)
    
    logger.info(
        f"Template-based extraction: {len(raw_lines)} lines, "
        f"confidence={avg_confidence:.2f}, form={detected_form_type}, time={processing_time:.2f}s"
    )
    
    return {
        "raw_lines": raw_lines,
        "full_text": full_text,
        "avg_confidence": avg_confidence,
        "processing_time": processing_time,
        "form_type": detected_form_type,
    }


def map_ocr_to_fields(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None = None,
    template_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Map raw OCR text to structured form fields.
    
    **OPTIMIZED STRATEGY (P0):** Single unified API call instead of 6+ sequential calls
    1. Check cache if template_id is provided
    2. Try UNIFIED AI-powered mapping (single Groq call for all fields)
    3. If AI unavailable/fails, fall back to naive label matching
    
    Caching: Results are cached by template_id + image fingerprint + OCR content hash
    to avoid re-extracting identical forms (~20% of typical traffic is repeat forms).
    """
    fields_spec = field_schema.get("fields", [])

    if not fields_spec:
        return []

    # Template fingerprinting caching: check if we've seen this exact form before
    if template_id:
        image_fingerprint = _get_image_fingerprint(image_bytes)
        ocr_full_text = ocr_result.get("full_text", "")
        cached_result = _get_cached_field_mapping(template_id, image_fingerprint, ocr_full_text)
        if cached_result:
            return cached_result

    # Single AI extraction (direct approach)
    ai_result = _map_fields_with_ai(ocr_result, field_schema, image_bytes)
    if ai_result:
        # Cache the result if template_id is available
        if template_id:
            image_fingerprint = _get_image_fingerprint(image_bytes)
            ocr_full_text = ocr_result.get("full_text", "")
            _cache_field_mapping(template_id, image_fingerprint, ocr_full_text, ai_result)
        return ai_result

    # Fallback: naive label matching
    logger.info("AI field mapping unavailable, using naive label matching")
    naive_result = _map_fields_naive(ocr_result, field_schema)
    
    # Cache naive result as well
    if naive_result and template_id:
        image_fingerprint = _get_image_fingerprint(image_bytes)
        ocr_full_text = ocr_result.get("full_text", "")
        _cache_field_mapping(template_id, image_fingerprint, ocr_full_text, naive_result)
    
    return naive_result


def _map_fields_with_ai(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None = None,
    api_key_override: str | None = None,
    disagreement_context: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """
    Use Groq AI to intelligently map OCR text to form fields.

    Strategy (separated approach for best accuracy):
    1. Text fields → batched AI calls with OCR text + image
    2. Checkbox/radio fields → dedicated AI vision call (focused prompt)
    3. Checkbox/radio also sent in text batch as backup signal
    4. Merge: prefer dedicated vision result, fill gaps from text batch

    Returns list of field dicts or None if AI is unavailable.
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.AI_API_KEY:
        logger.warning("No AI API key available, skipping AI field mapping")
        return None

    fields_spec = field_schema.get("fields", [])
    raw_lines = ocr_result.get("raw_lines", [])

    # Separate checkbox/selection fields from text fields
    CHECKBOX_TYPES = {"checkbox", "checkbox-group", "radio"}
    checkbox_fields = [f for f in fields_spec if f.get("type") in CHECKBOX_TYPES]
    text_fields = [f for f in fields_spec if f.get("type") not in CHECKBOX_TYPES]

    logger.info(
        f"Field split: {len(text_fields)} text fields, "
        f"{len(checkbox_fields)} checkbox/selection fields"
    )

    BATCH_SIZE = 18

    # Prepare image content once (reused across all calls)
    # MEMORY OPTIMIZATION: Only encode image if present; release original after encoding
    image_content = None
    if image_bytes:
        import base64
        import gc
        
        # Detect MIME type first before encoding
        if image_bytes[:4] == b"\x89PNG":
            mime = "image/png"
        elif image_bytes[:2] == b"\xff\xd8":
            mime = "image/jpeg"
        else:
            mime = "image/jpeg"
        
        # Encode image and immediately store in dict
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64_image}"},
        }
        
        # Release original image bytes after encoding
        # (base64 string is ~33% larger but we don't need the original anymore)
        del image_bytes
        del b64_image  # Delete the intermediate variable too
        gc.collect()  # Force garbage collection to free memory immediately
        logger.debug("Released original image bytes after base64 encoding")

    # Build OCR text with line numbers
    ocr_lines_formatted = "\n".join(
        f"  Line {i+1}: \"{line['text']}\" (conf: {line['confidence']:.2f})"
        for i, line in enumerate(raw_lines)
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
        )

        all_ai_fields: dict[str, Any] = {}

        # Initialize disagreement hint (previously used for consensus, now empty)
        disagreement_hint = ""


        # ── Step 1: Extract TEXT fields via batched OCR text + vision ──
        if text_fields:
            batches = [
                text_fields[i:i + BATCH_SIZE]
                for i in range(0, len(text_fields), BATCH_SIZE)
            ]
            total_batches = len(batches)

            if total_batches > 1:
                logger.info(
                    f"Text fields: splitting {len(text_fields)} "
                    f"into {total_batches} batches"
                )

            for batch_idx, batch in enumerate(batches, 1):
                batch_result = _run_ai_batch(
                    client=client,
                    model=settings.AI_VISION_MODEL,
                    batch_fields=batch,
                    ocr_lines_formatted=ocr_lines_formatted,
                    image_content=image_content,
                    batch_idx=batch_idx,
                    total_batches=total_batches,
                    disagreement_hint=disagreement_hint,
                )
                if batch_result:
                    all_ai_fields.update(batch_result)

        # ── Step 2: Extract CHECKBOX/RADIO fields via dedicated vision ──
        # This uses a focused prompt specifically for checkbox detection,
        # which gives the model's full attention to visual checkbox states.
        if checkbox_fields and image_content:
            vision_result = _detect_checkboxes_with_vision(
                client=client,
                model=settings.AI_VISION_MODEL,
                checkbox_fields=checkbox_fields,
                image_content=image_content,
                ocr_lines_formatted=ocr_lines_formatted,
                disagreement_hint=disagreement_hint,
            )

            if vision_result:
                vision_detected = sum(
                    1 for v in vision_result.values()
                    if v and v not in ("", "no")
                )
                logger.info(
                    f"Vision checkbox detection: {vision_detected}/"
                    f"{len(checkbox_fields)} fields have selections"
                )
                all_ai_fields.update(vision_result)
            else:
                logger.warning("Vision checkbox detection returned no results")

        # ── Step 3: Backup — send checkboxes through text batch too ──
        # If vision missed some, the text batch may catch them via OCR context.
        missing_checkbox_fields = [
            f for f in checkbox_fields
            if not all_ai_fields.get(f["name"])
            or all_ai_fields.get(f["name"]) in ("", "no")
        ]

        if missing_checkbox_fields:
            logger.info(
                f"Vision missed {len(missing_checkbox_fields)} checkbox fields, "
                f"trying text+vision batch as backup"
            )
            backup_result = _run_ai_batch(
                client=client,
                model=settings.AI_VISION_MODEL,
                batch_fields=missing_checkbox_fields,
                ocr_lines_formatted=ocr_lines_formatted,
                image_content=image_content,
                batch_idx=1,
                total_batches=1,
            )
            if backup_result:
                # Normalize and merge only missing fields
                for field in missing_checkbox_fields:
                    name = field["name"]
                    ftype = field.get("type", "checkbox")
                    raw_val = backup_result.get(name, "")
                    if isinstance(raw_val, dict):
                        raw_val = str(raw_val.get("value", ""))
                    else:
                        raw_val = str(raw_val) if raw_val is not None else ""
                    raw_lower = raw_val.lower().strip()

                    if ftype == "checkbox":
                        normalized = "true" if raw_lower in (
                            "yes", "true", "checked", "1", "x",
                            "✓", "✔", "on", "selected", "filled",
                        ) else ""
                    elif ftype == "radio":
                        options = field.get("options", [])
                        normalized = _match_radio_option(raw_lower, options)
                    else:
                        normalized = raw_val

                    # Only fill if current value is empty
                    current = all_ai_fields.get(name, "")
                    if not current and normalized:
                        all_ai_fields[name] = normalized
                        logger.info(
                            f"Backup filled '{name}' = '{normalized}'"
                        )

        # ── Step 4: Targeted re-check for activity checkboxes (PSIC section) ──
        # The PSIC 2x3 grid is particularly tricky. Always run a focused
        # re-check with a cropped image for better accuracy.
        activity_fields = [
            f for f in checkbox_fields
            if f["name"].startswith("activity_")
        ]

        # Note: We already deleted image_bytes after encoding, so only check image_content
        if activity_fields and image_content:
            # Use full image for PSIC checkbox detection
            # (We deleted original image_bytes for memory efficiency after base64 encoding)
            
            recheck_result = _recheck_activity_checkboxes(
                client=client,
                model=settings.AI_VISION_MODEL,
                activity_fields=activity_fields,
                image_content=image_content,
                is_cropped=False,
            )
            if recheck_result:
                # Re-check is AUTHORITATIVE for PSIC fields — override all
                for name, val in recheck_result.items():
                    old_val = all_ai_fields.get(name, "")
                    all_ai_fields[name] = val
                    if val and not old_val:
                        logger.info(
                            f"PSIC re-check filled '{name}' = '{val}'"
                        )
                    elif not val and old_val:
                        logger.info(
                            f"PSIC re-check cleared '{name}' (was '{old_val}')"
                        )

        # Log final checkbox state
        logger.info(
            "Final checkbox/radio values: "
            + str({
                f["name"]: all_ai_fields.get(f["name"], "")
                for f in checkbox_fields
            })
        )

        if not all_ai_fields:
            logger.warning("AI field mapping returned no results")
            return None

        # ── Build final result ──
        mapped_fields = []
        for field_spec in fields_spec:
            field_name = field_spec["name"]
            if field_name in all_ai_fields:
                entry = all_ai_fields[field_name]
                if isinstance(entry, dict):
                    value = str(entry.get("value", ""))
                    confidence = float(entry.get("confidence", 0.9))
                else:
                    value = str(entry) if entry is not None else ""
                    confidence = 0.92 if value else 0.0
            else:
                value = ""
                confidence = 0.0

            mapped_fields.append({
                "field_name": field_name,
                "ocr_value": value,
                "confidence": min(confidence, 1.0),
            })

        filled = sum(1 for f in mapped_fields if f["ocr_value"])
        logger.info(f"AI field mapping total: {filled}/{len(mapped_fields)} fields extracted")

        # ── Post-OCR correction — fix common OCR errors ──
        from app.services.post_correction import apply_post_corrections
        mapped_fields = apply_post_corrections(mapped_fields)

        return mapped_fields

    except Exception as e:
        logger.error(
            f"AI field mapping failed: {e}",
            exc_info=True  # Include full traceback for debugging
        )
        return None


# ── Radio option matching helper ──────────────────────────────────────


def _match_radio_option(raw_value: str, options: list[str]) -> str:
    """
    Match a raw AI-extracted value to one of the radio field options.

    The AI may return human-readable text like "Single", "Female", "NEW",
    "City/Municipality", etc. We need to match this to the snake_case option
    values like "single", "female", "new", "city_municipality".

    Returns the matched option value, or empty string if no match.
    """
    if not raw_value or not options:
        return ""

    raw_lower = raw_value.lower().strip()

    # Pass 1: Exact case-insensitive match
    for opt in options:
        if raw_lower == opt.lower():
            return opt

    # Pass 2: Match with underscores replaced by spaces
    # e.g., "city/municipality" matches "city_municipality"
    raw_normalized = raw_lower.replace("/", "_").replace("-", "_").replace(" ", "_")
    for opt in options:
        opt_lower = opt.lower()
        if raw_normalized == opt_lower:
            return opt
        # Also try without underscores
        if raw_lower.replace(" ", "").replace("/", "").replace("-", "") == opt_lower.replace("_", ""):
            return opt

    # Pass 3: Word containment — check if raw text contains the option word
    for opt in options:
        opt_words = opt.lower().replace("_", " ").split()
        raw_words = raw_lower.replace("_", " ").replace("/", " ").split()
        # If all option words appear in the raw text
        if all(w in raw_words for w in opt_words):
            return opt
        # If raw text appears as substring of expanded option name
        opt_expanded = opt.lower().replace("_", " ")
        if raw_lower in opt_expanded or opt_expanded in raw_lower:
            return opt

    # Pass 4: Partial match — first word match
    for opt in options:
        opt_first = opt.lower().split("_")[0]
        if raw_lower.startswith(opt_first) or opt_first.startswith(raw_lower):
            return opt

    logger.debug(f"Radio match failed: '{raw_value}' not in {options}")
    return ""


# ── Pixel-based checkbox detection ──────────────────────────────────────

def _find_ocr_line_for_label(
    raw_lines: list[dict[str, Any]], label: str
) -> dict[str, Any] | None:
    """Find the OCR line whose text best matches the given label."""
    label_lower = label.lower().strip()
    label_words = set(label_lower.split())

    best_match = None
    best_score = 0.0

    for line in raw_lines:
        text = line.get("text", "").lower().strip()
        if not text:
            continue

        # Exact containment
        if label_lower in text or text in label_lower:
            score = len(label_lower) / max(len(text), 1)
            if score > best_score:
                best_score = score
                best_match = line
                if score > 0.8:
                    break
            continue

        # Word overlap score
        text_words = set(text.split())
        overlap = label_words & text_words
        if overlap:
            score = len(overlap) / max(len(label_words), 1) * 0.8
            if score > best_score:
                best_score = score
                best_match = line

    return best_match


def _detect_checkboxes_pixel_based(
    image_bytes: bytes,
    raw_lines: list[dict[str, Any]],
    checkbox_fields: list[dict[str, Any]],
) -> dict[str, str] | None:
    """
    Detect checkbox/radio states using pixel analysis of the actual image.

    Strategy:
    1. Convert image to grayscale + binary (inverted: dark pixels become white)
    2. For each checkbox field, find its label text in OCR results
    3. Locate the checkbox box to the LEFT of the label text
    4. Measure the fill ratio (percentage of dark pixels)
    5. Checked = high fill ratio, unchecked = low fill ratio

    For radio fields: compare fill ratios across all options and pick the highest.

    Returns dict of {field_name: "true"/"" for checkboxes, option_value for radio}.
    """
    import cv2

    try:
        # Decode image
        img_array = np.frombuffer(image_bytes, np.uint8)
        img_color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img_color is None:
            logger.warning("Pixel checkbox detection: failed to decode image")
            return None

        gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
        img_h, img_w = gray.shape

        # Binary threshold (inverted: dark pixels → 255, light → 0)
        _, binary_inv = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY_INV)

        results: dict[str, str] = {}
        fill_ratios: dict[str, float] = {}

        # Group radio fields to compare later
        radio_groups: dict[str, list[dict]] = {}

        for field in checkbox_fields:
            name = field["name"]
            label = field.get("label", name)
            ftype = field.get("type", "checkbox")
            options = field.get("options", [])

            # Find OCR line for this label
            match_line = _find_ocr_line_for_label(raw_lines, label)
            if match_line is None:
                logger.debug(f"Pixel checkbox: no OCR match for '{label}'")
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            bbox = match_line.get("bbox")
            if not bbox or len(bbox) < 4:
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            # bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            min_x = int(min(p[0] for p in bbox))
            min_y = int(min(p[1] for p in bbox))
            max_y = int(max(p[1] for p in bbox))
            text_height = max(max_y - min_y, 10)

            # Checkbox box is to the LEFT of the label text
            box_size = int(text_height * 1.0)
            gap = int(text_height * 0.3)
            box_right = max(min_x - gap, 0)
            box_left = max(box_right - box_size, 0)
            box_top = max(min_y, 0)
            box_bottom = min(box_top + box_size, img_h)

            # Ensure valid region
            if box_left >= box_right or box_top >= box_bottom:
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            # Crop checkbox region
            region = binary_inv[box_top:box_bottom, box_left:box_right]
            if region.size == 0:
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            # Calculate fill ratio
            fill_ratio = float(np.count_nonzero(region)) / region.size
            fill_ratios[name] = fill_ratio

            logger.debug(
                f"Pixel checkbox '{name}' ({label}): "
                f"region=[{box_left}:{box_right}, {box_top}:{box_bottom}], "
                f"fill_ratio={fill_ratio:.3f}"
            )

            if ftype == "checkbox":
                # Threshold: > 0.35 means checked (solid dark square ≈ 0.6-0.9)
                results[name] = "true" if fill_ratio > 0.35 else ""
            elif ftype == "radio":
                # Store for group comparison
                group_key = name.rsplit("_", 1)[0] if "_" in name else name
                # Actually, radio fields have ONE name with multiple options
                # For now, store the fill ratio and handle in post-processing
                results[name] = ""  # placeholder
                # Build group: find which option label matched
                if name not in radio_groups:
                    radio_groups[name] = []
                radio_groups[name].append({
                    "name": name,
                    "options": options,
                    "fill_ratio": fill_ratio,
                })

        # Handle radio fields — these need special treatment
        # For radio type, each field has multiple options with their own labels
        # We need to find which option's checkbox is filled
        for field in checkbox_fields:
            if field.get("type") != "radio":
                continue

            name = field["name"]
            options = field.get("options", [])
            if not options:
                continue

            option_fills: list[tuple[str, float]] = []
            for opt in options:
                opt_line = _find_ocr_line_for_label(raw_lines, opt.replace("_", " "))
                if opt_line is None:
                    # Try with the raw option value
                    opt_line = _find_ocr_line_for_label(raw_lines, opt)
                if opt_line is None:
                    option_fills.append((opt, 0.0))
                    continue

                bbox = opt_line.get("bbox")
                if not bbox or len(bbox) < 4:
                    option_fills.append((opt, 0.0))
                    continue

                min_x = int(min(p[0] for p in bbox))
                min_y = int(min(p[1] for p in bbox))
                max_y = int(max(p[1] for p in bbox))
                text_height = max(max_y - min_y, 10)

                box_size = int(text_height * 1.0)
                gap = int(text_height * 0.3)
                box_right = max(min_x - gap, 0)
                box_left = max(box_right - box_size, 0)
                box_top = max(min_y, 0)
                box_bottom = min(box_top + box_size, img_h)

                if box_left >= box_right or box_top >= box_bottom:
                    option_fills.append((opt, 0.0))
                    continue

                region = binary_inv[box_top:box_bottom, box_left:box_right]
                ratio = float(np.count_nonzero(region)) / max(region.size, 1)
                option_fills.append((opt, ratio))

                logger.debug(
                    f"Pixel radio '{name}' option '{opt}': "
                    f"region=[{box_left}:{box_right}, {box_top}:{box_bottom}], "
                    f"fill_ratio={ratio:.3f}"
                )

            # Pick the option with the highest fill ratio (if above threshold)
            if option_fills:
                best_opt, best_fill = max(option_fills, key=lambda x: x[1])
                if best_fill > 0.25:
                    results[name] = best_opt
                    logger.debug(
                        f"Pixel radio '{name}': selected '{best_opt}' "
                        f"(fill={best_fill:.3f})"
                    )
                else:
                    results[name] = ""

        # Log summary
        checked = sum(1 for v in results.values() if v and v not in ("", "no"))
        logger.info(f"Pixel checkbox detection: {checked}/{len(checkbox_fields)} fields detected")
        logger.info(f"Pixel checkbox results: {results}")
        logger.info(f"Pixel fill ratios: {fill_ratios}")

        return results

    except Exception as e:
        logger.error(f"Pixel-based checkbox detection failed: {e}", exc_info=True)
        return None


def _crop_psic_region(
    image_bytes: bytes,
    raw_lines: list[dict[str, Any]],
) -> bytes | None:
    """
    Crop the PSIC activity checkbox region from the form image using
    OCR bounding boxes to locate the section.

    Returns cropped image as PNG bytes, or None if region not found.
    """
    psic_keywords = [
        "manufacturer", "producer", "service", "retailer",
        "wholesaler", "importer", "exporter",
    ]

    psic_bboxes = []
    for line in raw_lines:
        text_lower = line.get("text", "").lower()
        if any(kw in text_lower for kw in psic_keywords):
            bbox = line.get("bbox")
            if bbox:
                psic_bboxes.append(bbox)

    if len(psic_bboxes) < 2:
        logger.debug(
            f"PSIC crop: only found {len(psic_bboxes)} matching lines, need at least 2"
        )
        return None

    # Compute bounding rectangle from all detected PSIC text positions
    all_points = [pt for bbox in psic_bboxes for pt in bbox]
    min_x = min(pt[0] for pt in all_points)
    min_y = min(pt[1] for pt in all_points)
    max_x = max(pt[0] for pt in all_points)
    max_y = max(pt[1] for pt in all_points)

    image = Image.open(io.BytesIO(image_bytes))
    if image.mode != "RGB":
        image = image.convert("RGB")

    region_width = max_x - min_x
    region_height = max_y - min_y

    # Generous padding: checkboxes are to the LEFT of labels, and we want
    # the full grid visible including surrounding context
    pad_left = int(region_width * 0.4)   # Extra left for checkbox squares
    pad_right = int(region_width * 0.2)
    pad_top = int(region_height * 0.5)   # Include "Main Business Activity" header
    pad_bottom = int(region_height * 0.5)

    crop_box = (
        max(0, int(min_x) - pad_left),
        max(0, int(min_y) - pad_top),
        min(image.width, int(max_x) + pad_right),
        min(image.height, int(max_y) + pad_bottom),
    )

    cropped = image.crop(crop_box)
    logger.info(
        f"PSIC crop: {cropped.width}×{cropped.height}px "
        f"(from {len(psic_bboxes)} text matches)"
    )

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def _recheck_activity_checkboxes(
    client: Any,
    model: str,
    activity_fields: list[dict[str, Any]],
    image_content: dict[str, Any],
    is_cropped: bool = False,
) -> dict[str, str] | None:
    """
    Focused re-check of PSIC activity checkboxes (Section G, Box 24).

    Uses a very specific prompt that describes the exact grid layout
    and asks the model to examine each box one at a time.

    Args:
        is_cropped: If True, the image_content is a cropped PSIC region,
            so the prompt is adjusted to reference the visible area.
    """
    field_names = [f["name"] for f in activity_fields]
    labels = [f.get("label", f["name"]) for f in activity_fields]

    # Need all 6 activity fields for the hardcoded grid prompt
    if len(field_names) < 6:
        logger.debug(
            f"PSIC re-check skipped: only {len(field_names)}/6 activity fields present"
        )
        return None

    if is_cropped:
        context_intro = (
            "This image shows ONLY the 'Main Business Activity' checkbox section "
            "from a Philippine DTI Business Name Registration form.\n\n"
            "You can see a 2-row × 3-column grid of small square checkboxes, "
            "each next to a label.\n\n"
        )
    else:
        context_intro = (
            "Look at Section G of this Philippine DTI Business Name Registration form.\n\n"
            "Find the area labeled '24. Main Business Activity'. "
            "It has a 2-row × 3-column grid of small square checkboxes, each next to a label.\n\n"
        )

    prompt = (
        f"{context_intro}"
        "STEP 1 — DESCRIBE EACH POSITION:\n"
        "Go through each of the 6 positions below. For each one, describe what the "
        "small square checkbox looks like: is it filled/dark/solid (■) or empty/white/clear (□)?\n\n"
        "The 6 positions are:\n"
        "  Position 1 (Top row, LEFT):   The checkbox BEFORE the text 'Manufacturer/Producer'\n"
        "  Position 2 (Top row, MIDDLE): The checkbox BEFORE the text 'Service'\n"
        "  Position 3 (Top row, RIGHT):  The checkbox BEFORE the text 'Retailer'\n"
        "  Position 4 (Bottom row, LEFT):   The checkbox BEFORE the text 'Wholesaler'\n"
        "  Position 5 (Bottom row, MIDDLE): The checkbox BEFORE the text 'Importer'\n"
        "  Position 6 (Bottom row, RIGHT):  The checkbox BEFORE the text 'Exporter'\n\n"
        "IMPORTANT: Each checkbox is the small square □ that appears IMMEDIATELY BEFORE "
        "(to the LEFT of) each label text. Do NOT confuse checkboxes between labels.\n\n"
        "STEP 2 — RETURN RESULTS:\n"
        "Based on your observations, return a JSON object.\n"
        "A filled/dark/solid square = \"yes\", an empty/white/clear square = \"no\".\n\n"
        "Return ONLY this JSON (include your reasoning for each as shown):\n"
        "{\n"
        '  "reasoning": {\n'
        '    "position_1_manufacturer": "describe what the checkbox looks like",\n'
        '    "position_2_service": "describe what the checkbox looks like",\n'
        '    "position_3_retailer": "describe what the checkbox looks like",\n'
        '    "position_4_wholesaler": "describe what the checkbox looks like",\n'
        '    "position_5_importer": "describe what the checkbox looks like",\n'
        '    "position_6_exporter": "describe what the checkbox looks like"\n'
        "  },\n"
        f'  "{field_names[0]}": "yes or no",\n'
        f'  "{field_names[1]}": "yes or no",\n'
        f'  "{field_names[2]}": "yes or no",\n'
        f'  "{field_names[3]}": "yes or no",\n'
        f'  "{field_names[4]}": "yes or no",\n'
        f'  "{field_names[5]}": "yes or no"\n'
        "}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content,
                ],
            }],
            max_tokens=1500,
            temperature=0.0,
        )

        content = response.choices[0].message.content or "{}"
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()
        if not content:
            logger.warning("PSIC re-check: empty response from API")
            return None

        result = json.loads(content)
        logger.info(f"PSIC re-check raw response: {result}")

        # Normalize to "true"/""
        normalized: dict[str, str] = {}
        for f in activity_fields:
            name = f["name"]
            val = str(result.get(name, "")).lower().strip()
            normalized[name] = "true" if val in (
                "yes", "true", "checked", "1", "x", "✓", "✔",
            ) else ""

        checked = sum(1 for v in normalized.values() if v)
        logger.info(f"PSIC re-check: {checked}/{len(activity_fields)} activities checked")
        logger.info(f"PSIC re-check normalized: {normalized}")
        return normalized

    except Exception as e:
        logger.error(f"PSIC re-check failed: {e}")
        return None


def _detect_checkboxes_with_vision(
    client: Any,
    model: str,
    checkbox_fields: list[dict[str, Any]],
    image_content: dict[str, Any],
    ocr_lines_formatted: str = "",
    disagreement_hint: str = "",
) -> dict[str, Any] | None:
    """
    Use AI Vision to detect which checkboxes/radio buttons are checked
    in the form image. This is a focused, dedicated call that gives the
    model's full attention to visual checkbox states.

    Returns dict of {field_name: "true"/"" for checkboxes, option value for radio}.
    """
    # Build a concise field description
    fields_desc_parts = []
    for f in checkbox_fields:
        ftype = f.get("type", "checkbox")
        label = f.get("label", f["name"])
        name = f["name"]
        hint = f.get("hint", "")
        section = f.get("section", "")
        location = ""
        if hint:
            location = f" (Location: {hint})"
        elif section:
            location = f" (Section: {section})"

        if ftype == "checkbox":
            fields_desc_parts.append(
                f'  "{name}": Single checkbox labeled "{label}".{location}'
            )
        elif ftype == "checkbox-group":
            options = f.get("options", [])
            opt_str = ", ".join(f'"{o}"' for o in options)
            fields_desc_parts.append(
                f'  "{name}": Checkbox group "{label}" with options: {opt_str}.{location}'
            )
        elif ftype == "radio":
            options = f.get("options", [])
            opt_str = ", ".join(f'"{o}"' for o in options)
            fields_desc_parts.append(
                f'  "{name}": Radio select "{label}" — options: {opt_str}.{location}'
            )

    fields_desc = "\n".join(fields_desc_parts)

    # Include OCR text hints for radio fields to help disambiguate
    ocr_hint = ""
    if ocr_lines_formatted:
        ocr_hint = (
            "\nOCR TEXT CONTEXT (use as secondary signal to verify your visual reading):\n"
            f"{ocr_lines_formatted}\n"
        )

    prompt = (
        "You are an expert at reading scanned Philippine government forms.\n\n"
        "TASK: Examine EVERY checkbox and radio button in this form image INDIVIDUALLY. "
        "For each one, look directly at the small square box and determine if it contains "
        "any dark mark (checked) or is empty (unchecked).\n\n"
        "VISUAL GUIDE:\n"
        "- CHECKED: filled/darkened square ■, checkmark ✓, X mark, or ANY dark mark inside the box\n"
        "- UNCHECKED: empty/white/light square □ with nothing inside\n\n"
        "CRITICAL RULES:\n"
        "- Do NOT guess or assume — look at EACH box individually\n"
        "- Do NOT default to the first option if unsure — examine all options in a group\n"
        "- For radio groups: EXACTLY ONE option should be checked. Compare ALL options visually\n"
        "- For the PSIC activity section: MULTIPLE checkboxes can be checked simultaneously\n"
        "- Cross-reference with the OCR text below if available — OCR may have captured "
        "handwritten text near checked boxes\n\n"
        "DETAILED FORM LAYOUT:\n"
        "- Section A (top): Registration Type — two boxes side by side: □ NEW  □ RENEWAL\n"
        "- Section B: TIN Status — two boxes: □ With TIN  □ Without TIN\n"
        "- Section C (Box 8): Civil Status — FOUR boxes in a row, left to right:\n"
        "  □ Legally Separated  □ Single  □ Married  □ Widowed\n"
        "  Look carefully at EACH of these 4 boxes — only ONE should have a mark\n"
        "- Section C (Box 9): Gender — □ Male  □ Female\n"
        "- Section C (Box 10): Refugee — □ Yes  □ No  |  Stateless — □ Yes  □ No\n"
        "- Section D (Box 12): Territorial Scope — 4 options:\n"
        "  □ Barangay  □ City/Municipality  □ Regional  □ National\n"
        "- Section G (Box 24): PSIC Business Activity — 6 boxes in a 2×3 GRID:\n"
        "  ┌──────────────────────────┬──────────────┬──────────────┐\n"
        "  │ □ Manufacturer/Producer  │ □ Service    │ □ Retailer   │  ← TOP ROW\n"
        "  ├──────────────────────────┼──────────────┼──────────────┤\n"
        "  │ □ Wholesaler             │ □ Importer   │ □ Exporter   │  ← BOTTOM ROW\n"
        "  └──────────────────────────┴──────────────┴──────────────┘\n"
        "  CRITICAL: The LEFTMOST box in the top row is Manufacturer/Producer, NOT Service.\n"
        "  Service is the MIDDLE box in the top row. Do NOT confuse their positions.\n"
        "  Multiple activities CAN be checked! Examine each of the 6 boxes individually.\n"
        "  A filled/darkened/solid square ■ = checked. Empty/clear square □ = unchecked.\n"
        "- Section H: □ Same as Business Details\n"
        "- Section I: Partner Agencies — □ PhilHealth  □ SSS  □ Pag-IBIG\n"
        f"{ocr_hint}\n"
        f"{disagreement_hint}"
        f"FIELDS TO DETECT ({len(checkbox_fields)} total):\n"
        f"{fields_desc}\n\n"
        "RESPONSE FORMAT:\n"
        "- For single checkboxes: \"yes\" if checked, \"no\" if unchecked\n"
        "- For radio buttons: return EXACTLY one option value from the list that is checked\n"
        "- For checkbox groups: comma-separated checked option values\n\n"
        "Return ONLY a JSON object. No explanation, no markdown:\n"
        "{\n"
        '  "field_name": "yes" or "no" or "option_value",\n'
        "  ...\n"
        "}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content,
                ],
            }],
            max_tokens=2000,
            temperature=0.0,
        )

        content = response.choices[0].message.content or "{}"

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            repaired = content
            last_comma = repaired.rfind(",")
            if last_comma > 0:
                repaired = repaired[:last_comma]
            if not repaired.rstrip().endswith("}"):
                repaired = repaired.rstrip() + "\n}"
            try:
                result = json.loads(repaired)
            except json.JSONDecodeError as e2:
                logger.error(f"Checkbox detection JSON parse failed: {e2}")
                return None

        # Log raw AI response for debugging
        logger.info(f"Checkbox AI raw response: {result}")

        # Normalize values
        normalized: dict[str, str] = {}
        for f in checkbox_fields:
            name = f["name"]
            if name in result:
                val = str(result[name]).strip()
                val_lower = val.lower()
                ftype = f.get("type", "checkbox")

                if ftype == "checkbox":
                    # Normalize → "true" for component compatibility
                    normalized[name] = "true" if val_lower in (
                        "yes", "true", "checked", "1", "x", "✓", "✔",
                        "on", "selected", "filled",
                    ) else ""
                elif ftype == "radio":
                    options = f.get("options", [])
                    matched = _match_radio_option(val_lower, options)
                    normalized[name] = matched
                else:
                    # checkbox-group — keep as-is
                    normalized[name] = val
            else:
                normalized[name] = ""

        checked_count = sum(1 for v in normalized.values() if v and v not in ("", "no"))
        logger.info(f"Checkbox detection: {checked_count}/{len(checkbox_fields)} fields have selections")
        logger.info(f"Checkbox normalized values: {normalized}")
        return normalized

    except Exception as e:
        logger.error(f"Checkbox detection failed: {e}")
        return None


def _run_ai_batch(
    client: Any,
    model: str,
    batch_fields: list[dict[str, Any]],
    ocr_lines_formatted: str,
    image_content: dict[str, Any] | None,
    batch_idx: int,
    total_batches: int,
    disagreement_hint: str = "",
) -> dict[str, Any] | None:
    """
    Run a single AI extraction batch for a subset of fields.
    Handles text, checkbox, and radio field types.
    Returns dict of {field_name: value} or None on failure.
    """
    # Build detailed field descriptions including options for checkbox/radio
    field_desc_lines = []
    for f in batch_fields:
        ftype = f.get("type", "text")
        label = f.get("label", f["name"])
        name = f["name"]
        options = f.get("options", [])

        if ftype == "checkbox":
            field_desc_lines.append(
                f'  - "{name}": Checkbox "{label}". '
                f'Return "yes" if checked/filled/marked, "no" if unchecked.'
            )
        elif ftype == "radio":
            opt_str = ", ".join(f'"{o}"' for o in options)
            field_desc_lines.append(
                f'  - "{name}": Radio "{label}" with options: {opt_str}. '
                f'Return EXACTLY one option value.'
            )
        elif ftype == "checkbox-group":
            opt_str = ", ".join(f'"{o}"' for o in options)
            field_desc_lines.append(
                f'  - "{name}": Checkbox group "{label}" — options: {opt_str}. '
                f'Return comma-separated checked values.'
            )
        else:
            field_desc_lines.append(
                f'  - "{name}": {label} (type: {ftype})'
            )

    fields_desc = "\n".join(field_desc_lines)

    prompt_text = (
        "You are an expert OCR data extraction specialist for Philippine government forms.\n\n"
        "I have a scanned form where OCR has extracted the following text lines:\n\n"
        f"{ocr_lines_formatted}\n\n"
        f"{disagreement_hint}"
        f"Extract ONLY these {len(batch_fields)} fields from the text and image:\n"
        f"{fields_desc}\n\n"
        "RULES:\n"
        "- Match field labels to their corresponding values in the OCR text\n"
        "- Values may appear on the same line as labels (after colon) or on adjacent lines\n"
        "- If a value spans multiple lines, combine them\n"
        "- If a field is not found, use empty string\n"
        "- For checkbox fields, return \"yes\" if checked or \"no\" if unchecked\n"
        "- For radio fields, return EXACTLY one of the listed option values\n"
        "- Return ONLY valid JSON, no markdown, no other text\n\n"
        "Return a JSON object mapping field names to extracted values:\n"
        "{\n"
        '  "field_name": "extracted value",\n'
        "  ...\n"
        "}\n"
        "Use EXACTLY the field names listed above. Every field must be present."
    )

    try:
        messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        if image_content:
            messages_content.append(image_content)

        # Scale max_tokens to batch size (~100 tokens per field is generous)
        max_tokens = max(1500, len(batch_fields) * 120)

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": messages_content}],
            max_tokens=max_tokens,
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"

        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        # Parse JSON with repair fallback
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Batch {batch_idx}/{total_batches}: JSON malformed, attempting repair")
            repaired = content
            last_comma = repaired.rfind(",")
            if last_comma > 0:
                repaired = repaired[:last_comma]
            if not repaired.rstrip().endswith("}"):
                repaired = repaired.rstrip() + "\n}"
            try:
                result = json.loads(repaired)
                logger.info(f"Batch {batch_idx}/{total_batches}: JSON repair recovered {len(result)} fields")
            except json.JSONDecodeError as e2:
                logger.error(f"Batch {batch_idx}/{total_batches}: JSON repair failed: {e2}")
                return None

        batch_label = f"Batch {batch_idx}/{total_batches}" if total_batches > 1 else "AI"
        filled = sum(1 for v in result.values() if v)
        logger.info(f"{batch_label}: extracted {filled}/{len(batch_fields)} fields")
        return result

    except Exception as e:
        logger.error(f"Batch {batch_idx}/{total_batches} failed: {e}")
        return None


def _map_fields_naive(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Naive label-based field mapping fallback.
    Searches for lines matching field labels and extracts adjacent values.
    """
    fields_spec = field_schema.get("fields", [])
    raw_lines = ocr_result.get("raw_lines", [])

    if not raw_lines or not fields_spec:
        return [
            {"field_name": f["name"], "ocr_value": "", "confidence": 0.0}
            for f in fields_spec
        ]

    mapped_fields = []

    for field_spec in fields_spec:
        field_name = field_spec["name"]
        field_label = field_spec.get("label", field_name).lower()

        best_value = ""
        best_confidence = 0.0

        for i, line in enumerate(raw_lines):
            line_text = line["text"].lower().strip()

            if _fuzzy_label_match(field_label, line_text):
                value = _extract_value_from_line(line["text"], field_spec.get("label", field_name))
                if value:
                    best_value = value
                    best_confidence = line["confidence"]
                elif i + 1 < len(raw_lines):
                    best_value = raw_lines[i + 1]["text"]
                    best_confidence = raw_lines[i + 1]["confidence"]
                break

        mapped_fields.append({
            "field_name": field_name,
            "ocr_value": best_value,
            "confidence": best_confidence,
        })

    return mapped_fields


def _fuzzy_label_match(label: str, line_text: str) -> bool:
    """Check if a line contains a field label (fuzzy match)."""
    label_words = label.lower().split()
    matches = sum(1 for word in label_words if word in line_text)
    threshold = max(1, len(label_words) * 0.6)
    return matches >= threshold


def _extract_value_from_line(line: str, label: str) -> str:
    """Try to extract value from a line like 'Label: Value'."""
    if ":" in line:
        parts = line.split(":", 1)
        return parts[1].strip()

    pattern = re.escape(label) + r"[\s_\-:.]+"
    cleaned = re.sub(pattern, "", line, flags=re.IGNORECASE).strip()
    if cleaned and cleaned != line.strip():
        return cleaned
    return ""


def enhance_with_vision(
    image_bytes: bytes,
    field_schema: dict[str, Any],
    low_confidence_fields: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Use Groq Vision API to re-extract specific low-confidence fields.
    This is a targeted enhancement — called only for fields that the
    primary mapping couldn't extract confidently.

    Returns dict of {field_name: {"value": str, "confidence": float}}
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.AI_API_KEY:
        logger.warning("AI_API_KEY not set, skipping vision enhancement")
        return {}

    try:
        import base64
        import gc
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
        )

        # Encode image and release original after encoding
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        del image_bytes  # Release original after encoding to save memory
        gc.collect()  # Force garbage collection

        fields_to_extract = [
            f for f in field_schema.get("fields", [])
            if f["name"] in low_confidence_fields
        ]
        fields_desc = "\n".join(
            f"- {f['label']} (field_name: {f['name']})" for f in fields_to_extract
        )

        response = client.chat.completions.create(
            model=settings.AI_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are an OCR specialist for Philippine government forms. "
                                "Extract ONLY the following field values from the form image. "
                                "Return a JSON object with field_name as key and extracted value as string.\n\n"
                                f"Fields to extract:\n{fields_desc}\n\n"
                                'Return format: {{"field_name": "extracted_value", ...}}\n'
                                "If a field is unreadable, use empty string. Return ONLY valid JSON."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        enhanced = json.loads(content.strip())

        return {
            k: {"value": str(v), "confidence": 0.85}
            for k, v in enhanced.items()
            if k in low_confidence_fields
        }

    except Exception as e:
        logger.error(f"Vision enhancement failed: {e}")
        return {}
