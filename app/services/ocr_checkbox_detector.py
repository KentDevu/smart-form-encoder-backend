"""
OCR Checkbox Detector — Extract checkbox states from form regions.

Identifies checkbox fields by layout + OCR patterns (✓, X, inked boxes, dots).
Used alongside region classification to extract boolean/multi-select fields
(Yes/No, activity types, civil status, etc.) with confidence scoring.

Example:
  regions = [
    Region(type=CHECKBOX_GROUP, name="Y/N Questions", bbox=..., lines=[...]),
    ...
  ]
  detected_checkboxes = detect_checkboxes(
    regions=regions,
    raw_lines=raw_lines,
    field_schema=field_schema
  )
  # detected_checkboxes[0] = DetectedCheckbox(
  #    name="answers_yes",
  #    state=CheckboxState.CHECKED,
  #    confidence=0.92,
  #    bbox=...,
  #    anchor_text="Yes"
  # )
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any
import re
import logging
import os
import json
from pathlib import Path

from app.services.ocr_region_classifier import Region, RegionType, BBox

logger = logging.getLogger(__name__)


class CheckboxState(Enum):
    """States a checkbox can be in."""
    CHECKED = "checked"       # ✓, X, filled, inked
    UNCHECKED = "unchecked"   # empty, blank
    UNCLEAR = "unclear"       # ambiguous, smudged


@dataclass
class DetectedCheckbox:
    """Detected checkbox field with state and confidence."""
    name: str                  # Field name (e.g., "activity_manufacturer")
    state: CheckboxState
    confidence: float          # 0.0-1.0 confidence in detection
    bbox: BBox                # Bounding box of checkbox region
    anchor_text: str          # Associated label text (e.g., "Manufacturer")
    ocr_patterns: dict[str, Any] | None = None  # Debug info


# ──────────────────────────────────────────────────────────────────────
# Checkbox Detection Configuration
# ──────────────────────────────────────────────────────────────────────

# Patterns indicating a checkbox IS CHECKED
CHECKED_PATTERNS = [
    r"✓",                  # Unicode checkmark
    r"✔",                  # Variant checkmark
    r"\bx\b",              # Single 'x' (case-insensitive)
    r"\bX\b",              # Single 'X'
    r"☑",                  # Checked box unicode
    r"\|\|",               # Double pipe (filled look)
    r"█",                  # Solid block
    r"■",                  # Filled square
    r"●",                  # Solid circle
    r"\[\s*[x✓X✔]\s*\]",   # [x], [✓], etc.
]

# Patterns indicating a checkbox is UNCHECKED
UNCHECKED_PATTERNS = [
    r"☐",                  # Empty box unicode
    r"○",                  # Empty circle
    r"\[\s*\]",            # Empty brackets []
    r"\(\s*\)",            # Empty parentheses ()
]

# Patterns indicating UNCLEAR state
UNCLEAR_PATTERNS = [
    r"~",                  # Tilde (partial/scribble)
    r"\.{2,}",             # Multiple dots (smudge)
    r"\?",                 # Question mark
]

# ──────────────────────────────────────────────────────────────────────
# DTI-Specific Field Mappings
# ──────────────────────────────────────────────────────────────────────

DTI_CHECKBOX_FIELD_NAMES = {
    # Activity types (Section F)
    "Manufacturer": "activity_manufacturer",
    "Producer": "activity_producer",
    "Service": "activity_service",
    "Retailer": "activity_retailer",
    "Wholesaler": "activity_wholesaler",
    "Importer": "activity_importer",
    "Exporter": "activity_exporter",
    
    # Civil status (Section C)
    "Single": "civil_status_single",
    "Married": "civil_status_married",
    "Widowed": "civil_status_widowed",
    "Legally Separated": "civil_status_legally_separated",
    
    # Gender (Section C)
    "Male": "gender_male",
    "Female": "gender_female",
    
    # Registration type (Section A)
    "NEW": "reg_type_new",
    "RENEWAL": "reg_type_renewal",
    
    # TIN status (Section B)
    "With TIN": "tin_status_with_tin",
    "Without TIN": "tin_status_without_tin",
}


def _save_checkbox_debug_info(
    detected_checkboxes: list[DetectedCheckbox],
    image_path: str | None = None
) -> None:
    """
    Save debug information about detected checkboxes to JSON file.
    
    Args:
        detected_checkboxes: List of detected checkboxes
        image_path: Directory path for debug output (e.g., "/path/to/backend/debug_ocr/{form_id}")
    """
    if not image_path:
        logger.debug("[CHECKBOX_DEBUG] No image_path provided, skipping debug save")
        return
    
    try:
        # Create debug directory if it doesn't exist
        debug_dir = Path(image_path)
        logger.debug(f"[CHECKBOX_DEBUG] Creating debug directory: {debug_dir}")
        debug_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare debug data
        debug_data = {
            "total_checkboxes_detected": len(detected_checkboxes),
            "checkboxes": [
                {
                    "name": cb.name,
                    "state": cb.state.value,
                    "confidence": round(cb.confidence, 3),
                    "anchor_text": cb.anchor_text,
                    "bbox": {
                        "top": cb.bbox.top,
                        "left": cb.bbox.left,
                        "bottom": cb.bbox.bottom,
                        "right": cb.bbox.right,
                        "width": cb.bbox.width,
                        "height": cb.bbox.height,
                    } if cb.bbox else None,
                }
                for cb in detected_checkboxes
            ]
        }
        
        # Save to JSON
        debug_file = debug_dir / "checkbox_detection.json"
        with open(debug_file, "w") as f:
            json.dump(debug_data, f, indent=2)
        
        logger.info(f"[CHECKBOX_DEBUG] Saved detection report to {debug_file}")
    except Exception as e:
        logger.warning(f"[CHECKBOX_DEBUG] Failed to save debug info to {image_path}: {e}", exc_info=True)


def detect_checkboxes(
    regions: list[Region],
    raw_lines: list[dict[str, Any]],
    field_schema: dict[str, Any] | None = None,
    image_path: str | None = None,
) -> list[DetectedCheckbox]:
    """
    Detect checkboxes and their states from form regions.

    Args:
        regions: Classified regions from ocr_region_classifier
        raw_lines: Raw OCR output (text + confidence + bbox)
        field_schema: Optional field schema for field name mapping (DTI-specific)
        image_path: Optional path to source image for debug visualization

    Returns:
        List of DetectedCheckbox objects with states and confidence
    """
    detected_checkboxes = []
    
    # Find checkbox group regions
    checkbox_regions = [r for r in regions if r.type == RegionType.CHECKBOX_GROUP]
    
    if not checkbox_regions:
        logger.debug("No checkbox regions detected")
        return []
    
    for region in checkbox_regions:
        logger.debug(f"Processing checkbox region: {region.name}")
        
        # Extract checkboxes from this region's lines
        for line in region.lines:
            text = line.get("text", "").strip()
            if not text:
                continue
            
            # Detect checkbox state
            state, state_confidence = detect_checkbox_state(text)
            
            # Map to field name (DTI-specific defaults to text as fallback)
            field_name = DTI_CHECKBOX_FIELD_NAMES.get(text, text.lower().replace(" ", "_"))
            
            # Convert bbox from PaddleOCR format (nested list) or PIL format (flat list)
            bbox_raw = line.get("bbox", [0, 0, 100, 100])
            try:
                if bbox_raw and isinstance(bbox_raw[0], (list, tuple)) and len(bbox_raw) == 4:
                    # PaddleOCR format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    xs = [float(p[0]) for p in bbox_raw]
                    ys = [float(p[1]) for p in bbox_raw]
                    bbox = BBox(
                        top=min(ys),
                        left=min(xs),
                        bottom=max(ys),
                        right=max(xs),
                    )
                else:
                    # PIL format: [left, top, right, bottom]
                    bbox = BBox(
                        top=float(bbox_raw[1]),
                        left=float(bbox_raw[0]),
                        bottom=float(bbox_raw[3]),
                        right=float(bbox_raw[2]),
                    )
            except (TypeError, IndexError, ValueError):
                # Fallback to default bbox if conversion fails
                bbox = BBox(top=0, left=0, bottom=100, right=100)
            
            # Create detected checkbox record
            checkbox = DetectedCheckbox(
                name=field_name,
                state=state,
                confidence=state_confidence * line.get("confidence", 0.9),  # Combine OCR + pattern confidence
                bbox=bbox,
                anchor_text=text,
                ocr_patterns={"detected_state": state.value, "text": text},
            )
            detected_checkboxes.append(checkbox)
    
    logger.info(f"Detected {len(detected_checkboxes)} checkboxes from {len(checkbox_regions)} regions")
    
    # Save debug information if image_path provided
    _save_checkbox_debug_info(detected_checkboxes, image_path)
    
    return detected_checkboxes


def detect_checkbox_state(text: str, context_confidence: float = 0.5) -> tuple[CheckboxState, float]:
    """
    Determine checkbox state from OCR text.

    Args:
        text: OCR-extracted text from checkbox area
        context_confidence: Base confidence (can be adjusted by callers)

    Returns:
        Tuple of (CheckboxState, confidence_score 0.0-1.0)
    """
    if not text:
        return CheckboxState.UNCLEAR, 0.3
    
    # Compile patterns if not cached
    checked_pattern = _compile_pattern(CHECKED_PATTERNS)
    unchecked_pattern = _compile_pattern(UNCHECKED_PATTERNS)
    unclear_pattern = _compile_pattern(UNCLEAR_PATTERNS)
    
    # Check each pattern type
    if unclear_pattern.search(text):
        # Unclear takes precedence (highest ambiguity)
        return CheckboxState.UNCLEAR, 0.5
    
    if checked_pattern.search(text):
        # Checked detected → high confidence (0.8-0.95)
        confidence = 0.88 if len(text) > 10 else 0.92  # Single char check is clearer
        return CheckboxState.CHECKED, confidence
    
    if unchecked_pattern.search(text):
        # Empty pattern found → medium-high confidence
        return CheckboxState.UNCHECKED, 0.85
    
    # Default: UNCHECKED (forms typically have empty boxes by default)
    # But lower confidence if completely unclear
    if len(text) > 2 and not any(c.isalnum() for c in text):
        # Non-alphanumeric text (symbols, etc.) suggests empty box
        return CheckboxState.UNCHECKED, 0.65
    
    # Alphanumeric or label text: treat as label (unchecked)
    return CheckboxState.UNCHECKED, 0.70


def _compile_pattern(patterns: list[str]) -> re.Pattern:
    """
    Compile list of regex patterns into single pattern.

    Args:
        patterns: List of regex pattern strings

    Returns:
        Compiled regex pattern that matches any of the patterns
    """
    combined = "|".join(f"({p})" for p in patterns)
    return re.compile(combined, re.IGNORECASE | re.UNICODE)


def validate_checkbox_extraction(
    extracted_fields: dict[str, Any],
    detected_checkboxes: list[DetectedCheckbox],
) -> dict[str, Any]:
    """
    Validate/adjust checkbox field values based on detected checkboxes.

    Used as post-processing after Groq extraction to ensure checkbox fields
    are set correctly based on pattern detection.

    Args:
        extracted_fields: Fields extracted by Groq (may be empty for checkboxes)
        detected_checkboxes: Detected checkboxes with confirmed states

    Returns:
        Updated extracted_fields with checkbox values filled in
    """
    if not detected_checkboxes:
        return extracted_fields
    
    updated = extracted_fields.copy()
    
    for checkbox in detected_checkboxes:
        if checkbox.confidence >= 0.75:  # High confidence threshold
            # Set field value based on checkbox state
            if checkbox.state == CheckboxState.CHECKED:
                updated[checkbox.name] = "true"
            elif checkbox.state == CheckboxState.UNCHECKED:
                updated[checkbox.name] = ""
            # UNCLEAR state: leave as-is (don't override lower-confidence extraction)
    
    return updated


if __name__ == "__main__":
    # Quick test
    test_text_samples = [
        ("✓", CheckboxState.CHECKED),
        ("X", CheckboxState.CHECKED),
        ("☐", CheckboxState.UNCHECKED),
        ("[]", CheckboxState.UNCHECKED),
        ("~", CheckboxState.UNCLEAR),
        ("??", CheckboxState.UNCLEAR),
        ("Manufacturer", CheckboxState.UNCHECKED),
        ("", CheckboxState.UNCLEAR),
    ]
    
    for text, expected_state in test_text_samples:
        state, conf = detect_checkbox_state(text)
        status = "✓" if state == expected_state else "✗"
        print(f"{status} '{text}' → {state.value} (conf={conf:.2f})")
