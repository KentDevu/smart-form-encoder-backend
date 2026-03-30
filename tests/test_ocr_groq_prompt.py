"""
Unit tests for ocr_groq_prompt.py

Tests: prompt building, field descriptions, pattern sections
Coverage: 80%+
"""

import pytest
from typing import Any
from app.services.ocr_groq_prompt import (
    build_ocr_extraction_prompt,
    build_minimal_recovery_prompt,
    GROQ_SYSTEM_PROMPT,
)


# ============================================================================
# FIXTURES: Sample data for prompt building
# ============================================================================

@pytest.fixture
def sample_enriched_template() -> dict[str, Any]:
    """Enriched template with preprocessing hints."""
    return {
        "template_id": "business_permit_001",
        "name": "Business Permit Application",
        "fields": [
            {
                "name": "business_name",
                "label": "Business Name",
                "type": "text",
                "required": True,
                "section": "business_info",
                "extraction": {"anchor_label": "BUSINESS NAME"},
                "preprocessed": {
                    "anchor_found": True,
                    "anchor_text": "BUSINESS NAME",
                    "anchor_confidence": 0.92,
                    "context_lines": ["ABC Trading Corporation"],
                    "context_confidence": 0.88,
                    "anchor_line_index": 1,
                    "reading_order": 1,
                },
            },
            {
                "name": "proprietor",
                "label": "Proprietor / Owner",
                "type": "text",
                "required": True,
                "section": "owner_info",
                "extraction": {"anchor_label": "PROPRIETOR"},
                "preprocessed": {
                    "anchor_found": True,
                    "anchor_text": "PROPRIETOR / OWNER",
                    "anchor_confidence": 0.90,
                    "context_lines": ["Juan Dela Cruz"],
                    "context_confidence": 0.91,
                    "anchor_line_index": 3,
                    "reading_order": 3,
                },
            },
            {
                "name": "contact_number",
                "label": "Contact Number",
                "type": "phone",
                "required": False,
                "section": "contact",
                "extraction": {"anchor_label": "CONTACT NUMBER"},
                "preprocessed": {
                    "anchor_found": True,
                    "anchor_text": "CONTACT NUMBER",
                    "anchor_confidence": 0.89,
                    "context_lines": ["09175551234"],
                    "context_confidence": 0.85,
                    "anchor_line_index": 5,
                    "reading_order": 5,
                },
            },
            {
                "name": "email",
                "label": "Email Address",
                "type": "email",
                "required": False,
                "section": "contact",
                "extraction": {"anchor_label": "EMAIL ADDRESS"},
                "preprocessed": {
                    "anchor_found": False,
                    "context_lines": [],
                },
            },
        ],
        "pattern_matches": {
            "phone": ["09175551234"],
            "email": ["juan.cruz@example.com"],
            "date": ["15/06/2024"],
            "tin": ["123456789"],
            "amount": ["PHP 15,000.00"],
        },
    }


@pytest.fixture
def sample_ocr_result() -> dict[str, Any]:
    """Standard OCR result."""
    return {
        "raw_lines": [
            {"text": "BUSINESS PERMIT APPLICATION", "confidence": 0.95},
            {"text": "BUSINESS NAME", "confidence": 0.92},
            {"text": "ABC Trading Corporation", "confidence": 0.88},
            {"text": "PROPRIETOR / OWNER", "confidence": 0.90},
            {"text": "Juan Dela Cruz", "confidence": 0.91},
            {"text": "CONTACT NUMBER", "confidence": 0.89},
            {"text": "09175551234", "confidence": 0.85},
            {"text": "EMAIL ADDRESS", "confidence": 0.88},
            {"text": "juan.cruz@example.com", "confidence": 0.90},
        ],
        "full_text": "BUSINESS PERMIT APPLICATION\nBUSINESS NAME\nABC Trading Corporation\nPROPRIETOR / OWNER\nJuan Dela Cruz\nCONTACT NUMBER\n09175551234\nEMAIL ADDRESS\njuan.cruz@example.com",
    }


@pytest.fixture
def minimal_template() -> dict[str, Any]:
    """Minimal template without preprocessing hints."""
    return {
        "fields": [
            {
                "name": "field1",
                "label": "Label 1",
                "type": "text",
                "required": True,
                "section": "section1",
            }
        ],
        "pattern_matches": {},
    }


@pytest.fixture
def empty_ocr_result() -> dict[str, Any]:
    """Empty OCR result."""
    return {
        "raw_lines": [],
        "full_text": "",
    }


@pytest.fixture
def large_ocr_result() -> dict[str, Any]:
    """Large OCR result with 150+ lines."""
    raw_lines = [
        {"text": f"LINE {i}", "confidence": 0.85}
        for i in range(150)
    ]
    return {
        "raw_lines": raw_lines,
        "full_text": "\n".join(f"LINE {i}" for i in range(150)),
    }


