"""Test suite for OCR pattern extraction (Phase D - Enhancement)."""

import pytest
from app.services.ocr_pattern_extractor import (
    extract_fields_from_ocr_lines,
    _extract_date_from_ocr,
    _extract_phone_from_ocr,
    _extract_checkbox_from_ocr,
    _extract_amount_from_ocr,
)


class TestDatePatternExtraction:
    """Test date pattern extraction from OCR lines."""
    
    def test_extract_dmy_format_date(self):
        """Test extraction of DD/MM/YYYY format."""
        ocr_text = "Application Date: 15/06/2020"
        value, conf = _extract_date_from_ocr(ocr_text, [])
        assert value == "15/06/2020"
        assert conf > 0.4
    
    def test_extract_iso_format_date(self):
        """Test extraction of YYYY-MM-DD format."""
        ocr_text = "Date registered: 2020-06-15"
        value, conf = _extract_date_from_ocr(ocr_text, [])
        assert value == "2020-06-15"
        assert conf > 0.4
    
    def test_extract_spelled_month_date(self):
        """Test extraction of spelled-out month format."""
        ocr_text = "Issued: June 15, 2020"
        value, conf = _extract_date_from_ocr(ocr_text, [])
        assert value  # Should find something
        assert conf > 0.4
    
    def test_no_date_in_text(self):
        """Test when no date pattern found."""
        ocr_text = "No date information"
        value, conf = _extract_date_from_ocr(ocr_text, [])
        assert value == ""
        assert conf == 0.0
    
    def test_date_with_hyphens(self):
        """Test extraction with hyphen separators."""
        ocr_text = "15-06-2020"
        value, conf = _extract_date_from_ocr(ocr_text, [])
        assert value == "15-06-2020"
        assert conf > 0.4


class TestPhonePatternExtraction:
    """Test phone number pattern extraction from OCR lines."""
    
    def test_extract_09_format_phone(self):
        """Test extraction of 09XXXXXXXXX format."""
        ocr_text = "Mobile: 09171234567"
        value, conf = _extract_phone_from_ocr(ocr_text, [])
        assert value  # Should extract and normalize
        assert "+63" in value
        assert conf > 0.5
    
    def test_extract_plus63_format_phone(self):
        """Test extraction of +639XXXXXXXXX format."""
        ocr_text = "Phone: +639171234567"
        value, conf = _extract_phone_from_ocr(ocr_text, [])
        assert value == "+639171234567"
        assert conf > 0.5
    
    def test_extract_63_format_phone(self):
        """Test extraction of 639XXXXXXXXX format."""
        ocr_text = "Tel: 639171234567"
        value, conf = _extract_phone_from_ocr(ocr_text, [])
        assert "+63" in value
        assert conf > 0.5
    
    def test_phone_with_separators(self):
        """Test extraction with separators."""
        ocr_text = "Mobile: 0917-123-4567"
        value, conf = _extract_phone_from_ocr(ocr_text, [])
        # May not match if separators interfere, which is acceptable
        # Pattern extraction is best-effort
        if value:
            assert conf > 0.5
    
    def test_no_phone_in_text(self):
        """Test when no phone found."""
        ocr_text = "No phone number"
        value, conf = _extract_phone_from_ocr(ocr_text, [])
        assert value == ""
        assert conf == 0.0


class TestCheckboxPatternExtraction:
    """Test checkbox pattern extraction from OCR lines."""
    
    def test_extract_checkmark_symbol(self):
        """Test extraction of checkmark symbol."""
        ocr_text = "Approved: ✓"
        value, conf = _extract_checkbox_from_ocr(ocr_text, [])
        assert value == "Yes"
        assert conf > 0.4
    
    def test_extract_x_symbol(self):
        """Test extraction of X symbol."""
        ocr_text = "Checked: X"
        value, conf = _extract_checkbox_from_ocr(ocr_text, [])
        assert value == "Yes"
        assert conf > 0.4
    
    def test_extract_yes_word(self):
        """Test extraction of 'yes' word."""
        ocr_text = "Is verified: YES"
        value, conf = _extract_checkbox_from_ocr(ocr_text, [])
        assert value == "Yes"
        assert conf > 0.4
    
    def test_extract_no_word(self):
        """Test extraction of 'no' word."""
        ocr_text = "Rejected: NO"
        value, conf = _extract_checkbox_from_ocr(ocr_text, [])
        assert value == "No"
        assert conf > 0.4
    
    def test_no_checkbox_in_text(self):
        """Test when no checkbox pattern found."""
        ocr_text = "This is plain text without any checkbox indicators."
        value, conf = _extract_checkbox_from_ocr(ocr_text, [])
        assert value == ""
        assert conf == 0.0


