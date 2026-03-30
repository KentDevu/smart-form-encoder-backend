"""
Unit tests for ocr_preprocessing_hints.py

Tests: anchor finding, pattern extraction, reading order
Coverage: 80%+
"""

import pytest
from typing import Any
from app.services.ocr_preprocessing_hints import (
    AnchorMatch,
    find_anchor_in_raw_lines,
    extract_pattern_matches,
    build_reading_order,
    enrich_template_with_preprocessing_hints,
)


# ============================================================================
# FIXTURES: Sample OCR lines and templates
# ============================================================================

@pytest.fixture
def sample_raw_lines() -> list[dict[str, Any]]:
    """Standard OCR lines from PaddleOCR."""
    return [
        {
            "text": "BUSINESS PERMIT APPLICATION",
            "confidence": 0.95,
            "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]],
        },
        {
            "text": "BUSINESS NAME",
            "confidence": 0.92,
            "bbox": [[10, 50], [150, 50], [150, 70], [10, 70]],
        },
        {
            "text": "ABC Trading Corporation",
            "confidence": 0.88,
            "bbox": [[10, 85], [300, 85], [300, 105], [10, 105]],
        },
        {
            "text": "PROPRIETOR / OWNER",
            "confidence": 0.90,
            "bbox": [[10, 130], [250, 130], [250, 150], [10, 150]],
        },
        {
            "text": "Juan Dela Cruz",
            "confidence": 0.91,
            "bbox": [[10, 165], [200, 165], [200, 185], [10, 185]],
        },
        {
            "text": "CONTACT NUMBER",
            "confidence": 0.89,
            "bbox": [[10, 210], [200, 210], [200, 230], [10, 230]],
        },
        {
            "text": "09175551234",
            "confidence": 0.85,
            "bbox": [[10, 245], [150, 245], [150, 265], [10, 265]],
        },
        {
            "text": "EMAIL ADDRESS",
            "confidence": 0.88,
            "bbox": [[250, 210], [400, 210], [400, 230], [250, 230]],
        },
        {
            "text": "juan.cruz@example.com",
            "confidence": 0.90,
            "bbox": [[250, 245], [450, 245], [450, 265], [250, 265]],
        },
        {
            "text": "TIN / BIR ID",
            "confidence": 0.87,
            "bbox": [[10, 290], [150, 290], [150, 310], [10, 310]],
        },
        {
            "text": "123456789",
            "confidence": 0.86,
            "bbox": [[10, 325], [150, 325], [150, 345], [10, 345]],
        },
        {
            "text": "DATE OF APPLICATION",
            "confidence": 0.91,
            "bbox": [[250, 290], [450, 290], [450, 310], [250, 310]],
        },
        {
            "text": "15/06/2024",
            "confidence": 0.89,
            "bbox": [[250, 325], [350, 325], [350, 345], [250, 345]],
        },
        {
            "text": "AMOUNT",
            "confidence": 0.90,
            "bbox": [[10, 370], [100, 370], [100, 390], [10, 390]],
        },
        {
            "text": "PHP 15,000.00",
            "confidence": 0.88,
            "bbox": [[10, 405], [150, 405], [150, 425], [10, 425]],
        },
    ]


@pytest.fixture
def sample_field_schema() -> dict[str, Any]:
    """Standard form template with extraction hints."""
    return {
        "template_id": "business_permit_001",
        "name": "Business Permit Application",
        "fields": [
            {
                "name": "business_name",
                "label": "Business Name",
                "type": "text",
                "required": True,
                "section": "business_info",
                "extraction": {"anchor_label": "BUSINESS NAME"},
            },
            {
                "name": "proprietor",
                "label": "Proprietor / Owner",
                "type": "text",
                "required": True,
                "section": "owner_info",
                "extraction": {"anchor_label": "PROPRIETOR"},
            },
            {
                "name": "contact_number",
                "label": "Contact Number",
                "type": "phone",
                "required": False,
                "section": "contact",
                "extraction": {"anchor_label": "CONTACT NUMBER"},
            },
            {
                "name": "email",
                "label": "Email Address",
                "type": "email",
                "required": False,
                "section": "contact",
                "extraction": {"anchor_label": "EMAIL ADDRESS"},
            },
            {
                "name": "tin",
                "label": "TIN / BIR ID",
                "type": "text",
                "required": True,
                "section": "identification",
                "extraction": {"anchor_label": "TIN / BIR ID"},
            },
            {
                "name": "application_date",
                "label": "Date of Application",
                "type": "date",
                "required": True,
                "section": "dates",
                "extraction": {"anchor_label": "DATE OF APPLICATION"},
            },
            {
                "name": "amount",
                "label": "Amount",
                "type": "amount",
                "required": False,
                "section": "payment",
                "extraction": {"anchor_label": "AMOUNT"},
            },
        ],
    }


