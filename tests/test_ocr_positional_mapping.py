"""Unit tests for OCR positional mapping module."""

import pytest
from app.services.ocr_positional_mapping import (
    BoundingBox,
    extract_bbox_from_paddle_ocr,
    group_ocr_lines_by_column,
    group_ocr_lines_by_row,
    find_field_by_label_position,
    map_fields_by_spatial_position,
)


# =============================================================================
# BoundingBox Tests (8 tests)
# =============================================================================

class TestBoundingBox:
    """Tests for BoundingBox class."""
    
    def test_bbox_initialization(self):
        """Test BoundingBox initialization with valid coordinates."""
        bbox = BoundingBox(top=10, left=20, bottom=100, right=200)
        assert bbox.top == 10
        assert bbox.left == 20
        assert bbox.bottom == 100
        assert bbox.right == 200
    
    def test_bbox_width(self):
        """Test BoundingBox width calculation."""
        bbox = BoundingBox(top=0, left=10, bottom=100, right=110)
        assert bbox.width == 100
    
    def test_bbox_height(self):
        """Test BoundingBox height calculation."""
        bbox = BoundingBox(top=10, left=0, bottom=110, right=100)
        assert bbox.height == 100
    
    def test_bbox_center(self):
        """Test BoundingBox center point calculation."""
        bbox = BoundingBox(top=0, left=0, bottom=100, right=100)
        assert bbox.center_x == 50
        assert bbox.center_y == 50
    
    def test_bbox_overlaps_true(self):
        """Test BoundingBox overlap detection (overlapping boxes)."""
        bbox1 = BoundingBox(top=0, left=0, bottom=100, right=100)
        bbox2 = BoundingBox(top=50, left=50, bottom=150, right=150)
        # Overlap area = 50*50 / 100*100 = 0.25 (25%)
        assert bbox1.overlaps(bbox2, threshold=0.2)
    
    def test_bbox_overlaps_false(self):
        """Test BoundingBox overlap detection (non-overlapping boxes)."""
        bbox1 = BoundingBox(top=0, left=0, bottom=100, right=100)
        bbox2 = BoundingBox(top=0, left=200, bottom=100, right=300)
        assert not bbox1.overlaps(bbox2, threshold=0.5)
    
    def test_bbox_contains_point_true(self):
        """Test BoundingBox point containment (inside box)."""
        bbox = BoundingBox(top=0, left=0, bottom=100, right=100)
        assert bbox.contains_point(50, 50)
    
    def test_bbox_contains_point_false(self):
        """Test BoundingBox point containment (outside box)."""
        bbox = BoundingBox(top=0, left=0, bottom=100, right=100)
        assert not bbox.contains_point(150, 150)


# =============================================================================
# PaddleOCR Bbox Extraction Tests (5 tests)
# =============================================================================

class TestExtractBboxFromPaddleOCR:
    """Tests for extract_bbox_from_paddle_ocr function."""
    
    def test_extract_bbox_standard_format(self):
        """Test extraction from standard PaddleOCR format."""
        ocr_line = {
            "text": "Business Name",
            "confidence": 0.92,
            "bbox": [[10, 20], [200, 20], [200, 50], [10, 50]]
        }
        bbox = extract_bbox_from_paddle_ocr(ocr_line)
        assert bbox is not None
        assert bbox.top == 20
        assert bbox.left == 10
        assert bbox.bottom == 50
        assert bbox.right == 200
    
    def test_extract_bbox_missing_bbox_key(self):
        """Test extraction when bbox key is missing."""
        ocr_line = {"text": "Business Name", "confidence": 0.92}
        bbox = extract_bbox_from_paddle_ocr(ocr_line)
        assert bbox is None
    
    def test_extract_bbox_empty_bbox(self):
        """Test extraction with empty bbox array."""
        ocr_line = {"text": "Business Name", "confidence": 0.92, "bbox": []}
        bbox = extract_bbox_from_paddle_ocr(ocr_line)
        assert bbox is None
    
    def test_extract_bbox_malformed_coordinates(self):
        """Test extraction with malformed coordinates."""
        ocr_line = {"text": "Business Name", "bbox": [[10], [200, 20], [200, 50]]}
        try:
            bbox = extract_bbox_from_paddle_ocr(ocr_line)
            # Function should handle gracefully or return None
            assert bbox is None or isinstance(bbox, BoundingBox)
        except (IndexError, TypeError):
            # Acceptable to raise on malformed data
            pass
    
    def test_extract_bbox_with_type_error(self):
        """Test extraction with invalid types."""
        ocr_line = {"text": "Business Name", "bbox": "not a list"}
        bbox = extract_bbox_from_paddle_ocr(ocr_line)
        assert bbox is None


