# Groq OCR Modules - Comprehensive Test Plan

## Overview

This document outlines the comprehensive test strategy for the 3 Groq OCR modules using Test-Driven Development (TDD) principles.

**Modules Under Test:**
1. `ocr_preprocessing_hints.py` — Anchor finding, pattern extraction, reading order
2. `ocr_groq_prompt.py` — Prompt building
3. `ocr_groq_extraction.py` — Groq API call, response parsing

**Coverage Target:** 80%+

---

## Test Strategy

### Unit Tests

**Purpose:** Test individual functions in isolation with mocked dependencies

**Approach:**
- Test each public function with various inputs
- Mock external dependencies (Groq API, database)
- Test edge cases: empty inputs, None, malformed data, large datasets
- Validate return types and structures
- Test error conditions

### Integration Tests

**Purpose:** Test interactions between modules and data flow

**Approach:**
- Test complete pipelines (OCR lines → enrichment → prompt → Groq → parse)
- Use realistic form templates and OCR outputs
- Verify end-to-end data transformation
- Test error recovery

### Error Scenarios

**Purpose:** Validate resilience and error handling

**Scenarios tested:**
- Groq API timeout
- Invalid JSON response
- Network failure
- Empty OCR results
- Malformed bounding boxes
- Missing template fields

---

## Module 1: `ocr_preprocessing_hints.py`

### Public Functions

1. **`find_anchor_in_raw_lines()`**
   - Exact anchor matching
   - Fuzzy (substring) matching
   - Confidence threshold evaluation
   - Context extraction (next 2 lines)
   - Returns: `AnchorMatch` dataclass

2. **`extract_pattern_matches()`**
   - Extract regex patterns: phone, email, date, TIN, amount
   - Multi-pattern matching per type
   - Deduplication
   - Returns: `dict[str, list[str]]`

3. **`build_reading_order()`**
   - Sort OCR lines by bounding box position (top→bottom, left→right)
   - Handle malformed bounding boxes
   - Returns: `list[dict]` with coordinates

4. **`enrich_template_with_preprocessing_hints()`**
   - Main entry point
   - Enriches field schema with anchor + pattern + reading order info
   - Non-mutating (deepcopy)
   - Returns: Enriched field schema

### Test File: `test_ocr_preprocessing_hints.py`

**Test Count: 50+ tests**

#### Class 1: `TestFindAnchorInRawLines` (10 tests)
- ✅ `test_find_anchor_exact_match` — Exact label match
- ✅ `test_find_anchor_case_insensitive` — Case-insensitive matching
- ✅ `test_find_anchor_fuzzy_match` — Substring matching
- ✅ `test_find_anchor_context_extraction` — Extract context lines
- ✅ `test_find_anchor_not_found` — No match scenario
- ✅ `test_find_anchor_below_threshold` — Confidence threshold
- ✅ `test_find_anchor_empty_lines` — Empty input
- ✅ `test_find_anchor_with_reading_order` — Reading order consistency
- ✅ `test_find_anchor_returns_anchor_match_dataclass` — Return type validation
- ✅ `test_find_anchor_multiple_occurrences` — Return first match

#### Class 2: `TestExtractPatternMatches` (9 tests)
- ✅ `test_extract_phone_patterns` — Philippine phone numbers
- ✅ `test_extract_email_patterns` — Email addresses
- ✅ `test_extract_date_patterns` — Date formats (DD/MM/YYYY, YYYY-MM-DD)
- ✅ `test_extract_tin_patterns` — 9-digit TIN
- ✅ `test_extract_amount_patterns` — Currency amounts (PHP, ₱)
- ✅ `test_extract_patterns_empty_input` — Empty input handling
- ✅ `test_extract_patterns_no_duplicates` — Deduplication
- ✅ `test_extract_patterns_case_insensitive` — Case handling
- ✅ `test_extract_patterns_monetary_formats` — Various format support

