"""
Visual Checkbox Detector — Detects checkbox states from form image pixels.

Analyzes graphical checkbox regions (small boxes, squares) in form images to determine
if they are checked (filled/marked) or unchecked (empty). Complements text-based
checkbox detection for forms with both visual checkboxes and text labels.

Algorithm:
1. Load form image
2. Detect checkbox-like regions (small rectangular objects with borders)
3. Analyze pixel intensity to determine fill state (dark=checked, light=unchecked)
4. Match checkboxes to nearby OCR text labels (e.g., "Manufacturer", "Service")
5. Return DetectedCheckbox objects compatible with existing system
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class VisualCheckboxMatch:
    """Result of visual checkbox detection from image"""
    x: int                    # X coordinate of checkbox center
    y: int                    # Y coordinate of checkbox center
    width: int                # Checkbox width in pixels
    height: int               # Checkbox height in pixels
    fill_percentage: float    # Percentage of checkbox filled (0.0-1.0)
    is_checked: bool          # True if filled threshold exceeded
    confidence: float         # 0.0-1.0 confidence in detection


def detect_visual_checkboxes(
    image_path: str,
    min_box_size: int = 8,
    max_box_size: int = 50,
    fill_threshold: float = 0.4,
) -> list[VisualCheckboxMatch]:
    """
    Detect visual checkboxes in a form image.

    Args:
        image_path: Path to form image file
        min_box_size: Minimum checkbox dimension in pixels (default: 8)
        max_box_size: Maximum checkbox dimension in pixels (default: 50)
        fill_threshold: Percentage fill to classify as checked (default: 0.4)

    Returns:
        List of detected checkboxes with coordinates and fill status
    """
    try:
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            logger.warning(f"Failed to load image: {image_path}")
            return []

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply threshold to create binary image
        # Dark areas (text, checkmarks) = 0, light areas (paper) = 255
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Find contours (potential checkboxes and text)
        contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        checkboxes = []

        for contour in contours:
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)

            # Filter by size (checkbox-like dimensions)
            if w < min_box_size or h < min_box_size or w > max_box_size or h > max_box_size:
                continue

            # Filter by aspect ratio (checkboxes are roughly square)
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 0.6 or aspect_ratio > 1.6:
                continue

            # Extract checkbox region
            checkbox_region = gray[y : y + h, x : x + w]

            # Analyze fill: calculate percentage of dark pixels (checked = more dark pixels)
            # Threshold: pixels darker than 100 are considered "filled"
            dark_pixels = cv2.countNonZero(cv2.threshold(checkbox_region, 100, 255, cv2.THRESH_BINARY_INV)[1])
            total_pixels = w * h
            fill_percentage = dark_pixels / total_pixels if total_pixels > 0 else 0.0

            # Determine if checkbox is checked
            is_checked = fill_percentage >= fill_threshold

            # Confidence based on how clearly filled/empty it is
            # Higher confidence if clearly one or the other
            if fill_percentage < 0.1:
                confidence = 0.9  # Clearly empty
            elif fill_percentage > 0.7:
                confidence = 0.9  # Clearly filled
            else:
                confidence = 0.6 + (abs(fill_percentage - 0.5) * 0.4)  # Intermediate

            checkbox = VisualCheckboxMatch(
                x=x + w // 2,  # Center X
                y=y + h // 2,  # Center Y
                width=w,
                height=h,
                fill_percentage=fill_percentage,
                is_checked=is_checked,
                confidence=confidence,
            )
            checkboxes.append(checkbox)

        logger.info(f"Detected {len(checkboxes)} visual checkboxes from image")
        return checkboxes

    except Exception as e:
        logger.error(f"Error detecting visual checkboxes: {e}")
        return []


def match_visual_checkboxes_to_labels(
    visual_checkboxes: list[VisualCheckboxMatch],
    ocr_lines: list[dict[str, Any]],
    proximity_threshold: int = 60,
) -> dict[str, VisualCheckboxMatch]:
    """
    Match visual checkboxes to nearby OCR text labels.

    Args:
        visual_checkboxes: List of detected visual checkboxes
        ocr_lines: List of OCR line results with text and bboxes
        proximity_threshold: Max distance in pixels to associate checkbox with label

    Returns:
        Dictionary mapping label text to checkbox detection
    """
    matched = {}

    for label_line in ocr_lines:
        label_text = label_line.get("text", "").strip()
        bbox = label_line.get("bbox", [])

        # Skip if no text or invalid bbox
        if not label_text or not bbox:
            continue

        # Get label center position
        # Handle both PIL format [x1, y1, x2, y2] and nested format [[x1,y1], ...]
        try:
            if isinstance(bbox[0], (list, tuple)):
                # Nested format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                label_x = (min(xs) + max(xs)) / 2
                label_y = (min(ys) + max(ys)) / 2
            else:
                # Flat format: [x1, y1, x2, y2]
                label_x = (bbox[0] + bbox[2]) / 2
                label_y = (bbox[1] + bbox[3]) / 2
        except (IndexError, TypeError):
            continue

        # Find closest checkbox to this label
        closest_checkbox = None
        closest_distance = proximity_threshold

        for checkbox in visual_checkboxes:
            # Calculate distance from label to checkbox
            distance = ((checkbox.x - label_x) ** 2 + (checkbox.y - label_y) ** 2) ** 0.5

            # Look for checkboxes to the left or right of label (typical form layout)
            # Biases toward horizontal proximity which is common for form checkboxes
            if distance < closest_distance:
                closest_checkbox = checkbox
                closest_distance = distance

        if closest_checkbox:
            matched[label_text] = closest_checkbox
            logger.debug(f"Matched '{label_text}' to checkbox at ({closest_checkbox.x}, {closest_checkbox.y})")

    logger.info(f"Matched {len(matched)} visual checkboxes to labels")
    return matched


def analyze_checkbox_region(
    image: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
) -> tuple[bool, float]:
    """
    Analyze a single checkbox region to determine if checked.

    Args:
        image: Grayscale image
        x, y: Top-left corner of checkbox region
        w, h: Width and height of checkbox region

    Returns:
        Tuple of (is_checked, fill_percentage)
    """
    # Extract checkbox region
    checkbox_region = image[y : y + h, x : x + w]

    # Count dark pixels (filled)
    dark_pixels = cv2.countNonZero(cv2.threshold(checkbox_region, 100, 255, cv2.THRESH_BINARY_INV)[1])
    total_pixels = w * h
    fill_percentage = dark_pixels / total_pixels if total_pixels > 0 else 0.0

    # Standard threshold: >40% filled = checked
    is_checked = fill_percentage >= 0.4

    return is_checked, fill_percentage