@pytest.fixture
def low_confidence_lines() -> list[dict[str, Any]]:
    """OCR lines with low confidence scores."""
    return [
        {
            "text": "BUSINESS NAME",
            "confidence": 0.65,  # Below typical threshold
            "bbox": [[10, 50], [150, 50], [150, 70], [10, 70]],
        },
        {
            "text": "Some Company Ltd",
            "confidence": 0.60,
            "bbox": [[10, 85], [200, 85], [200, 105], [10, 105]],
        },
    ]


@pytest.fixture
def empty_raw_lines() -> list[dict[str, Any]]:
    """Empty OCR result."""
    return []


@pytest.fixture
def malformed_raw_lines() -> list[dict[str, Any]]:
    """Malformed OCR data (missing fields, bad bbox)."""
    return [
        {"text": "BAD LINE 1"},  # No confidence
        {"confidence": 0.8},  # No text
        {
            "text": "BAD BBOX",
            "confidence": 0.9,
            "bbox": [[10]],  # Invalid bbox
        },
        {
            "text": "NORMAL LINE",
            "confidence": 0.85,
            "bbox": [[10, 20], [100, 20], [100, 40], [10, 40]],
        },
    ]


# ============================================================================
# TESTS: find_anchor_in_raw_lines()
# ============================================================================

class TestFindAnchorInRawLines:
    """Test cases for find_anchor_in_raw_lines."""

    def test_find_anchor_exact_match(self, sample_raw_lines):
        """Exact match for anchor label."""
        result = find_anchor_in_raw_lines("BUSINESS NAME", sample_raw_lines)
        assert result.found is True
        assert result.anchor_text == "BUSINESS NAME"
        assert result.line_index == 1
        assert result.anchor_confidence >= 0.8
        assert result.anchor_confidence <= 1.0

    def test_find_anchor_case_insensitive(self, sample_raw_lines):
        """Anchor matching is case-insensitive."""
        result = find_anchor_in_raw_lines("business name", sample_raw_lines)
        assert result.found is True
        assert result.anchor_text == "BUSINESS NAME"

    def test_find_anchor_fuzzy_match(self, sample_raw_lines):
        """Partial match (substring) for anchor label."""
        result = find_anchor_in_raw_lines("PROPRIETOR", sample_raw_lines)
        assert result.found is True
        assert "PROPRIETOR" in result.anchor_text
        assert result.anchor_confidence > 0.7

    def test_find_anchor_context_extraction(self, sample_raw_lines):
        """Extract context lines after anchor."""
        result = find_anchor_in_raw_lines("BUSINESS NAME", sample_raw_lines)
        assert result.found is True
        assert len(result.context_lines) > 0
        assert "ABC Trading" in result.context_lines[0]

    def test_find_anchor_not_found(self, sample_raw_lines):
        """No match for anchor label."""
        result = find_anchor_in_raw_lines("NONEXISTENT FIELD", sample_raw_lines)
        assert result.found is False
        assert result.line_index is None
        assert result.anchor_text is None

    def test_find_anchor_below_threshold(self, low_confidence_lines):
        """Anchor below confidence threshold rejected."""
        result = find_anchor_in_raw_lines(
            "BUSINESS NAME",
            low_confidence_lines,
            threshold=0.8
        )
        assert result.found is False

    def test_find_anchor_empty_lines(self, empty_raw_lines):
        """Handle empty OCR result."""
        result = find_anchor_in_raw_lines("ANY LABEL", empty_raw_lines)
        assert result.found is False

    def test_find_anchor_with_reading_order(self, sample_raw_lines):
        """Reading order should match line index."""
        result = find_anchor_in_raw_lines("CONTACT NUMBER", sample_raw_lines)
        assert result.found is True
        assert result.reading_order == result.line_index

    def test_find_anchor_returns_anchor_match_dataclass(self, sample_raw_lines):
        """Return type is AnchorMatch dataclass."""
        result = find_anchor_in_raw_lines("BUSINESS NAME", sample_raw_lines)
        assert isinstance(result, AnchorMatch)

    def test_find_anchor_multiple_occurrences(self):
        """If multiple matches, return first one."""
        lines = [
            {"text": "AMOUNT", "confidence": 0.9, "bbox": [[0, 0], [50, 0], [50, 20], [0, 20]]},
            {"text": "Amount: 1000", "confidence": 0.8, "bbox": [[0, 30], [150, 30], [150, 50], [0, 50]]},
            {"text": "AMOUNT", "confidence": 0.95, "bbox": [[0, 100], [50, 100], [50, 120], [0, 120]]},
        ]
        result = find_anchor_in_raw_lines("AMOUNT", lines)
        assert result.found is True
        assert result.line_index == 0  # First match


