"""Integration tests for field validators in OCR pipeline.

Tests validator application post-AI extraction, confidence adjustment,
and integration with template schema.

Coverage: Option A (Post-AI Extraction) implementation
- Field type mapping from schema
- Confidence adjustment logic
- Required field handling
- Config toggle (ENABLE_FIELD_VALIDATORS)
"""

import pytest
from unittest.mock import MagicMock, patch
from app.services.ocr_service import _apply_field_validators


class TestFieldValidatorsIntegration:
    """Test field validator integration into OCR pipeline."""
    
    def test_validators_improve_date_field_confidence(self):
        """Test that date validators normalize values and improve confidence."""
        # Extracted field: raw date string, low confidence
        fields = [
            {
                "field_name": "registration_date",
                "ocr_value": "March 15, 2020",
                "confidence": 0.60,
            },
        ]
        
        # Schema with field type definition
        field_schema = {
            "fields": [
                {
                    "name": "registration_date",
                    "type": "date",
                    "required": True,
                },
            ],
        }
        
        # Apply validators with mocked config
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to DD/MM/YYYY format
        assert field["ocr_value"] == "15/03/2020"
        
        # Confidence should be improved (was 0.60, nominal +0.10 for valid date)
        assert field["confidence"] > 0.60
        assert field["confidence"] <= 1.0
        
        # Metadata preserved
        assert field["field_name"] == "registration_date"
    
    def test_validators_normalize_phone_number(self):
        """Test that phone validators normalize to +639XXXXXXXXX format."""
        fields = [
            {
                "field_name": "phone_number",
                "ocr_value": "09171234567",
                "confidence": 0.55,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "phone_number",
                    "type": "phone",
                    "required": True,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to +63 format
        assert field["ocr_value"] == "+639171234567"
        
        # Confidence should be adjusted
        assert field["confidence"] >= 0.55
    
    def test_validators_handle_required_field_missing(self):
        """Test that required field validators degrade confidence for missing values."""
        fields = [
            {
                "field_name": "business_name",
                "ocr_value": "",  # Missing value
                "confidence": 0.5,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "business_name",
                    "type": "text",
                    "required": True,  # Required!
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value still empty
        assert field["ocr_value"] == ""
        
        # Confidence should be DEGRADED (penalty for missing required field)
        # Expected: 0.5 - 0.25 (CONF_REQUIRED_MISSING) = 0.25
        assert field["confidence"] < 0.5
        assert field["confidence"] >= 0.0
    
    def test_validators_skip_for_disabled_config(self):
        """Test that validators are skipped when config is disabled."""
        fields = [
            {
                "field_name": "date_field",
                "ocr_value": "March 15, 2020",
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "date_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        # Validators disabled
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = False
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should return fields unchanged
        assert len(result) == 1
        field = result[0]
        assert field["ocr_value"] == "March 15, 2020"  # Not normalized
        assert field["confidence"] == 0.6  # Not adjusted
    
    def test_validators_skip_fields_not_in_schema(self):
        """Test that validators skip fields not present in template schema."""
        fields = [
            {
                "field_name": "unknown_field",
                "ocr_value": "some value",
                "confidence": 0.7,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "known_field",
                    "type": "text",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should return field unchanged (not in schema)
        assert len(result) == 1
        field = result[0]
        assert field["field_name"] == "unknown_field"
        assert field["ocr_value"] == "some value"
        assert field["confidence"] == 0.7
    
    def test_validators_handle_multiple_fields_mixed_results(self):
        """Test validators on multiple fields with mixed outcomes (improved, degraded, unchanged)."""
        fields = [
            {
                "field_name": "registration_date",
                "ocr_value": "15/03/2020",
                "confidence": 0.65,
            },
            {
                "field_name": "business_name",
                "ocr_value": "",  # Required, missing
                "confidence": 0.5,
            },
            {
                "field_name": "business_type",
                "ocr_value": "Partnership",
                "confidence": 0.8,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "registration_date",
                    "type": "date",
                    "required": True,
                },
                {
                    "name": "business_name",
                    "type": "text",
                    "required": True,
                },
                {
                    "name": "business_type",
                    "type": "text",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should process all three fields
        assert len(result) == 3
        
        registration_date_field = result[0]
        business_name_field = result[1]
        business_type_field = result[2]
        
        # Field 1: Date should be normalized (valid format → improved)
        assert registration_date_field["field_name"] == "registration_date"
        assert registration_date_field["ocr_value"] == "15/03/2020"
        assert registration_date_field["confidence"] >= 0.65
        
        # Field 2: Missing required value (degraded)
        assert business_name_field["field_name"] == "business_name"
        assert business_name_field["ocr_value"] == ""
        assert business_name_field["confidence"] < 0.5
        
        # Field 3: Optional text, no change
        assert business_type_field["field_name"] == "business_type"
        assert business_type_field["ocr_value"] == "Partnership"
        assert business_type_field["confidence"] == 0.8
    
    def test_validators_normalize_checkbox_to_yesno(self):
        """Test that checkbox validators normalize to Yes/No."""
        fields = [
            {
                "field_name": "has_employees",
                "ocr_value": "✓",  # Checkbox mark
                "confidence": 0.7,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "has_employees",
                    "type": "checkbox",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to "Yes"
        assert field["ocr_value"] == "Yes"
        
        # Confidence should be adjusted
        assert field["confidence"] >= 0.7
    
    def test_validators_normalize_amount_formatting(self):
        """Test that amount validators normalize to X,XXX.XX format."""
        fields = [
            {
                "field_name": "business_capital",
                "ocr_value": "₱50000",
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "business_capital",
                    "type": "amount",
                    "required": True,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to X,XXX.XX format
        assert field["ocr_value"] == "50,000.00"
        
        # Confidence should be adjusted
        assert field["confidence"] >= 0.6
    
    def test_validators_clamp_confidence_to_bounds(self):
        """Test that confidence is clamped to [0.0, 1.0] range."""
        fields = [
            {
                "field_name": "test_field",
                "ocr_value": "valid date",
                "confidence": 0.99,  # Already high
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "test_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Confidence should never exceed 1.0
        assert field["confidence"] <= 1.0
        assert field["confidence"] >= 0.0
    
    def test_validators_handle_empty_fields_list(self):
        """Test that validators gracefully handle empty fields list."""
        fields = []
        
        field_schema = {
            "fields": [
                {
                    "name": "some_field",
                    "type": "text",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should return empty list
        assert len(result) == 0
    
    def test_validators_handle_invalid_date_gracefully(self):
        """Test that validators handle invalid dates without crashing."""
        fields = [
            {
                "field_name": "date_field",
                "ocr_value": "not a date",
                "confidence": 0.5,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "date_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should return field with degraded confidence (invalid)
        assert len(result) == 1
        field = result[0]
        assert field["field_name"] == "date_field"
        # Invalid date should degrade confidence
        assert field["confidence"] < 0.5 or field["ocr_value"] == ""


class TestValidatorsEdgeCases:
    """Test edge cases and error handling."""
    
    def test_validators_with_empty_schema(self):
        """Test validators with empty field schema."""
        fields = [
            {
                "field_name": "any_field",
                "ocr_value": "value",
                "confidence": 0.7,
            },
        ]
        
        # Empty schema: no fields defined
        field_schema = {"fields": []}
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should return field unchanged (no schema to match)
        assert len(result) == 1
        field = result[0]
        assert field["ocr_value"] == "value"
        assert field["confidence"] == 0.7
    
    def test_validators_preserve_field_metadata(self):
        """Test that validators preserve field_name and only update value/confidence."""
        fields = [
            {
                "field_name": "original_name",
                "ocr_value": "03/15/2020",
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "original_name",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Field name should not change
        assert result[0]["field_name"] == "original_name"
    
    def test_validators_handle_whitespace_in_values(self):
        """Test that validators handle leading/trailing whitespace."""
        fields = [
            {
                "field_name": "date_field",
                "ocr_value": "  15/03/2020  ",  # Whitespace
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "date_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should handle whitespace and still normalize
        assert len(result) == 1
        # Result should be trimmed and normalized
        assert "  " not in result[0]["ocr_value"]
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to DD/MM/YYYY format
        assert field["ocr_value"] == "15/03/2020"
        
        # Confidence should be improved (was 0.60, nominal +0.10 for valid date)
        assert field["confidence"] > 0.60
        assert field["confidence"] <= 1.0
        
        # Metadata preserved
        assert field["field_name"] == "registration_date"
    
    def test_validators_normalize_phone_number(self):
        """Test that phone validators normalize to +639XXXXXXXXX format."""
        fields = [
            {
                "field_name": "phone_number",
                "ocr_value": "09171234567",
                "confidence": 0.55,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "phone_number",
                    "type": "phone",
                    "required": True,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to +63 format
        assert field["ocr_value"] == "+639171234567"
        
        # Confidence should be adjusted
        assert field["confidence"] >= 0.55
    
    def test_validators_handle_required_field_missing(self):
        """Test that required field validators degrade confidence for missing values."""
        fields = [
            {
                "field_name": "business_name",
                "ocr_value": "",  # Missing value
                "confidence": 0.5,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "business_name",
                    "type": "text",
                    "required": True,  # Required!
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value still empty
        assert field["ocr_value"] == ""
        
        # Confidence should be DEGRADED (penalty for missing required field)
        # Expected: 0.5 - 0.25 (CONF_REQUIRED_MISSING) = 0.25
        assert field["confidence"] < 0.5
        assert field["confidence"] >= 0.0
    
    def test_validators_skip_for_disabled_config(self):
        """Test that validators are skipped when config is disabled."""
        fields = [
            {
                "field_name": "date_field",
                "ocr_value": "March 15, 2020",
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "date_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        # Validators disabled
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = False
            result = _apply_field_validators(fields, field_schema)
        
        # Should return fields unchanged
        assert len(result) == 1
        field = result[0]
        assert field["ocr_value"] == "March 15, 2020"  # Not normalized
        assert field["confidence"] == 0.6  # Not adjusted
    
    def test_validators_skip_fields_not_in_schema(self):
        """Test that validators skip fields not present in template schema."""
        fields = [
            {
                "field_name": "unknown_field",
                "ocr_value": "some value",
                "confidence": 0.7,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "known_field",
                    "type": "text",
                    "required": False,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Should return field unchanged (not in schema)
        assert len(result) == 1
        field = result[0]
        assert field["field_name"] == "unknown_field"
        assert field["ocr_value"] == "some value"
        assert field["confidence"] == 0.7
    
    def test_validators_handle_multiple_fields_mixed_results(self):
        """Test validators on multiple fields with mixed outcomes (improved, degraded, unchanged)."""
        fields = [
            {
                "field_name": "registration_date",
                "ocr_value": "15/03/2020",
                "confidence": 0.65,
            },
            {
                "field_name": "business_name",
                "ocr_value": "",  # Required, missing
                "confidence": 0.5,
            },
            {
                "field_name": "business_type",
                "ocr_value": "Partnership",
                "confidence": 0.8,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "registration_date",
                    "type": "date",
                    "required": True,
                },
                {
                    "name": "business_name",
                    "type": "text",
                    "required": True,
                },
                {
                    "name": "business_type",
                    "type": "text",
                    "required": False,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Should process all three fields
        assert len(result) == 3
        
        registration_date_field = result[0]
        business_name_field = result[1]
        business_type_field = result[2]
        
        # Field 1: Date should be normalized (valid format → improved)
        assert registration_date_field["field_name"] == "registration_date"
        assert registration_date_field["ocr_value"] == "15/03/2020"
        assert registration_date_field["confidence"] >= 0.65
        
        # Field 2: Missing required value (degraded)
        assert business_name_field["field_name"] == "business_name"
        assert business_name_field["ocr_value"] == ""
        assert business_name_field["confidence"] < 0.5
        
        # Field 3: Optional text, no change
        assert business_type_field["field_name"] == "business_type"
        assert business_type_field["ocr_value"] == "Partnership"
        assert business_type_field["confidence"] == 0.8
    
    def test_validators_normalize_checkbox_to_yesno(self):
        """Test that checkbox validators normalize to Yes/No."""
        fields = [
            {
                "field_name": "has_employees",
                "ocr_value": "✓",  # Checkbox mark
                "confidence": 0.7,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "has_employees",
                    "type": "checkbox",
                    "required": False,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to "Yes"
        assert field["ocr_value"] == "Yes"
        
        # Confidence should be adjusted
        assert field["confidence"] >= 0.7
    
    def test_validators_normalize_amount_formatting(self):
        """Test that amount validators normalize to X,XXX.XX format."""
        fields = [
            {
                "field_name": "business_capital",
                "ocr_value": "₱50000",
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "business_capital",
                    "type": "amount",
                    "required": True,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Value should be normalized to X,XXX.XX format
        assert field["ocr_value"] == "50,000.00"
        
        # Confidence should be adjusted
        assert field["confidence"] >= 0.6
    
    def test_validators_clamp_confidence_to_bounds(self):
        """Test that confidence is clamped to [0.0, 1.0] range."""
        fields = [
            {
                "field_name": "test_field",
                "ocr_value": "valid date",
                "confidence": 0.99,  # Already high
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "test_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Assertions
        assert len(result) == 1
        field = result[0]
        
        # Confidence should never exceed 1.0
        assert field["confidence"] <= 1.0
        assert field["confidence"] >= 0.0
    
    def test_validators_handle_empty_fields_list(self):
        """Test that validators gracefully handle empty fields list."""
        fields = []
        
        field_schema = {
            "fields": [
                {
                    "name": "some_field",
                    "type": "text",
                    "required": False,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Should return empty list
        assert len(result) == 0
    
    def test_validators_handle_invalid_date_gracefully(self):
        """Test that validators handle invalid dates without crashing."""
        fields = [
            {
                "field_name": "date_field",
                "ocr_value": "not a date",
                "confidence": 0.5,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "date_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.services.ocr_service.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_FIELD_VALIDATORS = True
            result = _apply_field_validators(fields, field_schema)
        
        # Should return field with degraded confidence (invalid)
        assert len(result) == 1
        field = result[0]
        assert field["field_name"] == "date_field"
        # Invalid date should degrade confidence
        assert field["confidence"] < 0.5 or field["ocr_value"] == ""


class TestValidatorsEdgeCases:
    """Test edge cases and error handling."""
    
    def test_validators_with_empty_schema(self):
        """Test validators with empty field schema."""
        fields = [
            {
                "field_name": "any_field",
                "ocr_value": "value",
                "confidence": 0.7,
            },
        ]
        
        # Empty schema: no fields defined
        field_schema = {"fields": []}
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should return field unchanged (no schema to match)
        assert len(result) == 1
        field = result[0]
        assert field["ocr_value"] == "value"
        assert field["confidence"] == 0.7
    
    def test_validators_preserve_field_metadata(self):
        """Test that validators preserve field_name and only update value/confidence."""
        fields = [
            {
                "field_name": "original_name",
                "ocr_value": "03/15/2020",
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "original_name",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Field name should not change
        assert result[0]["field_name"] == "original_name"
    
    def test_validators_handle_whitespace_in_values(self):
        """Test that validators handle leading/trailing whitespace."""
        fields = [
            {
                "field_name": "date_field",
                "ocr_value": "  15/03/2020  ",  # Whitespace
                "confidence": 0.6,
            },
        ]
        
        field_schema = {
            "fields": [
                {
                    "name": "date_field",
                    "type": "date",
                    "required": False,
                },
            ],
        }
        
        with patch("app.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.ENABLE_FIELD_VALIDATORS = True
            mock_get_settings.return_value = mock_settings
            
            result = _apply_field_validators(fields, field_schema)
        
        # Should handle whitespace and still normalize
        assert len(result) == 1
        # Result should be trimmed and normalized
        assert "  " not in result[0]["ocr_value"]
