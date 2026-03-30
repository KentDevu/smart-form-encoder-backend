"""
Preprocess OCR data and enrich template hints for Groq extraction.

Input: raw OCR lines (from PaddleOCR) + field schema (from template)
Output: Enriched template with anchors + patterns + spatial context
"""

import re
import logging
from typing import Any, Optional
from dataclasses import dataclass, field as dataclass_field

logger = logging.getLogger(__name__)


@dataclass
class AnchorMatch:
    """Result of searching for an anchor label in OCR text."""
    found: bool
    line_index: Optional[int] = None
    anchor_text: Optional[str] = None
    anchor_confidence: Optional[float] = None
    context_lines: list[str] = dataclass_field(default_factory=list)
    context_confidence: Optional[float] = None
    reading_order: Optional[int] = None


def find_anchor_in_raw_lines(
    anchor_label: str,
    raw_lines: list[dict[str, Any]],
    threshold: float = 0.8
) -> AnchorMatch:
    """
    Search raw OCR lines for anchor label (fuzzy match).
    
    Args:
        anchor_label: e.g., "BUSINESS NAME", "PROPRIETOR"
        raw_lines: [{"text": "...", "confidence": 0.9, "bbox": [...]}]
        threshold: OCR confidence threshold for anchor match
    
    Returns:
        AnchorMatch with found=True/False and details
    """
    anchor_upper = anchor_label.upper().strip()
    
    # Exact match first
    for i, line in enumerate(raw_lines):
        text = line.get("text", "").upper().strip()
        conf = float(line.get("confidence", 0.0))
        
        if text == anchor_upper and conf >= threshold:
            # Extract next 2 lines as context
            context_lines = []
            context_confs = []
            for j in range(i + 1, min(i + 3, len(raw_lines))):
                next_line = raw_lines[j]
                context_lines.append(next_line.get("text", ""))
                context_confs.append(float(next_line.get("confidence", 0.5)))
            
            avg_context_conf = sum(context_confs) / len(context_confs) if context_confs else 0.0
            
            return AnchorMatch(
                found=True,
                line_index=i,
                anchor_text=text,
                anchor_confidence=conf,
                context_lines=context_lines,
                context_confidence=avg_context_conf,
                reading_order=i
            )
    
    # Fuzzy match (substring containment)
    for i, line in enumerate(raw_lines):
        text = line.get("text", "").upper().strip()
        conf = float(line.get("confidence", 0.0))
        
        # Check if anchor is substring (handles "PROPRIETOR" matching "OWNER / PROPRIETOR")
        if anchor_upper in text and conf >= threshold * 0.9:  # Slightly lower threshold
            context_lines = []
            context_confs = []
            for j in range(i + 1, min(i + 3, len(raw_lines))):
                next_line = raw_lines[j]
                context_lines.append(next_line.get("text", ""))
                context_confs.append(float(next_line.get("confidence", 0.5)))
            
            avg_context_conf = sum(context_confs) / len(context_confs) if context_confs else 0.0
            
            logger.debug(f"Anchor fuzzy match: {anchor_upper} in {text} (conf={conf:.2f})")
            
            return AnchorMatch(
                found=True,
                line_index=i,
                anchor_text=text,
                anchor_confidence=conf * 0.9,  # Reduce confidence for fuzzy match
                context_lines=context_lines,
                context_confidence=avg_context_conf,
                reading_order=i
            )
    
    # No match found
    return AnchorMatch(found=False)


