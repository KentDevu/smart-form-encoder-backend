"""
Unit tests for OCR Checkbox Detector.

Tests verify checkbox state detection, field mapping, and confidence scoring.

pytest coverage target: ≥80%
"""

import pytest
from typing import Any

from app.services.ocr_checkbox_detector import (
    CheckboxState,
    DetectedCheckbox,
    detect_checkboxes,
    detect_checkbox_state,
    validate_checkbox_extraction,
)
from app.services.ocr_region_classifier import Region, RegionType, BBox


class TestCheckboxState:
    """Tests for CheckboxState enum."""

    def test_checkbox_state_values(self):
        """Verify CheckboxState enum values."""
        assert CheckboxState.CHECKED.value == "checked"
        assert CheckboxState.UNCHECKED.value == "unchecked"
        assert CheckboxState.UNCLEAR.value == "unclear"


class TestDetectCheckboxState:
    """Tests for checkbox state detection from text."""

    def test_detect_checkmark(self):
        """Detect Unicode checkmark."""
        state, conf = detect_checkbox_state("✓")
        assert state == CheckboxState.CHECKED
        assert conf > 0.85

    def test_detect_x_mark(self):
        """Detect X mark."""
        state, conf = detect_checkbox_state("X")
        assert state == CheckboxState.CHECKED
        assert conf > 0.85

    def test_detect_lowercase_x(self):
        """Detect lowercase x."""
        state, conf = detect_checkbox_state("x")
        assert state == CheckboxState.CHECKED
        assert conf > 0.85

    def test_detect_filled_box_unicode(self):
        """Detect filled box unicode."""
        state, conf = detect_checkbox_state("☑")
        assert state == CheckboxState.CHECKED
        assert conf > 0.80

    def test_detect_empty_box_unicode(self):
        """Detect empty box unicode."""
        state, conf = detect_checkbox_state("☐")
        assert state == CheckboxState.UNCHECKED
        assert conf > 0.80

    def test_detect_empty_brackets(self):
        """Detect empty brackets."""
        state, conf = detect_checkbox_state("[]")
        assert state == CheckboxState.UNCHECKED
        assert conf > 0.80

    def test_detect_tilde_unclear(self):
        """Detect tilde as unclear."""
        state, conf = detect_checkbox_state("~")
        assert state == CheckboxState.UNCLEAR
        assert 0.4 < conf < 0.6

    def test_detect_question_mark_unclear(self):
        """Detect question mark as unclear."""
        state, conf = detect_checkbox_state("?")
        assert state == CheckboxState.UNCLEAR
        assert 0.4 < conf < 0.7

    def test_detect_empty_text(self):
        """Empty text → UNCLEAR."""
        state, conf = detect_checkbox_state("")
        assert state == CheckboxState.UNCLEAR
        assert conf < 0.5

    def test_detect_label_text(self):
        """Label text like 'Manufacturer' → UNCHECKED (default)."""
        state, conf = detect_checkbox_state("Manufacturer")
        assert state == CheckboxState.UNCHECKED
        assert conf > 0.65

    def test_detect_checked_in_longer_text(self):
        """Checkmark within longer text still detected."""
        state, conf = detect_checkbox_state("Some text ✓ more text")
        assert state == CheckboxState.CHECKED

    def test_detect_unclear_multiple_dots(self):
        """Multiple dots → UNCLEAR."""
        state, conf = detect_checkbox_state("....")
        assert state == CheckboxState.UNCLEAR


class TestDetectedCheckboxDataclass:
    """Tests for DetectedCheckbox dataclass."""

    def test_detected_checkbox_creation(self):
        """Create DetectedCheckbox with all fields."""
        bbox = BBox(top=100, left=50, bottom=120, right=70)
        checkbox = DetectedCheckbox(
            name="activity_manufacturer",
            state=CheckboxState.CHECKED,
            confidence=0.92,
            bbox=bbox,
            anchor_text="Manufacturer",
        )
        assert checkbox.name == "activity_manufacturer"
        assert checkbox.state == CheckboxState.CHECKED
        assert checkbox.confidence == 0.92
        assert checkbox.anchor_text == "Manufacturer"

    def test_detected_checkbox_with_patterns(self):
        """DetectedCheckbox can include OCR pattern info."""
        bbox = BBox(top=100, left=50, bottom=120, right=70)
        patterns = {"detected_state": "checked", "text": "✓"}
        checkbox = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.95,
            bbox=bbox,
            anchor_text="Label",
            ocr_patterns=patterns,
        )
        assert checkbox.ocr_patterns is not None
        assert checkbox.ocr_patterns["detected_state"] == "checked"


