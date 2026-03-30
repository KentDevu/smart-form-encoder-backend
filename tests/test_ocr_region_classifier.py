"""
Unit tests for OCR Region Classifier.

Tests verify region classification logic: bbox parsing, type detection,
grouping heuristics, and edge case handling.

pytest coverage target: ≥85%
"""

import pytest
from typing import Any

from app.services.ocr_region_classifier import (
    RegionType,
    BBox,
    Region,
    classify_regions,
    REGION_CONFIDENCE,
)


class TestBBox:
    """Tests for BBox geometry utilities."""

    def test_bbox_properties(self):
        """Verify bounding box properties (height, width, center)."""
        bbox = BBox(top=100, left=50, bottom=150, right=200)
        assert bbox.height == 50
        assert bbox.width == 150
        assert bbox.center_y == 125

    def test_bbox_overlaps_y_aligned(self):
        """Checkif two boxes overlap vertically."""
        bbox1 = BBox(top=100, left=50, bottom=150, right=200)
        bbox2 = BBox(top=120, left=50, bottom=170, right=200)
        assert bbox1.overlaps_y(bbox2, tolerance_px=20)

    def test_bbox_overlaps_y_not_aligned(self):
        """Check if two boxes do not overlap vertically."""
        bbox1 = BBox(top=100, left=50, bottom=150, right=200)
        bbox2 = BBox(top=250, left=50, bottom=300, right=200)
        assert not bbox1.overlaps_y(bbox2, tolerance_px=20)

    def test_bbox_overlaps_x(self):
        """Check horizontal overlap."""
        bbox1 = BBox(top=100, left=50, bottom=150, right=200)
        bbox2 = BBox(top=100, left=180, bottom=150, right=250)
        assert bbox1.overlaps_x(bbox2)  # Slight overlap

    def test_bbox_overlaps_x_not_overlapping(self):
        """Check non-overlapping boxes horizontally."""
        bbox1 = BBox(top=100, left=50, bottom=150, right=100)
        bbox2 = BBox(top=100, left=200, bottom=150, right=250)
        assert not bbox1.overlaps_x(bbox2)


class TestRegionDataclass:
    """Tests for Region dataclass."""

    def test_region_initialization(self):
        """Verify Region can be created with all fields."""
        bbox = BBox(top=100, left=50, bottom=150, right=200)
        line = {"text": "A. SECTION", "confidence": 0.95}
        region = Region(
            type=RegionType.SECTION_TITLE,
            name="A. SECTION",
            bbox=bbox,
            lines=[line],
            confidence=0.85,
        )
        assert region.type == RegionType.SECTION_TITLE
        assert region.name == "A. SECTION"
        assert len(region.lines) == 1
        assert region.confidence == 0.85

    def test_region_post_init_with_lines(self):
        """post_init should not warn if lines present."""
        bbox = BBox(top=100, left=50, bottom=150, right=200)
        line = {"text": "test"}
        region = Region(
            type=RegionType.TEXT_FIELD,
            name="Test",
            bbox=bbox,
            lines=[line],
        )
        # Should not raise; logger.debug is called but not fails
        assert len(region.lines) > 0


class TestClassifyRegionsEmpty:
    """Tests for edge case: empty/minimal input."""

    def test_classify_regions_empty_input(self):
        """Empty input should return empty regions list."""
        result = classify_regions([])
        assert result == []

    def test_classify_regions_single_line(self):
        """Single line should be classified."""
        lines = [
            {
                "text": "Single line",
                "confidence": 0.9,
                "bbox": [10, 10, 100, 30],
            }
        ]
        result = classify_regions(lines)
        # Should be classified as TEXT_FIELD (not a section header)
        assert len(result) == 1
        assert result[0].type == RegionType.TEXT_FIELD

    def test_classify_regions_invalid_bbox_format(self):
        """Invalid bbox format should be skipped gracefully."""
        lines = [
            {
                "text": "Good line",
                "confidence": 0.9,
                "bbox": [10, 10, 100, 30],
            },
            {
                "text": "Bad bbox",
                "confidence": 0.9,
                "bbox": "invalid",  # Invalid format
            },
        ]
        result = classify_regions(lines)
        # Should have 1 valid region; bad bbox skipped
        assert len(result) >= 1
        assert result[0].type == RegionType.TEXT_FIELD