# ============================================================================
# TESTS: build_ocr_extraction_prompt()
# ============================================================================

class TestBuildOCRExtractionPrompt:
    """Test cases for build_ocr_extraction_prompt."""

    def test_prompt_includes_system_instructions(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes Groq system instructions."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "expert OCR data extraction specialist" in prompt
        assert "Philippine government forms" in prompt

    def test_prompt_includes_field_definitions(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes all field definitions."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "business_name" in prompt
        assert "proprietor" in prompt
        assert "contact_number" in prompt

    def test_prompt_includes_field_types(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes field types."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "text" in prompt
        assert "phone" in prompt
        assert "email" in prompt

    def test_prompt_includes_anchor_information(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes anchor information for fields."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "BUSINESS NAME" in prompt
        assert "Anchor" in prompt

    def test_prompt_includes_ocr_lines(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes OCR lines."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "BUSINESS PERMIT APPLICATION" in prompt
        assert "[0]" in prompt or "[1]" in prompt  # Line numbers

    def test_prompt_includes_pattern_matches(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes extracted patterns."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "PATTERN MATCHES" in prompt
        assert "09175551234" in prompt or "phone" in prompt.lower()

    def test_prompt_includes_form_name(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes form name when provided."""
        form_name = "Business Permit Application"
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result, form_name)
        assert form_name in prompt

    def test_prompt_includes_json_output_requirement(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes JSON output format requirement."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "extracted_fields" in prompt
        assert "confidence" in prompt
        assert "BEGIN JSON OUTPUT" in prompt

    def test_prompt_is_string(self, sample_enriched_template, sample_ocr_result):
        """Prompt is a string."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert isinstance(prompt, str)

    def test_prompt_is_not_empty(self, sample_enriched_template, sample_ocr_result):
        """Prompt is not empty."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert len(prompt) > 100

    def test_prompt_with_empty_ocr(self, sample_enriched_template, empty_ocr_result):
        """Handle empty OCR result."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, empty_ocr_result)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_with_large_ocr(self, sample_enriched_template, large_ocr_result):
        """Handle large OCR result (context truncation)."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, large_ocr_result)
        # Should include first 100 lines
        assert "[0]" in prompt
        assert "... (50 more lines)" in prompt or "more lines" in prompt

    def test_prompt_without_patterns(self):
        """Handle template without pattern matches."""
        template = {
            "fields": [{"name": "field1", "label": "Field 1", "type": "text"}],
            "pattern_matches": {},
        }
        ocr = {
            "raw_lines": [{"text": "Some text", "confidence": 0.8}],
            "full_text": "Some text",
        }
        prompt = build_ocr_extraction_prompt(template, ocr)
        assert isinstance(prompt, str)

    def test_prompt_confidence_guidelines_included(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes confidence interpretation guidelines."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        assert "0.95" in prompt or "confidence" in prompt.lower()

    def test_prompt_includes_normalization_rules(self, sample_enriched_template, sample_ocr_result):
        """Prompt includes data normalization rules."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        # Check for normalization guidance
        assert "normali" in prompt.lower() or "format" in prompt.lower()


# ============================================================================
# TESTS: build_minimal_recovery_prompt()
# ============================================================================

class TestBuildMinimalRecoveryPrompt:
    """Test cases for build_minimal_recovery_prompt."""

    def test_recovery_prompt_includes_field_names(self, sample_ocr_result):
        """Recovery prompt includes field names."""
        failed_fields = [
            {"name": "field1", "label": "Field 1"},
            {"name": "field2", "label": "Field 2"},
        ]
        prompt = build_minimal_recovery_prompt(failed_fields, sample_ocr_result)
        assert "field1" in prompt
        assert "field2" in prompt

    def test_recovery_prompt_includes_full_text(self, sample_ocr_result):
        """Recovery prompt includes OCR full text."""
        failed_fields = [{"name": "business_name", "label": "Business Name"}]
        prompt = build_minimal_recovery_prompt(failed_fields, sample_ocr_result)
        assert "BUSINESS" in prompt or len(prompt) > 100

    def test_recovery_prompt_includes_json_format(self, sample_ocr_result):
        """Recovery prompt includes JSON output format."""
        failed_fields = [{"name": "field1", "label": "Field 1"}]
        prompt = build_minimal_recovery_prompt(failed_fields, sample_ocr_result)
        assert "extracted_fields" in prompt
        assert "field_name" in prompt

    def test_recovery_prompt_is_smaller_than_full(self, sample_enriched_template, sample_ocr_result):
        """Recovery prompt is simpler/smaller than full prompt."""
        full_prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        recovery_prompt = build_minimal_recovery_prompt(sample_enriched_template["fields"][:1], sample_ocr_result)
        assert len(recovery_prompt) < len(full_prompt)

    def test_recovery_prompt_truncates_large_text(self):
        """Recovery prompt truncates large OCR text."""
        large_text = "LINE\n" * 1000
        ocr = {
            "raw_lines": [],
            "full_text": large_text,
        }
        failed_fields = [{"name": "field1", "label": "Field 1"}]
        prompt = build_minimal_recovery_prompt(failed_fields, ocr)
        # Should truncate to 2000 chars
        assert len(prompt) < 3000


# ============================================================================
# TESTS: System Prompt
# ============================================================================

class TestSystemPrompt:
    """Test cases for GROQ_SYSTEM_PROMPT."""

    def test_system_prompt_exists(self):
        """System prompt is defined."""
        assert GROQ_SYSTEM_PROMPT is not None
        assert len(GROQ_SYSTEM_PROMPT) > 0

    def test_system_prompt_includes_critical_rules(self):
        """System prompt includes critical extraction rules."""
        assert "CRITICAL RULES" in GROQ_SYSTEM_PROMPT

    def test_system_prompt_includes_confidence_guidance(self):
        """System prompt includes confidence interpretation."""
        assert "CONFIDENCE" in GROQ_SYSTEM_PROMPT

    def test_system_prompt_includes_type_normalization(self):
        """System prompt includes type normalization rules."""
        assert "Type normalization" in GROQ_SYSTEM_PROMPT or "Dates" in GROQ_SYSTEM_PROMPT


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestPromptBuildingIntegration:
    """Integration tests for prompt building."""

    def test_full_prompt_generation_workflow(self, sample_enriched_template, sample_ocr_result):
        """Generate full prompt and verify completeness."""
        prompt = build_ocr_extraction_prompt(sample_enriched_template, sample_ocr_result)
        
        # Verify all sections are present
        assert "expert" in prompt.lower()
        assert any(f["name"] in prompt for f in sample_enriched_template["fields"])
        assert "BEGIN JSON OUTPUT" in prompt

    def test_prompt_with_multiple_sections(self):
        """Generate prompt with multiple form sections."""
        template = {
            "fields": [
                {
                    "name": "name",
                    "label": "Name",
                    "type": "text",
                    "required": True,
                    "section": "personal_info",
                    "preprocessed": {"anchor_found": True, "anchor_text": "NAME:", "context_lines": ["Juan Dela Cruz"]},
                },
                {
                    "name": "address",
                    "label": "Address",
                    "type": "text",
                    "required": True,
                    "section": "residential_info",
                    "preprocessed": {"anchor_found": True, "anchor_text": "ADDRESS:", "context_lines": ["123 Main St"]},
                },
                {
                    "name": "date_birth",
                    "label": "Date of Birth",
                    "type": "date",
                    "required": True,
                    "section": "personal_info",
                    "preprocessed": {"anchor_found": True, "anchor_text": "DOB:", "context_lines": ["01/15/1990"]},
                },
            ],
            "pattern_matches": {"date": ["01/15/1990"]},
        }
        
        ocr = {
            "raw_lines": [
                {"text": "NAME:", "confidence": 0.9},
                {"text": "Juan Dela Cruz", "confidence": 0.88},
                {"text": "ADDRESS:", "confidence": 0.9},
                {"text": "123 Main St", "confidence": 0.85},
                {"text": "DOB:", "confidence": 0.9},
                {"text": "01/15/1990", "confidence": 0.92},
            ],
            "full_text": "NAME:\nJuan Dela Cruz\nADDRESS:\n123 Main St\nDOB:\n01/15/1990",
        }
        
        prompt = build_ocr_extraction_prompt(template, ocr, form_name="Personal Information Form")
        
        # Verify all fields present
        assert "name" in prompt
        assert "address" in prompt
        assert "date_birth" in prompt
        assert "Personal Information Form" in prompt
        assert "personal_info" in prompt or "residential_info" in prompt


    def test_prompt_handles_missing_fields(self):
        """Prompt handles fields without preprocessing data."""
        template = {
            "fields": [
                {
                    "name": "field1",
                    "label": "Field 1",
                    "type": "text",
                    # Missing preprocessed
                },
                {
                    "name": "field2",
                    "label": "Field 2",
                    "type": "text",
                    "preprocessed": {"anchor_found": False},
                },
            ],
            "pattern_matches": {},
        }
        
        ocr = {
            "raw_lines": [{"text": "Some text", "confidence": 0.8}],
            "full_text": "Some text",
        }
        
        prompt = build_ocr_extraction_prompt(template, ocr)
        assert "field1" in prompt
        assert "field2" in prompt