class TestDetectCheckboxesFromRegions:
    """Tests for checkbox detection from region objects."""

    def test_detect_checkboxes_empty_regions(self):
        """No checkbox regions → return empty list."""
        regions = []
        result = detect_checkboxes(regions=regions, raw_lines=[])
        assert result == []

    def test_detect_checkboxes_no_checkbox_regions(self):
        """Region list with no CHECKBOX_GROUP type → return empty."""
        bbox = BBox(top=100, left=50, bottom=150, right=200)
        regions = [
            Region(
                type=RegionType.TEXT_FIELD,
                name="Text field",
                bbox=bbox,
                lines=[{"text": "Some text"}],
            )
        ]
        result = detect_checkboxes(regions=regions, raw_lines=[])
        assert result == []

    def test_detect_checkboxes_simple_yn(self):
        """Detect Y/N checkbox group."""
        bbox = BBox(top=100, left=50, bottom=120, right=70)
        regions = [
            Region(
                type=RegionType.CHECKBOX_GROUP,
                name="Y/N Question",
                bbox=bbox,
                lines=[
                    {"text": "Y", "confidence": 0.95, "bbox": [50, 100, 60, 115]},
                    {"text": "N", "confidence": 0.95, "bbox": [50, 120, 60, 135]},
                ],
            )
        ]
        result = detect_checkboxes(regions=regions, raw_lines=[])
        assert len(result) == 2
        # Both should be unchecked (default for label text)
        assert all(c.state == CheckboxState.UNCHECKED for c in result)

    def test_detect_checkboxes_activity_types(self):
        """Detect activity type checkboxes."""
        bbox = BBox(top=100, left=50, bottom=200, right=200)
        regions = [
            Region(
                type=RegionType.CHECKBOX_GROUP,
                name="Activity Types",
                bbox=bbox,
                lines=[
                    {"text": "Manufacturer", "confidence": 0.93, "bbox": [50, 100, 150, 115]},
                    {"text": "Service", "confidence": 0.92, "bbox": [50, 120, 120, 135]},
                    {"text": "Retailer", "confidence": 0.93, "bbox": [50, 140, 120, 155]},
                ],
            )
        ]
        result = detect_checkboxes(regions=regions, raw_lines=[])
        assert len(result) == 3
        # Verify field name mapping
        assert any(c.name == "activity_manufacturer" for c in result)
        assert any(c.name == "activity_service" for c in result)
        assert any(c.name == "activity_retailer" for c in result)

    def test_detect_checkboxes_with_marks(self):
        """Detect checkboxes with explicit marks (✓, X)."""
        bbox = BBox(top=100, left=50, bottom=150, right=70)
        regions = [
            Region(
                type=RegionType.CHECKBOX_GROUP,
                name="Marked checkboxes",
                bbox=bbox,
                lines=[
                    {"text": "✓", "confidence": 0.95, "bbox": [50, 100, 60, 115]},
                    {"text": "X", "confidence": 0.94, "bbox": [50, 130, 60, 145]},
                ],
            )
        ]
        result = detect_checkboxes(regions=regions, raw_lines=[])
        assert len(result) == 2
        # Both should be detected as CHECKED
        assert all(c.state == CheckboxState.CHECKED for c in result)
        assert all(c.confidence > 0.85 for c in result)

    def test_detect_checkboxes_confidence_combination(self):
        """Checkbox confidence combines pattern + OCR confidence."""
        bbox = BBox(top=100, left=50, bottom=120, right=70)
        regions = [
            Region(
                type=RegionType.CHECKBOX_GROUP,
                name="Test",
                bbox=bbox,
                lines=[
                    {"text": "✓", "confidence": 0.80, "bbox": [50, 100, 60, 115]},  # Pattern 0.92 * OCR 0.80
                ],
            )
        ]
        result = detect_checkboxes(regions=regions, raw_lines=[])
        assert len(result) == 1
        # Combined confidence = 0.92 * 0.80 ≈ 0.73
        assert 0.70 < result[0].confidence < 0.80