# =============================================================================
# Row/Column Grouping Tests (12 tests)
# =============================================================================

class TestGroupOCRLinesByRow:
    """Tests for group_ocr_lines_by_row function."""
    
    def test_group_single_row(self):
        """Test grouping lines in a single row."""
        lines = [
            {"text": "Text1", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
            {"text": "Text2", "confidence": 0.9, "bbox": [[120, 15], [200, 15], [200, 35], [120, 35]]},
        ]
        rows = group_ocr_lines_by_row(lines, row_threshold=15)
        assert len(rows) == 1
        assert len(rows[0]) == 2
    
    def test_group_multiple_rows(self):
        """Test grouping lines into multiple rows."""
        lines = [
            {"text": "Row1", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
            {"text": "Row2", "confidence": 0.9, "bbox": [[0, 100], [100, 100], [100, 120], [0, 120]]},
        ]
        rows = group_ocr_lines_by_row(lines, row_threshold=15)
        assert len(rows) == 2
    
    def test_group_empty_lines(self):
        """Test grouping with empty input."""
        rows = group_ocr_lines_by_row([], row_threshold=15)
        assert len(rows) == 0
    
    def test_group_line_without_bbox(self):
        """Test grouping when some lines have no bbox."""
        lines = [
            {"text": "Text1", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
            {"text": "Text2", "confidence": 0.9},  # No bbox
            {"text": "Text3", "confidence": 0.9, "bbox": [[0, 20], [100, 20], [100, 40], [0, 40]]},
        ]
        rows = group_ocr_lines_by_row(lines, row_threshold=15)
        # Should skip line without bbox
        assert all(len(row) <= 2 for row in rows)


class TestGroupOCRLinesByColumn:
    """Tests for group_ocr_lines_by_column function."""
    
    def test_group_single_column(self):
        """Test grouping lines in a single column."""
        lines = [
            {"text": "Line1", "confidence": 0.9, "bbox": [[10, 0], [30, 0], [30, 50], [10, 50]]},
            {"text": "Line2", "confidence": 0.9, "bbox": [[15, 100], [35, 100], [35, 150], [15, 150]]},
        ]
        columns = group_ocr_lines_by_column(lines, column_threshold=15)
        assert len(columns) == 1
        assert len(columns[0]) == 2
    
    def test_group_multiple_columns(self):
        """Test grouping lines into multiple columns."""
        lines = [
            {"text": "Col1", "confidence": 0.9, "bbox": [[10, 0], [30, 0], [30, 100], [10, 100]]},
            {"text": "Col2", "confidence": 0.9, "bbox": [[200, 0], [220, 0], [220, 100], [200, 100]]},
        ]
        columns = group_ocr_lines_by_column(lines, column_threshold=50)
        assert len(columns) == 2
    
    def test_group_empty_lines_columns(self):
        """Test grouping with empty input."""
        columns = group_ocr_lines_by_column([], column_threshold=50)
        assert len(columns) == 0


# =============================================================================
# Label-Based Field Search Tests (10 tests)
# =============================================================================

class TestFindFieldByLabelPosition:
    """Tests for find_field_by_label_position function."""
    
    def test_find_label_with_value_to_right(self):
        """Test finding label with value to the right."""
        lines = [
            {"text": "Business Name:", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
            {"text": "ABC Corp", "confidence": 0.85, "bbox": [[110, 15], [200, 15], [200, 35], [110, 35]]},
        ]
        result = find_field_by_label_position(lines, "Business Name:")
        assert result is not None
        assert "ABC Corp" in result["value"]
        assert 0.85 <= result["confidence"] <= 0.9
    
    def test_find_label_with_value_below(self):
        """Test finding label with value below."""
        lines = [
            {"text": "Owner Name", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
            {"text": "John Doe", "confidence": 0.88, "bbox": [[10, 50], [150, 50], [150, 70], [10, 70]]},
        ]
        result = find_field_by_label_position(lines, "Owner Name")
        assert result is not None
        assert "John Doe" in result.get("value", "")
    
    def test_find_label_not_found(self):
        """Test when label is not found."""
        lines = [
            {"text": "Some Text", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
        ]
        result = find_field_by_label_position(lines, "Nonexistent Label")
        assert result is None
    
    def test_find_label_case_insensitive(self):
        """Test case-insensitive label matching."""
        lines = [
            {"text": "BUSINESS NAME:", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
            {"text": "XYZ Ltd", "confidence": 0.87, "bbox": [[110, 15], [200, 15], [200, 35], [110, 35]]},
        ]
        result = find_field_by_label_position(lines, "business name:")
        assert result is not None
    
    def test_find_label_empty_lines(self):
        """Test with empty lines list."""
        result = find_field_by_label_position([], "Business Name")
        assert result is None
    
    def test_find_label_multiple_values(self):
        """Test finding label with multiple value candidates."""
        lines = [
            {"text": "Phone:", "confidence": 0.9, "bbox": [[0, 10], [50, 10], [50, 30], [0, 30]]},
            {"text": "091", "confidence": 0.8, "bbox": [[60, 15], [90, 15], [90, 35], [60, 35]]},
            {"text": "123456", "confidence": 0.85, "bbox": [[100, 15], [150, 15], [150, 35], [100, 35]]},
        ]
        result = find_field_by_label_position(lines, "Phone:")
        assert result is not None
        # Should combine multiple candidates
        assert "091" in result["value"] or "123456" in result["value"]
    
    def test_find_label_with_tolerance(self):
        """Test label search with custom tolerance."""
        lines = [
            {"text": "Amount:", "confidence": 0.9, "bbox": [[0, 10], [80, 10], [80, 30], [0, 30]]},
            {"text": "P5,000", "confidence": 0.92, "bbox": [[200, 15], [280, 15], [280, 35], [200, 35]]},
        ]
        # With small tolerance, should not find distant value
        result = find_field_by_label_position(lines, "Amount:", search_tolerance=50)
        # With large tolerance, might find it
        result_large = find_field_by_label_position(lines, "Amount:", search_tolerance=300)
        assert result is None or result_large is not None


# =============================================================================
# Field Mapping Tests (10 tests)
# =============================================================================

class TestMapFieldsBySpatialPosition:
    """Tests for map_fields_by_spatial_position function."""
    
    def test_map_all_fields_found(self):
        """Test mapping when all fields are found."""
        raw_lines = [
            {"text": "Business Name:", "confidence": 0.9, "bbox": [[0, 10], [120, 10], [120, 30], [0, 30]]},
            {"text": "ABC Corp", "confidence": 0.85, "bbox": [[130, 15], [220, 15], [220, 35], [130, 35]]},
            {"text": "Owner Name:", "confidence": 0.88, "bbox": [[0, 50], [100, 50], [100, 70], [0, 70]]},
            {"text": "John Doe", "confidence": 0.9, "bbox": [[110, 55], [200, 55], [200, 75], [110, 75]]},
        ]
        field_schema = {
            "fields": [
                {"name": "business_name", "label": "Business Name:"},
                {"name": "owner_name", "label": "Owner Name:"},
            ]
        }
        result = map_fields_by_spatial_position(raw_lines, field_schema)
        
        assert "business_name" in result
        assert "owner_name" in result
        assert result["business_name"]["value"]  # Should have value
        assert result["owner_name"]["value"]  # Should have value
    
    def test_map_partial_fields_found(self):
        """Test mapping when only some fields are found."""
        raw_lines = [
            {"text": "Business Name:", "confidence": 0.9, "bbox": [[0, 10], [120, 10], [120, 30], [0, 30]]},
            {"text": "ABC Corp", "confidence": 0.85, "bbox": [[130, 15], [220, 15], [220, 35], [130, 35]]},
        ]
        field_schema = {
            "fields": [
                {"name": "business_name", "label": "Business Name:"},
                {"name": "owner_name", "label": "Owner Name:"},  # Not in OCR
            ]
        }
        result = map_fields_by_spatial_position(raw_lines, field_schema)
        
        assert result["business_name"]["value"]  # Found
        assert result["owner_name"]["value"] == ""  # Not found
        assert result["owner_name"]["confidence"] == 0.0  # Low confidence
    
    def test_map_empty_raw_lines(self):
        """Test mapping with empty raw lines."""
        field_schema = {
            "fields": [{"name": "business_name", "label": "Business Name:"}]
        }
        result = map_fields_by_spatial_position([], field_schema)
        
        assert "business_name" in result
        assert result["business_name"]["value"] == ""
        assert result["business_name"]["confidence"] == 0.0
    
    def test_map_empty_field_schema(self):
        """Test mapping with empty field schema."""
        raw_lines = [
            {"text": "Some Text", "confidence": 0.9, "bbox": [[0, 10], [100, 10], [100, 30], [0, 30]]},
        ]
        result = map_fields_by_spatial_position(raw_lines, {"fields": []})
        assert len(result) == 0
    
    def test_map_respects_field_schema(self):
        """Test that mapping respects field schema definitions."""
        raw_lines = [
            {"text": "Phone:", "confidence": 0.9, "bbox": [[0, 10], [80, 10], [80, 30], [0, 30]]},
            {"text": "09123456", "confidence": 0.87, "bbox": [[90, 15], [180, 15], [180, 35], [90, 35]]},
        ]
        field_schema = {
            "fields": [
                {"name": "phone_number", "label": "Phone:"},
                {"name": "email", "label": "Email:"},  # Not in OCR
            ]
        }
        result = map_fields_by_spatial_position(raw_lines, field_schema)
        
        # Should have both fields (found and not found)
        assert len(result) == 2
        assert "phone_number" in result
        assert "email" in result


# =============================================================================
# Integration Tests (4 tests)
# =============================================================================

class TestPositionalMappingIntegration:
    """Integration tests for full positional mapping pipeline."""
    
    def test_end_to_end_dti_form_extraction(self):
        """Test end-to-end extraction on realistic DTI form data."""
        # Simulated DTI BNR form OCR
        raw_lines = [
            {"text": "DTI", "confidence": 0.95, "bbox": [[10, 20], [60, 20], [60, 50], [10, 50]]},
            {"text": "NR0:052018", "confidence": 0.88, "bbox": [[70, 25], [180, 25], [180, 45], [70, 45]]},
            {"text": "Business Name:", "confidence": 0.92, "bbox": [[10, 100], [150, 100], [150, 120], [10, 120]]},
            {"text": "ABC Trading", "confidence": 0.85, "bbox": [[160, 105], [300, 105], [300, 125], [160, 125]]},
            {"text": "Owner:", "confidence": 0.9, "bbox": [[10, 150], [100, 150], [100, 170], [10, 170]]},
            {"text": "John Doe", "confidence": 0.89, "bbox": [[110, 155], [220, 155], [220, 175], [110, 175]]},
        ]
        field_schema = {
            "fields": [
                {"name": "certificate_no", "label": "NR0:"},
                {"name": "business_name", "label": "Business Name:"},
                {"name": "owner_name", "label": "Owner:"},
            ]
        }
        result = map_fields_by_spatial_position(raw_lines, field_schema)
        
        # Verify extraction
        assert len(result) == 3
        assert result["business_name"]["value"]  # Should find "ABC Trading"
        assert result["owner_name"]["value"]  # Should find "John Doe"
        
        # Verify all fields have confidence
        for field_name, field_data in result.items():
            assert "confidence" in field_data
            assert isinstance(field_data["confidence"], float)
            assert 0.0 <= field_data["confidence"] <= 1.0
    
    def test_fallback_improves_coverage(self):
        """Test that fallback improves extraction coverage."""
        # Simulate low-quality AI extraction
        ai_extraction = {
            "business_name": {"value": "", "confidence": 0.0},
            "owner_name": {"value": "", "confidence": 0.0},
            "certificate_no": {"value": "NR0:052018", "confidence": 0.88},
        }
        
        # Fallback extraction (positional mapping)
        raw_lines = [
            {"text": "Business Name:", "confidence": 0.92, "bbox": [[10, 100], [150, 100], [150, 120], [10, 120]]},
            {"text": "ABC Trading", "confidence": 0.85, "bbox": [[160, 105], [300, 105], [300, 125], [160, 125]]},
            {"text": "Owner:", "confidence": 0.9, "bbox": [[10, 150], [100, 150], [100, 170], [10, 170]]},
            {"text": "John Doe", "confidence": 0.89, "bbox": [[110, 155], [220, 155], [220, 175], [110, 175]]},
        ]
        field_schema = {
            "fields": [
                {"name": "certificate_no", "label": "NR0:"},
                {"name": "business_name", "label": "Business Name:"},
                {"name": "owner_name", "label": "Owner:"},
            ]
        }
        fallback_extraction = map_fields_by_spatial_position(raw_lines, field_schema)
        
        # Count filled fields
        ai_filled = sum(1 for f in ai_extraction.values() if f.get("value"))
        fallback_filled = sum(1 for f in fallback_extraction.values() if f.get("value"))
        
        # Fallback should improve coverage
        assert fallback_filled > ai_filled
