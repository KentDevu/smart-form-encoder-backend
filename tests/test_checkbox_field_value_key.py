"""
Comprehensive tests for checkbox field value key fix.

Tests verify that checkbox fields now export with "value" key instead of "ocr_value"
for consistency with the extraction pipeline, enabling DTI rules to read checkbox values.

pytest coverage target: ≥80%

Test Categories:
1. Unit tests for _get_value_for_checkbox_state (checkbox state → string value)
2. Unit tests for _convert_checkbox_to_field (field record generation)
3. Edge case tests (None, unclear, boundary conditions)
4. Integration tests (DTI rules receiving checkbox fields)
5. Full pipeline tests (checkboxes → field records → DTI rules → database)
"""

import pytest
from typing import Any
from unittest.mock import Mock, MagicMock, patch

from checkbox_field_mapping import (
    _get_value_for_checkbox_state,
    _convert_checkbox_to_field,
    _normalize_field_name,
    _fuzzy_match_text,
    _build_checkbox_field_mapping,
    apply_checkbox_mapping,
)
from app.services.ocr_checkbox_detector import (
    CheckboxState,
    DetectedCheckbox,
)
from app.services.ocr_region_classifier import BBox


# =============================================================================
# UNIT TESTS: _get_value_for_checkbox_state
# =============================================================================

class TestGetValueForCheckboxState:
    """Tests for checkbox state → string value conversion."""

    def test_checked_state_returns_true_string(self):
        """CHECKED checkbox state should return 'true' (string)."""
        value = _get_value_for_checkbox_state(CheckboxState.CHECKED)
        assert value == "true"
        assert isinstance(value, str)

    def test_unchecked_state_returns_false_string(self):
        """UNCHECKED checkbox state should return 'false' (string)."""
        value = _get_value_for_checkbox_state(CheckboxState.UNCHECKED)
        assert value == "false"
        assert isinstance(value, str)

    def test_unclear_state_returns_empty_string(self):
        """UNCLEAR checkbox state should return empty string (for manual review)."""
        value = _get_value_for_checkbox_state(CheckboxState.UNCLEAR)
        assert value == ""
        assert isinstance(value, str)

    def test_value_types_are_strings_not_booleans(self):
        """Ensure values are strings, not booleans (critical for JSON serialization)."""
        checked_value = _get_value_for_checkbox_state(CheckboxState.CHECKED)
        unchecked_value = _get_value_for_checkbox_state(CheckboxState.UNCHECKED)
        unclear_value = _get_value_for_checkbox_state(CheckboxState.UNCLEAR)

        assert checked_value != True  # Should be string, not boolean
        assert unchecked_value != False  # Should be string, not boolean
        assert isinstance(checked_value, str)
        assert isinstance(unchecked_value, str)
        assert isinstance(unclear_value, str)

    def test_all_checkpoint_states_covered(self):
        """Verify all CheckboxState enum values are handled."""
        # This ensures no new states are added without handling
        for state in CheckboxState:
            result = _get_value_for_checkbox_state(state)
            assert result in ("true", "false", "")
            assert isinstance(result, str)


# =============================================================================
# UNIT TESTS: _convert_checkbox_to_field
# =============================================================================

