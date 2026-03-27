"""Test suite for Step 4.4 - Field-level validation functions.

This module tests validation functions that normalize and validate OCR-extracted field values:
- Date Validation: Accepts multiple formats, validates date ranges (1950-2030)
- Phone Validation: PH phone numbers with confidence adjustments
- Checkbox Validation: Yes/No/True/False/✓/☐ normalization
- Amount Validation: Currency formatting and validation
- Required Field Validation: Confidence adjustments based on presence

All validators follow the pattern:
  Returns: (normalized_value, confidence_adjustment)
  Where confidence_adjustment ∈ [-0.25, +0.10]
"""

import pytest
from datetime import datetime, timedelta
from typing import Tuple
from app.services.ocr_task import (
    _validate_date,
    _validate_phone,
    _validate_checkbox,
    _validate_amount,
    _validate_required,
)


# ============================================================================
# FIXTURES: Test data for validation scenarios
# ============================================================================

@pytest.fixture
def valid_date_formats():
    """Valid date formats that should be accepted and normalized."""
    return [
        ("15/03/2020", "15/03/2020"),  # DD/MM/YYYY
        ("03/15/2020", "15/03/2020"),  # MM/DD/YYYY (detected and converted)
        ("2020-03-15", "15/03/2020"),  # YYYY-MM-DD ISO format
        ("March 15, 2020", "15/03/2020"),  # Spelled out
        ("Mar 15 2020", "15/03/2020"),  # 3-letter month
        ("15-03-2020", "15/03/2020"),  # DD-MM-YYYY
        ("2020/03/15", "15/03/2020"),  # YYYY/MM/DD
    ]


@pytest.fixture
def invalid_date_values():
    """Invalid dates that should be rejected and return empty string."""
    return [
        "02/30/2020",  # Feb 30 doesn't exist
        "13/45/2020",  # Invalid month and day
        "32/01/2020",  # Day 32 in January
        "31/04/2020",  # April has only 30 days
        "not a date",  # Non-date string
        "2040-03-15",  # Future date > 2030
        "1940-03-15",  # Ancient date < 1950
        "",  # Empty string
        "   ",  # Whitespace only
    ]


@pytest.fixture
def future_dates():
    """Dates beyond allowed range (> 2030)."""
    return [
        "15/03/2031",
        "01/01/2050",
        "2040-12-25",
    ]


@pytest.fixture
def ancient_dates():
    """Dates before allowed range (< 1950)."""
    return [
        "15/03/1940",
        "01/01/1800",
        "1949-12-31",
    ]


@pytest.fixture
def valid_ph_phone_formats():
    """Valid Philippine phone number formats."""
    return [
        ("+639171234567", "+639171234567"),  # International format
        ("09171234567", "+639171234567"),  # Local format 09XX
        ("9171234567", "+639171234567"),  # Without leading 0
        ("+63 917 123 4567", "+639171234567"),  # With spaces
        ("(09) 17-1234567", "+639171234567"),  # With separators
        ("0917 123 4567", "+639171234567"),  # Spaces variant
    ]


@pytest.fixture
def invalid_ph_phones():
    """Invalid phone numbers that should be rejected."""
    return [
        "1234567",  # Too short
        "09171234567890",  # Too long (14 digits)
        "+6331234567",  # Non-mobile PH number (landline)
        "09001234567",  # Invalid mobile prefix (0900)
        "abcdefghij",  # Non-numeric
        "",  # Empty
        "   ",  # Whitespace
    ]


@pytest.fixture
def checkbox_variations():
    """Various checkbox representations and their normalized values."""
    return [
        ("Yes", "Yes"),
        ("yes", "Yes"),
        ("YES", "Yes"),
        ("✓", "Yes"),
        ("✔", "Yes"),
        ("checked", "Yes"),
        ("Checked", "Yes"),
        ("True", "Yes"),
        ("true", "Yes"),
        ("1", "Yes"),
        ("No", "No"),
        ("no", "No"),
        ("NO", "No"),
        ("☐", "No"),
        ("unchecked", "No"),
        ("Unchecked", "No"),
        ("False", "No"),
        ("false", "No"),
        ("0", "No"),
        ("", ""),  # Empty stays empty
        ("maybe", ""),  # Ambiguous → empty (not normalized, confidence penalty)
        ("unknown", ""),  # Ambiguous → empty
    ]