# ============================================================================
# TESTS: extract_pattern_matches()
# ============================================================================

class TestExtractPatternMatches:
    """Test cases for extract_pattern_matches."""

    def test_extract_phone_patterns(self, sample_raw_lines):
        """Extract Philippine phone number patterns."""
        matches = extract_pattern_matches(sample_raw_lines)
        assert "phone" in matches
        assert any("9175551234" in m or "0917" in m for m in matches["phone"])

    def test_extract_email_patterns(self, sample_raw_lines):
        """Extract email addresses."""
        matches = extract_pattern_matches(sample_raw_lines)
        assert "email" in matches
        assert any("juan.cruz@example.com" in m for m in matches["email"])

    def test_extract_date_patterns(self, sample_raw_lines):
        """Extract date patterns (DD/MM/YYYY, YYYY-MM-DD)."""
        matches = extract_pattern_matches(sample_raw_lines)
        assert "date" in matches
        assert any("15/06" in m or "2024" in m for m in matches["date"])

    def test_extract_tin_patterns(self, sample_raw_lines):
        """Extract TIN (9-digit numbers)."""
        matches = extract_pattern_matches(sample_raw_lines)
        assert "tin" in matches
        assert "123456789" in matches["tin"]

    def test_extract_amount_patterns(self, sample_raw_lines):
        """Extract currency amounts (PHP, ₱)."""
        matches = extract_pattern_matches(sample_raw_lines)
        assert "amount" in matches
        assert any("15,000" in m or "PHP" in m for m in matches["amount"])

    def test_extract_patterns_empty_input(self, empty_raw_lines):
        """Handle empty OCR result."""
        matches = extract_pattern_matches(empty_raw_lines)
        assert isinstance(matches, dict)
        for key in ["phone", "date", "email", "tin", "amount"]:
            assert key in matches
            assert isinstance(matches[key], list)

    def test_extract_patterns_no_duplicates(self):
        """No duplicate matches returned."""
        lines = [
            {"text": "Call me at 09175551234"},
            {"text": "My number is 09175551234"},
        ]
        matches = extract_pattern_matches(lines)
        assert len(matches["phone"]) == 1

    def test_extract_patterns_case_insensitive(self):
        """Pattern extraction is case-insensitive where applicable."""
        lines = [
            {"text": "EMAIL: JUAN@EXAMPLE.COM"},
            {"text": "Email: juan@example.com"},
        ]
        matches = extract_pattern_matches(lines)
        assert "juan@example.com" in [m.lower() for m in matches["email"]]

    def test_extract_patterns_monetary_formats(self):
        """Handle various monetary formats."""
        lines = [
            {"text": "PHP 100,000"},
            {"text": "₱100000.50"},
            {"text": "PHP 50"},
        ]
        matches = extract_pattern_matches(lines)
        assert "amount" in matches
        assert len(matches["amount"]) > 0


# ============================================================================
# TESTS: build_reading_order()
# ============================================================================

