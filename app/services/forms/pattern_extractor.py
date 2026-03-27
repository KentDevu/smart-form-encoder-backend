"""Pattern-based field extractor for missed OCR-AI fields (Option A).

Searches raw OCR lines for patterns matching validator types (date, phone, etc.).
Used to fill empty fields that Groq AI failed to extract.

Strategy:
1. For each empty field in the form
2. Check if field type has a pattern (date, phone, checkbox, amount)
3. Search raw OCR text for pattern matches
4. If found, extract and normalize using field validators
5. Store with "pattern_extracted" confidence flag
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Pattern definitions for each field type
PATTERNS = {
    "date": [
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b",  # DD/MM/YYYY or MM/DD/YYYY
        r"\b(19|20)\d{2}[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b",  # YYYY-MM-DD
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})\b",  # Month DD, YYYY
    ],
    "phone": [
        r"\+?63\d{2}\s*[-.\s]?\d{3,4}\s*[-.\s]?\d{3,4}",  # +639XX XXX XXXX
        r"\b09\d{2}\s*[-.\s]?\d{3,4}\s*[-.\s]?\d{3,4}\b",  # 09XX XXX XXXX
        r"\b[9]\d{9}\b",  # 9XXXXXXXXX (without country code)
    ],
    "amount": [
        r"₱?\s*(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)",  # ₱5,000.50 or variations
        r"P\s*(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)",  # P5,000.50
        r"\$\s*(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)",  # $5,000.50
    ],
    "checkbox": [
        r"[✓✔☑☒✅]\s*(?=\s|$)",  # Checkmarks
        r"\byes\b|\bno\b|\btrue\b|\bfalse\b",  # Yes/No/True/False
    ],
}

PATTERN_NAMES = {
    "date": "date_pattern",
    "phone": "phone_pattern",
    "amount": "amount_pattern",
    "checkbox": "checkbox_pattern",
}


def extract_patterns_from_ocr(
    ocr_lines: list[str],
    empty_fields: list[dict[str, Any]],
    field_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Search raw OCR lines for missing fields using pattern matching.
    
    Args:
        ocr_lines: Raw OCR text lines from PaddleOCR
        empty_fields: Fields with empty ocr_value that need extraction
        field_schema: Template field schema with type definitions
        
    Returns:
        List of newly extracted fields (with pattern_extracted flag)
        
    Example:
        ocr_lines = ["15 June 2020", "Mobile: 09171234567", "Amount: ₱50,000"]
        empty_fields = [
            {"field_name": "registration_date", "ocr_value": ""},
        ]
        field_schema = {
            "fields": [
                {"name": "registration_date", "type": "date"},
            ]
        }
        result = extract_patterns_from_ocr(ocr_lines, empty_fields, field_schema)
        # Returns:
        # [
        #     {
        #         "field_name": "registration_date",
        #         "ocr_value": "15 June 2020",
        #         "confidence": 0.65,
        #         "pattern_extracted": True,
        #     }
        # ]
    """
    from app.services.forms.field_validators import (
        validate_date,
        validate_phone,
        validate_amount,
        validate_checkbox,
    )

    # Build field type map
    field_defs = field_schema.get("fields", [])
    field_types = {
        f["name"]: f.get("type", "text")
        for f in field_defs
        if "name" in f
    }

    # Combine all OCR lines into searchable text
    ocr_text = "\n".join(ocr_lines)

    extracted = []
    validator_map = {
        "date": validate_date,
        "phone": validate_phone,
        "amount": validate_amount,
        "checkbox": validate_checkbox,
    }

    for field in empty_fields:
        field_name = field.get("field_name", "")
        field_type = field_types.get(field_name, "text")

        # Skip if no pattern available for this type
        if field_type not in PATTERNS:
            logger.debug(f"[PATTERN-EXTRACT] No pattern for type '{field_type}' on field '{field_name}'")
            continue

        # Search for pattern matches
        patterns = PATTERNS[field_type]
        found_value = None
        found_match = None

        for pattern in patterns:
            matches = re.finditer(pattern, ocr_text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                found_value = match.group(0)
                found_match = match
                break

            if found_value:
                break

        if not found_value:
            logger.debug(f"[PATTERN-EXTRACT] No pattern match for '{field_name}' ({field_type})")
            continue

        # Validate and normalize using field validators
        try:
            validator = validator_map.get(field_type)
            if validator:
                normalized, conf_adj = validator(found_value, 0.5)  # Base confidence 0.5 for pattern
                if normalized:  # Only use if validator returned a value
                    confidence = max(0.0, min(1.0, 0.5 + conf_adj))
                    extracted.append({
                        "field_name": field_name,
                        "ocr_value": normalized,
                        "confidence": confidence,
                        "pattern_extracted": True,
                    })
                    logger.info(
                        f"[PATTERN-EXTRACT] Extracted '{field_name}': '{found_value}' → '{normalized}' "
                        f"(confidence: {confidence:.2f})"
                    )
            else:
                # No validator for this type, use as-is with reduced confidence
                extracted.append({
                    "field_name": field_name,
                    "ocr_value": found_value,
                    "confidence": 0.45,  # Lower confidence for unvalidated patterns
                    "pattern_extracted": True,
                })
                logger.info(
                    f"[PATTERN-EXTRACT] Extracted '{field_name}' (no validator): '{found_value}' "
                    f"(confidence: 0.45)"
                )

        except Exception as e:
            logger.warning(
                f"[PATTERN-EXTRACT] Validation failed for '{field_name}': {e}"
            )
            # Continue to next field

    logger.info(
        f"[PATTERN-EXTRACT] Pattern extraction complete: "
        f"found {len(extracted)} fields from {len(empty_fields)} empty"
    )

    return extracted


def should_enable_pattern_extraction() -> bool:
    """Check if pattern extraction is enabled via config."""
    from app.config import get_settings
    
    settings = get_settings()
    return getattr(settings, "ENABLE_PATTERN_EXTRACTION", True)