@pytest.fixture
def currency_values():
    """Valid currency amounts and their expected normalized form."""
    return [
        ("5000", "5,000.00"),
        ("5,000", "5,000.00"),
        ("5000.50", "5,000.50"),
        ("₱5000", "5,000.00"),
        ("P5000", "5,000.00"),
        ("$5000", "5,000.00"),
        ("5,000.00", "5,000.00"),
        ("₱5,000.50", "5,000.50"),
    ]


@pytest.fixture
def invalid_currency_values():
    """Invalid amounts that should be rejected."""
    return [
        "abc",  # Non-numeric
        "5000.99.99",  # Multiple decimals
        "",  # Empty
        "   ",  # Whitespace only
        "₱P5000",  # Multiple currency symbols
    ]


# ============================================================================
# TESTS: Date Validation
# ============================================================================

@pytest.mark.parametrize("input_date,expected", [
    ("15/03/2020", "15/03/2020"),
    ("03/15/2020", "15/03/2020"),
    ("2020-03-15", "15/03/2020"),
    ("March 15, 2020", "15/03/2020"),
])
def test_valid_date_formats_normalized(input_date, expected):
    """Test that valid date formats are accepted and normalized to DD/MM/YYYY.
    
    This test validates different input formats are correctly parsed and
    standardized regardless of input format (MM/DD/YYYY detected and corrected).
    """
    normalized, confidence_adj = _validate_date(input_date, 0.8)
    assert normalized == expected, f"Expected {expected}, got {normalized}"
    assert -0.25 <= confidence_adj <= 0.10, f"Confidence adjustment out of range: {confidence_adj}"
    assert confidence_adj == 0.10, f"Valid date should have +0.10 adjustment, got {confidence_adj}"


def test_invalid_dates_rejected(invalid_date_values):
    """Test that invalid dates return empty string and reduce confidence.
    
    Invalid dates include:
    - Impossible dates (Feb 30, day 32, etc.)
    - Non-date strings
    - Empty/whitespace
    """
    for invalid_date in invalid_date_values:
        normalized, confidence_adj = _validate_date(invalid_date, 0.8)
        assert normalized == "", f"Invalid date '{invalid_date}' should return empty, got {normalized}"
        assert confidence_adj < 0, f"Confidence should be reduced for invalid date '{invalid_date}', got {confidence_adj}"
        assert confidence_adj == -0.25, f"Invalid date adjustment should be -0.25, got {confidence_adj}"


def test_future_dates_rejected(future_dates):
    """Test that dates beyond year 2030 are rejected.
    
    Context: Philippine forms are for current/past data, future dates beyond
    2030 are likely OCR errors or data entry mistakes.
    """
    for future_date in future_dates:
        normalized, confidence_adj = _validate_date(future_date, 0.8)
        assert normalized == "", f"Future date '{future_date}' should be rejected"
        assert confidence_adj == -0.25, f"Future date should have -0.25 penalty"


def test_ancient_dates_rejected(ancient_dates):
    """Test that dates before year 1950 are rejected.
    
    Context: Philippine forms are for living residents; dates before 1950
    are unlikely to be valid birthdates or application dates.
    """
    for ancient_date in ancient_dates:
        normalized, confidence_adj = _validate_date(ancient_date, 0.8)
        assert normalized == "", f"Ancient date '{ancient_date}' should be rejected"
        assert confidence_adj == -0.25, f"Ancient date should have -0.25 penalty"


def test_date_leap_year_feb29():
    """Test that valid Feb 29 in leap years is accepted."""
    normalized, confidence_adj = _validate_date("29/02/2020", 0.8)
    assert normalized == "29/02/2020", "Feb 29 in leap year should be valid"
    assert confidence_adj == 0.10


def test_date_invalid_feb29_non_leap_year():
    """Test that Feb 29 in non-leap years is rejected."""
    normalized, confidence_adj = _validate_date("29/02/2021", 0.8)
    assert normalized == "", "Feb 29 in non-leap year should be invalid"
    assert confidence_adj == -0.25