class TestBuildReadingOrder:
    """Test cases for build_reading_order."""

    def test_build_reading_order_top_to_bottom(self, sample_raw_lines):
        """Reading order: top-to-bottom, left-to-right."""
        ordered = build_reading_order(sample_raw_lines)
        assert len(ordered) == len(sample_raw_lines)
        
        # Y coordinates should be monotonically increasing or equal
        y_coords = [line["y"] for line in ordered]
        for i in range(1, len(y_coords)):
            assert y_coords[i] >= y_coords[i - 1]

    def test_build_reading_order_includes_text(self, sample_raw_lines):
        """Reading order includes text content."""
        ordered = build_reading_order(sample_raw_lines)
        for line in ordered:
            assert "text" in line
            assert len(line["text"]) > 0

    def test_build_reading_order_includes_coordinates(self, sample_raw_lines):
        """Reading order includes x,y coordinates."""
        ordered = build_reading_order(sample_raw_lines)
        for line in ordered:
            assert "x" in line
            assert "y" in line
            assert isinstance(line["x"], (int, float))
            assert isinstance(line["y"], (int, float))

    def test_build_reading_order_preserves_confidence(self, sample_raw_lines):
        """Reading order preserves OCR confidence."""
        ordered = build_reading_order(sample_raw_lines)
        for line in ordered:
            assert "confidence" in line

    def test_build_reading_order_empty_input(self, empty_raw_lines):
        """Handle empty OCR result."""
        ordered = build_reading_order(empty_raw_lines)
        assert ordered == []

    def test_build_reading_order_malformed_bbox(self, malformed_raw_lines):
        """Handle malformed bounding boxes gracefully."""
        ordered = build_reading_order(malformed_raw_lines)
        # Should not crash; may have default coordinates
        assert isinstance(ordered, list)

    def test_build_reading_order_same_y_sorted_by_x(self):
        """Lines at same Y coordinate sorted by X."""
        lines = [
            {"text": "A", "confidence": 0.9, "bbox": [[100, 10], [150, 10], [150, 30], [100, 30]]},
            {"text": "B", "confidence": 0.9, "bbox": [[50, 10], [100, 10], [100, 30], [50, 30]]},
            {"text": "C", "confidence": 0.9, "bbox": [[150, 10], [200, 10], [200, 30], [150, 30]]},
        ]
        ordered = build_reading_order(lines)
        texts = [line["text"] for line in ordered]
        assert texts == ["B", "A", "C"]

    def test_build_reading_order_line_numbers(self, sample_raw_lines):
        """Reading order includes original line numbers."""
        ordered = build_reading_order(sample_raw_lines)
        for line in ordered:
            assert "line_no" in line


# ============================================================================
# TESTS: enrich_template_with_preprocessing_hints()
# ============================================================================

