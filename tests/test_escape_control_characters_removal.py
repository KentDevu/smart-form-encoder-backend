r"""
Unit Tests for _escape_control_characters() — Removal Approach

Tests the escape_control_characters utility function which REMOVES invalid JSON
control characters (0x00-0x1F) from strings to prevent JSON parsing errors.

Strategy:
- Replacetab (\t = 0x09), newline (\n = 0x0A), carriage return (\r = 0x0D) with spaces
- Remove all other control chars (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F)

Status: Complete unit test suite for removal approach
"""

import pytest
from app.services.ocr_groq_extraction import _escape_control_characters


class TestRemovalBasic:
    """Test basic functionality and empty/normal inputs."""

    def test_empty_string(self):
        """Empty string returns empty."""
        assert _escape_control_characters("") == ""

    def test_no_control_characters(self):
        """String with no control chars (0x20+) passes through unchanged."""
        test_string = "Hello, World! 123"
        assert _escape_control_characters(test_string) == test_string

    def test_space_unchanged(self):
        """Space (0x20) is NOT a control char and should pass through."""
        assert _escape_control_characters(" ") == " "

    def test_printable_ascii_unchanged(self):
        """All printable ASCII characters pass through."""
        test_string = "!\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
        assert _escape_control_characters(test_string) == test_string

    def test_extended_unicode_unchanged(self):
        """Unicode characters (U+0080+) pass through unchanged."""
        test_string = "café ñoño 中文 🎉 अनुग্রহ"
        assert _escape_control_characters(test_string) == test_string


class TestRemovalControlCharacters:
    """Test removal of individual control characters."""

    @pytest.mark.parametrize("code,description", [
        (0x00, "NULL"),
        (0x01, "SOH"),
        (0x02, "STX"),
        (0x03, "ETX"),
        (0x04, "EOT"),
        (0x05, "ENQ"),
        (0x06, "ACK"),
        (0x07, "BEL"),
        (0x08, "BS"),
        # 0x09 (TAB) - special case, replaced with space
        # 0x0A (LF/newline) - special case, replaced with space
        (0x0B, "VT"), 
        (0x0C, "FF"),
        # 0x0D (CR) - special case, replaced with space
        (0x0E, "SO"),
        (0x0F, "SI"),
        (0x10, "DLE"),
        (0x11, "DC1"),
        (0x12, "DC2"),
        (0x13, "DC3"),
        (0x14, "DC4"),
        (0x15, "NAK"),
        (0x16, "SYN"),
        (0x17, "ETB"),
        (0x18, "CAN"),
        (0x19, "EM"),
        (0x1A, "SUB"),
        (0x1B, "ESC"),
        (0x1C, "FS"),
        (0x1D, "GS"),
        (0x1E, "RS"),
        (0x1F, "US"),
    ])
    def test_normal_control_chars_removed(self, code, description):
        """Normal control chars (except tab/newline/CR) are removed entirely."""
        char = chr(code)
        result = _escape_control_characters(char)
        assert result == "", f"Control char 0x{code:02X} ({description}) should be removed"

    def test_tab_replaced_with_space(self):
        """Tab (0x09) is replaced with space."""
        assert _escape_control_characters("\t") == " "

    def test_newline_replaced_with_space(self):
        """Newline (0x0A) is replaced with space."""
        assert _escape_control_characters("\n") == " "

    def test_carriage_return_replaced_with_space(self):
        """Carriage return (0x0D) is replaced with space."""
        assert _escape_control_characters("\r") == " "

    def test_null_byte_removed(self):
        """Null byte (0x00) is removed entirely."""
        assert _escape_control_characters("\x00") == ""


class TestRemovalBoundary:
    """Test boundary conditions between control and non-control chars."""

    def test_boundary_0x1F_last_control_char(self):
        """0x1F (US) is the last control char and should be removed."""
        assert _escape_control_characters("\x1F") == ""

    def test_boundary_0x20_first_non_control_char(self):
        """0x20 (space) is the first non-control char and should pass through."""
        assert _escape_control_characters("\x20") == " "

    def test_boundary_0x1E_before_last_control(self):
        """0x1E (RS) should be removed."""
        assert _escape_control_characters("\x1E") == ""

    def test_boundary_0x21_printable_exclamation(self):
        """0x21 (!) is non-control and should pass through."""
        assert _escape_control_characters("!") == "!"

    def test_boundary_transition_1e_to_21(self):
        """Transition from 0x1E (control) to 0x21 (printable)."""
        result = _escape_control_characters("\x1E!")
        assert result == "!"  # 0x1E removed, ! stays


