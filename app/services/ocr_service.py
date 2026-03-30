"""OCR extraction service — schema-driven, single-pass AI extraction.

Design philosophy:
- The template field_schema IS the extraction blueprint.
  Every field already has: name, label, type, hint, section, options.
  We use these directly rather than rediscovering structure on every call.
- One AI call per form (batched if >BATCH_SIZE fields), not 4+ separate calls.
- PaddleOCR runs once to get raw text + bounding boxes.
- AI receives: OCR text lines + field blueprint + image → fills slots.
- Checkboxes and text fields use the same call, differentiated by type hints.
- Post-correction runs as before.
"""

import io
import json
import logging
import time
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_paddle_ocr = None

BATCH_SIZE = 30  # fields per AI call — larger is fine, schema gives enough context


# ── PaddleOCR (unchanged) ────────────────────────────────────────────

def _get_paddle_ocr():
    global _paddle_ocr
    from app.config import get_settings
    settings = get_settings()

    if settings.LOW_RAM_MODE or not settings.CACHE_OCR_MODEL:
        from paddleocr import PaddleOCR
        return PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)

    if _paddle_ocr is None:
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
    return _paddle_ocr


def _pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    import fitz
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def _is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def _ocr_single_image(img_array: np.ndarray) -> list[dict[str, Any]]:
    ocr = _get_paddle_ocr()
    result = ocr.ocr(img_array)
    raw_lines = []
    if result and result[0]:
        for line in result[0]:
            bbox = line[0]
            text = line[1][0]
            confidence = float(line[1][1])
            raw_lines.append({"text": text, "confidence": confidence, "bbox": bbox})
    return raw_lines


def extract_text_from_image(image_bytes: bytes) -> dict[str, Any]:
    """Run PaddleOCR. Returns raw_lines, full_text, avg_confidence, processing_time."""
    start_time = time.time()
    raw_lines: list[dict[str, Any]] = []

    if _is_pdf(image_bytes):
        logger.info("Detected PDF, converting pages…")
        pages = _pdf_to_images(image_bytes)
        for page_num, page_img in enumerate(pages, 1):
            if page_img.mode != "RGB":
                page_img = page_img.convert("RGB")
            page_lines = _ocr_single_image(np.array(page_img))
            for line in page_lines:
                line["page"] = page_num
            raw_lines.extend(page_lines)
    else:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")
        raw_lines = _ocr_single_image(np.array(image))

    processing_time = time.time() - start_time
    total_conf = sum(l["confidence"] for l in raw_lines)
    avg_confidence = (total_conf / len(raw_lines)) if raw_lines else 0.0
    full_text = "\n".join(l["text"] for l in raw_lines)

    logger.info(
        f"OCR: {len(raw_lines)} lines, avg_conf={avg_confidence:.2f}, "
        f"time={processing_time:.2f}s"
    )
    return {
        "raw_lines": raw_lines,
        "full_text": full_text,
        "avg_confidence": avg_confidence,
        "processing_time": processing_time,
    }


# ── Schema-driven field descriptor ───────────────────────────────────

def _describe_field(field: dict[str, Any]) -> str:
    """
    Build a one-line extraction instruction for a single schema field.
    Uses every piece of metadata the schema already provides.
    """
    name = field["name"]
    label = field.get("label", name)
    ftype = field.get("type", "text")
    hint = field.get("hint", "")
    section = field.get("section", "")
    options = field.get("options", [])
    number = field.get("number", "")

    # Location context from schema metadata
    location_parts = []
    if section:
        location_parts.append(f"section: {section}")
    if hint:
        location_parts.append(hint)
    if number:
        location_parts.append(f"field #{number}")
    location = f" [{', '.join(location_parts)}]" if location_parts else ""

    # Type-specific extraction instruction
    if ftype == "checkbox":
        return (
            f'"{name}" — Checkbox labeled "{label}"{location}. '
            f'Return "true" if the box is checked/filled/marked, "" if empty.'
        )
    elif ftype == "radio" and options:
        opts = ", ".join(f'"{o}"' for o in options)
        return (
            f'"{name}" — Radio group "{label}"{location}. '
            f"Options: {opts}. Return EXACTLY one matching option value."
        )
    elif ftype == "checkbox-group" and options:
        opts = ", ".join(f'"{o}"' for o in options)
        return (
            f'"{name}" — Checkbox group "{label}"{location}. '
            f"Options: {opts}. Return comma-separated checked values."
        )
    elif ftype == "select" and options:
        opts = ", ".join(f'"{o}"' for o in options)
        return (
            f'"{name}" — Select "{label}"{location}. '
            f"Options: {opts}. Return the matching option value."
        )
    elif ftype == "date":
        return f'"{name}" — Date field "{label}"{location}. Return as written (e.g. YYYY-MM-DD or as found).'
    elif ftype == "number":
        return f'"{name}" — Numeric field "{label}"{location}. Return digits only.'
    else:
        return f'"{name}" — Text field "{label}"{location}.'


