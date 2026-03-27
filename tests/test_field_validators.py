"""Comprehensive test suite for field validators (Phase C - TDD RED Phase)."""

import pytest
from app.services.forms.field_validators import (
    validate_date,
    validate_phone,
    validate_checkbox,
    validate_amount,
    validate_required,
)


# =============================================================================
# DATE VALIDATOR TESTS (15 tests)
# =============================================================================

class TestValidateDateValidator:
    """Test date validation and normalization."""
    
    def test_valid_dmy_format_with_slashes(self):
        """Test DD/MM/YYYY format."""
        value, conf_adj = validate_date("15/06/1985", 0.5)
        assert value == "15/06/1985"
        assert conf_adj == 0.10
    
    def test_valid_dmy_format_with_hyphens(self):
        """Test DD-MM-YYYY format."""
        value, conf_adj = validate_date("15-06-1985", 0.5)
        assert value == "15/06/1985"
        assert conf_adj == 0.10
    
    def test_valid_iso_format(self):
        """Test YYYY-MM-DD ISO format."""
        value, conf_adj = validate_date("1985-06-15", 0.5)
        assert value == "15/06/1985"
        assert conf_adj == 0.10
    
    def test_valid_spelled_out_month(self):
        """Test spelled-out month format."""
        value, conf_adj = validate_date("June 15, 1985", 0.5)
        assert value == "15/06/1985"
        assert conf_adj == 0.10
    
    def test_valid_abbreviated_month(self):
        """Test abbreviated month format."""
        value, conf_adj = validate_date("15 Jun 1985", 0.5)
        assert value == "15/06/1985"
        assert conf_adj == 0.10
    
    def test_empty_date(self):
        """Test empty date string."""
        value, conf_adj = validate_date("", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_invalid_day_too_large(self):
        """Test invalid day (>31)."""
        value, conf_adj = validate_date("35/06/1985", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_invalid_month_too_large(self):
        """Test invalid month (>12)."""
        value, conf_adj = validate_date("15/13/1985", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_invalid_day_for_month_february(self):
        """Test invalid day for February (>28 non-leap)."""
        value, conf_adj = validate_date("29/02/1985", 0.5)  # 1985 not leap year
        assert value == ""
        assert conf_adj == -0.20
    
    def test_valid_leap_year_february(self):
        """Test February 29 in leap year."""
        value, conf_adj = validate_date("29/02/2000", 0.5)
        assert value == "29/02/2000"
        assert conf_adj == 0.10
    
    def test_year_below_range(self):
        """Test year below 1950."""
        value, conf_adj = validate_date("15/06/1940", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_year_above_range(self):
        """Test year above 2030."""
        value, conf_adj = validate_date("15/06/2040", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_malformed_date_string(self):
        """Test malformed date string."""
        value, conf_adj = validate_date("not-a-date", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_boundary_year_1950(self):
        """Test boundary year 1950 (lowest valid)."""
        value, conf_adj = validate_date("01/01/1950", 0.5)
        assert value == "01/01/1950"
        assert conf_adj == 0.10
    
    def test_boundary_year_2030(self):
        """Test boundary year 2030 (highest valid)."""
        value, conf_adj = validate_date("31/12/2030", 0.5)
        assert value == "31/12/2030"
        assert conf_adj == 0.10


# =============================================================================
# PHONE VALIDATOR TESTS (20 tests)
# =============================================================================

class TestValidatePhoneValidator:
    """Test phone number validation and standardization."""
    
    def test_valid_local_format_09(self):
        """Test local PH format with 0 prefix."""
        value, conf_adj = validate_phone("09171234567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05
    
    def test_valid_local_format_with_hyphens(self):
        """Test local format with hyphens."""
        value, conf_adj = validate_phone("0917-123-4567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05
    
    def test_valid_international_format_plus63(self):
        """Test international format with +63."""
        value, conf_adj = validate_phone("+639171234567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05
    
    def test_valid_international_format_63(self):
        """Test international format with 63."""
        value, conf_adj = validate_phone("639171234567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05
    
    def test_valid_with_spaces(self):
        """Test with spaces as separators."""
        value, conf_adj = validate_phone("0917 123 4567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05
    
    def test_valid_with_parentheses(self):
        """Test with parentheses format."""
        value, conf_adj = validate_phone("(09) 17-1234567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05
    
    def test_empty_phone(self):
        """Test empty phone string."""
        value, conf_adj = validate_phone("", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_invalid_too_short(self):
        """Test phone number too short."""
        value, conf_adj = validate_phone("0917123", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_invalid_too_long(self):
        """Test phone number too long."""
        value, conf_adj = validate_phone("09171234567890", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_invalid_mobile_prefix(self):
        """Test invalid mobile prefix."""
        value, conf_adj = validate_phone("09991234567", 0.5)  # 999 not valid
        assert value == ""
        assert conf_adj == -0.20
    
    def test_valid_globe_prefix_917(self):
        """Test Globe mobile prefix 917."""
        value, conf_adj = validate_phone("09171234567", 0.5)
        assert "+6391" in value
        assert conf_adj == 0.05
    
    def test_valid_smart_prefix_908(self):
        """Test Smart mobile prefix 908."""
        value, conf_adj = validate_phone("09081234567", 0.5)
        assert value == "+639081234567"
        assert conf_adj == 0.05
    
    def test_non_ph_number(self):
        """Test non-PH country code."""
        value, conf_adj = validate_phone("+14155552671", 0.5)  # US number
        assert value == ""
        assert conf_adj == -0.20
    
    def test_local_without_leading_zero(self):
        """Test local format without leading 0."""
        value, conf_adj = validate_phone("9171234567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05
    
    def test_mixed_separators(self):
        """Test with mixed separators."""
        value, conf_adj = validate_phone("09-17 123-4567", 0.5)
        assert value == "+639171234567"
        assert conf_adj == 0.05


# =============================================================================
# CHECKBOX VALIDATOR TESTS (15 tests)
# =============================================================================

class TestValidateCheckboxValidator:
    """Test checkbox value validation."""
    
    def test_yes_variant_exact(self):
        """Test 'Yes' variant."""
        value, conf_adj = validate_checkbox("Yes", 0.5)
        assert value == "Yes"
        assert conf_adj == 0.05
    
    def test_yes_variant_lowercase(self):
        """Test 'yes' variant (lowercase)."""
        value, conf_adj = validate_checkbox("yes", 0.5)
        assert value == "Yes"
        assert conf_adj == 0.05
    
    def test_yes_variant_y(self):
        """Test 'Y' variant."""
        value, conf_adj = validate_checkbox("Y", 0.5)
        assert value == "Yes"
        assert conf_adj == 0.05
    
    def test_yes_variant_true(self):
        """Test 'true' variant."""
        value, conf_adj = validate_checkbox("true", 0.5)
        assert value == "Yes"
        assert conf_adj == 0.05
    
    def test_yes_variant_checkmark(self):
        """Test checkmark symbol."""
        value, conf_adj = validate_checkbox("✓", 0.5)
        assert value == "Yes"
        assert conf_adj == 0.05
    
    def test_no_variant_exact(self):
        """Test 'No' variant."""
        value, conf_adj = validate_checkbox("No", 0.5)
        assert value == "No"
        assert conf_adj == 0.05
    
    def test_no_variant_n(self):
        """Test 'N' variant."""
        value, conf_adj = validate_checkbox("N", 0.5)
        assert value == "No"
        assert conf_adj == 0.05
    
    def test_no_variant_false(self):
        """Test 'false' variant."""
        value, conf_adj = validate_checkbox("false", 0.5)
        assert value == "No"
        assert conf_adj == 0.05
    
    def test_no_variant_zero(self):
        """Test '0' variant."""
        value, conf_adj = validate_checkbox("0", 0.5)
        assert value == "No"
        assert conf_adj == 0.05
    
    def test_empty_checkbox(self):
        """Test empty checkbox."""
        value, conf_adj = validate_checkbox("", 0.5)
        assert value == ""
        assert conf_adj == 0.0
    
    def test_ambiguous_maybe(self):
        """Test ambiguous 'maybe' value."""
        value, conf_adj = validate_checkbox("maybe", 0.5)
        assert value == ""
        assert conf_adj == -0.05
    
    def test_ambiguous_unknown(self):
        """Test ambiguous 'unknown' value."""
        value, conf_adj = validate_checkbox("unknown", 0.5)
        assert value == ""
        assert conf_adj == -0.05
    
    def test_ambiguous_question_mark(self):
        """Test ambiguous '?' value."""
        value, conf_adj = validate_checkbox("?", 0.5)
        assert value == ""
        assert conf_adj == -0.05
    
    def test_unrecognized_value(self):
        """Test unrecognized value."""
        value, conf_adj = validate_checkbox("xyz", 0.5)
        assert value == ""
        assert conf_adj == -0.05
    
    def test_case_insensitive_yes(self):
        """Test case insensitivity for YES."""
        value, conf_adj = validate_checkbox("YES", 0.5)
        assert value == "Yes"
        assert conf_adj == 0.05


# =============================================================================
# AMOUNT VALIDATOR TESTS (15 tests)
# =============================================================================

class TestValidateAmountValidator:
    """Test currency amount validation and formatting."""
    
    def test_plain_number(self):
        """Test plain number without currency."""
        value, conf_adj = validate_amount("5000", 0.5)
        assert value == "5,000.00"
        assert conf_adj == 0.08
    
    def test_number_with_decimal(self):
        """Test number with decimal places."""
        value, conf_adj = validate_amount("5000.50", 0.5)
        assert value == "5,000.50"
        assert conf_adj == 0.08
    
    def test_peso_symbol_currency(self):
        """Test with peso symbol."""
        value, conf_adj = validate_amount("₱5000", 0.5)
        assert value == "5,000.00"
        assert conf_adj == 0.08
    
    def test_p_prefix_currency(self):
        """Test with P prefix."""
        value, conf_adj = validate_amount("P5000", 0.5)
        assert value == "5,000.00"
        assert conf_adj == 0.08
    
    def test_dollar_currency(self):
        """Test with dollar symbol."""
        value, conf_adj = validate_amount("$5000", 0.5)
        assert value == "5,000.00"
        assert conf_adj == 0.08
    
    def test_number_with_thousands(self):
        """Test number with comma thousands separator."""
        value, conf_adj = validate_amount("5,000", 0.5)
        assert value == "5,000.00"
        assert conf_adj == 0.08
    
    def test_number_with_thousands_and_decimals(self):
        """Test number with thousands and decimals."""
        value, conf_adj = validate_amount("5,000.50", 0.5)
        assert value == "5,000.50"
        assert conf_adj == 0.08
    
    def test_negative_amount(self):
        """Test negative amount."""
        value, conf_adj = validate_amount("-5000", 0.5)
        assert value == "-5,000.00"
        assert conf_adj == 0.08
    
    def test_negative_with_currency(self):
        """Test negative with currency symbol."""
        value, conf_adj = validate_amount("₱-5000", 0.5)
        assert value == "-5,000.00"
        assert conf_adj == 0.08
    
    def test_zero_amount(self):
        """Test zero amount."""
        value, conf_adj = validate_amount("0", 0.5)
        assert value == "0.00"
        assert conf_adj == 0.08
    
    def test_empty_amount(self):
        """Test empty amount string."""
        value, conf_adj = validate_amount("", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_non_numeric_amount(self):
        """Test non-numeric amount."""
        value, conf_adj = validate_amount("abc", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_multiple_currency_symbols(self):
        """Test multiple currency symbols (invalid)."""
        value, conf_adj = validate_amount("₱$5000", 0.5)
        assert value == ""
        assert conf_adj == -0.20
    
    def test_large_amount(self):
        """Test large amount formatting."""
        value, conf_adj = validate_amount("1234567.89", 0.5)
        assert value == "1,234,567.89"
        assert conf_adj == 0.08
    
    def test_very_small_amount(self):
        """Test very small amount."""
        value, conf_adj = validate_amount("0.01", 0.5)
        assert value == "0.01"
        assert conf_adj == 0.08


# =============================================================================
# REQUIRED FIELD VALIDATOR TESTS (10 tests)
# =============================================================================

class TestValidateRequiredValidator:
    """Test required field validation."""
    
    def test_required_field_filled(self):
        """Test required field with value."""
        value, conf_adj = validate_required("Juan Dolos", is_required=True, confidence=0.5)
        assert value == "Juan Dolos"
        assert conf_adj == 0.05
    
    def test_required_field_empty(self):
        """Test required field without value."""
        value, conf_adj = validate_required("", is_required=True, confidence=0.5)
        assert value == ""
        assert conf_adj == -0.25
    
    def test_required_field_whitespace(self):
        """Test required field with only whitespace."""
        value, conf_adj = validate_required("   ", is_required=True, confidence=0.5)
        assert value == "   "
        assert conf_adj == -0.25
    
    def test_optional_field_filled(self):
        """Test optional field with value."""
        value, conf_adj = validate_required("Some value", is_required=False, confidence=0.5)
        assert value == "Some value"
        assert conf_adj == 0.0
    
    def test_optional_field_empty(self):
        """Test optional field without value."""
        value, conf_adj = validate_required("", is_required=False, confidence=0.5)
        assert value == ""
        assert conf_adj == 0.0
    
    def test_required_null_value(self):
        """Test required field with None."""
        value, conf_adj = validate_required(None, is_required=True, confidence=0.5)
        assert conf_adj == -0.25
    
    def test_optional_null_value(self):
        """Test optional field with None."""
        value, conf_adj = validate_required(None, is_required=False, confidence=0.5)
        assert conf_adj == 0.0
    
    def test_required_with_numeric_value(self):
        """Test required field with numeric value."""
        value, conf_adj = validate_required("12345", is_required=True, confidence=0.5)
        assert value == "12345"
        assert conf_adj == 0.05
    
    def test_required_with_special_characters(self):
        """Test required field with special characters."""
        value, conf_adj = validate_required("Test@#$%", is_required=True, confidence=0.5)
        assert value == "Test@#$%"
        assert conf_adj == 0.05
    
    def test_optional_with_empty_string(self):
        """Test optional field explicitly checking empty string."""
        value, conf_adj = validate_required("", is_required=False, confidence=0.8)
        assert value == ""
        assert conf_adj == 0.0


# =============================================================================
# INTEGRATION TESTS (5 tests)
# =============================================================================

class TestValidatorIntegration:
    """Test validators working together in pipeline."""
    
    def test_confidence_adjustment_positive(self):
        """Test that confidence can be improved."""
        date_val, date_adj = validate_date("15/06/1985", 0.3)
        new_confidence = max(0.0, min(1.0, 0.3 + date_adj))
        assert new_confidence > 0.3
    
    def test_confidence_adjustment_negative(self):
        """Test that confidence can be decreased."""
        phone_val, phone_adj = validate_phone("invalid", 0.8)
        new_confidence = max(0.0, min(1.0, 0.8 + phone_adj))
        assert new_confidence < 0.8
    
    def test_confidence_clamping_upper(self):
        """Test confidence clamping to [0, 1]."""
        # If starting at 0.95 and adjustment is +0.10
        clamped = max(0.0, min(1.0, 0.95 + 0.10))
        assert clamped == 1.0
    
    def test_confidence_clamping_lower(self):
        """Test confidence clamping to [0, 1]."""
        # If starting at 0.05 and adjustment is -0.25
        clamped = max(0.0, min(1.0, 0.05 - 0.25))
        assert clamped == 0.0
    
    def test_pipeline_sequence(self):
        """Test validators in sequence (simulating pipeline)."""
        # Simulate: Date → Phone → Amount → Required
        date_val, date_adj = validate_date("15/06/1985", 0.5)
        phone_val, phone_adj = validate_phone("09171234567", 0.5)
        amount_val, amount_adj = validate_amount("5000", 0.5)
        required_val, required_adj = validate_required("Yes", is_required=True, confidence=0.5)
        
        # All should succeed
        assert date_val == "15/06/1985"
        assert phone_val == "+639171234567"
        assert amount_val == "5,000.00"
        assert required_val == "Yes"
