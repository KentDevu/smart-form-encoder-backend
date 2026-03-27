"""Test suite for OCR confidence validation and fallback logic.

This module tests the confidence validation and fallback mechanisms added in the
OCR confidence regression fixes:

1. _validate_and_fallback_confidence() — Per-field confidence validation
2. Module-level validation in ocr_unified.py — API response parsing
3. Integration with field mapping — End-to-end validation

Test Categories:
- Valid confidence passthrough
- Missing confidence with fallback strategies
- Invalid confidence type/range handling
- Raw lines matching and confidence calculation
- Field value edge cases (empty, single-char)
- Integration with API response validation
"""

import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from typing import Any

from app.services.ocr_task import _validate_and_fallback_confidence


# ============================================================================
# FIXTURES: Test data for confidence validation scenarios
# ============================================================================

@pytest.fixture
def sample_raw_lines():
    """Sample OCR raw_lines with text and confidence scores."""
    return [
        {"text": "John Smith", "confidence": 0.95},
        {"text": "john smith", "confidence": 0.92},
        {"text": "123-456-7890", "confidence": 0.88},
        {"text": "01/15/2020", "confidence": 0.91},
        {"text": "Single", "confidence": 0.85},
    ]


@pytest.fixture
def field_data_valid_confidence():
    """Field data with valid confidence values."""
    return {
        "low": {"value": "test", "confidence": 0.0},
        "mid": {"value": "test", "confidence": 0.5},
        "high": {"value": "test", "confidence": 0.95},
        "max": {"value": "test", "confidence": 1.0},
    }


@pytest.fixture
def field_data_missing_confidence():
    """Field data with missing confidence key."""
    return {
        "name": {"value": "John Smith"},
        "phone": {"value": "123-456-7890"},
        "date": {"value": "01/15/2020"},
    }


@pytest.fixture
def field_data_invalid_confidence():
    """Field data with invalid confidence values."""
    return {
        "string_conf": {"value": "test", "confidence": "high"},
        "list_conf": {"value": "test", "confidence": [0.9]},
        "dict_conf": {"value": "test", "confidence": {"score": 0.9}},
        "out_of_range_high": {"value": "test", "confidence": 1.5},
        "out_of_range_low": {"value": "test", "confidence": -0.2},
    }


# ============================================================================
# TEST CLASS 1: Valid Confidence Passthrough
# ============================================================================

class TestValidConfidencePassthrough:
    """Test that valid confidence values pass through unchanged."""
    
    @pytest.mark.parametrize("conf_value", [0.0, 0.25, 0.5, 0.75, 0.95, 1.0])
    def test_valid_confidence_passthrough(self, conf_value):
        """Test that valid confidence in [0.0, 1.0] is returned unchanged."""
        field_data = {"value": "test_value", "confidence": conf_value}
        
        result = _validate_and_fallback_confidence(
            field_data,
            field_name="test_field",
            raw_lines=None
        )
        
        assert result == conf_value
        assert isinstance(result, float)
    
    def test_int_confidence_converted_to_float(self):
        """Test that integer confidence is converted to float."""
        field_data = {"value": "test", "confidence": 1}  # int, not float
        
        result = _validate_and_fallback_confidence(
            field_data,
            field_name="test_field",
            raw_lines=None
        )
        
        assert result == 1.0
        assert isinstance(result, float)


# ============================================================================
# TEST CLASS 2: Missing Confidence Key Fallback
# ============================================================================

