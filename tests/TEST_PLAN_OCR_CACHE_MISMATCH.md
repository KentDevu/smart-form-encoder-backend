# TDD Test Plan: OCR Cache Structure Mismatch Fix

**Objective:** Verify that `process_ocr_task()` correctly handles both fresh and cached OCR result structures.

**Fix Location:** [backend/app/services/ocr_task.py](../app/services/ocr_task.py#L310-L326)

**Fix Summary:**
- Lines 310-326 handle two OCR result structures:
  - **Fresh**: `{raw_lines: [...], full_text: str, ...}` (from PaddleOCR)
  - **Cached**: `{line_count: int, full_text: str, ...}` (from Redis, raw_lines excluded)
- Problem: KeyError when accessing `raw_lines` on cached results
- Solution: Use if/elif/else to safely detect structure type and extract `raw_lines_count`

---

## Part 1: UNIT TESTS (Test `raw_lines_count` extraction logic)

### Test File: `test_ocr_cache_structure.py`

#### UT-1: Extract raw_lines_count from FRESH OCR result
**Test ID:** `test_extract_rawlines_count_from_fresh_ocr_result`

**Precondition:** Fresh OCR result with `raw_lines` array

**Input:**
```python
ocr_result = {
    "raw_lines": [
        {"text": "Line 1", "confidence": 0.95},
        {"text": "Line 2", "confidence": 0.92},
        {"text": "Line 3", "confidence": 0.88},
    ],
    "full_text": "Line 1\nLine 2\nLine 3",
    "avg_confidence": 0.92,
    "processing_time": 2.5,
}
```

**Expected Assertion:**
```python
assert raw_lines_count == 3
assert raw_lines_count == len(ocr_result["raw_lines"])
```

**Why This Matters:** Verifies fresh results are correctly counted.

---

#### UT-2: Extract raw_lines_count from CACHED OCR result
**Test ID:** `test_extract_rawlines_count_from_cached_ocr_result`

**Precondition:** Cached OCR result with `line_count` instead of `raw_lines`

**Input:**
```python
ocr_result = {
    "line_count": 5,  # Pre-computed from Redis
    "full_text": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5",
    "avg_confidence": 0.89,
    "processing_time": 0.1,
}
# NOTE: raw_lines is NOT present (memory optimization)
```

**Expected Assertion:**
```python
assert raw_lines_count == 5
assert "line_count" in ocr_result
assert "raw_lines" not in ocr_result
```

**Why This Matters:** Verifies cached results use line_count and don't have raw_lines.

---

#### UT-3: Handle CORRUPTED OCR result (both keys missing)
**Test ID:** `test_handle_corrupted_ocr_result_no_keys`

**Precondition:** OCR result missing BOTH `raw_lines` and `line_count`

**Input:**
```python
ocr_result = {
    "full_text": "Some text",
    "avg_confidence": 0.50,
    "processing_time": 1.0,
    # Both raw_lines and line_count are missing!
}
```

**Expected Behavior:**
- Log ERROR message: `"OCR data integrity error for entry {form_entry_id}: missing both 'line_count' (cached) and 'raw_lines' (fresh)..."`
- Set `raw_lines_count = 0` as fallback
- Task continues (doesn't crash)
- Entry marked with 0 lines

**Expected Assertion:**
```python
assert raw_lines_count == 0
assert logger.error.called
assert "data integrity error" in logger.error.call_args[0][0]
```

**Why This Matters:** 
- Prevents KeyError exceptions
- Indicates data pipeline corruption
- Allows graceful degradation

---

#### UT-4: Verify final raw_ocr_data structure
**Test ID:** `test_final_raw_ocr_data_structure_excludes_raw_lines`

**Precondition:** After extracting raw_lines_count from either fresh or cached result

**Expected Output Structure:**
```python
entry.raw_ocr_data = {
    "full_text": "...",
    "raw_lines_count": 5,  # NOT raw_lines array
    "field_count": 3,
}

# Must NOT contain:
assert "raw_lines" not in entry.raw_ocr_data  # Memory optimization
```

**Why This Matters:** Verifies the memory optimization is applied (raw_lines excluded).

---

#### UT-5: Edge case — raw_lines with 0 lines
**Test ID:** `test_extract_rawlines_count_with_empty_raw_lines`

**Precondition:** Fresh result with empty raw_lines array (edge case of blank form)

**Input:**
```python
ocr_result = {
    "raw_lines": [],  # Empty array (blank page)
    "full_text": "",
    "avg_confidence": 0.0,
    "processing_time": 0.5,
}
```

**Expected Assertion:**
```python
assert raw_lines_count == 0
assert isinstance(raw_lines_count, int)
```

**Why This Matters:** Handles blank/empty forms without crashing.

---

#### UT-6: Edge case — raw_lines is None (data corruption variant)
**Test ID:** `test_extract_rawlines_count_when_raw_lines_is_none`

**Precondition:** Fresh result structure but raw_lines is None instead of array

**Input:**
```python
ocr_result = {
    "raw_lines": None,  # Corrupted: should be array but is None
    "full_text": "Some text",
    "avg_confidence": 0.50,
    "processing_time": 1.0,
}
```

**Expected Behavior:** 
- Should NOT crash trying `len(None)`
- Should be caught by the else clause (missing both keys)
- Result: `raw_lines_count = 0` with error logged

**Expected Assertion:**
```python
assert raw_lines_count == 0
assert logger.error.called
```

**Why This Matters:** Prevents TypeError on `len(None)`.

---

#### UT-7: Edge case — line_count is 0 (cached empty result)
**Test ID:** `test_extract_rawlines_count_with_zero_line_count`

**Precondition:** Cached result with line_count = 0

**Input:**
```python
ocr_result = {
    "line_count": 0,  # Cached empty result
    "full_text": "",
    "avg_confidence": 0.0,
    "processing_time": 0.1,
}
```

**Expected Assertion:**
```python
assert raw_lines_count == 0
assert isinstance(raw_lines_count, int)
```

**Why This Matters:** Handles zero case for both fresh and cached.

---

#### UT-8: Edge case — line_count is negative (data corruption)
**Test ID:** `test_extract_rawlines_count_with_negative_line_count`

**Precondition:** Cached result with invalid negative line_count

**Input:**
```python
ocr_result = {
    "line_count": -5,  # Corrupted: should never be negative
    "full_text": "Some text",
    "avg_confidence": 0.50,
    "processing_time": 0.1,
}
```

**Expected Behavior:**
- Should extract the value as-is (validate at a higher layer)
- OR: Validate and clamp to 0 with warning
- Test should specify which behavior is correct

**Expected Assertion:**
```python
assert raw_lines_count == -5  # OR == 0 if validation is applied
```

**Why This Matters:** Clarifies validation responsibilities.

---

#### UT-9: Type check — raw_lines_count is integer
**Test ID:** `test_raw_lines_count_is_integer_type`

**Precondition:** Any valid OCR result

**Expected Assertion:**
```python
assert isinstance(raw_lines_count, int)
assert raw_lines_count >= 0
```

**Why This Matters:** Ensures type safety for downstream code.

---

### UT-10: Verify confidence score calculation unchanged
**Test ID:** `test_confidence_score_calculation_unchanged_after_fix`

**Precondition:** OCR result with mapped fields

**Expected Behavior:**
- Confidence calculation logic is independent of cache structure fix
- Should use `avg_confidence` from ocr_result as-is

**Expected Assertion:**
```python
assert entry.confidence_score == ocr_result["avg_confidence"]
assert entry.confidence_score == avg_confidence
```

**Why This Matters:** Ensures fix doesn't affect confidence logic.

---

## Part 2: INTEGRATION TESTS (Test full `process_ocr_task()` function)

### Test File: `test_process_ocr_task_integration.py`

#### IT-1: Full pipeline with FRESH OCR result from cache miss
**Test ID:** `test_process_ocr_task_full_pipeline_fresh_result`

**Precondition:**
- Form entry in UPLOADED status
- Form template exists
- Cache MISS (will call `extract_text_from_image()`)
- Successfully extracts to EXTRACTED status

**Mocks:**
```python
@patch('app.services.ocr_task._download_image_from_r2')
@patch('app.services.ocr_task.extract_text_from_image')  # Returns fresh result
@patch('app.services.ocr_task.extract_fields_unified')
@patch('app.services.ocr_task.get_cached_ocr_result', return_value=None)  # Cache miss
```

**Expected Behavior:**
1. Download image
2. Call extract_text_from_image → returns fresh result with raw_lines
3. Extract raw_lines_count = len(ocr_result["raw_lines"])
4. Map fields
5. Save entry with raw_ocr_data containing raw_lines_count
6. Entry status = EXTRACTED

**Expected Assertions:**
```python
assert result["status"] == "extracted"
assert result["fields_count"] > 0
entry = db.query(FormEntry).filter_by(id=form_entry_id).first()
assert entry.status == FormEntryStatus.EXTRACTED
assert "raw_lines_count" in entry.raw_ocr_data
assert "raw_lines" not in entry.raw_ocr_data
```

**Why This Matters:** Verifies happy path with fresh results.

---

#### IT-2: Full pipeline with CACHED OCR result (cache hit)
**Test ID:** `test_process_ocr_task_full_pipeline_cached_result`

**Precondition:**
- Form entry in UPLOADED status
- Cache HIT (will NOT call `extract_text_from_image()`, will return cached)
- Cached result has line_count, not raw_lines

**Mocks:**
```python
@patch('app.services.ocr_task.get_cached_ocr_result')  # Cache hit
def mock_get_cached_ocr_result():
    return {
        "line_count": 7,  # Cached, not raw_lines
        "full_text": "Cached text",
        "avg_confidence": 0.88,
        "processing_time": 0.1,
    }
```

**Expected Behavior:**
1. Download image
2. Call get_cached_ocr_result → cache hit, returns result with line_count
3. Extract raw_lines_count = ocr_result["line_count"]
4. Continue normally to field extraction & save
5. Entry status = EXTRACTED

**Expected Assertions:**
```python
assert result["status"] == "extracted"
entry = db.query(FormEntry).filter_by(id=form_entry_id).first()
assert entry.raw_ocr_data["raw_lines_count"] == 7
assert "raw_lines" not in entry.raw_ocr_data
extract_text_from_image.assert_not_called()  # Cache hit skips OCR
```

**Why This Matters:** Verifies cached results work correctly.

---

#### IT-3: Handle OCR result with corrupted data (missing both keys)
**Test ID:** `test_process_ocr_task_handles_corrupted_ocr_result`

**Precondition:**
- OCR result returned by extract_text_from_image is corrupted
- Missing both raw_lines and line_count
- Task should not crash

**Mocks:**
```python
@patch('app.services.ocr_task.extract_text_from_image')
def mock_extract_return_corrupted():
    return {
        "full_text": "Some text",
        "avg_confidence": 0.5,
        "processing_time": 1.0,
        # Missing raw_lines AND line_count!
    }
```

**Expected Behavior:**
1. Task logs ERROR: "OCR data integrity error..."
2. Sets raw_lines_count = 0
3. Continues to save entry with 0 lines
4. Entry status = EXTRACTED (partial success, not FAILED)
5. Task returns successfully (doesn't crash)

**Expected Assertions:**
```python
assert result["status"] == "extracted"
assert logger.error.called
entry = db.query(FormEntry).filter_by(id=form_entry_id).first()
assert entry.raw_ocr_data["raw_lines_count"] == 0
assert entry.status == FormEntryStatus.EXTRACTED
```

**Why This Matters:** Ensures graceful degradation on data corruption.

---

#### IT-4: Database save with raw_ocr_data structure
**Test ID:** `test_process_ocr_task_saves_raw_ocr_data_correctly`

**Precondition:**
- Process OCR task with mocked services
- Verify what gets written to database

**Expected Behavior:**
- Database entry.raw_ocr_data contains only:
  - `full_text` (str)
  - `raw_lines_count` (int)
  - `field_count` (int)
- Database entry.raw_ocr_data does NOT contain:
  - `raw_lines` (array) — excluded for memory optimization
  - `avg_confidence` — moved to entry.confidence_score
  - `processing_time` — moved to entry.processing_time

**Expected Assertions:**
```python
entry = db.query(FormEntry).filter_by(id=form_entry_id).first()
raw_ocr_data = entry.raw_ocr_data

assert "full_text" in raw_ocr_data
assert "raw_lines_count" in raw_ocr_data
assert "field_count" in raw_ocr_data

assert "raw_lines" not in raw_ocr_data
assert "avg_confidence" not in raw_ocr_data
assert "processing_time" not in raw_ocr_data
```

**Why This Matters:** Verifies memory optimization is applied in database.

---

#### IT-5: Confidence score and processing_time extracted correctly
**Test ID:** `test_process_ocr_task_saves_confidence_and_processing_time`

**Precondition:**
- OCR result has avg_confidence = 0.87 and processing_time = 3.2
- Multiple fields with varying confidence

**Expected Behavior:**
- entry.confidence_score = avg_confidence from ocr_result
- entry.processing_time = processing_time from ocr_result
- These are separate from raw_ocr_data JSON

**Expected Assertions:**
```python
entry = db.query(FormEntry).filter_by(id=form_entry_id).first()
assert entry.confidence_score == 0.87
assert entry.processing_time == 3.2
assert entry.raw_ocr_data["raw_lines_count"] == 10
```

**Why This Matters:** Verifies metadata is properly extracted.

---

#### IT-6: Multiple sequential OCR tasks (fresh, then cached)
**Test ID:** `test_process_ocr_task_sequence_fresh_then_cached`

**Precondition:**
- Same image uploaded twice
- First call: cache miss → fresh result
- Second call: cache hit → cached result
- Both should produce identical raw_ocr_data

**Mocks:**
- First call: extract_text_from_image returns fresh with raw_lines
- Second call: get_cached_ocr_result returns cached with line_count

**Expected Behavior:**
- First entry: raw_lines_count calculated from len(raw_lines)
- Second entry: raw_lines_count from line_count
- Both entries have identical raw_lines_count value

**Expected Assertions:**
```python
entry1 = db.query(FormEntry).filter_by(id=form_entry_id_1).first()
entry2 = db.query(FormEntry).filter_by(id=form_entry_id_2).first()

assert entry1.raw_ocr_data["raw_lines_count"] == entry2.raw_ocr_data["raw_lines_count"]
assert entry1.raw_ocr_data["full_text"] == entry2.raw_ocr_data["full_text"]
```

**Why This Matters:** Verifies cache consistency — same image produces same results.

---

## Part 3: EDGE CASES & ERROR CONDITIONS

### Test File: `test_ocr_cache_edge_cases.py`

#### EC-1: Extremely large raw_lines array (memory stress)
**Test ID:** `test_handle_large_raw_lines_array`

**Precondition:** OCR result with 10,000+ lines (edge case)

**Input:**
```python
ocr_result = {
    "raw_lines": [{"text": f"Line {i}", "confidence": 0.9} for i in range(10000)],
    "full_text": "...",
    "avg_confidence": 0.85,
    "processing_time": 5.0,
}
```

**Expected Behavior:**
- raw_lines_count = 10000 (correctly counted)
- Task completes without OOM
- raw_lines is NOT stored in database (memory optimization)

**Expected Assertions:**
```python
assert raw_lines_count == 10000
assert "raw_lines" not in entry.raw_ocr_data
entry_json_size = len(json.dumps(entry.raw_ocr_data).encode())
assert entry_json_size < 100 * 1024  # < 100KB (without raw_lines)
```

**Why This Matters:** Stress test for memory optimization.

---

#### EC-2: Mixed type in raw_lines (corrupted array)
**Test ID:** `test_handle_raw_lines_with_mixed_types`

**Precondition:** raw_lines contains non-dict items (data corruption)

**Input:**
```python
ocr_result = {
    "raw_lines": [
        {"text": "Line 1", "confidence": 0.95},
        "Not a dict",  # Corrupted!
        None,
        {"text": "Line 3", "confidence": 0.88},
    ],
    "full_text": "...",
    "avg_confidence": 0.80,
    "processing_time": 1.0,
}
```

**Expected Behavior:**
- raw_lines is still counted (len still works)
- Count = 4 (length of array regardless of content)
- Task continues with best effort

**Expected Assertions:**
```python
assert raw_lines_count == 4
assert not isinstance(raw_lines_count, type(None))
```

**Why This Matters:** Ensures len() works on malformed arrays.

---

#### EC-3: Very long full_text (10MB+)
**Test ID:** `test_handle_very_long_full_text`

**Precondition:** OCR output with extremely long full_text

**Input:**
```python
ocr_result = {
    "raw_lines": [{"text": "x" * 100} for i in range(10000)],  # 10MB text
    "full_text": "x" * (10 * 1024 * 1024),  # 10MB
    "avg_confidence": 0.90,
    "processing_time": 10.0,
}
```

**Expected Behavior:**
- raw_lines_count extracted successfully
- raw_lines excluded from database (memory optimization)
- Database stores only raw_lines_count (not the array)

**Expected Assertions:**
```python
assert raw_lines_count == 10000
assert "raw_lines" not in entry.raw_ocr_data
# raw_ocr_data should be small even though input was huge
```

**Why This Matters:** Validates memory optimization for large data.

---

#### EC-4: Type mismatch — line_count is string instead of int
**Test ID:** `test_handle_line_count_as_string`

**Precondition:** Cached result where line_count is accidentally string

**Input:**
```python
ocr_result = {
    "line_count": "42",  # String instead of int
    "full_text": "...",
    "avg_confidence": 0.85,
    "processing_time": 0.1,
}
```

**Expected Behavior:**
- Should either coerce to int or log warning
- Task continues

**Expected Assertions:**
```python
# Either accept as-is or coerce
assert raw_lines_count == 42 or raw_lines_count == "42"
```

**Why This Matters:** Tests resilience to type mismatches in cache.

---

#### EC-5: Confidence score > 1.0 (data validation)
**Test ID:** `test_handle_confidence_over_100_percent`

**Precondition:** OCR result with avg_confidence = 1.5

**Input:**
```python
ocr_result = {
    "raw_lines": [...],
    "full_text": "...",
    "avg_confidence": 1.5,  # > 1.0 is invalid
    "processing_time": 1.0,
}
```

**Expected Behavior:**
- Entry saves with confidence_score = 1.5
- Validation should occur at higher layer (not in this function)
- OR: Clamp to [0.0, 1.0] with warning

**Expected Assertions:**
```python
assert entry.confidence_score >= 0.0
assert entry.confidence_score <= 1.0  # OR == 1.5 if no clamping
```

**Why This Matters:** Clarifies validation responsibility.

---

#### EC-6: Zero fields extracted
**Test ID:** `test_process_ocr_task_with_zero_fields`

**Precondition:**
- OCR successful (raw_lines_count > 0)
- But field extraction returns empty (no fields mapped)
- Entry should still save with field_count = 0

**Mocks:**
```python
@patch('app.services.ocr_task.extract_fields_unified', return_value={})
```

**Expected Behavior:**
- raw_ocr_data["field_count"] = 0
- Entry status = EXTRACTED (still marked as success)
- confidence_score = 0.0 (no fields to average)

**Expected Assertions:**
```python
assert result["fields_count"] == 0
assert entry.raw_ocr_data["field_count"] == 0
assert entry.confidence_score == 0.0
assert entry.status == FormEntryStatus.EXTRACTED
```

**Why This Matters:** Handles case where OCR works but field mapping fails.

---

#### EC-7: Processing time is 0 or negative
**Test ID:** `test_handle_zero_or_negative_processing_time`

**Precondition:** OCR result has processing_time = 0 or -1

**Input:**
```python
ocr_result = {
    "raw_lines": [...],
    "full_text": "...",
    "avg_confidence": 0.85,
    "processing_time": -0.5,  # Invalid
}
```

**Expected Behavior:**
- Store as-is (validation at higher layer)
- OR: Clamp to 0.0 with warning

**Expected Assertions:**
```python
assert entry.processing_time >= 0.0 or entry.processing_time == -0.5
```

**Why This Matters:** Clarifies validation boundaries.

---

## Part 4: REGRESSION TESTS (Verify existing functionality not broken)

### Test File: `test_ocr_task_regression.py`

#### REG-1: Field mapping still works after cache fix
**Test ID:** `test_field_mapping_unchanged_by_cache_fix`

**Expected:** Field extraction and confidence scoring unchanged

#### REG-2: WebSocket progress updates still published
**Test ID:** `test_websocket_progress_published_after_cache_fix`

**Expected:** `_publish_if_state_changed()` still called at milestones

#### REG-3: Error handling and retry logic unchanged
**Test ID:** `test_error_classification_unaffected_by_cache_fix`

**Expected:** Transient/permanent/partial error handling still works

#### REG-4: Database transactions still atomic
**Test ID:** `test_database_transaction_atomicity`

**Expected:** Rollback on exception, commit on success

#### REG-5: Memory cleanup (gc.collect) still called
**Test ID:** `test_memory_cleanup_still_invoked`

**Expected:** `gc.collect()` and `del image_bytes` still executed

---

## Part 5: CURRENT COVERAGE ANALYSIS

### Current Tests (Existing)
✓ `test_ocr_raw_lines.py::test_raw_ocr_data_structure_excludes_raw_lines` — Verifies raw_lines NOT in structure
✓ `test_ocr_raw_lines.py::test_raw_ocr_data_json_size_reduced` — Validates memory savings
✓ `test_ocr_raw_lines.py::test_raw_ocr_data_preserves_text_data` — Checks text integrity
✓ Module import test

### Coverage Gaps (NEW TESTS NEEDED)
✗ **No unit tests for the if/elif/else logic** (lines 310-326)
✗ **No tests for cached vs. fresh result handling**
✗ **No tests for corrupted data (both keys missing)**
✗ **No integration tests for full process_ocr_task()**
✗ **No edge cases (empty arrays, negative counts, type mismatches)**
✗ **No regression tests to verify existing logic unchanged**

### Proposed Test Distribution
- **Unit Tests (UT):** 10 tests → Focus on raw_lines extraction logic
- **Integration Tests (IT):** 6 tests → Focus on full pipeline
- **Edge Cases (EC):** 7 tests → Focus on error handling
- **Regression Tests (REG):** 5 tests → Focus on unchanged behavior
- **Total:** 28 test cases

---

## Part 6: IMPLEMENTATION ROADMAP (TDD Order)

### Phase 1: Unit Tests (RED)
1. Create `tests/test_ocr_cache_structure.py`:
   - UT-1 through UT-10
   - Write tests BEFORE implementation
   - All should FAIL initially

### Phase 2: Implementation (GREEN)
- Fix lines 310-326 in `ocr_task.py` to make UT tests pass
- Minimum implementation that satisfies all UTs

### Phase 3: Integration Tests (RED)
1. Create `tests/test_process_ocr_task_integration.py`:
   - IT-1 through IT-6
   - Write tests before integration fixes
   - All should FAIL initially

### Phase 4: Integration Implementation (GREEN)
- Ensure full `process_ocr_task()` passes IT tests
- Refactor if needed

### Phase 5: Edge Cases (RED)
1. Create `tests/test_ocr_cache_edge_cases.py`:
   - EC-1 through EC-7
   - Write tests BEFORE fixes
   - All should FAIL initially

### Phase 6: Edge Case Fixes (GREEN)
- Add error handling for edge cases

### Phase 7: Regression Tests (RED/GREEN)
1. Create `tests/test_ocr_task_regression.py`:
   - REG-1 through REG-5
   - RUN existing tests to ensure all PASS
   - Add new regression tests

### Phase 8: Coverage Verification
```bash
pytest tests/test_ocr_cache_structure.py -v --cov=app.services.ocr_task
pytest tests/test_process_ocr_task_integration.py -v --cov=app.services.ocr_task
pytest tests/test_ocr_cache_edge_cases.py -v --cov=app.services.ocr_task
pytest tests/test_ocr_task_regression.py -v --cov=app.services.ocr_task

# Combined coverage - TARGET: >=80% for ocr_task.py
pytest tests/ -v --cov=app.services.ocr_task --cov-report=html
```

---

## Part 7: PYTEST FIXTURES NEEDED

### `conftest.py` additions:

```python
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.form_entry import FormEntry, FormEntryStatus
from app.models.form_template import FormTemplate
from app.models.form_field import FormField


@pytest.fixture
def mock_db_session():
    """Mock database session for tests."""
    return MagicMock()


@pytest.fixture
def sample_form_entry(mock_db_session):
    """Sample FormEntry for testing."""
    entry = FormEntry(
        id="test-entry-123",
        template_id="template-1",
        image_url="s3://bucket/image.png",
        status=FormEntryStatus.UPLOADED,
        uploaded_by="user-1",
    )
    return entry


@pytest.fixture
def sample_form_template():
    """Sample FormTemplate for testing."""
    return FormTemplate(
        id="template-1",
        name="Test Form",
        field_schema={
            "fields": [
                {"name": "name", "type": "text"},
                {"name": "address", "type": "text"},
            ]
        },
    )


@pytest.fixture
def sample_fresh_ocr_result():
    """Fresh OCR result structure (with raw_lines array)."""
    return {
        "raw_lines": [
            {"text": "Line 1", "confidence": 0.95},
            {"text": "Line 2", "confidence": 0.92},
            {"text": "Line 3", "confidence": 0.88},
        ],
        "full_text": "Line 1\nLine 2\nLine 3",
        "avg_confidence": 0.92,
        "processing_time": 2.5,
    }


@pytest.fixture
def sample_cached_ocr_result():
    """Cached OCR result structure (with line_count, no raw_lines)."""
    return {
        "line_count": 3,
        "full_text": "Line 1\nLine 2\nLine 3",
        "avg_confidence": 0.92,
        "processing_time": 0.1,
    }


@pytest.fixture
def sample_corrupted_ocr_result():
    """Corrupted OCR result (missing both raw_lines and line_count)."""
    return {
        "full_text": "Some text",
        "avg_confidence": 0.50,
        "processing_time": 1.0,
    }
```

---

## Part 8: TEST EXECUTION CHECKLIST

- [ ] All 28 tests written and in RED status
- [ ] All unit tests (UT-1 to UT-10) failing
- [ ] All integration tests (IT-1 to IT-6) failing
- [ ] All edge case tests (EC-1 to EC-7) failing
- [ ] All regression tests (REG-1 to REG-5) initially PASSING (existing functionality)
- [ ] Lines 310-326 fixed to make tests GREEN
- [ ] All tests passing
- [ ] Coverage >= 80% for `app/services/ocr_task.py`
- [ ] No new warnings or errors in logs

---

## Part 9: MOCK/PATCH STRATEGY

```python
# For most tests
@patch('app.services.ocr_task._get_sync_session')
@patch('app.services.ocr_task._download_image_from_r2')
@patch('app.services.ocr_task.get_cached_ocr_result')
@patch('app.services.ocr_task.extract_text_from_image')
@patch('app.services.ocr_task.extract_fields_unified')
@patch('app.services.ocr_task.cache_ocr_result')
@patch('app.services.ocr_task.cache_field_extraction')
@patch('app.services.ocr_task._publish_if_state_changed')
```

---

## Part 10: SUCCESS CRITERIA

✅ All 28 tests passing
✅ Coverage >= 80% for `ocr_task.py` (lines 310-326 especially)
✅ No regressions (existing tests still pass)
✅ Cache structure mismatch never causes KeyError
✅ Corrupted data handled gracefully
✅ Memory optimization (raw_lines excluded) verified
✅ Both fresh and cached results work identically

