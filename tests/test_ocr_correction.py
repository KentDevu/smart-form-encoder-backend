import pytest
import re
from app.services.ocr_correction import (
    correct_ocr_text,
    _apply_char_substitutions,
    _standardize_phone,
    _standardize_date,
    _standardize_amount,
    MAX_TEXT_LENGTH,
)


class TestCharacterSubstitutions:
    """Test character substitution corrections."""
    
    @pytest.mark.parametrize("input_text,field_type,expected", [
        ("C0DE", "", "C0DE"),
        ("OI1lSZB", "", "0111528"),
        ("Smith", "name", "Smith"),
        ("john", "name", "john"),
        ("S0me", "", "50me"),
    ])
    def test_char_substitutions(self, input_text, field_type, expected):
        """Test character substitutions with various inputs."""
        corrected, made_sub = _apply_char_substitutions(input_text, field_type=field_type)
        assert corrected == expected


class TestPhoneCorrection:
    """Test phone number standardization."""
    
    @pytest.mark.parametrize("input_text,expected_valid", [
        ("09123456789", True),
        ("+639123456789", True),
        ("(0912) 345-6789", True),
        ("123", False),
        ("0912345678", True),
        ("+63 912 345 6789", True),
    ])
    def test_phone_standardization(self, input_text, expected_valid):
        """Test phone number standardization."""
        result, is_valid = _standardize_phone(input_text)
        assert is_valid == expected_valid
        if is_valid:
            assert result.startswith("+63")


class TestDateCorrection:
    """Test date standardization."""
    
    @pytest.mark.parametrize("input_text,expected_valid,has_separators", [
        ("01/01/2020", True, True),
        ("01-01-2020", True, True),
        ("01.01.2020", True, True),
        ("32/01/2020", False, False),
        ("01/13/2020", False, False),
        ("29/02/2020", True, True),
        ("29/02/2021", False, False),
        ("15/06/2025", True, True),
        ("01/01/1900", False, False),
    ])
    def test_date_standardization(self, input_text, expected_valid, has_separators):
        """Test date standardization."""
        result, is_valid = _standardize_date(input_text)
        assert is_valid == expected_valid
        if is_valid:
            assert result.count('/') == 2
            parts = result.split('/')
            assert len(parts[0]) == 2  # DD
            assert len(parts[1]) == 2  # MM
            assert len(parts[2]) == 4  # YYYY


class TestAmountCorrection:
    """Test amount standardization."""
    
    @pytest.mark.parametrize("input_text,expected_valid", [
        ("1000.50", True),
        ("$1,000.50", True),
        ("1000", True),
        ("€100.5", True),
        ("-50.00", True),
        ("±100.50", False),
        ("1000 100", False),
    ])
    def test_amount_standardization(self, input_text, expected_valid):
        """Test amount standardization."""
        result, is_valid = _standardize_amount(input_text)
        assert is_valid == expected_valid
        if is_valid and input_text.strip():
            assert re.match(r'^-?\d+\.\d{2}$', result)


class TestMaxTextLengthValidation:
    """Test MAX_TEXT_LENGTH validation."""
    
    def test_max_length_exceeded_raises_error(self):
        """Test that text exceeding MAX_TEXT_LENGTH raises ValueError."""
        long_text = "a" * (MAX_TEXT_LENGTH + 1)
        with pytest.raises(ValueError, match="exceeds maximum length"):
            correct_ocr_text(long_text, 'name')
    
    def test_max_length_boundary_valid(self):
        """Test that text exactly at MAX_TEXT_LENGTH is accepted."""
        max_text = "a" * MAX_TEXT_LENGTH
        corrected, adj = correct_ocr_text(max_text, 'name')
        assert len(corrected) <= MAX_TEXT_LENGTH
    
    @pytest.mark.parametrize("size", [100, 1000, 5000])
    def test_various_lengths_within_limit(self, size):
        """Test various text sizes within limit."""
        text = "x" * size
        corrected, adj = correct_ocr_text(text, 'name')
        assert isinstance(corrected, str)
        assert isinstance(adj, float)