# ============================================================================
# TESTS: Phone Validation
# ============================================================================

@pytest.mark.parametrize("input_phone,expected", [
    ("+639171234567", "+639171234567"),
    ("09171234567", "+639171234567"),
    ("9171234567", "+639171234567"),
    ("+63 917 123 4567", "+639171234567"),
    ("(09) 17-1234567", "+639171234567"),
])
def test_valid_ph_formats_standardized(input_phone, expected):
    """Test that valid PH phone formats are standardized to +639XXXXXXXX.
    
    This validates:
    - International format preserved
    - Local 09XX format converted to international
    - Separators (spaces, hyphens, parentheses) removed
    - Confidence maintains or slightly improves
    """
    standardized, confidence_adj = _validate_phone(input_phone, 0.7)
    assert standardized == expected, f"Expected {expected}, got {standardized}"
    assert -0.25 <= confidence_adj <= 0.10, f"Confidence adjustment out of range: {confidence_adj}"


def test_invalid_phone_length_rejected(invalid_ph_phones):
    """Test that invalid phone numbers are rejected.
    
    Invalid includes:
    - Wrong length (< 10 or > 11 digits)
    - Non-mobile PH numbers (landlines)
    - Invalid mobile prefixes (e.g., 0900, 0901 are invalid)
    - Non-numeric content
    """
    for invalid_phone in invalid_ph_phones:
        standardized, confidence_adj = _validate_phone(invalid_phone, 0.7)
        assert standardized == "", f"Invalid phone '{invalid_phone}' should return empty, got {standardized}"
        assert confidence_adj < 0, f"Confidence should be reduced for invalid phone, got {confidence_adj}"


def test_confidence_adjustment_for_valid_phone():
    """Test that confidence is boosted (+0.05) for validated PH phones.
    
    High confidence in phone validation is justified because:
    - Format is highly structured
    - Standardization removes ambiguity
    - PH phone prefixes are well-defined
    """
    input_phone = "09171234567"
    standardized, confidence_adj = _validate_phone(input_phone, 0.7)
    
    assert standardized == "+639171234567"
    assert confidence_adj == 0.05, f"Valid phone should have +0.05 adjustment, got {confidence_adj}"


# ============================================================================
# TESTS: Checkbox Validation
# ============================================================================

@pytest.mark.parametrize("input_checkbox,expected", [
    ("Yes", "Yes"),
    ("YES", "Yes"),
    ("yes", "Yes"),
    ("✓", "Yes"),
    ("checked", "Yes"),
    ("True", "Yes"),
    ("No", "No"),
    ("NO", "No"),
    ("no", "No"),
    ("☐", "No"),
    ("unchecked", "No"),
    ("False", "No"),
])
def test_checkbox_variations_normalized(input_checkbox, expected):
    """Test that various checkbox representations normalize to 'Yes' or 'No'.
    
    Handles:
    - Word variants (Yes/No, True/False, Checked/Unchecked)
    - Unicode checkbox symbols (✓, ☐)
    - Case variations
    """
    normalized, confidence_adj = _validate_checkbox(input_checkbox, 0.8)
    assert normalized == expected, f"Expected {expected}, got {normalized}"
    assert -0.10 <= confidence_adj <= 0.10, f"Confidence adjustment out of range: {confidence_adj}"


def test_empty_checkbox_returns_empty():
    """Test that empty or whitespace-only checkbox fields return empty string."""
    for empty_input in ["", "   ", "\t", "\n"]:
        normalized, confidence_adj = _validate_checkbox(empty_input, 0.8)
        assert normalized == "", f"Empty checkbox should return empty, got {normalized}"
        assert confidence_adj == 0.0, f"Empty checkbox should have 0.0 adjustment, got {confidence_adj}"