class TestRemovalMultiple:
    """Test multiple control characters."""

    def test_multiple_control_chars_in_sequence(self):
        """Multiple control chars are all removed."""
        # 0x01, 0x02, 0x03 are all removed
        result = _escape_control_characters("\x01\x02\x03")
        assert result == ""

    def test_control_chars_mixed_with_text(self):
        """Control chars removed, text preserved."""
        # "H" + 0x01 + "ello"
        result = _escape_control_characters("H\x01ello")
        assert result == "Hello"

    def test_control_chars_at_start(self):
        """Control chars at string start are removed."""
        result = _escape_control_characters("\x01\x02Hello")
        assert result == "Hello"

    def test_control_chars_at_end(self):
        """Control chars at string end are removed."""
        result = _escape_control_characters("Hello\x01\x02")
        assert result == "Hello"

    def test_control_chars_surrounded(self):
        """Control chars surrounded by text are removed."""
        result = _escape_control_characters("Start\x01\x02Middle\x03End")
        assert result == "StartMiddleEnd"

    def test_multiple_newlines_become_spaces(self):
        """Multiple newlines are replaced with spaces."""
        result = _escape_control_characters("Line1\nLine2\nLine3")
        assert result == "Line1 Line2 Line3"

    def test_tabs_and_newlines_mixed_become_spaces(self):
        """Mixed tabs and newlines are replaced with spaces."""
        result = _escape_control_characters("Col1\tCol2\nRow2\tVal")
        assert result == "Col1 Col2 Row2 Val"


class TestRemovalRealWorldScenarios:
    """Test real-world OCR and form scenarios."""

    def test_json_string_with_embedded_newline_in_value(self):
        """Newlines in field values are preserved as spaces (JSON-safe)."""
        # Simulates Groq response with "value": "line1\nline2\nline3"
        result = _escape_control_characters('{"field": "value\nwith\nnewlines"}')
        assert result == '{"field": "value with newlines"}'

    def test_json_string_with_embedded_tabs(self):
        """Tabs in field values are preserved as spaces (JSON-safe)."""
        result = _escape_control_characters('{"field": "col1\tcol2\tcol3"}')
        assert result == '{"field": "col1 col2 col3"}'

    def test_business_name_with_carriage_returns(self):
        """CR characters are replaced with spaces."""
        result = _escape_control_characters("Santos\rTrading\r")
        assert result == "Santos Trading "

    def test_multiline_json_structure(self):
        """JSON structure with formatting newlines/tabs becomes single-line friendly."""
        json_with_formatting = '{\n  "extracted_fields": [\n    {"field": "value"}\n  ]\n}'
        result = _escape_control_characters(json_with_formatting)
        # All newlines replaced with spaces, tabs replaced with spaces
        # {newline+spaces+newline...} becomes {space+spaces+space...}
        assert '\n' not in result  # No newlines in output
        assert '"extracted_fields"' in result  # Key preserved

    def test_phone_number_with_control_char_artifact(self):
        """Control char artifacts are removed, number preserved."""
        # Some OCR artifact: NUL byte inserted
        result = _escape_control_characters("0917\x00123\x014567")
        assert result == "09171234567"

    def test_form_feed_article_separated_sections(self):
        """Form feed (0x0C) separates sections, removed for cleaner data."""
        result = _escape_control_characters("Section1\fSection2\fSection3")
        assert result == "Section1Section2Section3"

    def test_special_characters_not_removed(self):
        """Unicode characters that look control-like are preserved."""
        # U+2013 EN DASH, U+2014 EM DASH (not control chars)
        result = _escape_control_characters("Value–123—456")
        assert result == "Value–123—456"

    def test_unicode_business_names(self):
        """International business names with control chars embedded."""
        result = _escape_control_characters("Café\x01Bar\x02Manila")
        assert result == "CaféBarManila"

    def test_emoji_characters_unchanged(self):
        """Emoji are preserved."""
        result = _escape_control_characters("Store🏪\x01Location📍")
        assert result == "Store🏪Location📍"