class TestMissingConfidenceFallback:
    """Test fallback logic when confidence key is missing."""
    
    def test_missing_confidence_no_raw_lines_returns_default(self, caplog):
        """Test that missing confidence without raw_lines returns 0.5."""
        field_data = {"value": "some_value"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="address",
                raw_lines=None
            )
        
        assert result == 0.5
        assert "[CONFIDENCE-MISSING]" in caplog.text
        assert "address" in caplog.text
    
    def test_missing_confidence_empty_field_value_returns_default(self, caplog):
        """Test that missing confidence with empty field_value returns 0.5."""
        field_data = {"value": ""}  # Empty value
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="optional_field",
                raw_lines=None
            )
        
        assert result == 0.5
        assert "[CONFIDENCE-MISSING]" in caplog.text
    
    def test_missing_confidence_with_matching_raw_lines(self, caplog, sample_raw_lines):
        """Test that missing confidence with matching raw_lines calculates from them."""
        field_data = {"value": "John Smith"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="full_name",
                raw_lines=sample_raw_lines
            )
        
        # Average of 0.95 and 0.92 = 0.935
        assert 0.92 <= result <= 0.96  # Allow small floating point variance
        assert "[CONFIDENCE-FALLBACK]" in caplog.text
        assert "calculated from" in caplog.text
    
    def test_missing_confidence_single_char_field_no_matching(self, caplog, sample_raw_lines):
        """Test that single-char field values avoid over-matching raw_lines."""
        field_data = {"value": "a"}  # Single char, should skip raw_lines matching
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="abbreviation",
                raw_lines=sample_raw_lines
            )
        
        # Should return default 0.5, not try to match from raw_lines
        assert result == 0.5
        assert "[CONFIDENCE-MISSING]" in caplog.text
    
    def test_missing_confidence_two_char_field_exact_match(self, caplog):
        """Test that 2-char fields use exact matching on raw_lines."""
        raw_lines = [
            {"text": "OK", "confidence": 0.99},
            {"text": "ok", "confidence": 0.98},
        ]
        field_data = {"value": "OK"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="status",
                raw_lines=raw_lines
            )
        
        # Should match "OK" and "ok" (case-insensitive) and average: (0.99 + 0.98) / 2 = 0.985
        assert 0.97 <= result <= 1.0
        assert "[CONFIDENCE-FALLBACK]" in caplog.text


# ============================================================================
# TEST CLASS 3: Invalid Confidence Type Handling
# ============================================================================

class TestInvalidConfidenceType:
    """Test handling of non-numeric confidence values."""
    
    @pytest.mark.parametrize("invalid_value", [
        "high",
        "0.95",
        ["0.95"],
        {"score": 0.95},
        None,
    ])
    def test_non_numeric_confidence_returns_default(self, invalid_value, caplog):
        """Test that non-numeric confidence falls back to 0.5."""
        field_data = {"value": "test_value", "confidence": invalid_value}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="test_field",
                raw_lines=None
            )
        
        assert result == 0.5
        assert "[CONFIDENCE-NOT-NUMERIC]" in caplog.text or "[CONFIDENCE-INVALID-TYPE]" in caplog.text
    
    def test_boolean_confidence_treated_as_numeric(self):
        """Test that boolean confidence is treated as numeric (True→1.0, False→0.0).
        
        Note: In Python, bool is a subclass of int, so isinstance(True, int) is True.
        This is expected behavior: True→1.0, False→0.0.
        """
        # Boolean True should be converted to float 1.0
        field_data_true = {"value": "test", "confidence": True}
        result_true = _validate_and_fallback_confidence(
            field_data_true,
            field_name="test_field",
            raw_lines=None
        )
        assert result_true == 1.0
        
        # Boolean False should be converted to float 0.0
        field_data_false = {"value": "test", "confidence": False}
        result_false = _validate_and_fallback_confidence(
            field_data_false,
            field_name="test_field",
            raw_lines=None
        )
        assert result_false == 0.0


# ============================================================================
# TEST CLASS 4: Out-of-Range Confidence Clamping
# ============================================================================

class TestOutOfRangeConfidenceClamping:
    """Test that out-of-range confidence values are clamped."""
    
    @pytest.mark.parametrize("out_of_range,expected_clamped", [
        (1.5, 1.0),    # Above max
        (2.0, 1.0),    # Way above max
        (-0.2, 0.0),   # Negative
        (-1.0, 0.0),   # Way negative
    ])
    def test_out_of_range_confidence_clamped(self, out_of_range, expected_clamped, caplog):
        """Test that out-of-range confidence is clamped to [0.0, 1.0]."""
        field_data = {"value": "test", "confidence": out_of_range}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="test_field",
                raw_lines=None
            )
        
        assert result == expected_clamped
        assert "[CONFIDENCE-OUT-OF-RANGE]" in caplog.text
        assert "clamped" in caplog.text


# ============================================================================
# TEST CLASS 5: Raw Lines Matching and Calculation
# ============================================================================

