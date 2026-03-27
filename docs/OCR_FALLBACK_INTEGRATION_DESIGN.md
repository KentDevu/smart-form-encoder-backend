# OCR Extraction Fallback Integration Design

> Status: Superseded by template-first architecture. See `backend/docs/TEMPLATE_FIRST_OCR_ARCHITECTURE.md`.

## Executive Summary

This document describes the integration of positional/spatial field mapping as a fallback strategy in the OCR extraction pipeline. The fallback activates when unified AI extraction produces low confidence scores or too few fields.

**Current Pipeline:** 
```
OCR Lines → Unified AI Extract (P0) → Fields → Store
```

**Enhanced Pipeline:**
```
OCR Lines → Unified AI Extract (P0) → Fields
                                        ↓
                              Check coverage/confidence
                                  (low?)
                                        ↓
                          Positional Fallback (P1) → Merged Fields → Store
```

---

## Current Architecture (Status Quo)

### ocr_task.py - Orchestrator
**Entry Point:** `process_ocr_task(form_entry_id)` (Celery task)

**Current Flow:**
```python
1. Download form image from R2 storage
2. Extract OCR: extract_text_from_image_with_template() 
   Returns: {raw_lines, full_text, avg_confidence, processing_time}
3. Extract Fields: extract_fields_unified()
   Input: field_schema, ocr_result
   Returns: {field_name: {value, confidence}}
4. Validate & Save to DB
   - Create FormField entries
   - Calculate average confidence
   - Update FormEntry status → "extracted"
```

**Current Issues:**
- Low confidence (0.21 on DTI BNR) indicates AI model struggling
- Only 19/55 fields extracted (34.5%)
- No fallback when extraction quality is poor
- AI model may not be optimized for government form structure

### ocr_unified.py - Field Extraction
**Core Function:** `extract_fields_unified(client, field_schema, ocr_result)`

**Input:**
- `field_schema`: {fields: [{name, label, type, options, required}, ...]}
- `ocr_result`: {raw_lines, full_text, avg_confidence, processing_time}
- `ocr_result.raw_lines`: List of {text, confidence, bbox} (from PaddleOCR)

**Output:**
- `{field_name: {value, confidence}, ...}`

**Process:**
1. Build comprehensive prompt with field schema + OCR text + OCR lines
2. Call AI API (Groq/Nvidia) with max_tokens=4000, temp=0.1
3. Parse JSON response
4. Return field extraction

---

## Proposed Fallback Integration

### Strategy Overview

**Fallback Trigger Conditions:**
```python
avg_confidence < 0.5  AND  extracted_fields < 30
     ↓
  Fallback activates
```

**Rationale:**
- 0.5 confidence = unreliable, AI guessing
- < 30/55 fields = incomplete extraction
- Both conditions true = high likelihood of poor AI performance

**Fallback Method:**
- Use **positional/spatial mapping** (ocr_positional_mapping.py)
- Match OCR text bounding boxes to template field regions
- Extract values by label proximity
- Merge fallback results with initial extraction

### Integration Points

#### 1. ocr_task.py - Add Fallback Decision Logic

**Location:** After `extract_fields_unified()` call (line ~399)

**Addition:**
```python
# Step 3a: Extract fields (primary strategy)
fields_dict = extract_fields_unified(
    client=ai_client,
    field_schema=template.field_schema,
    ocr_result=ocr_result,
    image_base64=None,
)

# Step 3b: Check if fallback needed (P1)
avg_initial_confidence = sum(f.get('confidence', 0) for f in fields_dict.values()) / len(fields_dict) if fields_dict else 0
filled_count = sum(1 for f in fields_dict.values() if f.get('value'))
should_use_fallback = avg_initial_confidence < 0.5 and filled_count < 30

if should_use_fallback:
    logger.info(f"[OCR-FALLBACK] Triggering positional mapping (confidence={avg_initial_confidence:.2f}, filled={filled_count})")
    
    # Step 3c: Apply fallback (P1)
    fallback_fields = map_fields_by_spatial_position(
        raw_lines=ocr_result.get('raw_lines', []),
        field_schema=template.field_schema,
    )
    
    # Step 3d: Merge fallback with primary
    merged_fields = _merge_extraction_results(fields_dict, fallback_fields)
    fields_dict = merged_fields
    
    logger.info(f"[OCR-FALLBACK] Merged: {filled_count} → {sum(1 for f in fields_dict.values() if f.get('value'))} fields")
else:
    logger.debug(f"[OCR-FALLBACK] Primary extraction sufficient (confidence={avg_initial_confidence:.2f}, filled={filled_count})")
```

#### 2. ocr_unified.py - No Changes Required
- Primary extraction function remains unchanged
- Fallback is applied at orchestration level (ocr_task.py), not in ocr_unified.py
- Allows clean separation of concerns

