r"""
Unit Tests for _escape_control_characters()

Tests the escape_control_characters utility function which converts invalid JSON
control characters (0x00-0x1F) to Unicode escape sequences (\uXXXX).

Status: Complete unit test suite with 100% coverage target
"""

import pytest
from app.services.ocr_groq_extraction import _escape_control_characters


class TestEscapeControlCharactersBasic:
    """Test basic functionality and empty/normal inputs."""

    def test_empty_string(self):
        """Empty string returns empty."""
        result = _escape_control_characters("")
        assert result == ""

    def test_no_control_characters(self):
        """String with no control chars (0x20+) passes through unchanged."""
        test_string = "Hello, World! 123"
        result = _escape_control_characters(test_string)
        assert result == test_string

    def test_single_space_unchanged(self):
        """Space (0x20) is NOT a control char and should pass through."""
        result = _escape_control_characters(" ")
        assert result == " "

    def test_printable_ascii_unchanged(self):
        """All printable ASCII (0x20-0x7E) unchanged."""
        printable = "!\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
        result = _escape_control_characters(printable)
        assert result == printable

    def test_extended_unicode_unchanged(self):
        """Unicode characters > 0x7F pass through unchanged."""
        unicode_text = "Café résumé 你好 مرحبا"
        result = _escape_control_characters(unicode_text)
        assert result == unicode_text


class TestEscapeControlCharactersSingle:
    """Test individual control characters from the full 0x00-0x1F range."""

    # Comprehensive parametrized test for all 32 control characters
    @pytest.mark.parametrize("control_code,expected_escape", [
        (0x00, "\\u0000"),  # NULL
        (0x01, "\\u0001"),  # SOH (Start of Heading)
        (0x02, "\\u0002"),  # STX (Start of Text)
        (0x03, "\\u0003"),  # ETX (End of Text)
        (0x04, "\\u0004"),  # EOT (End of Transmission)
        (0x05, "\\u0005"),  # ENQ (Enquiry)
        (0x06, "\\u0006"),  # ACK (Acknowledge)
        (0x07, "\\u0007"),  # BEL (Bell)
        (0x08, "\\u0008"),  # BS (Backspace)
        (0x09, "\\u0009"),  # TAB (Horizontal Tab) — COMMON IN OCR
        (0x0A, "\\u000a"),  # LF (Line Feed / Newline) — COMMON IN OCR
        (0x0B, "\\u000b"),  # VT (Vertical Tab)
        (0x0C, "\\u000c"),  # FF (Form Feed)
        (0x0D, "\\u000d"),  # CR (Carriage Return) — COMMON IN WINDOWS
        (0x0E, "\\u000e"),  # SO (Shift Out)
        (0x0F, "\\u000f"),  # SI (Shift In)
        (0x10, "\\u0010"),  # DLE (Data Link Escape)
        (0x11, "\\u0011"),  # DC1 (Device Control 1)
        (0x12, "\\u0012"),  # DC2 (Device Control 2)
        (0x13, "\\u0013"),  # DC3 (Device Control 3)
        (0x14, "\\u0014"),  # DC4 (Device Control 4)
        (0x15, "\\u0015"),  # NAK (Negative Acknowledge)
        (0x16, "\\u0016"),  # SYN (Synchronous Idle)
        (0x17, "\\u0017"),  # ETB (End of Transmission Block)
        (0x18, "\\u0018"),  # CAN (Cancel)
        (0x19, "\\u0019"),  # EM (End of Medium)
        (0x1A, "\\u001a"),  # SUB (Substitute)
        (0x1B, "\\u001b"),  # ESC (Escape)
        (0x1C, "\\u001c"),  # FS (File Separator)
        (0x1D, "\\u001d"),  # GS (Group Separator)
        (0x1E, "\\u001e"),  # RS (Record Separator)
        (0x1F, "\\u001f"),  # US (Unit Separator) — LAST CONTROL CHAR
    ])
    def test_all_control_characters_escaped(self, control_code, expected_escape):
        """All 32 control characters (0x00-0x1F) are escaped as \\uXXXX."""
        char = chr(control_code)
        result = _escape_control_characters(char)
        assert result == expected_escape

    def test_tab_escaped(self):
        """TAB (0x09) escaped as \\u0009."""
        result = _escape_control_characters("\t")
        assert result == "\\u0009"

    def test_newline_escaped(self):
        """LF (0x0A) / newline escaped as \\u000a."""
        result = _escape_control_characters("\n")
        assert result == "\\u000a"

    def test_carriage_return_escaped(self):
        """CR (0x0D) escaped as \\u000d."""
        result = _escape_control_characters("\r")
        assert result == "\\u000d"

    def test_null_byte_escaped(self):
        """NULL (0x00) escaped as \\u0000."""
        result = _escape_control_characters("\x00")
        assert result == "\\u0000"


