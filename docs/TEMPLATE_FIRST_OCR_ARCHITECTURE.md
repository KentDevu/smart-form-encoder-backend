# Template-First OCR Architecture

## Summary

The OCR pipeline now follows a template-first strategy:

1. Normalize and validate template schema (`fields[*].extraction`).
2. Run OCR once to get `raw_lines` and `full_text`.
3. Deterministically extract each field using template extraction metadata.
4. Send only unresolved fields to AI with field-scoped context.
5. Apply validators and form-specific rules.
6. Persist extracted values and source provenance.

## Design Goals

- Keep extraction deterministic whenever possible.
- Use AI only as a resolver, not as primary extractor.
- Make every extracted field traceable to extraction source.
- Eliminate runtime dependence on positional/pattern fallback layers.

## Core Modules

- `app/services/forms/template_schema.py`
  - Validates and normalizes extraction metadata.
- `app/services/forms/template_field_extractor.py`
  - Deterministic extractor driven by template map.
- `app/services/ocr_unified.py`
  - Targeted AI resolver for unresolved fields.
- `app/services/ocr_task.py`
  - Orchestrates the hard-cutover template-first flow.

## Extraction Metadata Contract

Each field supports:

- `extraction.strategy` (`label_nearby`, `line_match`, `checkbox_mark`)
- `extraction.anchor_labels` (ordered label hints)
- `extraction.search_region` (relative bounds: `x_min/y_min/x_max/y_max`)
- `extraction.ai_prompt_hint` (context for unresolved AI resolution)
- `extraction.value_postprocess` (reserved for future normalizers)

## Persistence Changes

`form_entries.raw_ocr_data` now includes:

- `field_sources` map (`deterministic`, `ai`, `rules`)
- `template_first_enabled` boolean

These fields support traceability and post-run analysis without requiring a new table.
