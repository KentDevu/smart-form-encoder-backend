"""Pattern-based field extraction from raw OCR lines (Phase D - Enhancement).

This module searches raw OCR lines for field values using regex patterns derived from validators.
Used to fill gaps left by AI extraction by looking for structured data patterns (dates, phones, 
amounts, etc.) within the raw OCR text.

Strategy: Option A - Pattern Extraction
- For each empty field, search raw OCR lines for matching patterns
- If patterns found, extract and validate values
- Prioritize high-confidence patterns (dates, phones)
- Fallback to lower-confidence patterns (amounts, addresses)
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_fields_from_ocr_lines(
    ocr_lines: list[str],
    field_schema: dict[str, Any],
    existing_fields: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Search raw OCR lines for field values using pattern matching.
    
    For each field NOT yet extracted (empty or not present), search OCR lines for
    patterns matching the field type. Extracts values with confidence scoring.
    
    Args:
        ocr_lines: List of raw OCR text lines from template-based extraction
                   Example: ["JUAN DELA CRUZ", "15/06/2020", "09171234567", ...]
        field_schema: Template field definitions 
                      {"fields": [{"name": "first_name", "type": "text"}, ...]}
        existing_fields: Currently extracted fields
                         {"first_name": {"value": "JUAN", "confidence": 0.7}, ...}
    
    Returns:
        Updated fields dict with newly extracted values for empty fields
        
    Strategy:
    1. Identify empty fields (not extracted yet)
    2. For each empty field, determine field type from schema
    3. Search OCR lines for patterns matching that type
    4. Extract first matching value with confidence scoring
    5. Return updated fields dict (new fields added, existing preserved)
    """
    if not ocr_lines or not field_schema:
        return existing_fields
    
    # Combine all OCR lines into single searchable text
    ocr_text = "\n".join(ocr_lines)
    
    # Build field type map from schema
    field_definitions = field_schema.get("fields", [])
    field_types = {
        f["name"]: {
            "type": f.get("type", "text"),
            "required": f.get("required", False),
            "label": f.get("label", ""),
        }
        for f in field_definitions
        if "name" in f
    }
    
    # Pattern extractors by field type
    extractors = {
        "date": _extract_date_from_ocr,
        "phone": _extract_phone_from_ocr,
        "checkbox": _extract_checkbox_from_ocr,
        "amount": _extract_amount_from_ocr,
    }
    
    updated_fields = dict(existing_fields)  # Copy to avoid mutation
    extraction_stats = {
        "searched": 0,
        "found": 0,
        "skipped": 0,
        "empty_lines": 0,
    }
    
    # Search for missing fields
    for field_name, field_def in field_types.items():
        # Skip if field already extracted
        if field_name in updated_fields:
            existing_value = updated_fields[field_name].get("ocr_value", "").strip()
            if existing_value:
                extraction_stats["skipped"] += 1
                logger.debug(f"[PATTERN-EXTRACT] Field '{field_name}' already filled, skipping")
                continue
        
        field_type = field_def["type"]
        extraction_stats["searched"] += 1
        
        # Look up extractor for this field type
        if field_type not in extractors:
            logger.debug(f"[PATTERN-EXTRACT] No extractor for type '{field_type}', skipping field '{field_name}'")
            continue
        
        try:
            extractor_fn = extractors[field_type]
            extracted_value, confidence = extractor_fn(ocr_text, ocr_lines)
            
            if extracted_value:
                updated_fields[field_name] = {
                    "field_name": field_name,
                    "ocr_value": extracted_value,
                    "confidence": confidence,
                }
                extraction_stats["found"] += 1
                logger.info(
                    f"[PATTERN-EXTRACT] Found {field_type.upper()} for '{field_name}': "
                    f"'{extracted_value}' (conf={confidence:.2f})"
                )
        except Exception as e:
            logger.warning(
                f"[PATTERN-EXTRACT] Pattern extraction failed for '{field_name}': {e}"
            )
    
    logger.info(
        f"[PATTERN-EXTRACT] Complete: searched {extraction_stats['searched']}, "
        f"found {extraction_stats['found']}, skipped {extraction_stats['skipped']}"
    )
    
    return updated_fields