#### 3. New File: ocr_positional_mapping.py
- Already created with core functions:
  - `BoundingBox` class with overlap/containment logic
  - `extract_bbox_from_paddle_ocr()` - Parse PaddleOCR coords
  - `group_ocr_lines_by_row()` / `group_ocr_lines_by_column()` - Spatial grouping
  - `find_field_by_label_position()` - Label-based search
  - `map_fields_by_spatial_position()` - Main fallback function

---

## Data Flow

### Input: OCR Result Format
From `extract_text_from_image_with_template()`:
```python
{
    "raw_lines": [
        {
            "text": "Business Name",
            "confidence": 0.92,
            "bbox": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]  # PaddleOCR format
        },
        ...
    ],
    "full_text": "Raw concatenated text",
    "avg_confidence": 0.68,
    "processing_time": 10.5
}
```

### Processing: Positional Mapping
```python
Input: raw_lines (with bbox), field_schema
  ↓
Extract BoundingBox from each line
  ↓
Group lines by row/column proximity
  ↓
For each field in schema:
  - Find label in OCR lines (fuzzy match)
  - Look for value to right/below label
  - Extract text from nearby lines
  - Calculate confidence from line confidences
  ↓
Output: {field_name: {value, confidence}, ...}
```

### Merging Strategy: _merge_extraction_results()
When both primary and fallback have results:
```python
for field_name in all_fields:
    primary = fields_dict.get(field_name, {})
    fallback = fallback_fields.get(field_name, {})
    
    primary_conf = primary.get('confidence', 0)
    fallback_conf = fallback.get('confidence', 0)
    
    if primary_conf > fallback_conf:
        # Keep primary (higher confidence)
        use = primary
    else:
        # Use fallback (better confidence)
        use = fallback
    
    merged[field_name] = use
```

---

## Implementation Checklist

### A1: Analysis & Architecture Design ✓
- [x] Analyze ocr_unified.py orchestration logic
- [x] Design fallback trigger points
- [x] Map integration points
- [x] Document data flow

### A2: Unit Test Framework (TBD)
- [ ] Create tests for BoundingBox operations
- [ ] Create tests for row/column grouping
- [ ] Create tests for label-based field search
- [ ] Create tests for integration paths

### A3: Implementation (TBD)
- [ ] Add fallback trigger condition to ocr_task.py
- [ ] Implement _merge_extraction_results() function
- [ ] Add logging for fallback activation

### A4: Integration Testing (TBD)
- [ ] Test fallback with real DTI BNR form
- [ ] Verify extraction improvements
- [ ] Verify backward compatibility

---

## Key Interfaces

### Fallback Function Signature
```python
def map_fields_by_spatial_position(
    raw_lines: list[dict[str, Any]],
    field_schema: dict[str, Any]
) -> dict[str, Any]:
    """
    Map OCR lines to form fields using positional analysis.
    
    Args:
        raw_lines: OCR extraction with bboxes
        field_schema: Template field definitions
        
    Returns:
        Dictionary mapping field_name → {value, confidence}
    """
```

### Merge Function Signature
```python
def _merge_extraction_results(
    primary: dict[str, Any],
    fallback: dict[str, Any]
) -> dict[str, Any]:
    """
    Merge primary and fallback extraction results.
    
    Strategy: Use result with higher confidence for each field.
    
    Args:
        primary: Results from unified AI extraction
        fallback: Results from positional mapping
        
    Returns:
        Merged {field_name: {value, confidence}} dict
    """
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Fallback produces wrong values** | Confidence thresholds: only use fallback if confident enough |
| **Fallback triggers incorrectly** | Dual condition check: confidence AND filled_count |
| **Over-confidence in fallback** | Post-processing validation layer (Phase C) catches errors |
| **Performance degradation** | Fallback only activates when needed; negligible overhead |
| **Backward compatibility break** | Primary path unchanged; fallback is purely additive |

---

## Future Enhancements

1. **Form-Specific Rules (Phase B):**
   - Post-processing validators for DTI BNR fields
   - Phone number formatting, amount parsing, date inference

2. **Field-Level Validation (Phase C):**
   - Schema-based validators for each field type
   - Confidence re-scoring post-validation

3. **Fine-tuned Models (Phase D):**
   - Use ML training pipeline to improve AI model accuracy
   - Replace generic Groq model with form-specific model

---

## Success Criteria

✅ Fallback integrates cleanly without breaking existing code  
✅ Fallback triggers correctly (low confidence + few fields)  
✅ Merged results improve coverage from 19/55 → ≥30/55  
✅ No regressions in existing high-confidence extractions  
✅ 80%+ test coverage for new code
