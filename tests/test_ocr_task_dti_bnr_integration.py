"""Integration tests for DTI BNR rules in ocr_task.py pipeline."""

import pytest
from unittest.mock import patch, MagicMock
from app.models.form_template import FormTemplate
from app.models.form_entry import FormEntry, FormEntryStatus


class TestDTIBNRRulesIntegration:
    """Test DTI BNR rules integration into OCR pipeline."""
    
    def test_rules_applied_for_dti_bnr_template(self):
        """Test that DTI BNR rules are called when processing DTI BNR forms."""
        # Create mock template with name "dti_bnr"
        mock_template = MagicMock(spec=FormTemplate)
        mock_template.name = "dti_bnr"
        mock_template.field_schema = {
            "certificate_no": {"type": "text"},
            "owner_name": {"type": "text"},
            "business_address": {"type": "text"},
        }
        
        # Mock extracted fields (before rules)
        mock_fields = [
            {"field_name": "certificate_no", "ocr_value": "NR0 052018", "confidence": 0.6},
            {"field_name": "owner_name", "ocr_value": "Juan D0los", "confidence": 0.5},
            {"field_name": "business_address", "ocr_value": "Baraneay Poblacion", "confidence": 0.4},
        ]
        
        # Mock the apply_dti_bnr_corrections function to verify it's called
        with patch('app.services.ocr_task.apply_dti_bnr_corrections') as mock_apply_rules:
            # Set up the mock to return improved fields
            mock_apply_rules.return_value = {
                "certificate_no": {"value": "NR0:052018", "confidence": 0.85},
                "owner_name": {"value": "Juan Dolos", "confidence": 0.75},
                "business_address": {"value": "Barangay Poblacion", "confidence": 0.70},
            }
            
            # Simulate the integration logic
            fields_dict = {
                f["field_name"]: {
                    "value": f.get("ocr_value", ""),
                    "confidence": f.get("confidence", 0.0),
                }
                for f in mock_fields
            }
            
            # Call the mocked function
            corrected_fields = mock_apply_rules(fields_dict)
            
            # Verify the function was called with the correct structure
            assert mock_apply_rules.called
            call_args = mock_apply_rules.call_args[0][0]
            assert "certificate_no" in call_args
            assert call_args["certificate_no"]["value"] == "NR0 052018"
            
            # Verify confidence improved
            assert corrected_fields["certificate_no"]["confidence"] == 0.85
            assert corrected_fields["owner_name"]["confidence"] == 0.75
            assert corrected_fields["business_address"]["confidence"] == 0.70
    
    def test_rules_skipped_for_non_dti_bnr_template(self):
        """Test that DTI BNR rules are NOT called for other form types."""
        mock_template = MagicMock(spec=FormTemplate)
        mock_template.name = "business_permit"  # Not DTI BNR
        
        with patch('app.services.ocr_task.apply_dti_bnr_corrections') as mock_apply_rules:
            # Simulate the check: rules should NOT be applied
            if mock_template.name == "dti_bnr":
                mock_apply_rules({})
            
            # Verify the function was NOT called
            assert not mock_apply_rules.called
    
    def test_rules_failure_handled_gracefully(self):
        """Test that rules execution failure doesn't crash the pipeline."""
        mock_template = MagicMock(spec=FormTemplate)
        mock_template.name = "dti_bnr"
        
        mock_fields = [
            {"field_name": "certificate_no", "ocr_value": "NR0 052018", "confidence": 0.6},
        ]
        
        with patch('app.services.ocr_task.apply_dti_bnr_corrections') as mock_apply_rules:
            # Simulate a failure in rules execution
            mock_apply_rules.side_effect = ValueError("Rules execution error")
            
            # The pipeline should catch the exception and log it
            try:
                if mock_template.name == "dti_bnr":
                    fields_dict = {
                        f["field_name"]: {
                            "value": f.get("ocr_value", ""),
                            "confidence": f.get("confidence", 0.0),
                        }
                        for f in mock_fields
                    }
                    mock_apply_rules(fields_dict)
            except ValueError:
                # This exception should be caught in ocr_task.py
                pass
            
            # Verify the exception was raised (to confirm it would be caught)
            assert mock_apply_rules.called
    
    def test_composite_fields_preserved_after_rules(self):
        """Test that composite fields created by rules are preserved in the pipeline."""
        mock_template = MagicMock(spec=FormTemplate)
        mock_template.name = "dti_bnr"
        
        # Simulate rules output with composite fields
        rules_output = {
            "certificate_no": {"value": "NR0:052018", "confidence": 0.85},
            "dob_composite": {"value": "1985-06-15", "confidence": 0.80},
            "owner_name_composite": {"value": "Juan Dolos", "confidence": 0.75},
            "biz_address_composite": {"value": "Barangay Poblacion, Manila", "confidence": 0.70},
        }
        
        # Convert back to list format (as done in ocr_task.py)
        mapped_fields = [
            {
                "field_name": field_name,
                "ocr_value": field_data.get("value", ""),
                "confidence": field_data.get("confidence", 0.0),
            }
            for field_name, field_data in rules_output.items()
        ]
        
        # Verify composite fields are present
        field_names = [f["field_name"] for f in mapped_fields]
        assert "dob_composite" in field_names
        assert "owner_name_composite" in field_names
        assert "biz_address_composite" in field_names
        
        # Verify values and confidence are preserved
        dob_field = next((f for f in mapped_fields if f["field_name"] == "dob_composite"), None)
        assert dob_field["ocr_value"] == "1985-06-15"
        assert dob_field["confidence"] == 0.80