class TestValidateCheckboxExtraction:
    """Tests for checkbox validation/post-processing."""

    def test_validate_empty_extracted_fields(self):
        """Validation on empty extraction."""
        extracted = {}
        checkboxes = [
            DetectedCheckbox(
                name="activity_mfg",
                state=CheckboxState.CHECKED,
                confidence=0.92,
                bbox=BBox(top=100, left=50, bottom=120, right=70),
                anchor_text="Manufacturer",
            )
        ]
        result = validate_checkbox_extraction(extracted, checkboxes)
        # Should add the checkbox field
        assert "activity_mfg" in result
        assert result["activity_mfg"] == "true"

    def test_validate_checked_state(self):
        """Validation sets 'true' for checked."""
        extracted = {}
        checkboxes = [
            DetectedCheckbox(
                name="yn_answer",
                state=CheckboxState.CHECKED,
                confidence=0.90,
                bbox=BBox(top=100, left=50, bottom=120, right=70),
                anchor_text="Yes",
            )
        ]
        result = validate_checkbox_extraction(extracted, checkboxes)
        assert result["yn_answer"] == "true"

    def test_validate_unchecked_state(self):
        """Validation sets empty string for unchecked."""
        extracted = {}
        checkboxes = [
            DetectedCheckbox(
                name="yn_answer",
                state=CheckboxState.UNCHECKED,
                confidence=0.88,
                bbox=BBox(top=100, left=50, bottom=120, right=70),
                anchor_text="No",
            )
        ]
        result = validate_checkbox_extraction(extracted, checkboxes)
        assert result["yn_answer"] == ""

    def test_validate_unclear_skipped(self):
        """UNCLEAR state doesn't override existing value."""
        extracted = {"yn_answer": "maybe"}
        checkboxes = [
            DetectedCheckbox(
                name="yn_answer",
                state=CheckboxState.UNCLEAR,
                confidence=0.5,
                bbox=BBox(top=100, left=50, bottom=120, right=70),
                anchor_text="?",
            )
        ]
        result = validate_checkbox_extraction(extracted, checkboxes)
        # Should keep original value
        assert result["yn_answer"] == "maybe"

    def test_validate_low_confidence_skipped(self):
        """Low confidence (<0.75) checkboxes skipped."""
        extracted = {}
        checkboxes = [
            DetectedCheckbox(
                name="yn_answer",
                state=CheckboxState.CHECKED,
                confidence=0.70,  # Below threshold
                bbox=BBox(top=100, left=50, bottom=120, right=70),
                anchor_text="Yes",
            )
        ]
        result = validate_checkbox_extraction(extracted, checkboxes)
        # Should NOT add field (confidence < 0.75)
        assert "yn_answer" not in result

    def test_validate_multiple_checkboxes(self):
        """Validate multiple checkboxes at once."""
        extracted = {}
        checkboxes = [
            DetectedCheckbox(
                name="activity_mfg",
                state=CheckboxState.CHECKED,
                confidence=0.90,
                bbox=BBox(top=100, left=50, bottom=120, right=70),
                anchor_text="Manufacturer",
            ),
            DetectedCheckbox(
                name="activity_retail",
                state=CheckboxState.UNCHECKED,
                confidence=0.88,
                bbox=BBox(top=130, left=50, bottom=150, right=70),
                anchor_text="Retailer",
            ),
        ]
        result = validate_checkbox_extraction(extracted, checkboxes)
        assert result["activity_mfg"] == "true"
        assert result["activity_retail"] == ""


class TestCheckboxMapping:
    """Tests for DTI-specific field name mapping."""

    def test_activity_types_mapping(self):
        """Verify activity type field mappings."""
        state, _ = detect_checkbox_state("Manufacturer")
        # Should map to activity_manufacturer
        assert detect_checkboxes(
            regions=[
                Region(
                    type=RegionType.CHECKBOX_GROUP,
                    name="Activities",
                    bbox=BBox(top=100, left=50, bottom=200, right=200),
                    lines=[{"text": "Manufacturer", "confidence": 0.93, "bbox": [50, 100, 150, 115]}],
                )
            ],
            raw_lines=[],
        )[0].name == "activity_manufacturer"

    def test_civil_status_mapping(self):
        """Verify civil status field mappings."""
        checkboxes = detect_checkboxes(
            regions=[
                Region(
                    type=RegionType.CHECKBOX_GROUP,
                    name="Civil Status",
                    bbox=BBox(top=100, left=50, bottom=200, right=200),
                    lines=[
                        {"text": "Single", "confidence": 0.93, "bbox": [50, 100, 100, 115]},
                        {"text": "Married", "confidence": 0.92, "bbox": [50, 120, 120, 135]},
                    ],
                )
            ],
            raw_lines=[],
        )
        assert any(c.name == "civil_status_single" for c in checkboxes)
        assert any(c.name == "civil_status_married" for c in checkboxes)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_detect_with_no_bbox_in_line(self):
        """Handle missing bbox in line gracefully."""
        regions = [
            Region(
                type=RegionType.CHECKBOX_GROUP,
                name="Test",
                bbox=BBox(top=100, left=50, bottom=120, right=70),
                lines=[
                    {"text": "✓", "confidence": 0.95},  # No bbox
                ],
            )
        ]
        result = detect_checkboxes(regions=regions, raw_lines=[])
        # Should handle gracefully
        assert len(result) == 1
        assert result[0].bbox.top == 0
        assert result[0].bbox.left == 0

    def test_detect_checkbox_html_entities(self):
        """Handle HTML-like entities."""
        state, conf = detect_checkbox_state("&check;")
        # Not explicitly checked, but shouldn't crash
        assert state in [CheckboxState.CHECKED, CheckboxState.UNCHECKED, CheckboxState.UNCLEAR]

    def test_detect_checkbox_mixed_case(self):
        """Mixed case checkmarks should still work."""
        state1, _ = detect_checkbox_state("x")
        state2, _ = detect_checkbox_state("X")
        assert state1 == CheckboxState.CHECKED
        assert state2 == CheckboxState.CHECKED


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=app.services.ocr_checkbox_detector", "--cov-report=term-missing"])