class TestRemovalIntegration:
    """Integration with JSON parsing."""

    def test_removal_makes_json_parseable(self):
        """Output of function produces valid JSON parseable strings."""
        import json
        # JSON with control char in value before function
        json_text = '{"field": "value\nwith\nnewline"}'
        cleaned = _escape_control_characters(json_text)
        # Should now be parseable (assuming no other JSON issues)
        try:
            parsed = json.loads(cleaned)
            assert parsed == {"field": "value with newline"}
        except json.JSONDecodeError:
            pytest.fail("Cleaned JSON should be parseable")

    def test_json_with_control_char_in_structure(self):
        """Control char in JSON structure (formatting) is handled."""
        # JSON with newline after {
        json_text = '{\n  "field": "value"\n}'
        cleaned = _escape_control_characters(json_text)
        import json
        parsed = json.loads(cleaned)
        assert "field" in parsed

    def test_groq_response_with_paragraph_marks(self):
        """Real OCR scenario: paragraph marks (0x14) mixed in extracted text."""
        # 0x14 (Device Control 4) is a control char and gets removed (not space)
        groq_like_response = '{"field_name": "name", "value": "Maria\x14Santos\x14Trading"}'
        cleaned = _escape_control_characters(groq_like_response)
        import json
        parsed = json.loads(cleaned)
        # 0x14 chars removed entirely, values concatenated
        assert parsed["value"] == "MariaSantosTrading"


class TestRemovalEdgeCases:
    """Edge cases and robustness."""

    def test_very_long_string_with_scattered_control_chars(self):
        """Long string with scattered control chars is cleaned efficiently."""
        # 1000 char string with control chars every 10 chars
        text = "".join(chr(0x41) * 9 + chr(0x01) for _ in range(100))  # 100 repetitions of A*9 + NUL
        result = _escape_control_characters(text)
        assert result == chr(0x41) * 900  # Only 900 As

    def test_only_control_characters(self):
        """String of only control chars becomes empty (or spaces for tab/newline/CR)."""
        result = _escape_control_characters("\x01\x02\x03\x04\x05")
        assert result == ""

    def test_alternating_control_and_text(self):
        """Alternating control and text results in text only."""
        result = _escape_control_characters("a\x01b\x02c\x03d")
        assert result == "abcd"

    def test_all_32_control_chars_in_one_string(self):
        """All 32 control chars (0x00-0x1F) handled correctly."""
        all_controls = "".join(chr(i) for i in range(0x20))
        result = _escape_control_characters(all_controls)
        # Should have spaces for 0x09, 0x0A, 0x0D, everything else removed
        assert result == "   "  # Three spaces for tab, newline, CR

    def test_string_with_backslash_preserved(self):
        """Backslash (0x5C) is preserved (not a control char)."""
        assert _escape_control_characters("path\\to\\file") == "path\\to\\file"

    def test_string_already_containing_escape_sequences(self):
        """String with visible escape sequences (e.g., \\n text) is handled."""
        # The literal characters '\n' in text (not the newline byte)
        text = "Line\\nBreak"  # Backslash-n, not newline
        assert _escape_control_characters(text) == "Line\\nBreak"


class TestRemovalTypeHandling:
    """Type checking and edge cases."""

    def test_accepts_string_input(self):
        """Function correctly accepts string input."""
        result = _escape_control_characters("test")
        assert isinstance(result, str)

    def test_returns_string_output(self):
        """Function returns string output."""
        result = _escape_control_characters("test\x01data")
        assert isinstance(result, str)

    def test_does_not_modify_original_string(self):
        """Function is pure - doesn't modify original."""
        original = "test\x01string"
        _escape_control_characters(original)
        assert original == "test\x01string"


class TestRemovalRobustness:
    """Robustness and functional properties."""

    def test_idempotency_on_already_cleaned(self):
        """Calling twice on same string produces same result."""
        text = "Already\x01Clean"
        first = _escape_control_characters(text)
        second = _escape_control_characters(first)
        assert first == second

    def test_consistency_across_calls(self):
        """Same input always produces same output."""
        text = "Test\x01Data\nMore"
        result1 = _escape_control_characters(text)
        result2 = _escape_control_characters(text)
        assert result1 == result2

    def test_no_side_effects(self):
        """Function has no side effects (pure function)."""
        original = "Original\nString"
        
        # Call multiple times
        _escape_control_characters(original)
        _escape_control_characters(original)
        _escape_control_characters(original)
        
        # Original unchanged
        assert original == "Original\nString"
