"""
OCR Region Classifier — Parse OCR output into logical form sections.

Classifies OCR lines into regions (checkbox groups, text fields, headers, section titles)
to provide spatial context for Groq field extraction. Enables better field mapping by
telling Groq "this region contains business address fields" vs raw line numbers.

Example:
  raw_lines = [
    {"text": "A. TYPE OF DTI REGISTRATION", "confidence": 0.98, "bbox": [10, 100, 400, 110]},
    {"text": "1.", "confidence": 0.99, "bbox": [30, 120, 45, 130]},
    {"text": "NEW", "confidence": 0.97, "bbox": [60, 120, 95, 130]},
    ...
  ]
  regions = classify_regions(raw_lines)
  # regions[0] = Region(type=SECTION_TITLE, name="A. TYPE OF DTI REGISTRATION", ...)
  # regions[1] = Region(type=CHECKBOX_GROUP, name="Registration Type", ...)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Region Classification Confidence Scores (heuristic-based, tunable)
# ──────────────────────────────────────────────────────────────────────
REGION_CONFIDENCE = {
    "section_title": 0.85,
    "checkbox_group": 0.70,
    "text_field": 0.75,
    "header": 0.80,
    "footer": 0.75,
    "unknown": 0.50,
}


class RegionType(Enum):
    """Classification of OCR region types in form."""
    SECTION_TITLE = "section_title"  # Bold section headers (A., B., C., etc.)
    CHECKBOX_GROUP = "checkbox_group"  # Group of checkboxes (Y/N, activity types, etc.)
    TEXT_FIELD = "text_field"  # Single/multi-line text input area
    HEADER = "header"  # Form header/title area
    FOOTER = "footer"  # Form footer/instructions area
    UNKNOWN = "unknown"  # Unclassified


@dataclass
class BBox:
    """Bounding box: (top, left, bottom, right) in pixels."""
    top: float
    left: float
    bottom: float
    right: float

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    def overlaps_y(self, other: "BBox", tolerance_px: int = 20) -> bool:
        """Check if two boxes overlap vertically (±tolerance)."""
        return abs(self.center_y - other.center_y) <= tolerance_px

    def overlaps_x(self, other: "BBox", tolerance_px: int = 50) -> bool:
        """Check if two boxes overlap horizontally (±tolerance)."""
        return not (self.right < other.left or self.left > other.right)


@dataclass
class Region:
    """Classified region in form."""
    type: RegionType
    name: str
    bbox: BBox
    lines: list[dict[str, Any]] = field(default_factory=list)  # OCR lines in this region
    confidence: float = 0.8  # Region classification confidence (heuristic)

    def __post_init__(self) -> None:
        """Validate region after initialization. Logs warning if region is empty."""
        if not self.lines:
            logger.debug(f"Region {self.name} has no lines (type={self.type})")


def classify_regions(raw_lines: list[dict[str, Any]]) -> list[Region]:
    """
    Parse OCR lines into logical form regions.

    Args:
        raw_lines: List of OCR line outputs, each with:
          {
            "text": "extracted text",
            "confidence": 0.95,
            "bbox": [left, top, right, bottom]  # x1, y1, x2, y2 format
          }

    Returns:
        List of Region objects, ordered top-to-bottom
    """
    if not raw_lines:
        logger.debug("No OCR lines provided; returning empty regions")
        return []

    # Convert bbox format from multiple formats to our [top, left, bottom, right]
    # Supports: PaddleOCR nested [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] and PIL flat [x1,y1,x2,y2]
    lines_with_bbox = []
    for line in raw_lines:
        try:
            bbox_raw = line.get("bbox", [0, 0, 100, 100])
            
            # Detect format:
            # - PaddleOCR: nested list of 4 coordinate pairs [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            # - PIL: flat list [x1, y1, x2, y2]
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
                # PIL format: [left, top, right, bottom] or [x1, y1, x2, y2]
                bbox = BBox(
                    top=float(bbox_raw[1]),
                    left=float(bbox_raw[0]),
                    bottom=float(bbox_raw[3]),
                    right=float(bbox_raw[2]),
                )
            lines_with_bbox.append((line, bbox))
        except (TypeError, IndexError, ValueError) as e:
            logger.warning(f"Invalid bbox in line '{line.get('text', '')}': {e}")
            continue

    if not lines_with_bbox:
        return []

    # ─── Step 1: Detect section header lines (bold, uppercase, short) ──────────
    section_headers = []
    for line, bbox in lines_with_bbox:
        text = line.get("text", "").strip()
        # Heuristic: Lines like "A. TITLE", "B. ANOTHER", "C. THIRD" are section headers
        if (
            text
            and len(text) >= 2  # ✅ CRITICAL FIX: Check length before indexing
            and len(text) < 100
            and text[0].isalpha()
            and text[1] == "."
            and text.isupper()
        ):
            section_headers.append((line, bbox))

    # ─── Step 2: Detect checkbox groups (consecutive short lines in columns) ───
    checkbox_groups = _detect_checkbox_groups(lines_with_bbox)

    # ─── Step 3: Cluster remaining lines into regions ────────────────────────
    regions = []
    
    # Track indices of used lines to avoid duplicates
    used_indices = set()

    # Add section headers first
    for i, (line, bbox) in enumerate(lines_with_bbox):
        for sect_line, sect_bbox in section_headers:
            if sect_line is line and sect_bbox.top == bbox.top:  # Same line object + position
                regions.append(
                    Region(
                        type=RegionType.SECTION_TITLE,
                        name=line.get("text", "").strip(),
                        bbox=bbox,
                        lines=[line],
                        confidence=REGION_CONFIDENCE["section_title"],
                    )
                )
                used_indices.add(i)
                break

    # Add checkbox groups
    for group in checkbox_groups:
        # Compute group bbox
        y_coords = [bbox.top for _, bbox in group] + [bbox.bottom for _, bbox in group]
        x_coords = [bbox.left for _, bbox in group] + [bbox.right for _, bbox in group]
        group_bbox = BBox(
            top=min(y_coords),
            left=min(x_coords),
            bottom=max(y_coords),
            right=max(x_coords),
        )
        # Group name from first label or "Checkbox Group"
        group_lines = [line for line, _ in group]
        group_name = " ".join([l.get("text", "").strip() for l in group_lines[:3]])
        if not group_name:
            group_name = "Checkbox Group"

        regions.append(
            Region(
                type=RegionType.CHECKBOX_GROUP,
                name=group_name,
                bbox=group_bbox,
                lines=group_lines,
                confidence=REGION_CONFIDENCE["checkbox_group"],
            )
        )
        
        # Track indices of lines in checkbox group
        for i, (line, bbox) in enumerate(lines_with_bbox):
            for group_line, _ in group:
                if line is group_line:
                    used_indices.add(i)
                    break

    # Add remaining lines as text fields
    remaining_lines = [(i, line, bbox) for i, (line, bbox) in enumerate(lines_with_bbox) if i not in used_indices]

    # Cluster remaining lines into text field regions
    text_regions = _cluster_text_regions([(line, bbox) for _, line, bbox in remaining_lines])
    for text_lines, text_bbox in text_regions:
        text_name = " ".join([l.get("text", "").strip()[:20] for l in text_lines[:2]])
        regions.append(
            Region(
                type=RegionType.TEXT_FIELD,
                name=text_name or "Text Field",
                bbox=text_bbox,
                lines=text_lines,
                confidence=REGION_CONFIDENCE["text_field"],
            )
        )

    # ─── Step 4: Sort regions top-to-bottom ───────────────────────────────────
    regions.sort(key=lambda r: r.bbox.top)

    logger.info(f"Classified {len(regions)} regions from {len(raw_lines)} OCR lines")
    for i, r in enumerate(regions):
        logger.debug(f"  Region {i+1}: {r.type.value} '{r.name[:30]}...' ({len(r.lines)} lines)")

    return regions


def _detect_checkbox_groups(
    lines_with_bbox: list[tuple[dict[str, Any], BBox]],
    min_group_size: int = 2,
    y_gap_threshold: int = 30,
    x_tolerance_px: int = 50,
) -> list[list[tuple[dict[str, Any], BBox]]]:
    """
    Detect groups of checkbox-like lines.

    Args:
        lines_with_bbox: List of (OCR line dict, BBox) tuples sorted top-to-bottom
        min_group_size: Minimum lines to form a group (default: 2)
        y_gap_threshold: Max vertical gap between lines in group (px, default: 30)
        x_tolerance_px: Max horizontal deviation for alignment (px, default: 50)

    Returns:
        List of checkbox groups; each group is list of (line dict, BBox) tuples.

    Heuristic: Short lines (1-3 words) that are vertically close and horizontally
    aligned form checkbox groups (e.g., Y/N options, activity checkboxes).
    """
    groups = []
    used = set()

    for i, (line, bbox) in enumerate(lines_with_bbox):
        if i in used:
            continue

        text = line.get("text", "").strip()
        # Checkbox-like: very short text (1-5 words), often single char
        if len(text) < 20 and len(text.split()) <= 3:
            # Start a new group
            group = [(line, bbox)]
            used.add(i)

            # Find other lines vertically near this one
            for j in range(i + 1, len(lines_with_bbox)):
                if j in used:
                    continue
                other_line, other_bbox = lines_with_bbox[j]
                other_text = other_line.get("text", "").strip()

                # Check if close vertically and horizontally aligned
                y_gap = other_bbox.top - bbox.bottom
                
                # ✅ HIGH FIX: Early exit if gap exceeds threshold (prevents O(n²) scan)
                if y_gap > y_gap_threshold:
                    break
                
                if (
                    y_gap > -5 and  # Close vertically (allow slight overlap)
                    other_bbox.overlaps_x(bbox, tolerance_px=x_tolerance_px) and  # Aligned horizontally
                    len(other_text) < 20 and len(other_text.split()) <= 3  # Also checkbox-like
                ):
                    group.append((other_line, other_bbox))
                    used.add(j)
                    # ✅ MEDIUM FIX: Comment explaining chaining behavior
                    bbox = other_bbox  # Update reference: chain-group consecutive lines

            if len(group) >= min_group_size:
                groups.append(group)

    return groups


def _cluster_text_regions(
    lines_with_bbox: list[tuple[dict[str, Any], BBox]],
    vertical_gap_threshold: int = 50,
) -> list[tuple[list[dict[str, Any]], BBox]]:
    """
    Cluster remaining lines into text field regions.

    Uses vertical gap to separate regions: if gap > threshold, start new region.

    Returns:
        List of (lines_in_region, region_bbox) tuples
    """
    if not lines_with_bbox:
        return []

    regions = []
    current_region_lines = []
    current_region_bbox = None

    for line, bbox in lines_with_bbox:
        if current_region_bbox is None:
            current_region_lines = [line]
            current_region_bbox = bbox
        else:
            # Check vertical gap
            gap = bbox.top - current_region_bbox.bottom
            if gap > vertical_gap_threshold:
                # Start new region
                regions.append((current_region_lines, current_region_bbox))
                current_region_lines = [line]
                current_region_bbox = bbox
            else:
                # Add to current region
                current_region_lines.append(line)
                # Expand bbox
                current_region_bbox = BBox(
                    top=min(current_region_bbox.top, bbox.top),
                    left=min(current_region_bbox.left, bbox.left),
                    bottom=max(current_region_bbox.bottom, bbox.bottom),
                    right=max(current_region_bbox.right, bbox.right),
                )

    # Add final region
    if current_region_lines:
        regions.append((current_region_lines, current_region_bbox))

    return regions