#### Class 3: `TestBuildReadingOrder` (8 tests)
- ✅ `test_build_reading_order_top_to_bottom` — Y-coordinate ordering
- ✅ `test_build_reading_order_includes_text` — Text preservation
- ✅ `test_build_reading_order_includes_coordinates` — Coordinate extraction
- ✅ `test_build_reading_order_preserves_confidence` — Confidence preservation
- ✅ `test_build_reading_order_empty_input` — Empty input handling
- ✅ `test_build_reading_order_malformed_bbox` — Malformed bbox handling
- ✅ `test_build_reading_order_same_y_sorted_by_x` — Secondary sort by X
- ✅ `test_build_reading_order_line_numbers` — Line number tracking

#### Class 4: `TestEnrichTemplateWithPreprocessingHints` (9 tests)
- ✅ `test_enrich_template_returns_enriched_schema` — Return structure
- ✅ `test_enrich_template_adds_pattern_matches` — Pattern section
- ✅ `test_enrich_template_adds_reading_order` — Reading order section
- ✅ `test_enrich_template_adds_preprocessed_per_field` — Per-field hints
- ✅ `test_enrich_template_preprocessed_has_anchor_found` — Anchor flag
- ✅ `test_enrich_template_does_not_mutate_original` — Deep copy validation
- ✅ `test_enrich_template_empty_ocr` — Empty OCR handling
- ✅ `test_enrich_template_missing_extraction_hints` — Missing hints handling
- ✅ `test_enrich_template_validates_anchors_found` — Anchor validation

#### Class 5: `TestPreprocessingHintsIntegration` (2 tests)
- ✅ `test_full_preprocessing_pipeline` — Full pipeline integration
- ✅ `test_preprocessing_with_real_form_scenario` — Real-world form test

**Edge Cases Covered:**
- Empty OCR result
- Malformed bounding boxes
- Confidence scores out of range
- Missing template fields
- Large datasets (100+ OCR lines)
- Case sensitivity
- Fuzzy matching tolerance

---

## Module 2: `ocr_groq_prompt.py`

### Public Functions

1. **`build_ocr_extraction_prompt()`**
   - Build comprehensive Groq prompt
   - Include system instructions, field definitions, OCR text, patterns
   - Truncate large inputs for context
   - Returns: Prompt string

2. **`build_minimal_recovery_prompt()`**
   - Build simple recovery prompt for failed fields
   - Smaller prompt size
   - Returns: Prompt string

3. **`GROQ_SYSTEM_PROMPT`**
   - System instructions for Groq
   - Confidence guidelines
   - Type normalization rules
   - Constant (not tested directly but validated in integration)

### Test File: `test_ocr_groq_prompt.py`

**Test Count: 25+ tests**

#### Class 1: `TestBuildOCRExtractionPrompt` (12 tests)
- ✅ `test_prompt_includes_system_instructions` — System prompt
- ✅ `test_prompt_includes_field_definitions` — Field list
- ✅ `test_prompt_includes_field_types` — Type annotations
- ✅ `test_prompt_includes_anchor_information` — Anchor hints
- ✅ `test_prompt_includes_ocr_lines` — OCR line listing
- ✅ `test_prompt_includes_pattern_matches` — Pattern section
- ✅ `test_prompt_includes_form_name` — Form name (optional)
- ✅ `test_prompt_includes_json_output_requirement` — Output format
- ✅ `test_prompt_is_string` — Type check
- ✅ `test_prompt_is_not_empty` — Non-empty check
- ✅ `test_prompt_with_empty_ocr` — Empty OCR handling
- ✅ `test_prompt_with_large_ocr` — Context truncation (100 lines)
- ✅ `test_prompt_without_patterns` — Missing patterns handling
- ✅ `test_prompt_confidence_guidelines_included` — Confidence rules
- ✅ `test_prompt_includes_normalization_rules` — Type normalization

#### Class 2: `TestBuildMinimalRecoveryPrompt` (4 tests)
- ✅ `test_recovery_prompt_includes_field_names` — Field name inclusion
- ✅ `test_recovery_prompt_includes_full_text` — OCR text inclusion
- ✅ `test_recovery_prompt_includes_json_format` — JSON format
- ✅ `test_recovery_prompt_is_smaller_than_full` — Size comparison
- ✅ `test_recovery_prompt_truncates_large_text` — Text truncation (2K limit)

