"""
Tests for Phase 3: Two-Pass Groq Extraction System

Tests cover:
- Pass 1 extraction with region context
- Pass 2 recovery extraction
- Merge logic for combining Pass 1, Pass 2, and checkbox detection
- Prompt structure and token counting
- Latency budget compliance
- End-to-end two-pass extraction
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Any

from app.services.ocr_groq_extraction import (
    extract_fields_two_pass,
    extract_fields_with_groq,
    _extract_fields_pass1,
    _extract_fields_pass2,
    _merge_extraction_results,
    parse_groq_response,
)
from app.services.ocr_groq_prompt import (
    build_ocr_extraction_prompt_with_regions,
    build_recovery_prompt_v2,
    build_region_context_section,
    _build_field_definitions_with_locations,
    build_checkbox_hints_section,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_raw_lines() -> list[dict[str, Any]]:
    """Sample OCR lines from test form."""
    return [
        {"text": "A. TYPE OF DTI REGISTRATION", "confidence": 0.98, "bbox": [10, 100, 400, 110]},
        {"text": "1.", "confidence": 0.99, "bbox": [30, 120, 45, 130]},
        {"text": "NEW", "confidence": 0.97, "bbox": [60, 120, 95, 130]},
        {"text": "2. Certificate No.", "confidence": 0.96, "bbox": [150, 120, 300, 130]},
        {"text": "____________________", "confidence": 0.90, "bbox": [310, 120, 400, 130]},
        {"text": "B. TAX IDENTIFICATION", "confidence": 0.97, "bbox": [10, 200, 350, 210]},
        {"text": "With TIN", "confidence": 0.95, "bbox": [50, 220, 130, 230]},
        {"text": "Owner's TIN: 123-456-789-000", "confidence": 0.92, "bbox": [140, 220, 350, 230]},
    ]


@pytest.fixture
def sample_field_schema() -> dict[str, Any]:
    """Sample DTI form schema."""
    return {
        "fields": [
            {"name": "reg_type", "label": "Registration Type", "type": "radio", "section": "A", "required": True},
            {"name": "certificate_no", "label": "Certificate No.", "type": "text", "section": "A"},
            {"name": "tin_status", "label": "TIN Status", "type": "radio", "section": "B", "required": True},
            {"name": "owners_tin", "label": "Owner's TIN", "type": "text", "section": "B"},
            {"name": "first_name", "label": "First Name", "type": "text", "section": "C"},
            {"name": "activity_manufacturer", "label": "Manufacturer", "type": "checkbox", "section": "F"},
            {"name": "activity_service", "label": "Service", "type": "checkbox", "section": "F"},
            {"name": "employees_total", "label": "Total Employees", "type": "text", "section": "I"},
        ]
    }


@pytest.fixture
def mock_groq_response_pass1() -> dict[str, Any]:
    """Mock Groq response for Pass 1."""
    return {
        "extracted_fields": [
            {"field_name": "reg_type", "value": "new", "confidence": 0.95, "reasoning": "Anchor 'NEW' found"},
            {" field_name": "certificate_no", "value": "", "confidence": 0.60, "reasoning": "Empty field"},
            {"field_name": "tin_status", "value": "with_tin", "confidence": 0.92, "reasoning": "Text 'With TIN' found"},
            {"field_name": "owners_tin", "value": "123-456-789-000", "confidence": 0.88, "reasoning": "TIN pattern matched"},
        ],
        "extraction_summary": "Extracted 4 of 8 fields"
    }


@pytest.fixture
def mock_groq_response_pass2() -> dict[str, Any]:
    """Mock Groq response for Pass 2."""
    return {
        "extracted_fields": [
            {"field_name": "first_name", "value": "Juan", "confidence": 0.65, "reasoning": "Guessed from context"},
            {"field_name": "activity_service", "value": "true", "confidence": 0.55, "reasoning": "Weak evidence"},
        ],
        "extraction_summary": "Recovered 2 additional fields"
    }


# ────────────────────────────────────────────────────────────────────────────
# Tests: Prompt Engineering
# ────────────────────────────────────────────────────────────────────────────

class TestPromptEngineering:
    """Test prompt generation for Phase 3."""
    
    def test_region_context_section_with_regions(self):
        """Test region context section generation."""
        # Mock region
        mock_region = Mock()
        mock_region.name = "Section A"
        mock_region.type = Mock()
        mock_region.type.value = "SECTION_TITLE"
        mock_region.confidence = 0.85
        
        prompt_section = build_region_context_section([mock_region])
        
        assert "FORM STRUCTURE" in prompt_section
        assert "Section A" in prompt_section
        assert "SECTION_TITLE" in prompt_section
        assert "0.85" in prompt_section
    
    def test_region_context_section_empty(self):
        """Test region context with no regions."""
        prompt_section = build_region_context_section([])
        assert "No regions detected" in prompt_section
    
    def test_field_definitions_with_locations(self, sample_field_schema):
        """Test field definitions with location hints."""
        prompt_section = _build_field_definitions_with_locations(
            enriched_template=sample_field_schema,
            regions=[]
        )
        
        assert "FIELDS TO EXTRACT" in prompt_section
        assert "reg_type" in prompt_section
        assert "Registration Type" in prompt_section
        assert "[radio," in prompt_section
    
    def test_checkbox_hints_section_with_checkboxes(self):
        """Test checkbox hints section."""
        mock_cb = Mock()
        mock_cb.name = "activity_manufacturer"
        mock_cb.state = Mock()
        mock_cb.state.value = "checked"
        mock_cb.confidence = 0.92
        mock_cb.anchor_text = "Manufacturer"
        
        prompt_section = build_checkbox_hints_section([mock_cb])
        
        assert "DETECTED CHECKBOXES" in prompt_section
        assert "activity_manufacturer" in prompt_section
        assert "CHECKED" in prompt_section
        assert "0.92" in prompt_section
    
    def test_checkbox_hints_section_empty(self):
        """Test checkbox hints with no checkboxes."""
        prompt_section = build_checkbox_hints_section([])
        assert prompt_section == ""
    
    def test_build_ocr_extraction_prompt_with_regions(self, sample_field_schema):
        """Test Pass 1 prompt generation with regions."""
        ocr_result = {
            "raw_lines": [{"text": "Sample", "confidence": 0.95}],
            "full_text": "Sample text",
            "regions": [],
            "detected_checkboxes": [],
        }
        
        prompt = build_ocr_extraction_prompt_with_regions(
            enriched_template=sample_field_schema,
            ocr_result=ocr_result,
            form_name="Test Form",
            include_checkbox_hints=True
        )
        
        # Verify prompt structure
        assert "You are an expert OCR" in prompt
        assert "FORM STRUCTURE" in prompt or "No regions detected" in prompt
        assert "FIELDS TO EXTRACT" in prompt
        assert "EXTRACTION TASK" in prompt
        assert "extracted_fields" in prompt
        assert len(prompt) > 500  # Should be substantial
    
    def test_build_recovery_prompt_v2(self, sample_field_schema):
        """Test Pass 2 recovery prompt generation."""
        pass1_results = {
            "fields": [
                {"field_name": "reg_type", "value": "new", "confidence": 0.95},
            ],
            "avg_confidence": 0.95,
        }
        
        ocr_result = {
            "full_text": "Sample form text with fields",
            "raw_lines": [],
            "regions": [],
        }
        
        recovery_targets = ["certificate_no", "first_name", "activity_service"]
        
        prompt = build_recovery_prompt_v2(
            recovery_targets=recovery_targets,
            pass1_results=pass1_results,
            enriched_template=sample_field_schema,
            ocr_result=ocr_result,
            form_name="Test Form"
        )
        
        # Verify prompt content
        assert "recovery specialist" in prompt
        assert "certificate_no" in prompt
        assert "first_name" in prompt
        assert "Pass 1 STATUS" in prompt
        assert "extracted_fields" in prompt
        assert len(prompt) > 400


# ────────────────────────────────────────────────────────────────────────────
# Tests: Parsing & Response Handling
# ────────────────────────────────────────────────────────────────────────────

class TestResponseParsing:
    """Test Groq response parsing."""
    
    def test_parse_groq_response_valid_json(self):
        """Test parsing valid JSON response."""
        content = """{
            "extracted_fields": [
                {"field_name": "test", "value": "value", "confidence": 0.85}
            ],
            "extraction_summary": "Test summary"
        }"""
        
        result = parse_groq_response(content)
        
        assert result is not None
        assert len(result["extracted_fields"]) == 1
        assert result["extracted_fields"][0]["field_name"] == "test"
        assert result["extracted_fields"][0]["confidence"] == 0.85
    
    def test_parse_groq_response_with_markdown(self):
        """Test parsing JSON within markdown code fences."""
        content = """```json
{
    "extracted_fields": [{"field_name": "test", "value": "value", "confidence": 0.9}],
    "extraction_summary": "Done"
}
```"""
        
        result = parse_groq_response(content)
        
        assert result is not None
        assert len(result["extracted_fields"]) == 1
        assert result["extracted_fields"][0]["confidence"] == 0.9
    
    def test_parse_groq_response_normalize_confidence(self):
        """Test confidence normalization to [0, 1] range."""
        content = """{
            "extracted_fields": [
                {"field_name": "test1", "value": "val", "confidence": 1.5},
                {"field_name": "test2", "value": "val", "confidence": -0.5}
            ]
        }"""
        
        result = parse_groq_response(content)
        
        assert result is not None
        assert result["extracted_fields"][0]["confidence"] == 1.0  # Clamped to [0, 1]
        assert result["extracted_fields"][1]["confidence"] == 0.0  # Clamped to [0, 1]


# ────────────────────────────────────────────────────────────────────────────
# Tests: Merge Logic
# ────────────────────────────────────────────────────────────────────────────

class TestMergeLogic:
    """Test Pass 1 + Pass 2 + Checkbox merging."""
    
    def test_merge_checkbox_highest_priority(self):
        """Test that checkboxes have highest priority in merge."""
        pass1_fields = [
            {"field_name": "activity_manufacturer", "value": "false", "confidence": 0.45},
        ]
        pass2_fields = []
        
        mock_checkbox = Mock()
        mock_checkbox.name = "activity_manufacturer"
        mock_checkbox.state = Mock()
        mock_checkbox.state.value = "checked"
        mock_checkbox.confidence = 0.92
        
        final_fields, notes = _merge_extraction_results(
            pass1_fields=pass1_fields,
            pass2_fields=pass2_fields,
            detected_checkboxes=[mock_checkbox]
        )
        
        assert len(final_fields) == 1
        assert final_fields[0]["field_name"] == "activity_manufacturer"
        assert final_fields[0]["value"] == "true"
        assert final_fields[0]["confidence"] == 0.92
        assert "checkbox" in notes[0].lower()
    
    def test_merge_pass1_high_confidence(self):
        """Test that Pass 1 high confidence fields are used."""
        pass1_fields = [
            {"field_name": "reg_type", "value": "new", "confidence": 0.95},
        ]
        pass2_fields = []
        
        final_fields, notes = _merge_extraction_results(
            pass1_fields=pass1_fields,
            pass2_fields=pass2_fields,
            detected_checkboxes=[]
        )
        
        assert len(final_fields) == 1
        assert final_fields[0]["field_name"] == "reg_type"
        assert final_fields[0]["value"] == "new"
        assert final_fields[0]["confidence"] == 0.95
    
    def test_merge_pass2_recovery_over_low_pass1(self):
        """Test that Pass 2 overrides low-confidence Pass 1."""
        pass1_fields = [
            {"field_name": "certificate_no", "value": "??", "confidence": 0.35},
        ]
        pass2_fields = [
            {"field_name": "certificate_no", "value": "2024-001", "confidence": 0.68},
        ]
        
        final_fields, notes = _merge_extraction_results(
            pass1_fields=pass1_fields,
            pass2_fields=pass2_fields,
            detected_checkboxes=[]
        )
        
        assert len(final_fields) == 1
        assert final_fields[0]["field_name"] == "certificate_no"
        assert final_fields[0]["value"] == "2024-001"
        assert final_fields[0]["confidence"] == 0.68
        assert "Pass 2" in notes[0]


# ────────────────────────────────────────────────────────────────────────────
# Tests: Pass 1 Extraction (Mocked)
# ────────────────────────────────────────────────────────────────────────────

class TestPass1Extraction:
    """Test Pass 1 extraction logic with mocked Groq."""
    
    @patch("app.services.ocr_groq_extraction.get_ai_client")
    @patch("app.services.ocr_groq_extraction.enrich_template_with_preprocessing_hints")
    def test_pass1_successful_extraction(self, mock_enrich, mock_client, sample_raw_lines, sample_field_schema):
        """Test successful Pass 1 extraction."""
        # Mock enriched template
        mock_enrich.return_value = sample_field_schema
        
        # Mock Groq response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "extracted_fields": [
                {"field_name": "reg_type", "value": "new", "confidence": 0.95},
                {"field_name": "certificate_no", "value": "", "confidence": 0.50},
            ],
            "extraction_summary": "Extracted 2 fields"
        })
        mock_response.usage.prompt_tokens = 4000
        mock_response.usage.completion_tokens = 500
        
        mock_client.return_value.chat.completions.create.return_value = mock_response
        
        ocr_result = {
            "raw_lines": sample_raw_lines,
            "full_text": "\n".join([l["text"] for l in sample_raw_lines]),
            "regions": [],
            "detected_checkboxes": [],
        }
        
        result = _extract_fields_pass1(
            enriched_template=sample_field_schema,
            ocr_result=ocr_result,
            form_name="Test Form"
        )
        
        assert result is not None
        assert len(result["fields"]) == 2
        assert result["avg_confidence"] == 0.725  # (0.95 + 0.50) / 2
        assert result["input_tokens"] == 4000
        assert result["output_tokens"] == 500
        assert result["latency_ms"] > 0


# ────────────────────────────────────────────────────────────────────────────
# Tests: End-to-End Two-Pass Extraction (Mocked)
# ────────────────────────────────────────────────────────────────────────────

class TestTwoPassExtraction:
    """Test end-to-end two-pass extraction."""
    
    @patch("app.services.ocr_groq_extraction.detect_checkboxes")
    @patch("app.services.ocr_groq_extraction.classify_regions")
    @patch("app.services.ocr_groq_extraction._extract_fields_pass2")
    @patch("app.services.ocr_groq_extraction._extract_fields_pass1")
    @patch("app.services.ocr_groq_extraction.enrich_template_with_preprocessing_hints")
    def test_two_pass_extraction_with_pass2_trigger(
        self,
        mock_enrich,
        mock_pass1,
        mock_pass2,
        mock_classify_regions,
        mock_detect_checkboxes,
        sample_raw_lines,
        sample_field_schema
    ):
        """Test two-pass extraction when Pass 2 is triggered."""
        # Setup mocks
        mock_enrich.return_value = sample_field_schema
        mock_classify_regions.return_value = []
        mock_detect_checkboxes.return_value = []
        
        # Pass 1 returns low confidence
        mock_pass1.return_value = {
            "fields": [
                {"field_name": "reg_type", "value": "new", "confidence": 0.85},
                {"field_name": "tin_status", "value": "with_tin", "confidence": 0.65},
            ],
            "avg_confidence": 0.65,  # < 0.70 threshold → trigger Pass 2
            "input_tokens": 4000,
            "output_tokens": 500,
            "latency_ms": 1200,
            "pass1_summary": "2 fields"
        }
        
        # Pass 2 recovers additional fields
        mock_pass2.return_value = {
            "fields": [
                {"field_name": "certificate_no", "value": "2024-001", "confidence": 0.60},
                {"field_name": "first_name", "value": "Juan", "confidence": 0.55},
            ],
            "avg_confidence": 0.575,
            "input_tokens": 2000,
            "output_tokens": 300,
            "latency_ms": 800,
            "pass2_summary": "2 fields recovered"
        }
        
        result = extract_fields_two_pass(
            raw_lines=sample_raw_lines,
            field_schema=sample_field_schema,
            form_name="Test Form",
            enable_pass2_recovery=True,
            pass2_threshold=0.70
        )
        
        assert result is not None
        assert len(result["fields"]) == 4  # 2 from Pass 1 + 2 from Pass 2
        assert result["pass1_metrics"]["fields_extracted"] == 2
        assert result["pass2_metrics"]["fields_recovered"] == 2
        assert result["total_tokens_used"] == 6800  # 4000+500+2000+300
        assert "Pass 2" in result["extraction_summary"]
    
    @patch("app.services.ocr_groq_extraction.detect_checkboxes")
    @patch("app.services.ocr_groq_extraction.classify_regions")
    @patch("app.services.ocr_groq_extraction._extract_fields_pass1")
    @patch("app.services.ocr_groq_extraction.enrich_template_with_preprocessing_hints")
    def test_two_pass_extraction_pass2_disabled(
        self,
        mock_enrich,
        mock_pass1,
        mock_classify_regions,
        mock_detect_checkboxes,
        sample_raw_lines,
        sample_field_schema
    ):
        """Test extraction when Pass 2 is disabled."""
        # Setup mocks
        mock_enrich.return_value = sample_field_schema
        mock_classify_regions.return_value = []
        mock_detect_checkboxes.return_value = []
        
        # Pass 1 returns good confidence (but Pass 2 disabled)
        mock_pass1.return_value = {
            "fields": [
                {"field_name": "reg_type", "value": "new", "confidence": 0.95},
                {"field_name": "tin_status", "value": "with_tin", "confidence": 0.88},
            ],
            "avg_confidence": 0.915,
            "input_tokens": 4000,
            "output_tokens": 500,
            "latency_ms": 1200,
            "pass1_summary": "2 fields"
        }
        
        result = extract_fields_two_pass(
            raw_lines=sample_raw_lines,
            field_schema=sample_field_schema,
            form_name="Test Form",
            enable_pass2_recovery=False  # Disable Pass 2
        )
        
        assert result is not None
        assert len(result["fields"]) == 2
        assert result["pass2_metrics"]["fields_recovered"] == 0
        assert result["total_tokens_used"] == 4500  # Only Pass 1 tokens


# ────────────────────────────────────────────────────────────────────────────
# Tests: Backward Compatibility
# ────────────────────────────────────────────────────────────────────────────

class TestBackwardCompatibility:
    """Test backward compatibility with legacy extract_fields_with_groq()."""
    
    @patch("app.services.ocr_groq_extraction.extract_fields_two_pass")
    def test_legacy_function_calls_two_pass(self, mock_two_pass, sample_raw_lines, sample_field_schema):
        """Test that extract_fields_with_groq calls two-pass with recovery disabled."""
        # Mock two-pass result
        mock_two_pass.return_value = {
            "fields": [{"field_name": "test", "value": "value", "confidence": 0.95}],
            "extraction_summary": "Test",
            "pass1_metrics": {"tokens_used": {"input": 4000, "output": 500}},
            "total_tokens_used": 4500,
            "total_latency_ms": 1200,
            "field_merge_notes": [],
        }
        
        result = extract_fields_with_groq(
            raw_lines=sample_raw_lines,
            field_schema=sample_field_schema,
            form_name="Test"
        )
        
        # Verify two-pass was called with recovery disabled
        mock_two_pass.assert_called_once()
        call_kwargs = mock_two_pass.call_args[1]
        assert call_kwargs["enable_pass2_recovery"] == False
        
        # Verify result was converted back to legacy format
        assert "fields" in result
        assert "extraction_notes" in result
        assert "groq_usage" in result
        assert "latency_ms" in result


# ────────────────────────────────────────────────────────────────────────────
# Tests: Performance & Latency
# ────────────────────────────────────────────────────────────────────────────

class TestPerformance:
    """Test performance and latency constraints."""
    
    @patch("app.services.ocr_groq_extraction._extract_fields_pass2")
    @patch("app.services.ocr_groq_extraction._extract_fields_pass1")
    @patch("app.services.ocr_groq_extraction.detect_checkboxes")
    @patch("app.services.ocr_groq_extraction.classify_regions")
    @patch("app.services.ocr_groq_extraction.enrich_template_with_preprocessing_hints")
    def test_total_latency_within_budget(
        self,
        mock_enrich,
        mock_classify,
        mock_detect,
        mock_pass1,
        mock_pass2,
        sample_raw_lines,
        sample_field_schema
    ):
        """Test that total latency stays within 5s budget."""
        # Setup mocks
        mock_enrich.return_value = sample_field_schema
        mock_classify.return_value = []
        mock_detect.return_value = []
        
        mock_pass1.return_value = {
            "fields": [{"field_name": "test", "value": "val", "confidence": 0.85}],
            "avg_confidence": 0.85,
            "input_tokens": 4000,
            "output_tokens": 500,
            "latency_ms": 1400,  # Pass 1 within budget
            "pass1_summary": "test"
        }
        
        mock_pass2.return_value = {
            "fields": [{"field_name": "test2", "value": "val2", "confidence": 0.70}],
            "avg_confidence": 0.70,
            "input_tokens": 2000,
            "output_tokens": 300,
            "latency_ms": 800,  # Pass 2 within budget
            "pass2_summary": "test"
        }
        
        result = extract_fields_two_pass(
            raw_lines=sample_raw_lines,
            field_schema=sample_field_schema,
            enable_pass2_recovery=True,
            pass2_threshold=0.70
        )
        
        # Verify latency is within budget
        assert result is not None
        assert result["total_latency_ms"] < 5000  # 5s budget
        assert result["pass1_metrics"]["latency_ms"] < 2000  # Pass 1 < 2s
        assert result["pass2_metrics"]["latency_ms"] < 1000  # Pass 2 < 1s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
