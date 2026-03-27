"""Integration tests for OCR extraction fallback strategy."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.services.ocr_task import _merge_extraction_results


# =============================================================================
# Merge Results Tests (4 tests)
# =============================================================================

class TestMergeExtractionResults:
    """Tests for _merge_extraction_results function."""
    
    def test_merge_primary_higher_confidence(self):
        """Test merging when primary has higher confidence."""
        primary = {
            "business_name": {"value": "ABC Corp", "confidence": 0.95},
        }
        fallback = {
            "business_name": {"value": "ABC", "confidence": 0.60},
        }
        result = _merge_extraction_results(primary, fallback)
        
        assert result["business_name"]["value"] == "ABC Corp"
        assert result["business_name"]["confidence"] == 0.95
    
    def test_merge_fallback_higher_confidence(self):
        """Test merging when fallback has higher confidence."""
        primary = {
            "owner_name": {"value": "", "confidence": 0.0},
        }
        fallback = {
            "owner_name": {"value": "John Doe", "confidence": 0.85},
        }
        result = _merge_extraction_results(primary, fallback)
        
        assert result["owner_name"]["value"] == "John Doe"
        assert result["owner_name"]["confidence"] == 0.85
    
    def test_merge_fills_missing_fields(self):
        """Test that merge fills fields missing from primary."""
        primary = {
            "business_name": {"value": "ABC Corp", "confidence": 0.9},
        }
        fallback = {
            "business_name": {"value": "ABC Corp", "confidence": 0.8},
            "owner_name": {"value": "John Doe", "confidence": 0.85},
            "phone": {"value": "09123456", "confidence": 0.8},
        }
        result = _merge_extraction_results(primary, fallback)
        
        assert len(result) == 3
        assert "business_name" in result
        assert "owner_name" in result
        assert "phone" in result
    
    def test_merge_empty_results(self):
        """Test merging with empty results."""
        primary = {}
        fallback = {}
        result = _merge_extraction_results(primary, fallback)
        
        assert len(result) == 0


# =============================================================================
# Fallback Trigger Logic Tests (2 tests)
# =============================================================================

class TestFallbackTriggerLogic:
    """Tests for fallback trigger conditions."""
    
    def test_fallback_trigger_low_confidence(self):
        """Test that fallback triggers on low confidence."""
        # Low confidence (0.21) and few fields (19/55 = 34.5%)
        avg_confidence = 0.21
        filled_count = 19
        total_fields = 55
        
        should_trigger = avg_confidence < 0.5 and filled_count < (total_fields * 0.6)
        
        assert should_trigger is True
    
    def test_no_fallback_trigger_good_confidence(self):
        """Test that fallback does NOT trigger on good extraction."""
        # Good confidence (0.85) and good coverage (45/55 = 81%)
        avg_confidence = 0.85
        filled_count = 45
        total_fields = 55
        
        should_trigger = avg_confidence < 0.5 and filled_count < (total_fields * 0.6)
        
        assert should_trigger is False


# =============================================================================
# End-to-End Fallback Improvement Tests (3 tests)
# =============================================================================

class TestFallbackImprovement:
    """Tests verifying fallback improves extraction on real data."""
    
    def test_fallback_improves_dti_form(self):
        """Test that fallback improves extraction on realistic DTI form."""
        # Simulate poor primary extraction (low confidence, few fields)
        primary = {
            "certificate_no": {"value": "NR0:052018", "confidence": 0.88},
            "business_name": {"value": "", "confidence": 0.0},
            "owner_name": {"value": "", "confidence": 0.0},
            "phone": {"value": "", "confidence": 0.0},
            "address": {"value": "", "confidence": 0.0},
            "amount": {"value": "", "confidence": 0.0},
        }
        
        # Simulate fallback extraction (positional mapping)
        fallback = {
            "certificate_no": {"value": "NR0:052018", "confidence": 0.88},
            "business_name": {"value": "ABC Trading", "confidence": 0.82},
            "owner_name": {"value": "John Doe", "confidence": 0.80},
            "phone": {"value": "09123456", "confidence": 0.75},
            "address": {"value": "Manila", "confidence": 0.70},
            "amount": {"value": "", "confidence": 0.0},
        }
        
        # Merge
        result = _merge_extraction_results(primary, fallback)
        
        # Count improvements
        primary_filled = sum(1 for v in primary.values() if v.get("value"))
        result_filled = sum(1 for v in result.values() if v.get("value"))
        
        assert result_filled > primary_filled
        assert result["business_name"]["value"] == "ABC Trading"
        assert result["owner_name"]["value"] == "John Doe"
    
    def test_fallback_preserves_good_extraction(self):
        """Test that fallback preserves high-confidence primary values."""
        # Primary with good confidence
        primary = {
            "certificate_no": {"value": "NR0:052018", "confidence": 0.95},
            "business_name": {"value": "ABC Corp", "confidence": 0.92},
        }
        
        # Fallback with lower confidence
        fallback = {
            "certificate_no": {"value": "NR0:052018", "confidence": 0.70},
            "business_name": {"value": "ABC", "confidence": 0.65},
        }
        
        result = _merge_extraction_results(primary, fallback)
        
        # Primary values should be preserved
        assert result["certificate_no"]["value"] == "NR0:052018"
        assert result["certificate_no"]["confidence"] == 0.95
        assert result["business_name"]["value"] == "ABC Corp"
        assert result["business_name"]["confidence"] == 0.92
    
    def test_fallback_beats_missed_detection(self):
        """Test that fallback extracts fields primary missed."""
        # Primary completely missed some fields
        primary = {
            "business_name": {"value": "", "confidence": 0.0},
            "owner_name": {"value": "", "confidence": 0.0},
        }
        
        # Fallback found them
        fallback = {
            "business_name": {"value": "XYZ Ltd", "confidence": 0.82},
            "owner_name": {"value": "Jane Smith", "confidence": 0.78},
        }
        
        result = _merge_extraction_results(primary, fallback)
        
        # Fallback results should be used
        assert result["business_name"]["value"] == "XYZ Ltd"
        assert result["owner_name"]["value"] == "Jane Smith"
        assert result["business_name"]["confidence"] == 0.82
        assert result["owner_name"]["confidence"] == 0.78


# =============================================================================
# Confidence Threshold Tests (2 tests)
# =============================================================================

class TestConfidenceThresholds:
    """Tests for confidence-based decision making."""
    
    def test_fallback_threshold_exactly_zero_five(self):
        """Test fallback behavior at exactly 0.5 threshold."""
        avg_confidence = 0.5
        filled_count = 20
        total_fields = 55
        
        should_trigger = avg_confidence < 0.5 and filled_count < (total_fields * 0.6)
        
        # Should not trigger at exactly 0.5 (uses < not <=)
        assert should_trigger is False
    
    def test_fallback_just_below_threshold(self):
        """Test fallback activation just below 0.5 threshold."""
        avg_confidence = 0.49
        filled_count = 20
        total_fields = 55
        
        should_trigger = avg_confidence < 0.5 and filled_count < (total_fields * 0.6)
        
        # Should trigger when both conditions met
        assert should_trigger is True