def extract_pattern_matches(
    raw_lines: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """
    Search all OCR lines for common structured patterns.
    
    Returns:
    {
        "phone": ["09175551234", "+639175551234"],
        "date": ["15/06/2020", "2020-06-15"],
        "email": ["juan@example.com"],
        "tin": ["123456789"],
        "amount": ["PHP 100,000", "100000"],
    }
    """
    combined_text = "\n".join(line.get("text", "") for line in raw_lines)
    
    patterns = {
        "phone": [
            r"(?:\+63|63)?9[0-2]\d[\s\-]?\d{3}[\s\-]?\d{4}",  # +639xx or 09xx format
            r"0(9[0-2]\d{8})",  # 09xxxxxxxxx
        ],
        "date": [
            r"\d{1,2}[/-]\d{1,2}[/-]\d{4}",  # DD/MM/YYYY
            r"\d{4}[/-]\d{1,2}[/-]\d{1,2}",  # YYYY-MM-DD
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}",  # Month DD, YYYY
        ],
        "email": [
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        ],
        "tin": [
            r"\b\d{9}\b",  # 9-digit TIN (isolated)
        ],
        "amount": [
            r"PHP\s*[\d,]+(?:\.\d{2})?",  # PHP format
            r"₱[\d,]+(?:\.\d{2})?",  # Peso symbol
        ],
    }
    
    matches = {}
    for pattern_type, pattern_list in patterns.items():
        matches[pattern_type] = []
        for pattern in pattern_list:
            found = re.findall(pattern, combined_text, re.IGNORECASE)
            matches[pattern_type].extend(found)
        # Remove duplicates, keep order
        matches[pattern_type] = list(dict.fromkeys(matches[pattern_type]))
    
    logger.info(f"Pattern extraction: {sum(len(v) for v in matches.values())} matches found")
    return matches


def build_reading_order(raw_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sort OCR lines into reading order (top-to-bottom, left-to-right).
    
    Returns list of {line_no, text, y, x} sorted by Y then X.
    """
    lines_with_pos = []
    for i, line in enumerate(raw_lines):
        bbox = line.get("bbox", [[0, 0], [0, 0], [0, 0], [0, 0]])
        # bbox format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        try:
            y_coords = [p[1] for p in bbox]
            x_coords = [p[0] for p in bbox]
            y = min(y_coords)  # Top of bounding box
            x = min(x_coords)  # Left of bounding box
        except (IndexError, TypeError):
            y, x = 0, 0
        
        lines_with_pos.append({
            "line_no": i,
            "text": line.get("text", ""),
            "y": y,
            "x": x,
            "confidence": float(line.get("confidence", 0.5))
        })
    
    # Sort by Y (top-to-bottom), then X (left-to-right)
    sorted_lines = sorted(lines_with_pos, key=lambda l: (l["y"], l["x"]))
    return sorted_lines


def enrich_template_with_preprocessing_hints(
    raw_lines: list[dict[str, Any]],
    field_schema: dict[str, Any]
) -> dict[str, Any]:
    """
    Main entry point: enrich template field definitions with OCR preprocessing hints.
    
    Args:
        raw_lines: [{"text": "...", "confidence": 0.9, "bbox": [...]}]
        field_schema: {"fields": [{"name": "...", "label": "...", ...}]}
    
    Returns:
        Mutated field_schema with "preprocessed" key in each field
    """
    from copy import deepcopy
    enriched = deepcopy(field_schema)
    
    # Extract pattern matches globally
    pattern_matches = extract_pattern_matches(raw_lines)
    enriched["pattern_matches"] = pattern_matches
    
    # Build reading order
    reading_order = build_reading_order(raw_lines)
    enriched["reading_order"] = reading_order
    
    # For each field, find anchor and extract context
    fields = enriched.get("fields", [])
    for field in fields:
        field_name = field.get("name", "")
        extraction_hints = field.get("extraction", {})
        anchor_label = extraction_hints.get("anchor_label")
        
        if anchor_label:
            anchor_match = find_anchor_in_raw_lines(anchor_label, raw_lines)
            field["preprocessed"] = {
                "anchor_found": anchor_match.found,
                "anchor_text": anchor_match.anchor_text,
                "anchor_confidence": anchor_match.anchor_confidence,
                "context_lines": anchor_match.context_lines,
                "context_confidence": anchor_match.context_confidence,
                "anchor_line_index": anchor_match.line_index,
                "reading_order": anchor_match.reading_order,
            }
            logger.debug(f"Field {field_name}: anchor={anchor_match.found}")
        else:
            field["preprocessed"] = {
                "anchor_found": False,
                "context_lines": [],
            }
    
    logger.info(
        f"Template enriched: {len(fields)} fields, "
        f"{sum(1 for f in fields if f.get('preprocessed', {}).get('anchor_found'))} anchors found"
    )
    
    return enriched
