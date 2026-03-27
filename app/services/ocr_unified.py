"""Template-bounded AI resolver for unresolved OCR fields."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_targeted_prompt(
    unresolved_fields: list[dict[str, Any]],
    ocr_lines: list[dict[str, Any]],
    full_text: str,
) -> str:
    fields_json = json.dumps(
        [
            {
                "name": field["name"],
                "label": field.get("label", field["name"]),
                "type": field.get("type", "text"),
                "options": field.get("options", []),
                "hint": field.get("ai_prompt_hint"),
                "context_lines": field.get("context_lines", []),
            }
            for field in unresolved_fields
        ],
        indent=2,
    )
    ocr_preview = "\n".join(
        f"- {line.get('text', '')} (conf={float(line.get('confidence', 0.0)):.2f})"
        for line in ocr_lines[:80]
    )
    return (
        "You are resolving OCR fields using bounded context from a template map.\n"
        "Only return values for requested fields.\n\n"
        f"UNRESOLVED_FIELDS:\n{fields_json}\n\n"
        f"OCR_LINES:\n{ocr_preview}\n\n"
        f"FULL_TEXT:\n{full_text}\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "fields": {\n'
        '    "field_name": {"value": "string", "confidence": 0.0}\n'
        "  }\n"
        "}\n"
    )


def extract_fields_unified(
    client: Any,
    field_schema: dict[str, Any],
    ocr_result: dict[str, Any],
    unresolved_field_names: list[str] | None = None,
    deterministic_results: dict[str, dict[str, Any]] | None = None,
    model: str | None = None,
) -> dict[str, Any] | None:
    """
    Resolve unresolved fields using template-scoped OCR context.
    Returns {field_name: {value, confidence}}.
    """
    if model is None:
        model = get_settings().AI_VISION_MODEL

    all_fields = field_schema.get("fields", [])
    requested = set(unresolved_field_names or [])
    unresolved_fields: list[dict[str, Any]] = []

    for field in all_fields:
        name = field.get("name")
        if not name:
            continue
        if requested and name not in requested:
            continue
        if deterministic_results and not deterministic_results.get(name, {}).get("unresolved", False):
            continue
        unresolved_fields.append(
            {
                "name": name,
                "label": field.get("label", name),
                "type": field.get("type", "text"),
                "options": field.get("options", []),
                "ai_prompt_hint": (field.get("extraction") or {}).get("ai_prompt_hint"),
                "context_lines": (deterministic_results or {}).get(name, {}).get("context_lines", []),
            }
        )

    if not unresolved_fields:
        return {}

    prompt = _build_targeted_prompt(
        unresolved_fields=unresolved_fields,
        ocr_lines=ocr_result.get("raw_lines", []),
        full_text=ocr_result.get("full_text", ""),
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            max_tokens=2500,
            temperature=0.1,
        )
        content = response.choices[0].message.content or "{}"
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0]
        payload = json.loads(content.strip())
        return payload.get("fields", {})
    except Exception as exc:
        logger.error("Targeted AI resolver failed: %s", exc, exc_info=True)
        return None