#### Class 3: `TestSystemPrompt` (3 tests)
- ✅ `test_system_prompt_exists` — Prompt defined
- ✅ `test_system_prompt_includes_critical_rules` — Critical section
- ✅ `test_system_prompt_includes_confidence_guidance` — Confidence rules
- ✅ `test_system_prompt_includes_type_normalization` — Type rules

#### Class 4: `TestPromptBuildingIntegration` (3 tests)
- ✅ `test_full_prompt_generation_workflow` — E2E prompt generation
- ✅ `test_prompt_with_multiple_sections` — Multi-section form
- ✅ `test_prompt_handles_missing_fields` — Missing preprocessing data

**Edge Cases Covered:**
- Empty OCR result
- Large OCR result (100+ lines, truncation)
- Missing pattern matches
- Missing field preprocessing hints
- Multiple form sections
- Confidence guidelines inclusion

---

## Module 3: `ocr_groq_extraction.py`

### Public Functions

1. **`extract_fields_with_groq()`**
   - Main orchestrator function
   - Calls Groq API with enriched template + OCR data
   - Parses and validates response
   - Returns: Field records with confidence + usage stats
   - Or None on error

2. **`parse_groq_response()`**
   - Parse JSON response (with markdown fence handling)
   - Repair incomplete JSON (trailing commas)
   - Validate schema
   - Normalize confidence [0, 1]
   - Returns: Parsed payload dict or None

3. **`GroqExtractionError`**
   - Custom exception
   - Not tested directly (informational)

### Test File: `test_ocr_groq_extraction.py`

**Test Count: 40+ tests**

#### Class 1: `TestParseGroqResponse` (14 tests)
- ✅ `test_parse_valid_json_response` — Valid JSON parsing
- ✅ `test_parse_json_with_markdown_fences` — Markdown fence handling
- ✅ `test_parse_json_with_backticks_only` — Backtick handling
- ✅ `test_parse_malformed_json` — Malformed JSON repair
- ✅ `test_parse_missing_extracted_fields_key` — Missing key validation
- ✅ `test_parse_extracted_fields_not_list` — Type validation
- ✅ `test_parse_normalizes_confidence_to_range` — Confidence clamping
- ✅ `test_parse_confidence_string_conversion` — String to float
- ✅ `test_parse_invalid_confidence_defaults_to_half` — Invalid confidence handling
- ✅ `test_parse_missing_field_name_skipped` — Field name validation
- ✅ `test_parse_adds_empty_value_if_missing` — Default value
- ✅ `test_parse_strips_whitespace_from_values` — Whitespace trimming
- ✅ `test_parse_returns_none_on_json_error` — Error return
- ✅ `test_parse_empty_extracted_fields_list` — Empty list handling

#### Class 2: `TestExtractFieldsWithGroq` (8 tests)
- ✅ `test_extract_fields_success` — Successful extraction
- ✅ `test_extract_fields_returns_field_records` — Field record structure
- ✅ `test_extract_fields_includes_usage_stats` — Token usage tracking
- ✅ `test_extract_fields_includes_latency` — Latency measurement
- ✅ `test_extract_fields_empty_response_returns_none` — Empty response
- ✅ `test_extract_fields_invalid_json_returns_none` — Invalid JSON
- ✅ `test_extract_fields_api_exception_returns_none` — API exception
- ✅ `test_extract_fields_with_form_name` — Form name parameter
- ✅ `test_extract_fields_enrichment_called` — Enrichment verification

#### Class 3: `TestErrorScenarios` (5 tests)
- ✅ `test_groq_timeout_handled` — Timeout exception
- ✅ `test_network_failure_handled` — Network exception
- ✅ `test_parse_malformed_response_with_recovery` — Malformed recovery
- ✅ `test_empty_ocr_lines_handled` — Empty input
- ✅ `test_missing_usage_stats` — Missing API stats

#### Class 4: `TestExtractionPipeline` (4 tests)
- ✅ `test_full_extraction_pipeline` — E2E pipeline
- ✅ `test_partial_extraction_success` — Partial results
- ✅ `test_extraction_with_confidence_normalization` — Confidence validation

