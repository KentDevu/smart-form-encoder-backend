"""
AI-powered template generation service.

Accepts a sample form image and uses Groq Vision to analyze the form structure,
then produces a FormLayoutSchema JSON that the DynamicFormRenderer can render.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def generate_template_from_image(image_bytes: bytes) -> dict[str, Any]:
    """
    Analyze a sample form image with AI Vision and return a FormLayoutSchema.

    Returns a dict matching the FormLayoutSchema structure:
    {
        "header": "Republic of the Philippines",
        "subheader": "...",
        "title": "Form Name",
        "sections": [ { "title": "...", "layout": "table", "fields": [...] } ],
        "footer": "...",
        "fields": [ flat list for backward compat ]
    }

    Raises RuntimeError if AI is unavailable or fails to produce valid output.
    """
    from app.config import get_settings

    settings = get_settings()

    if not settings.AI_API_KEY:
        raise RuntimeError("AI_API_KEY not configured — cannot generate template")

    # Detect MIME type
    if image_bytes[:4] == b"\x89PNG":
        mime = "image/png"
    elif image_bytes[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    elif image_bytes[:4] == b"%PDF":
        # Convert first page of PDF to image
        image_bytes, mime = _pdf_first_page_to_image(image_bytes)
    else:
        mime = "image/jpeg"

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "You are an expert at analyzing paper form layouts used in Philippine government offices. "
        "I will show you an image of a form. Your job is to produce a COMPLETE and ACCURATE "
        "JSON layout schema that describes EVERY field, checkbox, and blank in the form.\n\n"
        "The JSON must use this structure:\n"
        "```\n"
        "{\n"
        '  "header": "top institutional header text",\n'
        '  "subheader": "department or office name below header",\n'
        '  "title": "main form title",\n'
        '  "sections": [\n'
        "    {\n"
        '      "title": "A. SECTION NAME (keep letter/number prefix if present)",\n'
        '      "layout": "table",\n'
        '      "fields": [\n'
        "        {\n"
        '          "name": "snake_case_field_name",\n'
        '          "label": "Visible Label exactly as shown on form",\n'
        '          "type": "text",\n'
        '          "width": "full",\n'
        '          "number": "3"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "footer": "certification text at the bottom (if any)"\n'
        "}\n"
        "```\n\n"
        "FIELD TYPES:\n"
        '- "text" — single text input (most common)\n'
        '- "date" — date field\n'
        '- "number" — numeric input\n'
        '- "textarea" — multi-line text\n'
        '- "checkbox" — single yes/no checkbox\n'
        '- "checkbox-group" — group of checkboxes (include "options" array with each option label)\n'
        '- "radio" — radio button group (include "options" array)\n'
        '- "select" — dropdown (include "options" array)\n\n'
        "FIELD WIDTH — assign based on how fields sit side-by-side on the SAME ROW in the form:\n"
        '- "full" — field takes the whole row\n'
        '- "half" — 2 fields sit side by side on one row\n'
        '- "third" — 3 fields sit side by side on one row\n'
        '- "quarter" — 4 fields sit side by side on one row\n\n'
        "CRITICAL RULES:\n"
        "1. Extract EVERY SINGLE field, blank, and checkbox visible in the form. Do NOT skip any.\n"
        "2. If a field has a number on the form (e.g. '3. First Name'), put ONLY the number in \"number\": \"3\" "
        "and put ONLY the label text in \"label\": \"First Name\" — do NOT put the number inside the label.\n"
        "3. Keep section titles EXACTLY as printed on the form. Copy them character by character. "
        "For example if it says 'C. OWNER\\'S INFORMATION', write exactly 'C. OWNER\\'S INFORMATION'. "
        "Do NOT paraphrase, abbreviate, or rearrange section titles.\n"
        "4. For checkbox groups (e.g. gender Male/Female, civil status), use type \"checkbox-group\" "
        "with \"options\" listing each choice.\n"
        "5. Look at how many fields sit side by side in each row to determine correct widths.\n"
        "6. For fields with Year/Month/Day sub-fields, create separate fields for each.\n"
        "7. field \"name\" must be lowercase snake_case, unique across the whole form.\n"
        "8. If a field label mentions '(Area code)' or similar hint, include it in the label.\n"
        "9. Return ONLY valid JSON. No extra text, no markdown explanation.\n"
        "10. Be EXHAUSTIVE — it is better to have too many fields than too few.\n"
        "11. Read the form image VERY carefully. Zoom in mentally on each section.\n"
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
        )

        response = client.chat.completions.create(
            model=settings.AI_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=4000,
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"

        # Strip markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        schema = json.loads(content.strip())

        # Validate minimal structure
        if "title" not in schema:
            raise ValueError("Missing 'title' in generated schema")
        if "sections" not in schema or not isinstance(schema["sections"], list):
            raise ValueError("Missing or invalid 'sections' in generated schema")

        # Build backward-compat flat fields list
        flat_fields: list[dict[str, str]] = []
        for section in schema["sections"]:
            for field in section.get("fields", []):
                flat_fields.append({
                    "name": field["name"],
                    "label": field["label"],
                    "type": field.get("type", "text"),
                })
        schema["fields"] = flat_fields

        logger.info(
            "AI generated template: %s (%d sections, %d fields)",
            schema.get("title", "?"),
            len(schema["sections"]),
            len(flat_fields),
        )
        return schema

    except json.JSONDecodeError as e:
        logger.error("AI returned invalid JSON for template generation: %s", e)
        raise RuntimeError(f"AI returned invalid JSON: {e}") from e
    except Exception as e:
        logger.error("AI template generation failed: %s", e)
        raise RuntimeError(f"Template generation failed: {e}") from e


def _pdf_first_page_to_image(pdf_bytes: bytes) -> tuple[bytes, str]:
    """Convert the first page of a PDF to a PNG image."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(dpi=200)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes, "image/png"