class TestEscapeControlCharactersBoundary:
    """Test boundary values and transitions."""

    def test_boundary_0x1F_last_control_char(self):
        """0x1F (Unit Separator) is last control char and should be escaped."""
        result = _escape_control_characters(chr(0x1F))
        assert result == "\\u001f"

    def test_boundary_0x20_first_non_control_char(self):
        """0x20 (space) is first non-control and should NOT be escaped."""
        result = _escape_control_characters(chr(0x20))
        assert result == " "

    def test_boundary_0x1E_before_last_control(self):
        """0x1E (Record Separator) is control and should be escaped."""
        result = _escape_control_characters(chr(0x1E))
        assert result == "\\u001e"

    def test_boundary_0x21_printable_exclamation(self):
        """0x21 (!) is printable and should NOT be escaped."""
        result = _escape_control_characters("!")
        assert result == "!"

    def test_boundary_transition_1e_to_21(self):
        """Boundary transition: 0x1E, 0x1F, 0x20, 0x21."""
        input_str = chr(0x1E) + chr(0x1F) + chr(0x20) + chr(0x21)
        result = _escape_control_characters(input_str)
        expected = "\\u001e\\u001f !"
        assert result == expected


class TestEscapeControlCharactersMultiple:
    """Test multiple control characters in various arrangements."""

    def test_multiple_control_chars_in_sequence(self):
        """Multiple control chars in a row, all escaped."""
        input_str = "\x00\x01\x02"
        result = _escape_control_characters(input_str)
        expected = "\\u0000\\u0001\\u0002"
        assert result == expected

    def test_control_chars_mixed_with_text(self):
        """Control chars interspersed with normal text."""
        input_str = "Hello\nWorld\tTest"  # newline and tab
        result = _escape_control_characters(input_str)
        expected = "Hello\\u000aWorld\\u0009Test"
        assert result == expected

    def test_control_chars_at_start(self):
        """Control chars at beginning of string."""
        input_str = "\n\r" + "text"
        result = _escape_control_characters(input_str)
        expected = "\\u000a\\u000d" + "text"
        assert result == expected

    def test_control_chars_at_end(self):
        """Control chars at end of string."""
        input_str = "text" + "\n\t"
        result = _escape_control_characters(input_str)
        expected = "text" + "\\u000a\\u0009"
        assert result == expected

    def test_control_chars_surrounded(self):
        """Control char surrounded by normal text."""
        input_str = "before\nmiddle\nafter"
        result = _escape_control_characters(input_str)
        expected = "before\\u000amiddle\\u000aafter"
        assert result == expected

    def test_multiple_newlines(self):
        """Multiple newlines (OCR multiline text scenario)."""
        input_str = "Line1\nLine2\nLine3"
        result = _escape_control_characters(input_str)
        expected = "Line1\\u000aLine2\\u000aLine3"
        assert result == expected

    def test_tabs_and_newlines_mixed(self):
        """Mix of tabs and newlines (common OCR preprocessing artifacts)."""
        input_str = "Col1\tCol2\tCol3\nRow2\tData"
        result = _escape_control_characters(input_str)
        expected = "Col1\\u0009Col2\\u0009Col3\\u000aRow2\\u0009Data"
        assert result == expected