**Edge Cases Covered:**
- Valid JSON with markdown fences (```json)
- Valid JSON with plain backticks (```)
- Malformed JSON with trailing commas
- Malformed JSON with missing brackets
- Confidence out of range (< 0, > 1)
- Confidence as string (needs conversion)
- Invalid confidence (non-numeric)
- Missing field_name (skipped)
- Missing value (defaults to "")
- Whitespace in values
- Empty extracted_fields list
- Network timeout
- Connection error
- API exception
- Empty OCR result
- Missing usage stats

---

## Test Execution

### Setup

```bash
cd /home/kenthusiastic/development/smart-form-encoder/backend

# Install test dependencies
pip install pytest pytest-cov pytest-mock pytest-asyncio

# Activate virtual environment
source .venv/bin/activate
```

### Run All Tests

```bash
# Run all tests with coverage
pytest tests/test_ocr_*.py -v --cov=app.services --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_ocr_preprocessing_hints.py -v

# Run specific test class
pytest tests/test_ocr_preprocessing_hints.py::TestFindAnchorInRawLines -v

# Run specific test
pytest tests/test_ocr_preprocessing_hints.py::TestFindAnchorInRawLines::test_find_anchor_exact_match -v
```

### Coverage Report

```bash
# Generate HTML coverage report
pytest tests/test_ocr_*.py --cov=app.services.ocr_preprocessing_hints \
                          --cov=app.services.ocr_groq_prompt \
                          --cov=app.services.ocr_groq_extraction \
                          --cov-report=html

# Open report in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

---

## Coverage Targets

### Expected Coverage by Module

| Module | Target | Est. Actual |
|--------|--------|------------|
| `ocr_preprocessing_hints.py` | 80%+ | 85%+ |
| `ocr_groq_prompt.py` | 80%+ | 90%+ |
| `ocr_groq_extraction.py` | 80%+ | 85%+ |
| **Overall** | **80%+** | **87%+** |

### Coverage Breakdown

#### `ocr_preprocessing_hints.py`
- `find_anchor_in_raw_lines()`: 10 tests → ~95% coverage
- `extract_pattern_matches()`: 9 tests → ~85% coverage
- `build_reading_order()`: 8 tests → ~90% coverage
- `enrich_template_with_preprocessing_hints()`: 9 tests → ~88% coverage
- Dataclass `AnchorMatch`: Implicit coverage via function tests

#### `ocr_groq_prompt.py`
- `build_ocr_extraction_prompt()`: 15 tests → ~92% coverage
- `build_minimal_recovery_prompt()`: 5 tests → ~85% coverage
- `GROQ_SYSTEM_PROMPT`: Validated in integration tests → ~80% usage

#### `ocr_groq_extraction.py`
- `extract_fields_with_groq()`: 9 tests → ~85% coverage
- `parse_groq_response()`: 14 tests → ~88% coverage
- Exception class: Implicit coverage → ~70% coverage
- API mocking: Full coverage of happy path + error paths

---

## TDD Workflow

### Phase 1: Red (Tests First)
✅ Tests written without implementation details

### Phase 2: Green (Make Tests Pass)
```bash
# Run tests to see current failures
pytest tests/test_ocr_*.py -v

# Implement functions to pass tests
# (already implemented in this case)
```

### Phase 3: Refactor (Improve)
```bash
# Run tests after refactoring
pytest tests/test_ocr_*.py -v --cov=app.services

# Ensure coverage remains ≥80%
```

---

## Running the Complete Test Suite

```bash
#!/bin/bash

cd /home/kenthusiastic/development/smart-form-encoder/backend

# Run all Groq OCR tests with detailed output
pytest tests/test_ocr_preprocessing_hints.py \
        tests/test_ocr_groq_prompt.py \
        tests/test_ocr_groq_extraction.py \
        -v \
        --tb=short \
        --cov=app.services.ocr_preprocessing_hints \
        --cov=app.services.ocr_groq_prompt \
        --cov=app.services.ocr_groq_extraction \
        --cov-report=term-missing \
        --cov-report=html