class TestSectionHeaderDetection:
    """Tests for section header detection (A., B., C., etc.)."""

    def test_section_header_detected(self):
        """Valid section header 'A. TITLE' should be detected."""
        lines = [
            {
                "text": "A. TYPE OF DTI REGISTRATION",
                "confidence": 0.98,
                "bbox": [10, 100, 400, 120],
            }
        ]
        result = classify_regions(lines)
        assert len(result) == 1
        assert result[0].type == RegionType.SECTION_TITLE
        assert result[0].name == "A. TYPE OF DTI REGISTRATION"

    def test_section_header_multiple(self):
        """Multiple section headers should all be detected."""
        lines = [
            {
                "text": "A. TYPE OF DTI REGISTRATION",
                "confidence": 0.98,
                "bbox": [10, 100, 400, 120],
            },
            {
                "text": "B. TAX IDENTIFICATION NO. (TIN)",
                "confidence": 0.97,
                "bbox": [10, 250, 400, 270],
            },
            {
                "text": "C. OWNER'S INFORMATION",
                "confidence": 0.98,
                "bbox": [10, 400, 400, 420],
            },
        ]
        result = classify_regions(lines)
        # All should be section headers
        section_headers = [r for r in result if r.type == RegionType.SECTION_TITLE]
        assert len(section_headers) == 3

    def test_section_header_not_uppercase(self):
        """Non-uppercase text should NOT be detected as section header."""
        lines = [{"text": "A. lowercase text", "confidence": 0.98, "bbox": [10, 100, 400, 120]}]
        result = classify_regions(lines)
        # Should be TEXT_FIELD, not SECTION_TITLE
        assert len(result) == 1
        assert result[0].type != RegionType.SECTION_TITLE

    def test_section_header_short_text(self):
        """Very short section header like '1.' should NOT match (needs letter first)."""
        lines = [{"text": "1. SOMETHING", "confidence": 0.98, "bbox": [10, 100, 400, 120]}]
        result = classify_regions(lines)
        # '1.' doesn't start with letter, so not a section header
        # Should be classified as TEXT_FIELD
        assert result[0].type == RegionType.TEXT_FIELD


class TestCheckboxGroupDetection:
    """Tests for checkbox group detection."""

    def test_detect_checkbox_group_simple(self):
        """Simple checkbox group (Y/N) should be detected."""
        lines = [
            {"text": "Y", "confidence": 0.95, "bbox": [30, 120, 50, 135]},
            {"text": "N", "confidence": 0.95, "bbox": [30, 150, 50, 165]},
        ]
        result = classify_regions(lines)
        # Should detect as CHECKBOX_GROUP
        checkbox_groups = [r for r in result if r.type == RegionType.CHECKBOX_GROUP]
        assert len(checkbox_groups) >= 1

    def test_detect_checkbox_group_activity_types(self):
        """Activity checkbox group (Manufacturer, Service, etc.)."""
        lines = [
            {"text": "Manufacturer", "confidence": 0.92, "bbox": [30, 300, 120, 315]},
            {"text": "Service", "confidence": 0.93, "bbox": [30, 330, 100, 345]},
            {"text": "Retailer", "confidence": 0.91, "bbox": [30, 360, 100, 375]},
            {"text": "Wholesaler", "confidence": 0.90, "bbox": [30, 390, 110, 405]},
        ]
        result = classify_regions(lines)
        checkbox_groups = [r for r in result if r.type == RegionType.CHECKBOX_GROUP]
        assert len(checkbox_groups) >= 1

    def test_checkbox_group_minimum_size(self):
        """Single line should NOT form a checkbox group (min_group_size=2)."""
        lines = [{"text": "Y", "confidence": 0.95, "bbox": [30, 120, 50, 135]}]
        result = classify_regions(lines)
        # Single line shouldn't form checkbox group
        checkbox_groups = [r for r in result if r.type == RegionType.CHECKBOX_GROUP]
        assert len(checkbox_groups) == 0


class TestTextFieldRegionDetection:
    """Tests for text field region detection."""

    def test_text_field_multi_line(self):
        """Multiple lines should be grouped into TEXT_FIELD region."""
        lines = [
            {"text": "First Name", "confidence": 0.90, "bbox": [10, 300, 100, 315]},
            {"text": "Given Name Here", "confidence": 0.88, "bbox": [10, 310, 200, 325]},
        ]
        result = classify_regions(lines)
        text_fields = [r for r in result if r.type == RegionType.TEXT_FIELD]
        assert len(text_fields) >= 1

    def test_text_field_separated_by_gap(self):
        """Large gaps should separate into different TEXT_FIELD regions."""
        lines = [
            {"text": "Line 1", "confidence": 0.90, "bbox": [10, 100, 100, 115]},
            {"text": "Line 2", "confidence": 0.90, "bbox": [10, 200, 100, 215]},  # 85px gap below line 1
        ]
        result = classify_regions(lines)
        text_fields = [r for r in result if r.type == RegionType.TEXT_FIELD]
        # Should have 2 separate regions due to large gap
        assert len(text_fields) == 2