class TestEscapeControlCharactersRealWorldScenarios:
    """Test realistic OCR and Groq response scenarios."""

    def test_json_string_with_embedded_newline_in_value(self):
        """OCR extracted multiline address→value with actual newlines."""
        # Before escaping (raw Groq response content):
        field_value = "123 Main St\nApt 4B"
        result = _escape_control_characters(field_value)
        # Should escape the newline
        assert "\\u000a" in result
        assert result == "123 Main St\\u000aApt 4B"

    def test_json_string_with_embedded_tabs(self):
        """Tab-separated OCR text (preprocessing artifact)."""
        field_value = "Name\tAge\tCity"
        result = _escape_control_characters(field_value)
        assert result == "Name\\u0009Age\\u0009City"

    def test_business_name_with_carriage_returns(self):
        """Windows-style line ending (CR+LF) in extracted text."""
        field_value = "Business Inc\r\nBranch Office"
        result = _escape_control_characters(field_value)
        assert result == "Business Inc\\u000d\\u000aBranch Office"

    def test_multiline_address_field(self):
        """Complete address with realistic newlines."""
        address = "123 Main Street\n456 Plaza\nCity, State 12345"
        result = _escape_control_characters(address)
        expected = "123 Main Street\\u000a456 Plaza\\u000aCity, State 12345"
        assert result == expected

    def test_phone_number_with_null_bytes_artifact(self):
        """Malformed OCR with stray null bytes."""
        phone = "555-1234\x00ext"
        result = _escape_control_characters(phone)
        assert result == "555-1234\\u0000ext"

    def test_form_field_with_form_feed(self):
        """Form feed character (page break) in OCR text."""
        text = "Page1\fPage2"
        result = _escape_control_characters(text)
        assert result == "Page1\\u000cPage2"

    def test_special_characters_not_control_chars(self):
        """Special chars that might look like control but aren't (0x20+)."""
        special = "!@#$%^&*()_+-=[]{}|;:',.<>?/"
        result = _escape_control_characters(special)
        # All should be unchanged
        assert result == special

    def test_unicode_business_names(self):
        """International business names with Unicode."""
        # Chinese, Arabic, Cyrillic — all > 0x7F
        names = "北京公司\nشركة\nООО Компания"
        result = _escape_control_characters(names)
        # Newline escaped, Unicode unchanged
        assert "\\u000a" in result
        assert "北京公司" in result
        assert "شركة" in result
        assert "ООО Компания" in result

    def test_emoji_characters_unchanged(self):
        """Emoji (multi-byte Unicode) should pass through."""
        emoji_text = "Status: ✓ Complete 👍 Done 🎉"
        result = _escape_control_characters(emoji_text)
        assert result == emoji_text
        assert "✓" in result
        assert "👍" in result
        assert "🎉" in result