# ── Single schema-driven AI extraction call ───────────────────────────

def _extract_batch_with_schema(
    client: Any,
    model: str,
    batch_fields: list[dict[str, Any]],
    ocr_lines_formatted: str,
    image_content: dict[str, Any] | None,
    batch_idx: int,
    total_batches: int,
) -> dict[str, Any] | None:
    """
    One AI call for a batch of fields.

    The prompt is schema-driven: every field descriptor is derived from the
    template schema (label, type, section, hint, options) so the AI knows
    exactly what it's looking for and where on the form to find it.
    """
    field_instructions = "\n".join(
        f"  {i+1}. {_describe_field(f)}"
        for i, f in enumerate(batch_fields)
    )

    batch_label = f"batch {batch_idx}/{total_batches}" if total_batches > 1 else "all fields"
    prompt = (
        "You are an OCR data extraction specialist for Philippine government forms.\n\n"
        "FORM TEXT (from PaddleOCR — use as primary signal):\n"
        f"{ocr_lines_formatted}\n\n"
        f"EXTRACT THESE {len(batch_fields)} FIELDS ({batch_label}):\n"
        f"{field_instructions}\n\n"
        "RULES:\n"
        "- Cross-reference the OCR text lines above with the form image.\n"
        "- Each field description tells you the label and location on the form.\n"
        "- For checkboxes: look at the actual box — filled/dark/marked = \"true\", empty = \"\".\n"
        "- For radio buttons: compare ALL options visually, return exactly one.\n"
        "- For text: find the value written next to or below the label.\n"
        "- If a field is blank or unreadable, return empty string \"\".\n"
        "- Return ONLY valid JSON — no markdown, no explanation.\n\n"
        "JSON format (use exact field names as keys):\n"
        '{\n  "field_name": "extracted value",\n  ...\n}'
    )

    try:
        messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image_content:
            messages_content.append(image_content)

        max_tokens = max(1500, len(batch_fields) * 100)

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": messages_content}],
            max_tokens=max_tokens,
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"

        # Strip markdown fences
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Attempt repair: strip trailing incomplete entry
            repaired = content
            last_comma = repaired.rfind(",")
            if last_comma > 0:
                repaired = repaired[:last_comma]
            if not repaired.rstrip().endswith("}"):
                repaired = repaired.rstrip() + "\n}"
            try:
                result = json.loads(repaired)
                logger.info(f"Batch {batch_idx}: JSON repaired, {len(result)} fields")
            except json.JSONDecodeError as e:
                logger.error(f"Batch {batch_idx}: JSON parse failed: {e}")
                return None

        filled = sum(1 for v in result.values() if v and v != "false")
        logger.info(f"Batch {batch_idx}/{total_batches}: {filled}/{len(batch_fields)} fields extracted")
        return result

    except Exception as e:
        logger.error(f"Batch {batch_idx} failed: {e}")
        return None


# ── Normalise AI output per field type ───────────────────────────────

def _normalise_value(raw: Any, field: dict[str, Any]) -> str:
    """Normalise AI output to the expected format for the field type."""
    if raw is None:
        return ""

    # Handle nested dict from AI (shouldn't happen but defensive)
    if isinstance(raw, dict):
        raw = raw.get("value", "")

    value = str(raw).strip()
    ftype = field.get("type", "text")

    if ftype == "checkbox":
        low = value.lower()
        if low in ("yes", "true", "checked", "1", "x", "✓", "✔", "on", "selected", "filled"):
            return "true"
        return ""

    elif ftype == "radio":
        options = field.get("options", [])
        if not options:
            return value
        # Try exact match first
        low = value.lower().strip()
        for opt in options:
            if low == opt.lower():
                return opt
        # Try partial/normalised match
        norm = low.replace("/", "_").replace("-", "_").replace(" ", "_")
        for opt in options:
            if norm == opt.lower():
                return opt
        # Word containment
        for opt in options:
            opt_words = set(opt.lower().replace("_", " ").split())
            raw_words = set(low.replace("_", " ").replace("/", " ").split())
            if opt_words and opt_words.issubset(raw_words):
                return opt
        logger.debug(f"Radio match failed for '{value}' against {options}")
        return ""

    elif ftype == "checkbox-group":
        # AI may return comma-separated
        return value

    elif ftype == "number":
        import re
        digits = re.sub(r"[^\d]", "", value)
        return digits

    return value


# ── Main public entry point ───────────────────────────────────────────