class TestRawLinesMatching:
    """Test confidence calculation from raw OCR lines."""
    
    def test_word_boundary_matching_for_long_values(self, caplog):
        """Test word boundary regex matching for 3+ char values."""
        raw_lines = [
            {"text": "The company name is ABC", "confidence": 0.90},
            {"text": "ABC is valid", "confidence": 0.92},
        ]
        field_data = {"value": "ABC"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="company",
                raw_lines=raw_lines
            )
        
        # Should match "ABC" as word boundary, average: (0.90 + 0.92) / 2 = 0.91
        assert 0.89 <= result <= 0.93
        assert "calculated from 2 matching" in caplog.text
    
    def test_word_boundary_no_substring_match(self, caplog):
        """Test that word boundary prevents substring matches."""
        raw_lines = [
            {"text": "ABCD123", "confidence": 0.95},  # Contains "ABC" but not as word boundary
            {"text": "ABC is here", "confidence": 0.90},  # Contains "ABC" as word
        ]
        field_data = {"value": "ABC"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="code",
                raw_lines=raw_lines
            )
        
        # Should match only "ABC is here", not "ABCD123"
        assert result == 0.90
    
    def test_no_matching_lines_returns_default(self, caplog):
        """Test that no matching raw_lines returns default 0.5."""
        raw_lines = [
            {"text": "John Smith", "confidence": 0.95},
            {"text": "maria", "confidence": 0.88},
        ]
        field_data = {"value": "unknown_value"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="name",
                raw_lines=raw_lines
            )
        
        assert result == 0.5
        assert "[CONFIDENCE-MISSING]" in caplog.text
    
    def test_raw_lines_confidence_clamped_before_averaging(self, caplog):
        """Test that raw_lines confidence is clamped before averaging."""
        raw_lines = [
            {"text": "valid_text", "confidence": 0.95},
            {"text": "valid_text", "confidence": 1.5},  # Out of range
            {"text": "valid_text", "confidence": -0.1},  # Negative
        ]
        field_data = {"value": "valid_text"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="field",
                raw_lines=raw_lines
            )
        
        # Should clamp 1.5 → 1.0, -0.1 → 0.0, average: (0.95 + 1.0 + 0.0) / 3
        assert 0.60 <= result <= 0.68  # Approximately 0.65


# ============================================================================
# TEST CLASS 6: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_field_value_with_raw_lines(self, caplog, sample_raw_lines):
        """Test that empty field_value doesn't match raw_lines."""
        field_data = {"value": ""}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="field",
                raw_lines=sample_raw_lines
            )
        
        assert result == 0.5
    
    def test_whitespace_only_field_value(self, caplog, sample_raw_lines):
        """Test that whitespace-only field_value is treated as empty."""
        field_data = {"value": "   "}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="field",
                raw_lines=sample_raw_lines
            )
        
        # After strip(), becomes empty, so should return 0.5
        assert result == 0.5
    
    def test_field_data_without_value_key(self, caplog, sample_raw_lines):
        """Test that missing 'value' key uses empty string, but valid confidence is returned.
        
        If confidence IS provided and valid, it should be used even without a value.
        """
        field_data = {"confidence": 0.9}  # No 'value' key
        
        result = _validate_and_fallback_confidence(
            field_data,
            field_name="field",
            raw_lines=sample_raw_lines
        )
        
        # Confidence is valid, so it should be returned (value key is not required)
        assert result == 0.9
    
    def test_raw_lines_with_missing_text_key(self, caplog):
        """Test that raw_lines entries without 'text' key don't crash."""
        raw_lines = [
            {"confidence": 0.95},  # No 'text' key
            {"text": "Some Text", "confidence": 0.90},
        ]
        field_data = {"value": "Some Text"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="field",
                raw_lines=raw_lines
            )
        
        # Should handle gracefully and match only the second entry
        assert result == 0.90
    
    def test_empty_raw_lines_list(self, caplog):
        """Test that empty raw_lines list returns default."""
        field_data = {"value": "test"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="field",
                raw_lines=[]
            )
        
        assert result == 0.5
    
    def test_special_regex_characters_in_field_value(self, caplog):
        """Test that special regex characters are properly escaped in regex patterns.
        
        Note: Field values starting with special characters (like $) don't work with word
        boundaries since \b requires word characters. Use the 2-char exact match path instead.
        """
        # Use numeric value with special chars in the middle instead of at the start
        raw_lines = [
            {"text": "amount 1000.50 dollars", "confidence": 0.92},
            {"text": "1000.50 is valid", "confidence": 0.90},
        ]
        field_data = {"value": "1000.50"}
        
        with caplog.at_level(logging.WARNING):
            result = _validate_and_fallback_confidence(
                field_data,
                field_name="price",
                raw_lines=raw_lines
            )
        
        # Should escape "." and match correctly with word boundaries
        assert 0.88 <= result <= 0.93  # Average of 0.92 and 0.90