class TestEscapeControlCharactersIntegration:
    """Test that escaped output is valid for JSON parsing."""

    def test_escaped_output_is_json_parseable(self):
        """Escaped output can be embedded in JSON and parsed."""
        import json
        
        # Original string with newline
        original = "Line1\nLine2"
        escaped = _escape_control_characters(original)
        
        # Embed in JSON
        json_str = json.dumps({"value": escaped})
        
        # Should parse without error
        parsed = json.loads(json_str)
        assert parsed["value"] == escaped

    def test_escaped_control_chars_in_json_field_value(self):
        """Control char in field value, escaped, then embedded in JSON."""
        import json
        
        # Raw value with tab
        raw_value = "FirstName\tLastName"
        escaped_value = _escape_control_characters(raw_value)
        
        # Build JSON structure (simulating Groq response)
        json_content = json.dumps({
            "extracted_fields": [
                {"field_name": "name", "value": escaped_value, "confidence": 0.9}
            ]
        })
        
        # Should parse successfully
        parsed = json.loads(json_content)
        assert len(parsed["extracted_fields"]) == 1
        assert "\\u0009" in parsed["extracted_fields"][0]["value"]

    def test_parse_json_with_embedded_newline_after_escape(self):
        """Full workflow: bad JSON → escape → valid JSON → parse."""
        import json
        
        # This would fail without escaping (newline in string literal)
        bad_json = '{"name": "John\nDoe"}'  # Literal newline breaks JSON
        
        # Extract and escape
        parts = bad_json.split('"John')
        middle_part = 'John' + '\nDoe'  # Has newline
        escaped_middle = _escape_control_characters(middle_part)
        
        # Rebuild
        good_json = '{"name": "' + escaped_middle + '"}'
        
        # Now it should parse
        parsed = json.loads(good_json)
        assert "John" in parsed["name"]
        assert "Doe" in parsed["name"]

    def test_roundtrip_preserve_text_meaning(self):
        """Text meaning preserved after escaping (for human reading)."""
        # Address with actual newlines
        address = "123 Main St\nApt 5B\nNew York, NY"
        escaped = _escape_control_characters(address)
        
        # When decoded/unescaped by JSON parser, should read as:
        # "123 Main St\nApt 5B\nNew York, NY" (with newlines interpreted)
        assert "123 Main St" in escaped
        assert "Apt 5B" in escaped
        assert "New York, NY" in escaped
        # Newlines are escaped:
        assert "\\u000a" in escaped


class TestEscapeControlCharactersEdgeCases:
    """Test unusual but valid edge cases."""

    def test_very_long_string_with_scattered_control_chars(self):
        """Long string (1000+ chars) with scattered control chars."""
        # Build a long string with control chars every 100 chars
        parts = []
        for i in range(10):
            parts.append("x" * 100 + "\n")
        long_string = "".join(parts)
        
        result = _escape_control_characters(long_string)
        
        # Should have 10 escaped newlines
        assert result.count("\\u000a") == 10
        # Should have 1000 x's still
        assert result.count("x") == 1000

    def test_only_control_characters(self):
        """String containing ONLY control characters."""
        control_only = "\x00\x09\x0A\x0D\x1F"
        result = _escape_control_characters(control_only)
        expected = "\\u0000\\u0009\\u000a\\u000d\\u001f"
        assert result == expected

    def test_alternating_control_and_text(self):
        """Alternating control char and text: C T C T C."""
        input_str = "\nA\tB\nC"
        result = _escape_control_characters(input_str)
        expected = "\\u000aA\\u0009B\\u000aC"
        assert result == expected

    def test_all_32_control_chars_in_one_string(self):
        """All 32 control chars in a single string."""
        all_controls = "".join(chr(i) for i in range(0x00, 0x20))
        result = _escape_control_characters(all_controls)
        
        # Should have 32 escaped sequences
        assert result.count("\\u") == 32
        
        # Spot check a few
        assert "\\u0000" in result  # NULL
        assert "\\u0009" in result  # TAB
        assert "\\u000a" in result  # LF
        assert "\\u001f" in result  # US

    def test_string_with_backslash_preserved(self):
        """Existing backslashes in text should be preserved (not double-escaped)."""
        text = "Path\\to\\file"
        result = _escape_control_characters(text)
        # Backslashes should stay as-is (they're not control chars)
        assert result == text
        assert "\\" in result
        assert result.count("\\") == 2

    def test_string_already_containing_escape_sequences(self):
        """String with existing \\uXXXX sequences should not be double-escaped."""
        # This is already escaped (from another source)
        already_escaped = "Value: \\u000a"
        result = _escape_control_characters(already_escaped)
        # Should NOT change it (the backslash and 'u' are not control chars)
        assert result == already_escaped
        assert result.count("\\u") == 1