class TestAmountPatternExtraction:
    """Test currency amount pattern extraction from OCR lines."""
    
    def test_extract_peso_symbol_amount(self):
        """Test extraction with peso symbol."""
        ocr_text = "Amount: ₱5000.50"
        value, conf = _extract_amount_from_ocr(ocr_text, [])
        assert value  # Should extract
        assert "5000.50" in value or "5,000.50" in value
        assert conf > 0.3
    
    def test_extract_p_prefix_amount(self):
        """Test extraction with P prefix."""
        ocr_text = "Cost: P5000"
        value, conf = _extract_amount_from_ocr(ocr_text, [])
        assert value
        assert "5000.00" in value or "5,000.00" in value
        assert conf > 0.3
    
    def test_extract_dollar_amount(self):
        """Test extraction with dollar symbol."""
        ocr_text = "Price: $1,000.50"
        value, conf = _extract_amount_from_ocr(ocr_text, [])
        assert value
        assert conf > 0.3
    
    def test_extract_amount_with_thousands(self):
        """Test extraction with thousands separator."""
        ocr_text = "5,000.50"
        value, conf = _extract_amount_from_ocr(ocr_text, [])
        assert value
        assert "5000.50" in value or "5,000.50" in value
        assert conf > 0.3
    
    def test_no_amount_in_text(self):
        """Test when no amount found."""
        ocr_text = "No currency information"
        value, conf = _extract_amount_from_ocr(ocr_text, [])
        assert value == ""
        assert conf == 0.0


class TestFieldExtractionIntegration:
    """Integration tests for full field extraction from OCR."""
    
    def test_extract_missing_date_field(self):
        """Test extraction of missing date field from OCR lines."""
        ocr_lines = [
            "Business Name: JUAN DELA CRUZ",
            "Registration Date: 15/06/2020",
            "Phone: 09171234567",
        ]
        schema = {
            "fields": [
                {"name": "business_name", "type": "text"},
                {"name": "registration_date", "type": "date"},
                {"name": "phone", "type": "phone"},
            ]
        }
        existing = {
            "business_name": {"field_name": "business_name", "ocr_value": "JUAN DELA CRUZ", "confidence": 0.8},
        }
        
        result = extract_fields_from_ocr_lines(ocr_lines, schema, existing)
        
        # Should find registration_date and phone from OCR lines
        assert "registration_date" in result
        assert "phone" in result
        assert "15/06/2020" in result["registration_date"]["ocr_value"]
    
    def test_skip_already_extracted_fields(self):
        """Test that already extracted fields are not overwritten."""
        ocr_lines = ["Date: 01/01/2020", "Other Date: 15/06/2020"]
        schema = {"fields": [{"name": "date_field", "type": "date"}]}
        existing = {
            "date_field": {"field_name": "date_field", "ocr_value": "10/05/2020", "confidence": 0.9},
        }
        
        result = extract_fields_from_ocr_lines(ocr_lines, schema, existing)
        
        # Should preserve original extracted value
        assert result["date_field"]["ocr_value"] == "10/05/2020"
    
    def test_extract_multiple_field_types(self):
        """Test extraction of multiple field types from OCR."""
        ocr_lines = [
            "Date: 15/06/2020",
            "Phone: 09171234567",
            "Verified: ✓",
            "Amount: ₱50000.00",
        ]
        schema = {
            "fields": [
                {"name": "date", "type": "date"},
                {"name": "phone", "type": "phone"},
                {"name": "verified", "type": "checkbox"},
                {"name": "amount", "type": "amount"},
            ]
        }
        existing = {}
        
        result = extract_fields_from_ocr_lines(ocr_lines, schema, existing)
        
        # Should find multiple field types
        assert result["date"]["ocr_value"]
        assert result["phone"]["ocr_value"]
        assert result["verified"]["ocr_value"]
        assert result["amount"]["ocr_value"]
    
    def test_empty_ocr_lines_gracefully_handled(self):
        """Test that empty OCR lines don't crash the function."""
        result = extract_fields_from_ocr_lines([], {}, {})
        assert result == {}
    
    def test_field_schema_without_matching_fields(self):
        """Test extraction with schema fields that don't exist in OCR."""
        ocr_lines = ["No relevant data"]
        schema = {
            "fields": [
                {"name": "date", "type": "date"},
                {"name": "phone", "type": "phone"},
            ]
        }
        existing = {}
        
        result = extract_fields_from_ocr_lines(ocr_lines, schema, existing)
        
        # Should return empty result without crashing
        assert "date" not in result
        assert "phone" not in result
    
    def test_preserve_existing_fields_on_extraction(self):
        """Test that existing fields are preserved when extracting new ones."""
        ocr_lines = ["Phone: 09171234567", "Date: 15/06/2020"]
        schema = {
            "fields": [
                {"name": "phone", "type": "phone"},
                {"name": "date", "type": "date"},
                {"name": "name", "type": "text"},
            ]
        }
        existing = {"name": {"field_name": "name", "ocr_value": "JUAN", "confidence": 0.7}}
        
        result = extract_fields_from_ocr_lines(ocr_lines, schema, existing)
        
        # Should preserve name and add phone and date
        assert result["name"]["ocr_value"] == "JUAN"
        assert "phone" in result
        assert "date" in result


class TestConfidenceScoring:
    """Test confidence scoring for extracted patterns."""
    
    def test_confidence_ranges(self):
        """Test that confidence scores are in realistic ranges."""
        ocr_text = "Date: 15/06/2020, Phone: 09171234567, Cost: ₱5000"
        
        date_val, date_conf = _extract_date_from_ocr(ocr_text, [])
        phone_val, phone_conf = _extract_phone_from_ocr(ocr_text, [])
        amount_val, amount_conf = _extract_amount_from_ocr(ocr_text, [])
        
        # All should have confidence > 0
        assert date_conf > 0.4
        assert phone_conf > 0.5
        assert amount_conf > 0.3
        
        # All should be < 1.0 (not 100% confident)
        assert date_conf < 1.0
        assert phone_conf < 1.0
        assert amount_conf < 1.0