# ============================================================================
# TEST CLASS 7: Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests with real-world scenarios."""
    
    def test_typical_form_field_extraction(self):
        """Test typical form field extraction scenario."""
        # Simulate API response for a name field
        field_data = {"value": "Maria Santos", "confidence": 0.93}
        
        result = _validate_and_fallback_confidence(
            field_data,
            field_name="full_name",
            raw_lines=[]
        )
        
        assert result == 0.93
    
    def test_degraded_confidence_fallback_scenario(self):
        """Test scenario where confidence is missing and must be calculated."""
        raw_lines = [
            {"text": "Maria", "confidence": 0.88},
            {"text": "Santos", "confidence": 0.85},
            {"text": "Maria Santos", "confidence": 0.86},
        ]
        field_data = {"value": "Maria Santos"}  # No confidence key
        
        result = _validate_and_fallback_confidence(
            field_data,
            field_name="full_name",
            raw_lines=raw_lines
        )
        
        # Should match "Maria Santos" line, return 0.86
        assert result == 0.86
    
    def test_confidence_with_optional_raw_lines_none(self):
        """Test that None raw_lines doesn't crash."""
        field_data = {"value": "test", "confidence": 0.75}
        
        result = _validate_and_fallback_confidence(
            field_data,
            field_name="field",
            raw_lines=None
        )
        
        assert result == 0.75
    
    def test_multiple_field_validation_sequence(self):
        """Test validating multiple fields in sequence."""
        raw_lines = [
            {"text": "2020", "confidence": 0.94},
            {"text": "01/15/2020", "confidence": 0.91},
        ]
        
        # Field 1: Valid confidence
        result1 = _validate_and_fallback_confidence(
            {"value": "John", "confidence": 0.85},
            field_name="first_name",
            raw_lines=raw_lines
        )
        assert result1 == 0.85
        
        # Field 2: Missing confidence, should calculate
        result2 = _validate_and_fallback_confidence(
            {"value": "01/15/2020"},
            field_name="birth_date",
            raw_lines=raw_lines
        )
        assert result2 == 0.91
        
        # Field 3: Invalid confidence, should use fallback
        result3 = _validate_and_fallback_confidence(
            {"value": "test", "confidence": "high"},
            field_name="field3",
            raw_lines=raw_lines
        )
        assert result3 == 0.5


# ============================================================================
# TEST CLASS 8: Logging Verification
# ============================================================================

class TestLoggingOutput:
    """Verify correct logging at each validation stage."""
    
    def test_valid_confidence_no_warning_logged(self, caplog):
        """Test that valid confidence doesn't produce warnings."""
        field_data = {"value": "test", "confidence": 0.85}
        
        with caplog.at_level(logging.WARNING):
            _validate_and_fallback_confidence(
                field_data,
                field_name="field",
                raw_lines=None
            )
        
        # Should have no warnings
        assert not any("[CONFIDENCE-" in msg for msg in caplog.text.split('\n'))
    
    def test_fallback_warning_format(self, caplog):
        """Test that fallback warning includes required information."""
        raw_lines = [{"text": "test", "confidence": 0.88}]
        field_data = {"value": "test"}
        
        with caplog.at_level(logging.WARNING):
            _validate_and_fallback_confidence(
                field_data,
                field_name="sample_field",
                raw_lines=raw_lines
            )
        
        # Check log format
        log_text = caplog.text
        assert "[CONFIDENCE-FALLBACK]" in log_text
        assert "sample_field" in log_text
        assert "calculated from" in log_text or "matching OCR" in log_text


# ============================================================================
# PARAMETRIZED EDGE CASE TESTS
# ============================================================================

class TestParametrizedEdgeCases:
    """Parametrized tests for comprehensive coverage."""
    
    @pytest.mark.parametrize(
        "field_value,raw_lines_count,expected_result_type",
        [
            ("normal_value", 5, float),
            ("", 0, float),
            ("a", 10, float),
            ("💾", 3, float),  # Unicode character
        ]
    )
    def test_various_field_value_types(self, field_value, raw_lines_count, expected_result_type):
        """Test with various field value types."""
        raw_lines = [
            {"text": f"line_{i}", "confidence": 0.90}
            for i in range(raw_lines_count)
        ]
        field_data = {
            "value": field_value,
            "confidence": 0.75,
        }
        
        result = _validate_and_fallback_confidence(
            field_data,
            field_name="field",
            raw_lines=raw_lines
        )
        
        assert isinstance(result, expected_result_type)
        assert 0.0 <= result <= 1.0