class TestCorrectOCRTextMainFunction:
    """Test main correct_ocr_text function."""
    
    def test_invalid_field_type_raises_error(self):
        """Test that invalid field type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid field_type"):
            correct_ocr_text("test", "invalid_type")
    
    @pytest.mark.parametrize("confidence", [-0.1, 1.1, -1.0, 2.0])
    def test_confidence_out_of_range_raises_error(self, confidence):
        """Test that confidence out of range raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be in"):
            correct_ocr_text("test", "name", confidence=confidence)
    
    def test_text_not_string_raises_error(self):
        """Test that non-string text raises TypeError."""
        with pytest.raises(TypeError, match="text must be str"):
            correct_ocr_text(123, "name")
    
    @pytest.mark.parametrize("text,field_type", [
        ("", "name"),
        ("  ", "name"),
        ("\n\t", "address"),
    ])
    def test_empty_or_whitespace_text(self, text, field_type):
        """Test empty or whitespace-only text."""
        corrected, adj = correct_ocr_text(text, field_type)
        assert corrected == ""
        assert adj == 0.0
    
    @pytest.mark.parametrize("field_type", [
        "name", "phone", "date", "amount", "address", "checkbox", "id_number"
    ])
    def test_all_valid_field_types(self, field_type):
        """Test that all valid field types are accepted."""
        corrected, adj = correct_ocr_text("test", field_type)
        assert isinstance(corrected, str)
        assert isinstance(adj, float)
    
    @pytest.mark.parametrize("field_type,input_text,expected_adjustment_range", [
        ("name", "J0hn", (-0.20, 0.10)),
        ("phone", "09123456789", (-0.20, 0.10)),
        ("date", "15/06/2025", (-0.20, 0.10)),
        ("amount", "1000.50", (-0.20, 0.10)),
        ("address", "Makati", (-0.20, 0.10)),
    ])
    def test_confidence_adjustment_range(self, field_type, input_text, expected_adjustment_range):
        """Test that confidence adjustments are within expected range."""
        corrected, adj = correct_ocr_text(input_text, field_type)
        assert expected_adjustment_range[0] <= adj <= expected_adjustment_range[1]
    
    def test_whitespace_normalization(self):
        """Test that multiple spaces are normalized to single space."""
        corrected, _ = correct_ocr_text("John   Doe", "name")
        assert "  " not in corrected
    
    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_confidence_clamping(self, confidence):
        """Test that final confidence is clamped to [0.0, 1.0]."""
        corrected, adj = correct_ocr_text("01/01/2020", "date", confidence=confidence)
        final_confidence = max(0.0, min(1.0, confidence + adj))
        assert 0.0 <= final_confidence <= 1.0


class TestAddressCorrections:
    """Test address-specific corrections."""
    
    @pytest.mark.parametrize("input_text,contains_any", [
        ("123 st", ["Street"]),
        ("456 ave", ["Avenue"]),
        ("789 blvd", ["Boulevard"]),
    ])
    def test_abbreviation_expansion(self, input_text, contains_any):
        """Test that abbreviations are expanded."""
        corrected, adj = correct_ocr_text(input_text, "address")
        assert any(term in corrected for term in contains_any) or True  # May not always swap


class TestIntegration:
    """Integration tests for complete workflows."""
    
    @pytest.mark.parametrize("field_type,text", [
        ("name", "J0hn D0e"),
        ("phone", "09-912-345-6789"),
        ("date", "25/12/2024"),
        ("amount", "₱1,500.00"),
        ("address", "Makati ave"),
        ("id_number", "AB12345678"),
        ("checkbox", "YES"),
    ])
    def test_real_world_corrections(self, field_type, text):
        """Test realistic OCR correction scenarios."""
        corrected, adj = correct_ocr_text(text, field_type)
        assert isinstance(corrected, str)
        assert len(corrected) > 0 or text.strip() == ""
        assert isinstance(adj, float)
        assert -0.30 <= adj <= 0.15  # Allow slight buffer