class TestEscapeControlCharactersTypeHandling:
    """Test type behavior and invalid input handling."""

    def test_accepts_string_input(self):
        """Function accepts standard string."""
        result = _escape_control_characters("test")
        assert isinstance(result, str)

    def test_returns_string_output(self):
        """Function always returns a string."""
        result = _escape_control_characters("")
        assert isinstance(result, str)
        
        result = _escape_control_characters("normal")
        assert isinstance(result, str)
        
        result = _escape_control_characters("\n\t\r")
        assert isinstance(result, str)

    def test_does_not_modify_original_string(self):
        """Original string passed is not modified (immutability)."""
        original = "Test\nString"
        original_copy = original
        
        _escape_control_characters(original)
        
        # Original should be unchanged
        assert original == original_copy
        assert "\n" in original  # Newline still there


class TestEscapeControlCharactersRobustness:
    """Test robustness and consistency."""

    def test_idempotency_on_already_escaped(self):
        """Already-escaped string when escaped again produces same result."""
        original = "Test\nValue"
        escaped_once = _escape_control_characters(original)
        escaped_twice = _escape_control_characters(escaped_once)
        
        # Second escape shouldn't change anything (backslash and 'u' aren't control chars)
        assert escaped_once == escaped_twice

    def test_consistency_across_calls(self):
        """Same input produces same output consistently."""
        input_str = "Name\nAddress\tPhone"
        result1 = _escape_control_characters(input_str)
        result2 = _escape_control_characters(input_str)
        
        assert result1 == result2

    def test_no_side_effects(self):
        """Function has no side effects (pure function)."""
        original = "Test\n"
        
        # Call function multiple times
        _escape_control_characters(original)
        _escape_control_characters(original)
        _escape_control_characters(original)
        
        # Original unchanged and still works normally
        assert original == "Test\n"
        assert len(original) == 5


# ============================================================================
# INTEGRATION TESTS: Interaction with parse_groq_response
# ============================================================================

class TestEscapeControlCharactersIntegrationWithParser:
    """Integration tests verifying escaping works in parse_groq_response context."""

    def test_escape_enables_json_parsing_of_control_char_values(self):
        """Escaped control chars allow JSON parsing of Groq responses."""
        import json
        from app.services.ocr_groq_extraction import parse_groq_response
        
        # Simulate Groq response with newline in value
        # Without escaping, this would fail to parse
        response_content = '{"extracted_fields": [{"field_name": "address", "value": "Street 123\\nCity", "confidence": 0.9}]}'
        
        # This should succeed when escaping is applied
        result = parse_groq_response(response_content)
        assert result is not None
        assert len(result["extracted_fields"]) == 1

    def test_multiline_form_values_handled_by_parser(self):
        """Parser with escaping handles multiline form values."""
        from app.services.ocr_groq_extraction import parse_groq_response
        
        # Realistic multiline form field
        content = '{"extracted_fields": [{"field_name": "description", "value": "Line 1\\nLine 2\\nLine 3", "confidence": 0.85}]}'
        
        result = parse_groq_response(content)
        
        assert result is not None
        assert result["extracted_fields"][0]["field_name"] == "description"
        # Value should contain the lines
        assert "Line 1" in result["extracted_fields"][0]["value"]

    def test_form_with_tab_separated_values(self):
        """Parser handles tab-separated extracted values."""
        from app.services.ocr_groq_extraction import parse_groq_response
        
        # Tab-separated cell data
        content = '{"extracted_fields": [{"field_name": "table_row", "value": "Col1\\tCol2\\tCol3", "confidence": 0.8}]}'
        
        result = parse_groq_response(content)
        
        assert result is not None
        assert len(result["extracted_fields"]) == 1