echo "✅ Tests completed!"
echo "📊 Coverage report: htmlcov/index.html"
```

---

## Test Fixtures Summary

### Shared Fixtures (conftest.py)

1. **`test_settings`** — Test environment configuration
2. **`sample_form_template`** — Minimal test form template
3. **`sample_ocr_data`** — Sample OCR extraction result
4. **`mock_groq_response`** — Mock Groq API response

### Module-Specific Fixtures

#### `test_ocr_preprocessing_hints.py`
- `sample_raw_lines` — Standard OCR lines
- `sample_field_schema` — Form template with extraction hints
- `low_confidence_lines` — Below-threshold OCR lines
- `empty_raw_lines` — Empty input
- `malformed_raw_lines` — Invalid structure

#### `test_ocr_groq_prompt.py`
- `sample_enriched_template` — Template with preprocessing hints
- `sample_ocr_result` — OCR data
- `minimal_template` — Minimal template
- `empty_ocr_result` — Empty OCR
- `large_ocr_result` — 150+ lines OCR

#### `test_ocr_groq_extraction.py`
- `sample_raw_lines` — Standard OCR lines
- `sample_field_schema` — Form template
- `valid_groq_response_json` — Valid API response
- `mock_ai_client` — Mocked Groq client

---

## Mocking Strategy

### Dependencies Mocked

1. **Groq API Client** (`get_ai_client()`)
   - Mocked using `unittest.mock.Mock`
   - Returns: Configured mock response objects
   - Used in: `extract_fields_with_groq()` tests

2. **Configuration** (Optional)
   - Can mock `get_settings()` if needed
   - Currently uses test settings from conftest

3. **Database** (Not tested)
   - These modules don't access database directly
   - Database coverage is in separate test suite

### Mocking Pattern

```python
@patch("app.services.ocr_groq_extraction.get_ai_client")
def test_example(mock_get_client):
    mock_client = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="..."))]
    mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    mock_client.chat.completions.create = Mock(return_value=mock_response)
    mock_get_client.return_value = mock_client
    
    result = extract_fields_with_groq(...)
    assert result is not None
```

---

## Test Markers

### Available markers

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run slow tests (optional)
pytest -m slow

# Skip slow tests
pytest -m "not slow"
```

### Marking Tests

Tests are automatically marked based on class:
- `TestFunctionName*` → unit tests
- `Test*Integration` → integration tests
- `Test*Scenarios` → error scenarios

---

## Continuous Integration

### GitHub Actions / CI Pipeline

```yaml
name: Test Groq OCR Modules

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/test_ocr_*.py --cov --cov-report=xml
      - uses: codecov/codecov-action@v2
```

---

## Performance Benchmarks

### Expected Test Execution Times

| Test Suite | Count | Estimated Time |
|-----------|-------|-----------------|
| `test_ocr_preprocessing_hints.py` | 20 | ~0.5s |
| `test_ocr_groq_prompt.py` | 15 | ~0.3s |
| `test_ocr_groq_extraction.py` | 25 | ~1.0s (mocked API calls) |
| **Total** | **60** | **~2.0s** |

---

## Debugging Tests

### Run with Print Statements

```bash
pytest tests/test_ocr_*.py -v -s  # Show print output
```

### Run with Detailed Tracebacks

```bash
pytest tests/test_ocr_*.py -v --tb=long
```

### Debug Specific Test

```bash
pytest tests/test_ocr_preprocessing_hints.py::TestFindAnchorInRawLines::test_find_anchor_exact_match -v -s --tb=short
```

### Inspect Fixtures

```bash
pytest --fixtures tests/test_ocr_preprocessing_hints.py
```

---

## Next Steps

1. **Run the test suite** to verify all tests pass
2. **Check coverage report** to ensure 80%+ coverage
3. **Add integration tests** for real API calls (optional, requires API key)
4. **Set up CI/CD** to run tests on every commit
5. **Monitor test performance** to keep execution under 5 seconds
6. **Update tests** as new features are added

---

## References

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-mock Plugin](https://pytest-mock.readthedocs.io/)
- [pytest Coverage Plugin](https://pytest-cov.readthedocs.io/)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