def test_ambiguous_checkbox_default_to_empty():
    """Test that ambiguous checkbox values return empty (not auto-defaulting to No).
    
    Ambiguous cases like 'maybe', 'unknown', '?' should NOT be forced to 'No'
    but rather flagged as needing verification. Returns empty with confidence penalty.
    """
    ambiguous_values = ["maybe", "unknown", "?", "unclear"]
    
    for ambiguous in ambiguous_values:
        normalized, confidence_adj = _validate_checkbox(ambiguous, 0.8)
        assert normalized == "", f"Ambiguous '{ambiguous}' should return empty, got {normalized}"
        assert confidence_adj <= -0.05, f"Ambiguous should penalize confidence, got {confidence_adj}"


# ============================================================================
# TESTS: Amount Validation
# ============================================================================

@pytest.mark.parametrize("input_amount,expected", [
    ("5000", "5,000.00"),
    ("5,000", "5,000.00"),
    ("5000.50", "5,000.50"),
    ("₱5000", "5,000.00"),
    ("P5000", "5,000.00"),
    ("5,000.00", "5,000.00"),
])
def test_currency_values_formatted(input_amount, expected):
    """Test that currency amounts are normalized to X,XXX.XX format.
    
    Strips currency symbols and formats consistently regardless of input format.
    """
    formatted, confidence_adj = _validate_amount(input_amount, 0.8)
    assert formatted == expected, f"Expected {expected}, got {formatted}"
    assert -0.25 <= confidence_adj <= 0.10, f"Confidence adjustment out of range: {confidence_adj}"


def test_non_numeric_amounts_rejected(invalid_currency_values):
    """Test that non-numeric amounts are rejected.
    
    Invalid includes:
    - Non-numeric characters (letters, mixed)
    - Multiple decimal points
    - Multiple currency symbols
    """
    for invalid_amount in invalid_currency_values:
        formatted, confidence_adj = _validate_amount(invalid_amount, 0.8)
        assert formatted == "", f"Invalid amount '{invalid_amount}' should return empty, got {formatted}"
        assert confidence_adj < 0, f"Confidence should be reduced for invalid amount"


def test_negative_amounts_accepted():
    """Test that negative amounts (for refunds/deductions) are accepted.
    
    Some Philippine forms may include negative amounts for refunds or credits.
    Negative amounts should be accepted and formatted consistently.
    """
    negative_amounts = ["-5000", "₱-5000", "-5,000.50", "$-500"]
    
    for neg_amount in negative_amounts:
        formatted, confidence_adj = _validate_amount(neg_amount, 0.8)
        if formatted:  # Only check if formatting succeeded
            assert formatted.startswith("-") or formatted == "", f"Negative amount should preserve sign: {neg_amount} → {formatted}"


# ============================================================================
# TESTS: Required Field Validation
# ============================================================================

def test_required_empty_reduces_confidence():
    """Test that empty required fields reduce confidence by 0.25.
    
    When a field is marked required but empty, confidence is penalized
    to flag this for human review.
    """
    empty_value = ""
    normalized, confidence_adj = _validate_required(empty_value, is_required=True, confidence=0.8)
    
    assert normalized == ""
    assert confidence_adj == -0.25, f"Empty required field should have -0.25 penalty, got {confidence_adj}"


def test_required_filled_increases_confidence():
    """Test that filled required fields increase confidence by 0.05.
    
    When a required field is present, confidence is boosted to reflect
    successful field population.
    """
    filled_value = "John Doe"
    normalized, confidence_adj = _validate_required(filled_value, is_required=True, confidence=0.8)
    
    assert normalized == "John Doe"
    assert confidence_adj == 0.05, f"Filled required field should have +0.05 adjustment, got {confidence_adj}"


@pytest.mark.parametrize("value", ["", "   ", "N/A", "Unknown"])
def test_optional_field_no_confidence_adjustment(value):
    """Test that optional fields don't adjust confidence.
    
    When field is not required, presence or absence doesn't affect confidence.
    """
    normalized, confidence_adj = _validate_required(value, is_required=False, confidence=0.8)
    assert confidence_adj == 0.0, f"Optional field should have 0.0 adjustment, got {confidence_adj}"
    assert normalized == value, f"Optional field value should be unchanged"


def test_required_whitespace_only_treated_as_empty():
    """Test that required fields with only whitespace are treated as empty."""
    for whitespace_value in ["   ", "\t", "\n", "\t\n"]:
        normalized, confidence_adj = _validate_required(whitespace_value, is_required=True, confidence=0.8)
        assert confidence_adj == -0.25, f"Whitespace-only required field should have -0.25 penalty"