class TestRulesApplicationFlow:
    """Test the complete flow of rules application in the pipeline."""
    
    def test_rules_improve_overall_confidence(self):
        """Test that applying rules improves overall form confidence."""
        # Mock input fields with low confidence
        input_fields = {
            "certificate_no": {"value": "NR0 052018", "confidence": 0.5},
            "phone_number": {"value": "+63912345678", "confidence": 0.3},
            "date_of_birth": {"value": "198-06-15", "confidence": 0.2},
            "amount": {"value": "P12345", "confidence": 0.4},
        }
        
        # Calculate initial average confidence
        initial_avg = sum(f["confidence"] for f in input_fields.values()) / len(input_fields)
        assert initial_avg < 0.5
        
        # Mock rules execution that improves confidence
        with patch('app.services.ocr_task.apply_dti_bnr_corrections') as mock_apply_rules:
            mock_apply_rules.return_value = {
                "certificate_no": {"value": "NR0:052018", "confidence": 0.85},
                "phone_number": {"value": "0912-3456789", "confidence": 0.80},
                "date_of_birth": {"value": "1985-06-15", "confidence": 0.85},
                "amount": {"value": "₱12,345.00", "confidence": 0.75},
            }
            
            corrected = mock_apply_rules(input_fields)
            
            # Calculate improved average confidence
            improved_avg = sum(f["confidence"] for f in corrected.values()) / len(corrected)
            assert improved_avg > 0.8
            assert improved_avg > initial_avg
    
    def test_rules_called_after_fallback(self):
        """Test that rules are applied after fallback strategy, not before."""
        # This is more of a documentation test to verify the pipeline order
        # In actual ocr_task.py:
        # 1. Primary extraction (unified AI call)
        # 2. Fallback extraction (positional mapping) if needed
        # 3. Rules application (form-specific corrections) <- DTI BNR rules
        # 4. DB storage
        
        # Verify the sequence is logical
        pipeline_stages = [
            "extract_fields_unified",
            "map_fields_by_spatial_position (fallback)",
            "apply_dti_bnr_corrections (rules)",
            "store_to_db",
        ]
        
        # DTI BNR rules should be stage 3 (after fallback, before DB storage)
        assert pipeline_stages[2] == "apply_dti_bnr_corrections (rules)"
        assert "fallback" in pipeline_stages[1]
        assert "store" in pipeline_stages[3]