def _extract_date_from_ocr(
    ocr_text: str,
    ocr_lines: list[str],
) -> tuple[str, float]:
    """
    Search OCR text for date patterns.
    
    Matches: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, Month DD, YYYY, etc.
    Returns: (normalized_date, confidence)
    """
    # Date patterns (in priority order)
    patterns = [
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",  # DD/MM/YYYY or YYYY/MM/DD
        r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",  # YYYY-MM-DD
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2}),?\s+(\d{4})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, ocr_text, re.IGNORECASE)
        if match:
            return str(match.group(0)), 0.50  # Medium confidence for pattern-extracted dates
    
    return "", 0.0


def _extract_phone_from_ocr(
    ocr_text: str,
    ocr_lines: list[str],
) -> tuple[str, float]:
    """
    Search OCR text for Philippine phone number patterns.
    
    Matches: 09xxxxxxxxx, +639xxxxxxxxx, 639xxxxxxxxx, etc.
    Returns: (normalized_phone, confidence)
    """
    # Phone patterns (PH mobile formats)
    patterns = [
        r"(\+63|63)?9[0-2]\d[\s-]?\d{3}[\s-]?\d{4}",  # With separators
        r"(\+63|63)?9[0-2]\d{8}",  # +639xxxxxxxxx or 639xxxxxxxxx or 09xxxxxxxxx
        r"0(9[0-2]\d{8})",  # 09xxxxxxxxx
    ]
    
    for pattern in patterns:
        match = re.search(pattern, ocr_text)
        if match:
            phone_str = match.group(0)
            # Normalize to +639xxxxxxxxx format
            phone_clean = re.sub(r"[^\d+]", "", phone_str)
            if phone_clean.startswith("+63"):
                normalized = phone_clean
            elif phone_clean.startswith("63"):
                normalized = f"+{phone_clean}"
            elif phone_clean.startswith("9"):
                normalized = f"+63{phone_clean}"
            else:
                normalized = f"+639{phone_clean[-10:]}"
            
            return normalized, 0.55  # Medium-high confidence for phone patterns
    
    return "", 0.0


def _extract_checkbox_from_ocr(
    ocr_text: str,
    ocr_lines: list[str],
) -> tuple[str, float]:
    """
    Search OCR text for checkbox patterns (yes/no indicators).
    
    Matches: ✓, ✔, checked, YES, NO, etc.
    Returns: ("Yes" or "No" or "", confidence)
    """
    # Yes patterns (word boundaries to avoid false matches)
    # Don't match single 'x' as it appears in words like "checkbox"
    yes_patterns = [r"✓", r"✔", r"\byes\b", r"\bchecked\b", r"\b[Xx][\s•·*]"]
    for pattern in yes_patterns:
        if re.search(pattern, ocr_text, re.IGNORECASE):
            return "Yes", 0.45  # Lower confidence for checkbox patterns
    
    # No patterns (word boundaries to avoid false positives like "No data")
    no_patterns = [r"☐", r"☒", r"\bno\b\s", r"\bno\b$", r"\bunchecked\b"]
    for pattern in no_patterns:
        if re.search(pattern, ocr_text, re.IGNORECASE | re.MULTILINE):
            return "No", 0.45
    
    return "", 0.0


def _extract_amount_from_ocr(
    ocr_text: str,
    ocr_lines: list[str],
) -> tuple[str, float]:
    """
    Search OCR text for currency amount patterns.
    
    Matches: X,XXX.XX, ₱5000.50, $1000, etc.
    Returns: (normalized_amount, confidence)
    """
    # Amount patterns - match currency followed by number with or without decimals
    # Matches: ₱5000.50, P5,000, $10000, etc.
    patterns = [
        r"[₱P$€£¥]\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)",  # Currency + amount
        r"(\d+(?:,\d{3})*(?:\.\d{1,2})?)",  # Plain amount
    ]
    
    for pattern in patterns:
        match = re.search(pattern, ocr_text)
        if match:
            # Get the captured group
            amount_str = match.group(1)
            # Clean and normalize
            amount_clean = re.sub(r"[^0-9.,]", "", amount_str)
            try:
                amount_float = float(amount_clean.replace(",", ""))
                formatted = f"{amount_float:,.2f}"
                return formatted, 0.40  # Lower confidence for amount extraction
            except ValueError:
                continue
    
    return "", 0.0