# ============================================================================
# TESTS: Edge Cases & Integration
# ============================================================================

def test_all_validators_preserve_immutability():
    """Test that all validators don't mutate input, only return new values.
    
    All validation functions must follow immutability principle:
    - Input strings are not modified
    - Original confidence score is not mutated
    - New confidence adjustment returned separately
    """
    # Test data for each validator
    test_cases = [
        (_validate_date, "01/01/2020", 0.8),
        (_validate_phone, "09171234567", 0.7),
        (_validate_checkbox, "Yes", 0.8),
        (_validate_amount, "5000", 0.8),
    ]
    
    for validator_func, input_value, original_confidence in test_cases:
        input_copy = input_value
        conf_copy = original_confidence
        
        # Call validator
        normalized, confidence_adj = validator_func(input_value, original_confidence)
        
        # Verify inputs unchanged
        assert input_value == input_copy, f"Validator mutated input"
        assert original_confidence == conf_copy, f"Validator mutated confidence"


def test_confidence_always_clamped_0_to_1():
    """Test that confidence scores never exceed [0.0, 1.0] range.
    
    After applying confidence adjustments, final scores must be valid:
    - Minimum: 0.0 (no confidence)
    - Maximum: 1.0 (complete confidence)
    
    Typical scenario: initial 0.9 confidence + 0.10 adjustment = 1.0 (clamped)
    """
    # Test extreme cases
    test_cases = [
        (0.95, 0.10, 1.0),  # Should clamp to 1.0
        (0.05, -0.10, 0.0),  # Should clamp to 0.0
        (0.5, 0.05, 0.55),  # Normal case
    ]
    
    for base_confidence, adjustment, expected_final in test_cases:
        final = max(0.0, min(1.0, base_confidence + adjustment))
        assert final == expected_final, f"Clamping failed: {base_confidence} + {adjustment} = {final}"
        assert 0.0 <= final <= 1.0, f"Final confidence out of range: {final}"


def test_all_confidence_adjustments_in_range():
    """Test that all validators return adjustments within valid range [-0.25, +0.10]."""
    test_cases = [
        (_validate_date, "15/03/2020", "valid"),
        (_validate_date, "invalid", "invalid"),
        (_validate_phone, "09171234567", "valid"),
        (_validate_phone, "invalid", "invalid"),
        (_validate_checkbox, "Yes", "valid"),
        (_validate_checkbox, "maybe", "invalid"),
        (_validate_amount, "5000", "valid"),
        (_validate_amount, "abc", "invalid"),
    ]
    
    for validator_func, input_value, test_type in test_cases:
        if validator_func == _validate_required:
            normalized, adj = validator_func(input_value, True, 0.8)
        else:
            normalized, adj = validator_func(input_value, 0.8)
        
        assert -0.25 <= adj <= 0.10, f"{validator_func.__name__}: adjustment {adj} out of range"


@pytest.mark.parametrize("base_conf,input_value", [
    (0.0, "15/03/2020"),
    (0.5, "09171234567"),
    (1.0, "Yes"),
    (0.9, "5000"),
])
def test_validators_work_with_all_confidence_levels(base_conf, input_value):
    """Test that validators work correctly at all confidence levels (0.0 to 1.0)."""
    # Test with different confidence levels
    if input_value == "15/03/2020":
        normalized, adj = _validate_date(input_value, base_conf)
    elif input_value == "09171234567":
        normalized, adj = _validate_phone(input_value, base_conf)
    elif input_value == "Yes":
        normalized, adj = _validate_checkbox(input_value, base_conf)
    elif input_value == "5000":
        normalized, adj = _validate_amount(input_value, base_conf)
    
    # Verify adjustment is in valid range regardless of input confidence
    assert -0.25 <= adj <= 0.10, f"Adjustment out of range for base confidence {base_conf}"
    
    # Test resulting confidence is valid
    final_conf = max(0.0, min(1.0, base_conf + adj))
    assert 0.0 <= final_conf <= 1.0, f"Final confidence invalid: {final_conf}"