def map_ocr_to_fields(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None = None,
) -> list[dict[str, Any]]:
    """
    Schema-driven field extraction.

    1. Build image content once.
    2. Format OCR lines once.
    3. Send fields to AI in batches (schema provides all context).
    4. Normalise results per field type.
    5. Fall back to naive label match for any missing fields.
    6. Run post-correction.
    """
    fields_spec: list[dict[str, Any]] = field_schema.get("fields", [])
    if not fields_spec:
        return []

    from app.config import get_settings
    settings = get_settings()

    if not settings.AI_API_KEY:
        logger.warning("No AI API key — falling back to naive label matching")
        return _map_fields_naive(ocr_result, field_schema)

    # ── Build shared assets ──────────────────────────────────────────
    raw_lines = ocr_result.get("raw_lines", [])

    ocr_lines_formatted = "\n".join(
        f"  Line {i+1} (conf {line['confidence']:.2f}): \"{line['text']}\""
        for i, line in enumerate(raw_lines)
    )

    image_content: dict[str, Any] | None = None
    if image_bytes:
        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        if image_bytes[:4] == b"\x89PNG":
            mime = "image/png"
        elif image_bytes[:2] == b"\xff\xd8":
            mime = "image/jpeg"
        else:
            mime = "image/jpeg"
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }

    # ── AI extraction in batches ─────────────────────────────────────
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
        )
        model = settings.AI_VISION_MODEL

        batches = [
            fields_spec[i:i + BATCH_SIZE]
            for i in range(0, len(fields_spec), BATCH_SIZE)
        ]
        total_batches = len(batches)
        if total_batches > 1:
            logger.info(f"Schema-driven extraction: {len(fields_spec)} fields in {total_batches} batches")

        all_results: dict[str, Any] = {}

        for idx, batch in enumerate(batches, 1):
            batch_result = _extract_batch_with_schema(
                client=client,
                model=model,
                batch_fields=batch,
                ocr_lines_formatted=ocr_lines_formatted,
                image_content=image_content,
                batch_idx=idx,
                total_batches=total_batches,
            )
            if batch_result:
                all_results.update(batch_result)

    except Exception as e:
        logger.error(f"AI extraction failed: {e}")
        return _map_fields_naive(ocr_result, field_schema)

    # ── Build final mapped list ──────────────────────────────────────
    mapped_fields: list[dict[str, Any]] = []

    for field_spec in fields_spec:
        name = field_spec["name"]
        raw_value = all_results.get(name, "")
        value = _normalise_value(raw_value, field_spec)

        # Confidence: high if AI returned something, lower if empty
        confidence = 0.92 if value else 0.0

        mapped_fields.append({
            "field_name": name,
            "ocr_value": value,
            "confidence": confidence,
        })

    filled = sum(1 for f in mapped_fields if f["ocr_value"])
    logger.info(
        f"Schema-driven extraction complete: {filled}/{len(mapped_fields)} fields filled"
    )

    # ── Post-correction ──────────────────────────────────────────────
    from app.services.post_correction import apply_post_corrections
    mapped_fields = apply_post_corrections(mapped_fields)

    return mapped_fields


def enhance_with_vision(
    image_bytes: bytes,
    field_schema: dict[str, Any],
    low_confidence_fields: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Targeted re-extraction for fields that scored below threshold.
    Uses the same schema-driven approach but scoped to just the problem fields.
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.AI_API_KEY:
        return {}

    fields_to_retry = [
        f for f in field_schema.get("fields", [])
        if f["name"] in low_confidence_fields
    ]

    if not fields_to_retry:
        return {}

    logger.info(f"Vision re-extraction for {len(fields_to_retry)} low-confidence fields")

    # Minimal OCR result (no text lines — rely on image only for enhancement)
    ocr_result = {"raw_lines": [], "full_text": ""}

    result = map_ocr_to_fields(
        ocr_result,
        {"fields": fields_to_retry},
        image_bytes,
    )

    return {
        f["field_name"]: {"value": f["ocr_value"], "confidence": 0.85}
        for f in result
        if f["ocr_value"]
    }


# ── Naive fallback (unchanged logic, kept lean) ───────────────────────

def _map_fields_naive(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """Label-match fallback when AI is unavailable."""
    import re

    fields_spec = field_schema.get("fields", [])
    raw_lines = ocr_result.get("raw_lines", [])

    if not raw_lines or not fields_spec:
        return [{"field_name": f["name"], "ocr_value": "", "confidence": 0.0} for f in fields_spec]

    mapped = []
    for field_spec in fields_spec:
        name = field_spec["name"]
        label = field_spec.get("label", name).lower()
        label_words = set(label.split())
        best_value, best_conf = "", 0.0

        for i, line in enumerate(raw_lines):
            line_text = line["text"].lower().strip()
            line_words = set(line_text.split())
            overlap = label_words & line_words
            if len(overlap) >= max(1, len(label_words) * 0.6):
                # Try same line (after colon)
                if ":" in line["text"]:
                    candidate = line["text"].split(":", 1)[1].strip()
                    if candidate:
                        best_value, best_conf = candidate, line["confidence"]
                        break
                # Try next line
                if i + 1 < len(raw_lines):
                    best_value = raw_lines[i + 1]["text"]
                    best_conf = raw_lines[i + 1]["confidence"]
                    break

        mapped.append({"field_name": name, "ocr_value": best_value, "confidence": best_conf})

    return mapped