class TestEnrichTemplateWithPreprocessingHints:
    """Test cases for enrich_template_with_preprocessing_hints."""

    def test_enrich_template_returns_enriched_schema(self, sample_raw_lines, sample_field_schema):
        """Enriched template includes all original fields."""
        enriched = enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        assert "fields" in enriched
        assert len(enriched["fields"]) == len(sample_field_schema["fields"])

    def test_enrich_template_adds_pattern_matches(self, sample_raw_lines, sample_field_schema):
        """Enriched template includes pattern_matches."""
        enriched = enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        assert "pattern_matches" in enriched
        assert isinstance(enriched["pattern_matches"], dict)

    def test_enrich_template_adds_reading_order(self, sample_raw_lines, sample_field_schema):
        """Enriched template includes reading_order."""
        enriched = enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        assert "reading_order" in enriched
        assert isinstance(enriched["reading_order"], list)

    def test_enrich_template_adds_preprocessed_per_field(self, sample_raw_lines, sample_field_schema):
        """Each field gets a preprocessed section."""
        enriched = enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        for field in enriched["fields"]:
            assert "preprocessed" in field

    def test_enrich_template_preprocessed_has_anchor_found(self, sample_raw_lines, sample_field_schema):
        """Preprocessed section includes anchor_found flag."""
        enriched = enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        for field in enriched["fields"]:
            assert "anchor_found" in field["preprocessed"]

    def test_enrich_template_does_not_mutate_original(self, sample_raw_lines, sample_field_schema):
        """Original field_schema is not mutated (deepcopy)."""
        original_fields_count = len(sample_field_schema["fields"])
        enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        assert len(sample_field_schema["fields"]) == original_fields_count
        assert "preprocessed" not in sample_field_schema["fields"][0]

    def test_enrich_template_empty_ocr(self, empty_raw_lines, sample_field_schema):
        """Handle empty OCR result."""
        enriched = enrich_template_with_preprocessing_hints(empty_raw_lines, sample_field_schema)
        assert enriched is not None
        for field in enriched["fields"]:
            assert field["preprocessed"]["anchor_found"] is False

    def test_enrich_template_missing_extraction_hints(self):
        """Handle fields without extraction hints."""
        raw_lines = [{"text": "Any", "confidence": 0.8, "bbox": [[0, 0], [50, 0], [50, 20], [0, 20]]}]
        schema = {
            "fields": [
                {
                    "name": "field1",
                    "label": "Field 1",
                    "type": "text",
                    # No "extraction" key
                }
            ]
        }
        enriched = enrich_template_with_preprocessing_hints(raw_lines, schema)
        assert enriched["fields"][0]["preprocessed"]["anchor_found"] is False

    def test_enrich_template_validates_anchors_found(self, sample_raw_lines, sample_field_schema):
        """Validate that anchors are correctly marked as found."""
        enriched = enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        business_name_field = enriched["fields"][0]  # business_name
        assert business_name_field["preprocessed"]["anchor_found"] is True
        assert business_name_field["preprocessed"]["anchor_text"] == "BUSINESS NAME"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestPreprocessingHintsIntegration:
    """Integration tests across multiple preprocessing functions."""

    def test_full_preprocessing_pipeline(self, sample_raw_lines, sample_field_schema):
        """Full pipeline: enrich → check anchors → check patterns → check reading order."""
        enriched = enrich_template_with_preprocessing_hints(sample_raw_lines, sample_field_schema)
        
        # Validate all components are present and consistent
        assert len(enriched["reading_order"]) == len(sample_raw_lines)
        assert len(enriched["pattern_matches"]) > 0
        assert all("preprocessed" in f for f in enriched["fields"])

    def test_preprocessing_with_real_form_scenario(self):
        """Simulate real form processing scenario."""
        raw_lines = [
            {"text": "CEDULA / COMMUNITY TAX CERTIFICATE", "confidence": 0.93, "bbox": [[10, 20], [400, 20], [400, 40], [10, 40]]},
            {"text": "Name:", "confidence": 0.91, "bbox": [[10, 70], [100, 70], [100, 90], [10, 90]]},
            {"text": "Maria Santos Garcia", "confidence": 0.87, "bbox": [[120, 70], [300, 70], [300, 90], [120, 90]]},
            {"text": "Sex: F", "confidence": 0.92, "bbox": [[10, 110], [100, 110], [100, 130], [10, 130]]},
            {"text": "Date of Birth: 05/15/1985", "confidence": 0.88, "bbox": [[120, 110], [300, 110], [300, 130], [120, 130]]},
            {"text": "Citizenship: Filipino", "confidence": 0.90, "bbox": [[10, 150], [200, 150], [200, 170], [10, 170]]},
        ]
        
        schema = {
            "fields": [
                {"name": "name", "label": "Name", "type": "text", "section": "personal", "extraction": {"anchor_label": "Name:"}},
                {"name": "dob", "label": "Date of Birth", "type": "date", "section": "personal", "extraction": {"anchor_label": "Date of Birth:"}},
                {"name": "citizenship", "label": "Citizenship", "type": "text", "section": "personal", "extraction": {"anchor_label": "Citizenship:"}},
            ]
        }
        
        enriched = enrich_template_with_preprocessing_hints(raw_lines, schema)
        
        # Verify extractable patterns
        assert enriched["pattern_matches"]["date"]  # Should find date
        
        # Verify anchors
        assert enriched["fields"][0]["preprocessed"]["anchor_found"]
        assert enriched["fields"][1]["preprocessed"]["anchor_found"]
        assert enriched["fields"][2]["preprocessed"]["anchor_found"]
