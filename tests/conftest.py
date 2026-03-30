"""
Shared fixtures and configuration for Groq OCR tests.

pytest conftest.py
"""

import os
import pytest
from typing import Any
from unittest.mock import Mock, patch


# Set up minimal env before importing to avoid validation errors
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("AI_VISION_MODEL", "llama-3.3-70b-versatile")
os.environ.setdefault("AI_BASE_URL", "https://api.groq.com/openai/v1")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only")
os.environ.setdefault("HASH_ALGORITHM", "bcrypt")


@pytest.fixture(scope="session")
def test_settings():
    """Test settings."""
    from app.config import Settings
    return Settings()


@pytest.fixture
def sample_form_template() -> dict[str, Any]:
    """Sample form template for testing."""
    return {
        "template_id": "test_form_001",
        "name": "Test Form",
        "sections": ["basic_info", "contact"],
        "fields": [
            {
                "name": "full_name",
                "label": "Full Name",
                "type": "text",
                "required": True,
                "section": "basic_info",
                "extraction": {"anchor_label": "FULL NAME"},
            },
            {
                "name": "email",
                "label": "Email",
                "type": "email",
                "required": False,
                "section": "contact",
                "extraction": {"anchor_label": "EMAIL"},
            },
        ],
    }


@pytest.fixture
def sample_ocr_data() -> dict[str, Any]:
    """Sample OCR extraction data."""
    return {
        "raw_lines": [
            {
                "text": "FULL NAME",
                "confidence": 0.95,
                "bbox": [[10, 20], [100, 20], [100, 40], [10, 40]],
            },
            {
                "text": "John Doe",
                "confidence": 0.92,
                "bbox": [[10, 50], [100, 50], [100, 70], [10, 70]],
            },
            {
                "text": "EMAIL",
                "confidence": 0.93,
                "bbox": [[150, 20], [230, 20], [230, 40], [150, 40]],
            },
            {
                "text": "john@example.com",
                "confidence": 0.90,
                "bbox": [[150, 50], [300, 50], [300, 70], [150, 70]],
            },
        ],
        "full_text": "FULL NAME\nJohn Doe\nEMAIL\njohn@example.com",
    }


@pytest.fixture
def mock_groq_response() -> dict[str, Any]:
    """Mock Groq API response."""
    return {
        "extracted_fields": [
            {
                "field_name": "full_name",
                "value": "John Doe",
                "confidence": 0.92,
                "reasoning": "Anchor found at line 0, value at line 1",
            },
            {
                "field_name": "email",
                "value": "john@example.com",
                "confidence": 0.90,
                "reasoning": "Anchor found at line 2, value at line 3",
            },
        ],
        "extraction_summary": "Successfully extracted 2 of 2 fields",
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers",
        "unit: mark test as a unit test",
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow",
    )