class TestRegionOrdering:
    """Tests for region ordering (top-to-bottom)."""

    def test_regions_ordered_top_to_bottom(self):
        """Regions should be ordered top-to-bottom by bbox."""
        lines = [
            {"text": "Bottom section", "confidence": 0.90, "bbox": [10, 400, 200, 420]},
            {"text": "A. TOP SECTION", "confidence": 0.98, "bbox": [10, 100, 200, 120]},
            {"text": "Middle section", "confidence": 0.90, "bbox": [10, 250, 200, 270]},
        ]
        result = classify_regions(lines)
        # Check that regions are sorted by top coordinate
        for i in range(len(result) - 1):
            assert result[i].bbox.top <= result[i + 1].bbox.top


class TestComplexForm:
    """Integration test: multi-section form."""

    def test_complete_dti_like_form(self):
        """Full form structure similar to DTI registration."""
        lines = [
            # Section A
            {"text": "A. TYPE OF DTI REGISTRATION", "confidence": 0.98, "bbox": [10, 100, 400, 120]},
            {"text": "1.", "confidence": 0.99, "bbox": [30, 140, 45, 155]},
            {"text": "NEW", "confidence": 0.97, "bbox": [60, 140, 100, 155]},
            {"text": "RENEWAL", "confidence": 0.97, "bbox": [120, 140, 180, 155]},
            # Section B (with gap)
            {"text": "B. TAX IDENTIFICATION NO. (TIN)", "confidence": 0.98, "bbox": [10, 250, 400, 270]},
            {"text": "2.", "confidence": 0.99, "bbox": [30, 290, 45, 305]},
            {"text": "With TIN", "confidence": 0.96, "bbox": [60, 290, 130, 305]},
            {"text": "Without TIN", "confidence": 0.96, "bbox": [150, 290, 230, 305]},
            # Section C (with gap)
            {"text": "C. OWNER'S INFORMATION", "confidence": 0.98, "bbox": [10, 400, 400, 420]},
            {"text": "First Name", "confidence": 0.94, "bbox": [30, 440, 130, 455]},
            {"text": "Middle Name", "confidence": 0.93, "bbox": [150, 440, 270, 455]},
            {"text": "Last Name", "confidence": 0.94, "bbox": [290, 440, 380, 455]},
        ]
        result = classify_regions(lines)

        # Verify structure
        section_headers = [r for r in result if r.type == RegionType.SECTION_TITLE]
        assert len(section_headers) == 3  # A, B, C

        # Verify ordering
        for i in range(len(result) - 1):
            assert result[i].bbox.top <= result[i + 1].bbox.top

        # Verify regions have lines
        for r in result:
            assert len(r.lines) > 0


class TestConfidenceConfiguration:
    """Tests for REGION_CONFIDENCE configuration."""

    def test_confidence_dict_exists(self):
        """REGION_CONFIDENCE dict should be defined."""
        assert REGION_CONFIDENCE is not None
        assert isinstance(REGION_CONFIDENCE, dict)

    def test_confidence_values_in_range(self):
        """All confidence values should be 0.0-1.0."""
        for key, value in REGION_CONFIDENCE.items():
            assert 0.0 <= value <= 1.0

    def test_confidence_keys_valid(self):
        """All keys should correspond to region types."""
        expected_keys = {
            "section_title",
            "checkbox_group",
            "text_field",
            "header",
            "footer",
            "unknown",
        }
        assert set(REGION_CONFIDENCE.keys()) == expected_keys


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_very_long_text(self):
        """Very long text (>100 chars) should not be section header."""
        lines = [
            {
                "text": "A. " + "VERY LONG TEXT " * 20,
                "confidence": 0.98,
                "bbox": [10, 100, 1000, 120],
            }
        ]
        result = classify_regions(lines)
        # Should not be detected as section header (len > 100)
        section_headers = [r for r in result if r.type == RegionType.SECTION_TITLE]
        assert len(section_headers) == 0

    def test_text_with_special_characters(self):
        """Text with special chars should be handled."""
        lines = [
            {"text": "A. OWNER'S INFORMATION", "confidence": 0.98, "bbox": [10, 100, 400, 120]},
            {"text": "Address: #123 St.", "confidence": 0.90, "bbox": [10, 200, 300, 215]},
        ]
        result = classify_regions(lines)
        # Should handle without crashing
        assert len(result) >= 1

    def test_empty_text_fields(self):
        """Empty text should be handled gracefully."""
        lines = [
            {"text": "", "confidence": 0.99, "bbox": [10, 100, 100, 115]},
            {"text": "Normal text", "confidence": 0.90, "bbox": [10, 130, 200, 145]},
        ]
        result = classify_regions(lines)
        # Should handle empty text
        assert len(result) >= 1

    def test_missing_confidence_field(self):
        """Missing confidence field should use default."""
        lines = [
            {"text": "A. SECTION", "bbox": [10, 100, 300, 120]},  # No confidence field
        ]
        result = classify_regions(lines)
        assert len(result) == 1
        # Region should still be created
        assert result[0].type == RegionType.SECTION_TITLE


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=app.services.ocr_region_classifier", "--cov-report=term-missing"])