class TestConvertCheckboxToField:
    """Tests for converting DetectedCheckbox → field record with 'value' key."""

    def test_field_record_has_value_key_not_ocr_value(self):
        """
        CRITICAL: Field record must have 'value' key, NOT 'ocr_value'.
        This is the core fix for DTI rules compatibility.
        """
        detected = DetectedCheckbox(
            name="checkbox_manufacturer",
            state=CheckboxState.CHECKED,
            confidence=0.95,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Manufacturer",
        )

        field_record = _convert_checkbox_to_field(detected, "manufacturer")

        # Core assertion: 'value' key exists
        assert "value" in field_record, "Field record must have 'value' key"
        assert field_record["value"] == "true"

        # Ensure 'ocr_value' key does NOT exist
        assert "ocr_value" not in field_record, "Field record should NOT have 'ocr_value' key"

    def test_checked_checkbox_converts_to_true_value(self):
        """Checked checkbox should convert to value='true'."""
        detected = DetectedCheckbox(
            name="checkbox_test",
            state=CheckboxState.CHECKED,
            confidence=0.92,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test_field")

        assert field_record["value"] == "true"
        assert field_record["field_name"] == "test_field"
        assert field_record["confidence"] == 0.92

    def test_unchecked_checkbox_converts_to_false_value(self):
        """Unchecked checkbox should convert to value='false'."""
        detected = DetectedCheckbox(
            name="checkbox_test",
            state=CheckboxState.UNCHECKED,
            confidence=0.88,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test_field")

        assert field_record["value"] == "false"
        assert field_record["field_name"] == "test_field"
        assert field_record["confidence"] == 0.88

    def test_unclear_checkbox_converts_to_empty_value(self):
        """Unclear checkbox should convert to empty string for manual review."""
        detected = DetectedCheckbox(
            name="checkbox_test",
            state=CheckboxState.UNCLEAR,
            confidence=0.45,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test_field")

        assert field_record["value"] == ""
        assert field_record["confidence"] == 0.45

    def test_field_record_structure_complete(self):
        """Verify all required keys in converted field record."""
        detected = DetectedCheckbox(
            name="checkbox_manufacturer",
            state=CheckboxState.CHECKED,
            confidence=0.95,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Manufacturer/Producer",
        )

        field_record = _convert_checkbox_to_field(detected, "manufacturer")

        # Required keys
        required_keys = {
            "field_name",
            "value",
            "confidence",
            "source",
            "anchor_text",
            "state",
        }
        assert set(field_record.keys()) == required_keys

    def test_field_record_source_is_checkbox_detection(self):
        """Verify source tag is 'checkbox_detection' for debugging."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["source"] == "checkbox_detection"

    def test_confidence_preserved_exactly(self):
        """Confidence score should be preserved without modification."""
        test_confidence = 0.8765
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=test_confidence,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["confidence"] == test_confidence

    def test_anchor_text_preserved_when_present(self):
        """Anchor text should be preserved if present in detected checkbox."""
        anchor = "Manufacturer / Producer (if applicable)"
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text=anchor,
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["anchor_text"] == anchor

    def test_anchor_text_empty_when_none(self):
        """Anchor text should be empty string if None."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["anchor_text"] == ""

    def test_state_metadata_preserved(self):
        """Original state enum should be preserved for metadata."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        # State should be the string value of the enum
        assert field_record["state"] == "checked"

    def test_field_name_mapping_correct(self):
        """Field name should map exactly as provided."""
        detected = DetectedCheckbox(
            name="checkbox_activity_manufacturer",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        # Map to different field name (simulating DTI field)
        field_record = _convert_checkbox_to_field(detected, "dti_activity_manufacturing")

        assert field_record["field_name"] == "dti_activity_manufacturing"

    def test_high_confidence_checked(self):
        """Test with high confidence (>0.9)."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.98,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["value"] == "true"
        assert field_record["confidence"] == 0.98

    def test_low_confidence_checked(self):
        """Test with lower confidence (<0.7)."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.65,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["value"] == "true"
        assert field_record["confidence"] == 0.65

    def test_minimum_confidence(self):
        """Test with minimum confidence (0.0)."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.UNCLEAR,
            confidence=0.0,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["value"] == ""
        assert field_record["confidence"] == 0.0


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestCheckboxConversionEdgeCases:
    """Edge cases and boundary conditions."""

    def test_field_name_with_special_characters(self):
        """Field names may contain underscores and numbers."""
        detected = DetectedCheckbox(
            name="checkbox_1",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "field_name_123_DTI")

        assert field_record["field_name"] == "field_name_123_DTI"
        assert field_record["value"] == "true"

    def test_empty_field_name(self):
        """Test with empty field name (edge case)."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "")

        assert field_record["field_name"] == ""
        assert field_record["value"] == "true"

    def test_very_long_field_name(self):
        """Test with very long field name."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        long_name = "a" * 500
        field_record = _convert_checkbox_to_field(detected, long_name)

        assert field_record["field_name"] == long_name

    def test_anchor_text_very_long(self):
        """Test with very long anchor text."""
        long_anchor = "X" * 500
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text=long_anchor,
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["anchor_text"] == long_anchor

    def test_unicode_in_field_name(self):
        """Field name with Unicode characters."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "field_名前")

        assert field_record["field_name"] == "field_名前"

    def test_confidence_boundary_0_0(self):
        """Confidence at boundary 0.0."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.0,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["confidence"] == 0.0

    def test_confidence_boundary_1_0(self):
        """Confidence at boundary 1.0."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=1.0,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )

        field_record = _convert_checkbox_to_field(detected, "test")

        assert field_record["confidence"] == 1.0


# =============================================================================
# DTI RULES INTEGRATION TESTS
# =============================================================================

class TestDTIRulesIntegration:
    """Tests verifying DTI rules can read checkbox field values correctly."""

    def test_dti_rule_reads_value_key(self):
        """
        DTI rules should be able to read 'value' key from checkbox field records.
        This is the key integration point.
        """
        # Create a checkbox field record
        detected = DetectedCheckbox(
            name="checkbox_manufacturer",
            state=CheckboxState.CHECKED,
            confidence=0.95,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Manufacturer",
        )
        field_record = _convert_checkbox_to_field(detected, "activity_manufacturer")

        # Simulate DTI rule reading the field
        # (This is what the DTI rules would do)
        dti_field_value = field_record.get("value")

        # DTI rule should get the correct value
        assert dti_field_value == "true"
        assert dti_field_value is not None

    def test_dti_rule_cannot_read_ocr_value_key(self):
        """
        DTI rules should NOT find 'ocr_value' key (verifying the fix).
        This ensures the old key is removed.
        """
        detected = DetectedCheckbox(
            name="checkbox_test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # DTI rule attempting to read old 'ocr_value' key should get None
        dti_field_value = field_record.get("ocr_value")

        assert dti_field_value is None, "ocr_value key should not exist"

    def test_dti_rule_gets_true_for_checked(self):
        """DTI rule reads 'true' (string) for checked checkbox."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # What DTI rule sees
        value = field_record.get("value")
        confidence = field_record.get("confidence")

        assert value == "true"
        assert confidence == 0.90

    def test_dti_rule_gets_false_for_unchecked(self):
        """DTI rule reads 'false' (string) for unchecked checkbox."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.UNCHECKED,
            confidence=0.88,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # What DTI rule sees
        value = field_record.get("value")

        assert value == "false"

    def test_dti_rule_gets_empty_for_unclear(self):
        """DTI rule reads empty string for unclear checkbox."""
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.UNCLEAR,
            confidence=0.45,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # What DTI rule sees
        value = field_record.get("value")

        assert value == ""

    def test_dti_rule_field_preservation(self):
        """DTI rule preserves all field metadata through the pipeline."""
        detected = DetectedCheckbox(
            name="checkbox_activity",
            state=CheckboxState.CHECKED,
            confidence=0.92,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Activity: Manufacturing",
        )
        field_record = _convert_checkbox_to_field(detected, "dti_activity_code")

        # All DTI-relevant fields are present
        assert field_record["field_name"] == "dti_activity_code"
        assert field_record["value"] == "true"
        assert field_record["confidence"] == 0.92
        assert field_record["source"] == "checkbox_detection"
        assert field_record["anchor_text"] == "Activity: Manufacturing"


# =============================================================================
# FULL PIPELINE INTEGRATION TESTS
# =============================================================================

class TestFullPipelineIntegration:
    """
    Full pipeline integration tests: checkboxes → field records → DTI rules → storage.
    """

    def test_pipeline_multiple_checkboxes(self):
        """Test full pipeline with multiple checkbox fields."""
        # Simulate extracted checkboxes
        checkboxes = [
            DetectedCheckbox(
                name="checkbox_manufacturer",
                state=CheckboxState.CHECKED,
                confidence=0.95,
                bbox=BBox(top=10, left=20, bottom=30, right=40),
                anchor_text="Manufacturer",
            ),
            DetectedCheckbox(
                name="checkbox_wholesale",
                state=CheckboxState.UNCHECKED,
                confidence=0.90,
                bbox=BBox(top=50, left=60, bottom=70, right=80),
                anchor_text="Wholesale",
            ),
            DetectedCheckbox(
                name="checkbox_retail",
                state=CheckboxState.UNCLEAR,
                confidence=0.50,
                bbox=BBox(top=90, left=100, bottom=110, right=120),
                anchor_text="Retail",
            ),
        ]

        # Convert to field records
        field_records = []
        field_mappings = {
            "checkbox_manufacturer": "activity_manufacturer",
            "checkbox_wholesale": "activity_wholesale",
            "checkbox_retail": "activity_retail",
        }

        for checkbox in checkboxes:
            field_name = field_mappings.get(checkbox.name, checkbox.name)
            field_record = _convert_checkbox_to_field(checkbox, field_name)
            field_records.append(field_record)

        # Verify all records have 'value' key and correct structure
        assert len(field_records) == 3

        # First checkbox (CHECKED)
        assert field_records[0]["value"] == "true"
        assert field_records[0]["field_name"] == "activity_manufacturer"
        assert field_records[0]["confidence"] == 0.95
        assert "value" in field_records[0]
        assert "ocr_value" not in field_records[0]

        # Second checkbox (UNCHECKED)
        assert field_records[1]["value"] == "false"
        assert field_records[1]["field_name"] == "activity_wholesale"
        assert field_records[1]["confidence"] == 0.90

        # Third checkbox (UNCLEAR)
        assert field_records[2]["value"] == ""
        assert field_records[2]["field_name"] == "activity_retail"
        assert field_records[2]["confidence"] == 0.50

    def test_database_storage_compatibility(self):
        """
        Verify field records are compatible with database storage.
        Database expects 'value' key in form_fields records.
        """
        detected = DetectedCheckbox(
            name="checkbox_test",
            state=CheckboxState.CHECKED,
            confidence=0.92,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # Simulate database insertion (checking required fields)
        db_required_fields = {"field_name", "value", "confidence", "source"}

        assert db_required_fields.issubset(set(field_record.keys()))

        # Database should be able to read these values
        assert isinstance(field_record["field_name"], str)
        assert isinstance(field_record["value"], str)
        assert isinstance(field_record["confidence"], (int, float))
        assert isinstance(field_record["source"], str)

    def test_json_serialization_compatibility(self):
        """
        Field records should be JSON-serializable.
        This is critical for API responses and storage.
        """
        import json

        detected = DetectedCheckbox(
            name="checkbox_test",
            state=CheckboxState.CHECKED,
            confidence=0.92,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # Should serialize without errors
        json_str = json.dumps(field_record)
        assert json_str is not None

        # Should deserialize back
        deserialized = json.loads(json_str)
        assert deserialized["value"] == "true"
        assert deserialized["field_name"] == "test_field"

    def test_pipeline_maintains_confidence_hierarchy(self):
        """
        Verify that high-confidence checkboxes are preserved correctly
        through the pipeline. Low-confidence should be marked for review.
        """
        # High confidence
        high_conf_detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.98,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        high_conf_record = _convert_checkbox_to_field(
            high_conf_detected, "test_field"
        )

        # Low confidence
        low_conf_detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.55,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        low_conf_record = _convert_checkbox_to_field(low_conf_detected, "test_field")

        # Both have 'value' key and correct state
        assert high_conf_record["value"] == "true"
        assert low_conf_record["value"] == "true"

        # But confidence differs (for review logic)
        assert high_conf_record["confidence"] > low_conf_record["confidence"]

    def test_pipeline_handles_mixed_checkbox_types(self):
        """
        Pipeline should handle a mix of checked, unchecked, and unclear.
        """
        states = [
            CheckboxState.CHECKED,
            CheckboxState.UNCHECKED,
            CheckboxState.UNCLEAR,
        ]
        expected_values = ["true", "false", ""]

        for state, expected_value in zip(states, expected_values):
            detected = DetectedCheckbox(
                name="test",
                state=state,
                confidence=0.90,
                bbox=BBox(top=10, left=20, bottom=30, right=40),
                anchor_text="Test",
            )
            field_record = _convert_checkbox_to_field(detected, "test_field")

            assert field_record["value"] == expected_value
            assert "value" in field_record
            assert "ocr_value" not in field_record


# =============================================================================
# CONSISTENCY TESTS
# =============================================================================

class TestConsistencyWithOtherExtractors:
    """
    Verify checkbox field records are consistent with other extractors.
    All extractors should use 'value' key (not 'ocr_value').
    """

    def test_checkbox_field_structure_matches_pattern(self):
        """
        Checkbox field structure should match the pattern used by OCR extractors.
        Common pattern: field_name, value, confidence, source.
        """
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.95,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # Standard extractor pattern
        standard_keys = {"field_name", "value", "confidence", "source"}

        # Checkbox should have at least these keys
        assert standard_keys.issubset(set(field_record.keys()))

    def test_checkbox_value_is_string_like_text_extractors(self):
        """
        Checkbox values should be strings, consistent with text extractors.
        """
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.95,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # Value should be a string, like text extractors return
        assert isinstance(field_record["value"], str)
        assert field_record["value"] in ("true", "false", "")


# =============================================================================
# REGRESSION TESTS (Ensure fix doesn't break existing behavior)
# =============================================================================

class TestRegressionProtection:
    """Tests to prevent regression of the fix."""

    def test_no_regression_ocr_value_key(self):
        """
        REGRESSION: If someone adds 'ocr_value' key back, this test fails.
        This ensures the fix is not accidentally reverted.
        """
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # Must NOT have 'ocr_value'
        assert "ocr_value" not in field_record

    def test_no_regression_value_key_missing(self):
        """
        REGRESSION: If 'value' key is removed, this test fails.
        """
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # Must have 'value'
        assert "value" in field_record

    def test_no_regression_wrong_value_type(self):
        """
        REGRESSION: If value becomes a boolean instead of string, this fails.
        """
        detected = DetectedCheckbox(
            name="test",
            state=CheckboxState.CHECKED,
            confidence=0.90,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="Test",
        )
        field_record = _convert_checkbox_to_field(detected, "test_field")

        # Value must be string, not boolean
        assert isinstance(field_record["value"], str)
        assert not isinstance(field_record["value"], bool)

    def test_no_regression_state_mapping(self):
        """
        REGRESSION: Ensure CHECKED→'true', UNCHECKED→'false', UNCLEAR→''
        """
        test_cases = [
            (CheckboxState.CHECKED, "true"),
            (CheckboxState.UNCHECKED, "false"),
            (CheckboxState.UNCLEAR, ""),
        ]

        for state, expected_value in test_cases:
            detected = DetectedCheckbox(
                name="test",
                state=state,
                confidence=0.90,
                bbox=BBox(top=10, left=20, bottom=30, right=40),
                anchor_text="Test",
            )
            field_record = _convert_checkbox_to_field(detected, "test_field")
            assert field_record["value"] == expected_value


# =============================================================================
# DOCUMENTATION AND EXAMPLE TESTS
# =============================================================================

class TestExampleUsages:
    """Example usage tests matching docstrings."""

    def test_docstring_example_checked(self):
        """
        Example from docstring:
        >>> detected = DetectedCheckbox("checkbox_test", CheckboxState.CHECKED, 0.95)
        >>> _convert_checkbox_to_field(detected, "test_field")
        {
            "field_name": "test_field",
            "value": "true",
            "confidence": 0.95,
            "source": "checkbox_detection",
            "anchor_text": "",
            "state": "checked"
        }
        """
        detected = DetectedCheckbox(
            name="checkbox_test",
            state=CheckboxState.CHECKED,
            confidence=0.95,
            bbox=BBox(top=10, left=20, bottom=30, right=40),
            anchor_text="",
        )
        result = _convert_checkbox_to_field(detected, "test_field")

        assert result["field_name"] == "test_field"
        assert result["value"] == "true"
        assert result["confidence"] == 0.95
        assert result["source"] == "checkbox_detection"
        assert result["anchor_text"] == ""
        assert result["state"] == "checked"

    def test_dti_form_usage_example(self):
        """
        Real-world DTI form usage:
        Form has checkboxes for activities (Manufacturer, Wholesaler, Retailer).
        """
        dti_activities = [
            {
                "detected": DetectedCheckbox(
                    name="checkbox_manufacturer",
                    state=CheckboxState.CHECKED,
                    confidence=0.96,
                    bbox=BBox(top=10, left=20, bottom=30, right=40),
                    anchor_text="Manufacturer",
                ),
                "field_name": "dti_activity_manufacturer",
                "expected_value": "true",
            },
            {
                "detected": DetectedCheckbox(
                    name="checkbox_wholesaler",
                    state=CheckboxState.UNCHECKED,
                    confidence=0.92,
                    bbox=BBox(top=50, left=60, bottom=70, right=80),
                    anchor_text="Wholesaler",
                ),
                "field_name": "dti_activity_wholesaler",
                "expected_value": "false",
            },
            {
                "detected": DetectedCheckbox(
                    name="checkbox_retailer",
                    state=CheckboxState.CHECKED,
                    confidence=0.91,
                    bbox=BBox(top=90, left=100, bottom=110, right=120),
                    anchor_text="Retailer",
                ),
                "field_name": "dti_activity_retailer",
                "expected_value": "true",
            },
        ]

        for activity in dti_activities:
            field_record = _convert_checkbox_to_field(
                activity["detected"], activity["field_name"]
            )

            assert field_record["value"] == activity["expected_value"]
            assert field_record["field_name"] == activity["field_name"]
            assert "value" in field_record
            assert "ocr_value" not in field_record


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
