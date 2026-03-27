"""Positional OCR field mapping using bounding boxes and template regions.

Extract form fields by matching OCR bounding boxes to template field definition regions.
Uses spatial positioning (top, left, bottom, right) from OCR lines to map text to fields.
"""

import logging
from typing import Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """Bounding box in pixel coordinates."""
    top: float
    left: float
    bottom: float
    right: float
    
    @property
    def width(self) -> float:
        return self.right - self.left
    
    @property
    def height(self) -> float:
        return self.bottom - self.top
    
    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2
    
    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2
    
    def overlaps(self, other: 'BoundingBox', threshold: float = 0.5) -> bool:
        """Check if this box overlaps with another (threshold: 0.0-1.0 overlap ratio)."""
        # Calculate intersection area
        inter_left = max(self.left, other.left)
        inter_right = min(self.right, other.right)
        inter_top = max(self.top, other.top)
        inter_bottom = min(self.bottom, other.bottom)
        
        if inter_right <= inter_left or inter_bottom <= inter_top:
            return False  # No intersection
        
        intersection = (inter_right - inter_left) * (inter_bottom - inter_top)
        self_area = self.width * self.height
        overlap_ratio = intersection / self_area if self_area > 0 else 0
        
        return overlap_ratio >= threshold
    
    def contains_point(self, x: float, y: float) -> bool:
        """Check if point is inside box."""
        return self.left <= x <= self.right and self.top <= y <= self.bottom


def extract_bbox_from_paddle_ocr(ocr_line: dict[str, Any]) -> Optional[BoundingBox]:
    """Extract bounding box from PaddleOCR line result.
    
    PaddleOCR bbox format: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
    Convert to normalized top-left-bottom-right.
    """
    try:
        bbox = ocr_line.get('bbox', [])
        if not bbox or len(bbox) < 4:
            return None
        
        # Extract min/max coordinates
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        
        return BoundingBox(
            top=min(ys),
            left=min(xs),
            bottom=max(ys),
            right=max(xs),
        )
    except (IndexError, TypeError, KeyError):
        return None


def group_ocr_lines_by_column(raw_lines: list[dict[str, Any]], 
                               column_threshold: float = 50) -> list[list[dict[str, Any]]]:
    """Group OCR lines into columns by X-coordinate proximity.
    
    Args:
        raw_lines: List of OCR lines with bbox
        column_threshold: Horizontal pixel distance to consider same column
        
    Returns:
        List of column groups (each group is a list of lines)
    """
    if not raw_lines:
        return []
    
    # Sort by left coordinate
    sorted_lines = sorted(
        raw_lines,
        key=lambda l: extract_bbox_from_paddle_ocr(l).left if extract_bbox_from_paddle_ocr(l) else 0
    )
    
    columns = []
    current_column = []
    current_x = None
    
    for line in sorted_lines:
        bbox = extract_bbox_from_paddle_ocr(line)
        if not bbox:
            continue
        
        if current_x is None:
            current_x = bbox.left
            current_column = [line]
        elif abs(bbox.left - current_x) <= column_threshold:
            # Same column
            current_column.append(line)
        else:
            # New column
            if current_column:
                columns.append(current_column)
            current_x = bbox.left
            current_column = [line]
    
    if current_column:
        columns.append(current_column)
    
    return columns


def group_ocr_lines_by_row(raw_lines: list[dict[str, Any]], 
                            row_threshold: float = 15) -> list[list[dict[str, Any]]]:
    """Group OCR lines into rows by Y-coordinate proximity.
    
    Args:
        raw_lines: List of OCR lines with bbox
        row_threshold: Vertical pixel distance to consider same row
        
    Returns:
        List of row groups (each group is a list of lines)
    """
    if not raw_lines:
        return []
    
    # Sort by top coordinate
    sorted_lines = sorted(
        raw_lines,
        key=lambda l: extract_bbox_from_paddle_ocr(l).top if extract_bbox_from_paddle_ocr(l) else 0
    )
    
    rows = []
    current_row = []
    current_y = None
    
    for line in sorted_lines:
        bbox = extract_bbox_from_paddle_ocr(line)
        if not bbox:
            continue
        
        if current_y is None:
            current_y = bbox.top
            current_row = [line]
        elif abs(bbox.top - current_y) <= row_threshold:
            # Same row
            current_row.append(line)
        else:
            # New row
            if current_row:
                rows.append(current_row)
            current_y = bbox.top
            current_row = [line]
    
    if current_row:
        rows.append(current_row)
    
    return rows


def find_field_by_label_position(raw_lines: list[dict[str, Any]], 
                                  field_label: str,
                                  search_tolerance: float = 150) -> Optional[dict[str, Any]]:
    """Find field value by locating its label first, then gathering nearby OCR text.
    
    Strategy:
    1. Search for field label in OCR lines (exact or fuzzy match)
    2. Look for text to the right or below the label
    3. Group nearby text into field value
    
    Args:
        raw_lines: OCR extraction with bboxes
        field_label: Label text to search for (e.g., "Business Name:", "Owner:")
        search_tolerance: Pixel distance to search for value after label
        
    Returns:
        Dictionary with "value" and "confidence" or None if not found
    """
    # Search for label
    label_bbox = None
    for line in raw_lines:
        text = line.get('text', '').lower()
        if field_label.lower() in text:
            bbox = extract_bbox_from_paddle_ocr(line)
            if bbox:
                label_bbox = bbox
                break
    
    if not label_bbox:
        return None
    
    # Look for value text (to the right or below label)
    value_candidates = []
    for line in raw_lines:
        bbox = extract_bbox_from_paddle_ocr(line)
        if not bbox or bbox == label_bbox:
            continue
        
        # Check if line is to the right (same vertical level) or below
        is_right = bbox.left > label_bbox.right and abs(bbox.top - label_bbox.top) < 30
        is_below = bbox.top > label_bbox.top and abs(bbox.left - label_bbox.left) < 50
        
        if (is_right or is_below) and bbox.left - label_bbox.right < search_tolerance:
            value_candidates.append(line)
    
    if not value_candidates:
        return None
    
    # Combine text from candidates
    combined_text = " ".join(c.get('text', '') for c in value_candidates)
    avg_confidence = (sum(float(c.get('confidence', 0.5)) for c in value_candidates) 
                      / len(value_candidates))
    
    logger.info(f"[POSITIONAL-MAP] Found field '{field_label}': '{combined_text}' (conf={avg_confidence:.2f})")
    
    return {
        "value": combined_text.strip(),
        "confidence": avg_confidence,
    }


def map_fields_by_spatial_position(raw_lines: list[dict[str, Any]],
                                    field_schema: dict[str, Any]) -> dict[str, Any]:
    """Map OCR lines to form fields using positional/spatial analysis.
    
    Uses bounding box coordinates and field label proximity to extract values.
    
    Args:
        raw_lines: OCR extraction with bboxes
        field_schema: Template field definitions
        
    Returns:
        Dictionary mapping field_name → {value, confidence}
    """
    logger.info("[POSITIONAL-MAP] Starting positional field mapping")
    
    fields_def = field_schema.get('fields', [])
    extracted_fields = {}
    
    for field_def in fields_def:
        field_name = field_def.get('name')
        field_label = field_def.get('label', field_name)
        
        logger.debug(f"[POSITIONAL-MAP] Searching for field: {field_name} (label: {field_label})")
        
        # Try to find field by label proximity
        found = find_field_by_label_position(raw_lines, field_label)
        
        if found:
            extracted_fields[field_name] = found
        else:
            # Field not found - return empty with low confidence
            extracted_fields[field_name] = {
                "value": "",
                "confidence": 0.0,
            }
            logger.debug(f"[POSITIONAL-MAP] Field not found: {field_name}")
    
    found_count = sum(1 for f in extracted_fields.values() if f.get('value'))
    total_count = len(extracted_fields)
    logger.info(f"[POSITIONAL-MAP] Mapped {found_count}/{total_count} fields via positional analysis")
    
    return extracted_fields
