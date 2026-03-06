"""OCR extraction service using PaddleOCR with Groq AI-powered field mapping."""

import io
import json
import logging
import re
import time
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Lazy-load PaddleOCR to avoid slow import on every request
_paddle_ocr = None


def _get_paddle_ocr():
    """Lazy initialize PaddleOCR instance."""
    global _paddle_ocr
    if _paddle_ocr is None:
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            use_gpu=False,
            show_log=False,
        )
    return _paddle_ocr


def _pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    """Convert PDF bytes to a list of PIL Images (one per page)."""
    import fitz  # PyMuPDF

    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        # Render at 300 DPI for good OCR quality
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def _is_pdf(data: bytes) -> bool:
    """Check if bytes represent a PDF file."""
    return data[:5] == b"%PDF-"


def _ocr_single_image(img_array: np.ndarray) -> list[dict[str, Any]]:
    """Run PaddleOCR on a single numpy image array and return raw lines."""
    ocr = _get_paddle_ocr()
    result = ocr.ocr(img_array)

    raw_lines = []
    if result and result[0]:
        for line in result[0]:
            bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text = line[1][0]
            confidence = float(line[1][1])
            raw_lines.append({
                "text": text,
                "confidence": confidence,
                "bbox": bbox,
            })
    return raw_lines


def extract_text_from_image(image_bytes: bytes) -> dict[str, Any]:
    """
    Run PaddleOCR on an image or PDF and return structured results.
    PDFs are converted to images first (one per page), then OCR is run on each page.

    Returns:
        {
            "raw_lines": [{"text": str, "confidence": float, "bbox": list}],
            "full_text": str,
            "avg_confidence": float,
            "processing_time": float,
        }
    """
    start_time = time.time()

    raw_lines: list[dict[str, Any]] = []

    if _is_pdf(image_bytes):
        # Convert PDF pages to images and OCR each page
        logger.info("Detected PDF input, converting pages to images...")
        pages = _pdf_to_images(image_bytes)
        logger.info(f"PDF has {len(pages)} page(s)")

        for page_num, page_img in enumerate(pages, 1):
            if page_img.mode != "RGB":
                page_img = page_img.convert("RGB")
            img_array = np.array(page_img)
            page_lines = _ocr_single_image(img_array)
            # Tag lines with page number
            for line in page_lines:
                line["page"] = page_num
            raw_lines.extend(page_lines)
            logger.info(f"Page {page_num}: extracted {len(page_lines)} lines")
    else:
        # Single image
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_array = np.array(image)
        raw_lines = _ocr_single_image(img_array)

    processing_time = time.time() - start_time
    total_confidence = sum(line["confidence"] for line in raw_lines)
    avg_confidence = (total_confidence / len(raw_lines)) if raw_lines else 0.0
    full_text = "\n".join(line["text"] for line in raw_lines)

    logger.info(
        f"OCR extracted {len(raw_lines)} lines, avg confidence: {avg_confidence:.2f}, "
        f"time: {processing_time:.2f}s"
    )

    return {
        "raw_lines": raw_lines,
        "full_text": full_text,
        "avg_confidence": avg_confidence,
        "processing_time": processing_time,
    }


def map_ocr_to_fields(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None = None,
) -> list[dict[str, Any]]:
    """
    Map raw OCR text to structured form fields.

    Strategy:
    1. If consensus is enabled and enough API keys are available, use
       multi-AI consensus extraction (3 generators + 1 adversary checker)
    2. Otherwise, try single AI-powered mapping (Groq)
    3. If AI unavailable/fails, fall back to naive label matching
    """
    fields_spec = field_schema.get("fields", [])

    if not fields_spec:
        return []

    # Try consensus extraction if enabled
    from app.config import get_settings
    settings = get_settings()

    if settings.AI_CONSENSUS_ENABLED:
        api_keys = settings.ai_api_keys
        if len(api_keys) >= 4:
            from app.services.consensus_service import run_consensus_extraction

            logger.info(
                f"Consensus mode: {len(api_keys)} API keys available "
                f"(3 generators + 1 checker)"
            )
            consensus_result = run_consensus_extraction(
                ocr_result=ocr_result,
                field_schema=field_schema,
                image_bytes=image_bytes,
                extract_fn=_map_fields_with_ai_single,
                api_keys=api_keys,
                settings=settings,
            )
            if consensus_result:
                return consensus_result
            logger.warning("Consensus extraction failed, falling back to single AI")
        else:
            logger.info(
                f"Consensus enabled but only {len(api_keys)} API key(s) "
                f"(need 4). Using single AI extraction."
            )

    # Single AI extraction (original behavior)
    ai_result = _map_fields_with_ai(ocr_result, field_schema, image_bytes)
    if ai_result:
        return ai_result

    # Fallback: naive label matching
    logger.info("AI field mapping unavailable, using naive label matching")
    return _map_fields_naive(ocr_result, field_schema)


def _map_fields_with_ai_single(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None = None,
    api_key_override: str | None = None,
    disagreement_context: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """Wrapper for consensus system — delegates to _map_fields_with_ai with key override."""
    return _map_fields_with_ai(
        ocr_result, field_schema, image_bytes,
        api_key_override=api_key_override,
        disagreement_context=disagreement_context,
    )


def _map_fields_with_ai(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None = None,
    api_key_override: str | None = None,
    disagreement_context: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """
    Use Groq AI to intelligently map OCR text to form fields.

    Strategy (separated approach for best accuracy):
    1. Text fields → batched AI calls with OCR text + image
    2. Checkbox/radio fields → dedicated AI vision call (focused prompt)
    3. Checkbox/radio also sent in text batch as backup signal
    4. Merge: prefer dedicated vision result, fill gaps from text batch

    Args:
        api_key_override: If provided, use this API key instead of the default.

    Returns list of field dicts or None if AI is unavailable.
    """
    from app.config import get_settings
    settings = get_settings()

    active_api_key = api_key_override or settings.AI_API_KEY

    if not active_api_key:
        logger.warning("No AI API key available, skipping AI field mapping")
        return None

    fields_spec = field_schema.get("fields", [])
    raw_lines = ocr_result.get("raw_lines", [])

    # Separate checkbox/selection fields from text fields
    CHECKBOX_TYPES = {"checkbox", "checkbox-group", "radio"}
    checkbox_fields = [f for f in fields_spec if f.get("type") in CHECKBOX_TYPES]
    text_fields = [f for f in fields_spec if f.get("type") not in CHECKBOX_TYPES]

    logger.info(
        f"Field split: {len(text_fields)} text fields, "
        f"{len(checkbox_fields)} checkbox/selection fields"
    )

    BATCH_SIZE = 18

    # Prepare image content once (reused across all calls)
    image_content = None
    if image_bytes:
        import base64
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        if image_bytes[:4] == b"\x89PNG":
            mime = "image/png"
        elif image_bytes[:2] == b"\xff\xd8":
            mime = "image/jpeg"
        else:
            mime = "image/jpeg"
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64_image}"},
        }

    # Build OCR text with line numbers
    ocr_lines_formatted = "\n".join(
        f"  Line {i+1}: \"{line['text']}\" (conf: {line['confidence']:.2f})"
        for i, line in enumerate(raw_lines)
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=active_api_key,
            base_url=settings.AI_BASE_URL,
        )

        all_ai_fields: dict[str, Any] = {}

        # Build disagreement hint for re-extraction rounds
        disagreement_hint = ""
        if disagreement_context:
            hint_lines = []
            for fname, ctx in disagreement_context.items():
                votes = ctx.get("previous_votes", [])
                hint_lines.append(
                    f'  - "{fname}": previous extractors voted {votes} '
                    f'(no consensus reached — look VERY carefully at this field)'
                )
            disagreement_hint = (
                "\n⚠️ ATTENTION — DISPUTED FIELDS FROM PREVIOUS ROUND:\n"
                "The following fields had disagreements between independent extractors. "
                "You MUST examine these fields with EXTRA care. Look at the actual "
                "image closely — do not guess.\n"
                + "\n".join(hint_lines) + "\n"
            )
            logger.info(
                f"Injecting disagreement context for {len(disagreement_context)} fields"
            )

        # ── Step 1: Extract TEXT fields via batched OCR text + vision ──
        if text_fields:
            batches = [
                text_fields[i:i + BATCH_SIZE]
                for i in range(0, len(text_fields), BATCH_SIZE)
            ]
            total_batches = len(batches)

            if total_batches > 1:
                logger.info(
                    f"Text fields: splitting {len(text_fields)} "
                    f"into {total_batches} batches"
                )

            for batch_idx, batch in enumerate(batches, 1):
                batch_result = _run_ai_batch(
                    client=client,
                    model=settings.AI_VISION_MODEL,
                    batch_fields=batch,
                    ocr_lines_formatted=ocr_lines_formatted,
                    image_content=image_content,
                    batch_idx=batch_idx,
                    total_batches=total_batches,
                    disagreement_hint=disagreement_hint,
                )
                if batch_result:
                    all_ai_fields.update(batch_result)

        # ── Step 2: Extract CHECKBOX/RADIO fields via dedicated vision ──
        # This uses a focused prompt specifically for checkbox detection,
        # which gives the model's full attention to visual checkbox states.
        if checkbox_fields and image_content:
            vision_result = _detect_checkboxes_with_vision(
                client=client,
                model=settings.AI_VISION_MODEL,
                checkbox_fields=checkbox_fields,
                image_content=image_content,
                ocr_lines_formatted=ocr_lines_formatted,
                disagreement_hint=disagreement_hint,
            )

            if vision_result:
                vision_detected = sum(
                    1 for v in vision_result.values()
                    if v and v not in ("", "no")
                )
                logger.info(
                    f"Vision checkbox detection: {vision_detected}/"
                    f"{len(checkbox_fields)} fields have selections"
                )
                all_ai_fields.update(vision_result)
            else:
                logger.warning("Vision checkbox detection returned no results")

        # ── Step 3: Backup — send checkboxes through text batch too ──
        # If vision missed some, the text batch may catch them via OCR context.
        missing_checkbox_fields = [
            f for f in checkbox_fields
            if not all_ai_fields.get(f["name"])
            or all_ai_fields.get(f["name"]) in ("", "no")
        ]

        if missing_checkbox_fields:
            logger.info(
                f"Vision missed {len(missing_checkbox_fields)} checkbox fields, "
                f"trying text+vision batch as backup"
            )
            backup_result = _run_ai_batch(
                client=client,
                model=settings.AI_VISION_MODEL,
                batch_fields=missing_checkbox_fields,
                ocr_lines_formatted=ocr_lines_formatted,
                image_content=image_content,
                batch_idx=1,
                total_batches=1,
            )
            if backup_result:
                # Normalize and merge only missing fields
                for field in missing_checkbox_fields:
                    name = field["name"]
                    ftype = field.get("type", "checkbox")
                    raw_val = backup_result.get(name, "")
                    if isinstance(raw_val, dict):
                        raw_val = str(raw_val.get("value", ""))
                    else:
                        raw_val = str(raw_val) if raw_val is not None else ""
                    raw_lower = raw_val.lower().strip()

                    if ftype == "checkbox":
                        normalized = "true" if raw_lower in (
                            "yes", "true", "checked", "1", "x",
                            "✓", "✔", "on", "selected", "filled",
                        ) else ""
                    elif ftype == "radio":
                        options = field.get("options", [])
                        normalized = _match_radio_option(raw_lower, options)
                    else:
                        normalized = raw_val

                    # Only fill if current value is empty
                    current = all_ai_fields.get(name, "")
                    if not current and normalized:
                        all_ai_fields[name] = normalized
                        logger.info(
                            f"Backup filled '{name}' = '{normalized}'"
                        )

        # ── Step 4: Targeted re-check for activity checkboxes (PSIC section) ──
        # The PSIC 2x3 grid is particularly tricky. Always run a focused
        # re-check with a cropped image for better accuracy.
        activity_fields = [
            f for f in checkbox_fields
            if f["name"].startswith("activity_")
        ]

        if activity_fields and image_bytes and image_content:
            # Crop PSIC region for focused detection
            psic_image_bytes = _crop_psic_region(image_bytes, raw_lines)
            psic_image_content = image_content  # fallback to full image
            is_cropped = False

            if psic_image_bytes:
                import base64 as b64_mod
                b64_psic = b64_mod.b64encode(psic_image_bytes).decode("utf-8")
                psic_image_content = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_psic}"},
                }
                is_cropped = True
                logger.info("PSIC re-check: using cropped region")
            else:
                logger.info("PSIC re-check: crop failed, using full image")

            recheck_result = _recheck_activity_checkboxes(
                client=client,
                model=settings.AI_VISION_MODEL,
                activity_fields=activity_fields,
                image_content=psic_image_content,
                is_cropped=is_cropped,
            )
            if recheck_result:
                # Re-check is AUTHORITATIVE for PSIC fields — override all
                for name, val in recheck_result.items():
                    old_val = all_ai_fields.get(name, "")
                    all_ai_fields[name] = val
                    if val and not old_val:
                        logger.info(
                            f"PSIC re-check filled '{name}' = '{val}'"
                        )
                    elif not val and old_val:
                        logger.info(
                            f"PSIC re-check cleared '{name}' (was '{old_val}')"
                        )

        # Log final checkbox state
        logger.info(
            "Final checkbox/radio values: "
            + str({
                f["name"]: all_ai_fields.get(f["name"], "")
                for f in checkbox_fields
            })
        )

        if not all_ai_fields:
            logger.warning("AI field mapping returned no results")
            return None

        # ── Build final result ──
        mapped_fields = []
        for field_spec in fields_spec:
            field_name = field_spec["name"]
            if field_name in all_ai_fields:
                entry = all_ai_fields[field_name]
                if isinstance(entry, dict):
                    value = str(entry.get("value", ""))
                    confidence = float(entry.get("confidence", 0.9))
                else:
                    value = str(entry) if entry is not None else ""
                    confidence = 0.92 if value else 0.0
            else:
                value = ""
                confidence = 0.0

            mapped_fields.append({
                "field_name": field_name,
                "ocr_value": value,
                "confidence": min(confidence, 1.0),
            })

        filled = sum(1 for f in mapped_fields if f["ocr_value"])
        logger.info(f"AI field mapping total: {filled}/{len(mapped_fields)} fields extracted")

        # ── Post-OCR correction — fix common OCR errors ──
        from app.services.post_correction import apply_post_corrections
        mapped_fields = apply_post_corrections(mapped_fields)

        return mapped_fields

    except Exception as e:
        logger.error(f"AI field mapping failed: {e}")
        return None


# ── Radio option matching helper ──────────────────────────────────────


def _match_radio_option(raw_value: str, options: list[str]) -> str:
    """
    Match a raw AI-extracted value to one of the radio field options.

    The AI may return human-readable text like "Single", "Female", "NEW",
    "City/Municipality", etc. We need to match this to the snake_case option
    values like "single", "female", "new", "city_municipality".

    Returns the matched option value, or empty string if no match.
    """
    if not raw_value or not options:
        return ""

    raw_lower = raw_value.lower().strip()

    # Pass 1: Exact case-insensitive match
    for opt in options:
        if raw_lower == opt.lower():
            return opt

    # Pass 2: Match with underscores replaced by spaces
    # e.g., "city/municipality" matches "city_municipality"
    raw_normalized = raw_lower.replace("/", "_").replace("-", "_").replace(" ", "_")
    for opt in options:
        opt_lower = opt.lower()
        if raw_normalized == opt_lower:
            return opt
        # Also try without underscores
        if raw_lower.replace(" ", "").replace("/", "").replace("-", "") == opt_lower.replace("_", ""):
            return opt

    # Pass 3: Word containment — check if raw text contains the option word
    for opt in options:
        opt_words = opt.lower().replace("_", " ").split()
        raw_words = raw_lower.replace("_", " ").replace("/", " ").split()
        # If all option words appear in the raw text
        if all(w in raw_words for w in opt_words):
            return opt
        # If raw text appears as substring of expanded option name
        opt_expanded = opt.lower().replace("_", " ")
        if raw_lower in opt_expanded or opt_expanded in raw_lower:
            return opt

    # Pass 4: Partial match — first word match
    for opt in options:
        opt_first = opt.lower().split("_")[0]
        if raw_lower.startswith(opt_first) or opt_first.startswith(raw_lower):
            return opt

    logger.debug(f"Radio match failed: '{raw_value}' not in {options}")
    return ""


# ── Pixel-based checkbox detection ──────────────────────────────────────

def _find_ocr_line_for_label(
    raw_lines: list[dict[str, Any]], label: str
) -> dict[str, Any] | None:
    """Find the OCR line whose text best matches the given label."""
    label_lower = label.lower().strip()
    label_words = set(label_lower.split())

    best_match = None
    best_score = 0.0

    for line in raw_lines:
        text = line.get("text", "").lower().strip()
        if not text:
            continue

        # Exact containment
        if label_lower in text or text in label_lower:
            score = len(label_lower) / max(len(text), 1)
            if score > best_score:
                best_score = score
                best_match = line
                if score > 0.8:
                    break
            continue

        # Word overlap score
        text_words = set(text.split())
        overlap = label_words & text_words
        if overlap:
            score = len(overlap) / max(len(label_words), 1) * 0.8
            if score > best_score:
                best_score = score
                best_match = line

    return best_match


def _detect_checkboxes_pixel_based(
    image_bytes: bytes,
    raw_lines: list[dict[str, Any]],
    checkbox_fields: list[dict[str, Any]],
) -> dict[str, str] | None:
    """
    Detect checkbox/radio states using pixel analysis of the actual image.

    Strategy:
    1. Convert image to grayscale + binary (inverted: dark pixels become white)
    2. For each checkbox field, find its label text in OCR results
    3. Locate the checkbox box to the LEFT of the label text
    4. Measure the fill ratio (percentage of dark pixels)
    5. Checked = high fill ratio, unchecked = low fill ratio

    For radio fields: compare fill ratios across all options and pick the highest.

    Returns dict of {field_name: "true"/"" for checkboxes, option_value for radio}.
    """
    import cv2

    try:
        # Decode image
        img_array = np.frombuffer(image_bytes, np.uint8)
        img_color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img_color is None:
            logger.warning("Pixel checkbox detection: failed to decode image")
            return None

        gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
        img_h, img_w = gray.shape

        # Binary threshold (inverted: dark pixels → 255, light → 0)
        _, binary_inv = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY_INV)

        results: dict[str, str] = {}
        fill_ratios: dict[str, float] = {}

        # Group radio fields to compare later
        radio_groups: dict[str, list[dict]] = {}

        for field in checkbox_fields:
            name = field["name"]
            label = field.get("label", name)
            ftype = field.get("type", "checkbox")
            options = field.get("options", [])

            # Find OCR line for this label
            match_line = _find_ocr_line_for_label(raw_lines, label)
            if match_line is None:
                logger.debug(f"Pixel checkbox: no OCR match for '{label}'")
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            bbox = match_line.get("bbox")
            if not bbox or len(bbox) < 4:
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            # bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            min_x = int(min(p[0] for p in bbox))
            min_y = int(min(p[1] for p in bbox))
            max_y = int(max(p[1] for p in bbox))
            text_height = max(max_y - min_y, 10)

            # Checkbox box is to the LEFT of the label text
            box_size = int(text_height * 1.0)
            gap = int(text_height * 0.3)
            box_right = max(min_x - gap, 0)
            box_left = max(box_right - box_size, 0)
            box_top = max(min_y, 0)
            box_bottom = min(box_top + box_size, img_h)

            # Ensure valid region
            if box_left >= box_right or box_top >= box_bottom:
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            # Crop checkbox region
            region = binary_inv[box_top:box_bottom, box_left:box_right]
            if region.size == 0:
                results[name] = ""
                fill_ratios[name] = 0.0
                continue

            # Calculate fill ratio
            fill_ratio = float(np.count_nonzero(region)) / region.size
            fill_ratios[name] = fill_ratio

            logger.debug(
                f"Pixel checkbox '{name}' ({label}): "
                f"region=[{box_left}:{box_right}, {box_top}:{box_bottom}], "
                f"fill_ratio={fill_ratio:.3f}"
            )

            if ftype == "checkbox":
                # Threshold: > 0.35 means checked (solid dark square ≈ 0.6-0.9)
                results[name] = "true" if fill_ratio > 0.35 else ""
            elif ftype == "radio":
                # Store for group comparison
                group_key = name.rsplit("_", 1)[0] if "_" in name else name
                # Actually, radio fields have ONE name with multiple options
                # For now, store the fill ratio and handle in post-processing
                results[name] = ""  # placeholder
                # Build group: find which option label matched
                if name not in radio_groups:
                    radio_groups[name] = []
                radio_groups[name].append({
                    "name": name,
                    "options": options,
                    "fill_ratio": fill_ratio,
                })

        # Handle radio fields — these need special treatment
        # For radio type, each field has multiple options with their own labels
        # We need to find which option's checkbox is filled
        for field in checkbox_fields:
            if field.get("type") != "radio":
                continue

            name = field["name"]
            options = field.get("options", [])
            if not options:
                continue

            option_fills: list[tuple[str, float]] = []
            for opt in options:
                opt_line = _find_ocr_line_for_label(raw_lines, opt.replace("_", " "))
                if opt_line is None:
                    # Try with the raw option value
                    opt_line = _find_ocr_line_for_label(raw_lines, opt)
                if opt_line is None:
                    option_fills.append((opt, 0.0))
                    continue

                bbox = opt_line.get("bbox")
                if not bbox or len(bbox) < 4:
                    option_fills.append((opt, 0.0))
                    continue

                min_x = int(min(p[0] for p in bbox))
                min_y = int(min(p[1] for p in bbox))
                max_y = int(max(p[1] for p in bbox))
                text_height = max(max_y - min_y, 10)

                box_size = int(text_height * 1.0)
                gap = int(text_height * 0.3)
                box_right = max(min_x - gap, 0)
                box_left = max(box_right - box_size, 0)
                box_top = max(min_y, 0)
                box_bottom = min(box_top + box_size, img_h)

                if box_left >= box_right or box_top >= box_bottom:
                    option_fills.append((opt, 0.0))
                    continue

                region = binary_inv[box_top:box_bottom, box_left:box_right]
                ratio = float(np.count_nonzero(region)) / max(region.size, 1)
                option_fills.append((opt, ratio))

                logger.debug(
                    f"Pixel radio '{name}' option '{opt}': "
                    f"region=[{box_left}:{box_right}, {box_top}:{box_bottom}], "
                    f"fill_ratio={ratio:.3f}"
                )

            # Pick the option with the highest fill ratio (if above threshold)
            if option_fills:
                best_opt, best_fill = max(option_fills, key=lambda x: x[1])
                if best_fill > 0.25:
                    results[name] = best_opt
                    logger.debug(
                        f"Pixel radio '{name}': selected '{best_opt}' "
                        f"(fill={best_fill:.3f})"
                    )
                else:
                    results[name] = ""

        # Log summary
        checked = sum(1 for v in results.values() if v and v not in ("", "no"))
        logger.info(f"Pixel checkbox detection: {checked}/{len(checkbox_fields)} fields detected")
        logger.info(f"Pixel checkbox results: {results}")
        logger.info(f"Pixel fill ratios: {fill_ratios}")

        return results

    except Exception as e:
        logger.error(f"Pixel-based checkbox detection failed: {e}", exc_info=True)
        return None


def _crop_psic_region(
    image_bytes: bytes,
    raw_lines: list[dict[str, Any]],
) -> bytes | None:
    """
    Crop the PSIC activity checkbox region from the form image using
    OCR bounding boxes to locate the section.

    Returns cropped image as PNG bytes, or None if region not found.
    """
    psic_keywords = [
        "manufacturer", "producer", "service", "retailer",
        "wholesaler", "importer", "exporter",
    ]

    psic_bboxes = []
    for line in raw_lines:
        text_lower = line.get("text", "").lower()
        if any(kw in text_lower for kw in psic_keywords):
            bbox = line.get("bbox")
            if bbox:
                psic_bboxes.append(bbox)

    if len(psic_bboxes) < 2:
        logger.debug(
            f"PSIC crop: only found {len(psic_bboxes)} matching lines, need at least 2"
        )
        return None

    # Compute bounding rectangle from all detected PSIC text positions
    all_points = [pt for bbox in psic_bboxes for pt in bbox]
    min_x = min(pt[0] for pt in all_points)
    min_y = min(pt[1] for pt in all_points)
    max_x = max(pt[0] for pt in all_points)
    max_y = max(pt[1] for pt in all_points)

    image = Image.open(io.BytesIO(image_bytes))
    if image.mode != "RGB":
        image = image.convert("RGB")

    region_width = max_x - min_x
    region_height = max_y - min_y

    # Generous padding: checkboxes are to the LEFT of labels, and we want
    # the full grid visible including surrounding context
    pad_left = int(region_width * 0.4)   # Extra left for checkbox squares
    pad_right = int(region_width * 0.2)
    pad_top = int(region_height * 0.5)   # Include "Main Business Activity" header
    pad_bottom = int(region_height * 0.5)

    crop_box = (
        max(0, int(min_x) - pad_left),
        max(0, int(min_y) - pad_top),
        min(image.width, int(max_x) + pad_right),
        min(image.height, int(max_y) + pad_bottom),
    )

    cropped = image.crop(crop_box)
    logger.info(
        f"PSIC crop: {cropped.width}×{cropped.height}px "
        f"(from {len(psic_bboxes)} text matches)"
    )

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def _recheck_activity_checkboxes(
    client: Any,
    model: str,
    activity_fields: list[dict[str, Any]],
    image_content: dict[str, Any],
    is_cropped: bool = False,
) -> dict[str, str] | None:
    """
    Focused re-check of PSIC activity checkboxes (Section G, Box 24).

    Uses a very specific prompt that describes the exact grid layout
    and asks the model to examine each box one at a time.

    Args:
        is_cropped: If True, the image_content is a cropped PSIC region,
            so the prompt is adjusted to reference the visible area.
    """
    field_names = [f["name"] for f in activity_fields]
    labels = [f.get("label", f["name"]) for f in activity_fields]

    # Need all 6 activity fields for the hardcoded grid prompt
    if len(field_names) < 6:
        logger.debug(
            f"PSIC re-check skipped: only {len(field_names)}/6 activity fields present"
        )
        return None

    if is_cropped:
        context_intro = (
            "This image shows ONLY the 'Main Business Activity' checkbox section "
            "from a Philippine DTI Business Name Registration form.\n\n"
            "You can see a 2-row × 3-column grid of small square checkboxes, "
            "each next to a label.\n\n"
        )
    else:
        context_intro = (
            "Look at Section G of this Philippine DTI Business Name Registration form.\n\n"
            "Find the area labeled '24. Main Business Activity'. "
            "It has a 2-row × 3-column grid of small square checkboxes, each next to a label.\n\n"
        )

    prompt = (
        f"{context_intro}"
        "STEP 1 — DESCRIBE EACH POSITION:\n"
        "Go through each of the 6 positions below. For each one, describe what the "
        "small square checkbox looks like: is it filled/dark/solid (■) or empty/white/clear (□)?\n\n"
        "The 6 positions are:\n"
        "  Position 1 (Top row, LEFT):   The checkbox BEFORE the text 'Manufacturer/Producer'\n"
        "  Position 2 (Top row, MIDDLE): The checkbox BEFORE the text 'Service'\n"
        "  Position 3 (Top row, RIGHT):  The checkbox BEFORE the text 'Retailer'\n"
        "  Position 4 (Bottom row, LEFT):   The checkbox BEFORE the text 'Wholesaler'\n"
        "  Position 5 (Bottom row, MIDDLE): The checkbox BEFORE the text 'Importer'\n"
        "  Position 6 (Bottom row, RIGHT):  The checkbox BEFORE the text 'Exporter'\n\n"
        "IMPORTANT: Each checkbox is the small square □ that appears IMMEDIATELY BEFORE "
        "(to the LEFT of) each label text. Do NOT confuse checkboxes between labels.\n\n"
        "STEP 2 — RETURN RESULTS:\n"
        "Based on your observations, return a JSON object.\n"
        "A filled/dark/solid square = \"yes\", an empty/white/clear square = \"no\".\n\n"
        "Return ONLY this JSON (include your reasoning for each as shown):\n"
        "{\n"
        '  "reasoning": {\n'
        '    "position_1_manufacturer": "describe what the checkbox looks like",\n'
        '    "position_2_service": "describe what the checkbox looks like",\n'
        '    "position_3_retailer": "describe what the checkbox looks like",\n'
        '    "position_4_wholesaler": "describe what the checkbox looks like",\n'
        '    "position_5_importer": "describe what the checkbox looks like",\n'
        '    "position_6_exporter": "describe what the checkbox looks like"\n'
        "  },\n"
        f'  "{field_names[0]}": "yes or no",\n'
        f'  "{field_names[1]}": "yes or no",\n'
        f'  "{field_names[2]}": "yes or no",\n'
        f'  "{field_names[3]}": "yes or no",\n'
        f'  "{field_names[4]}": "yes or no",\n'
        f'  "{field_names[5]}": "yes or no"\n'
        "}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content,
                ],
            }],
            max_tokens=1500,
            temperature=0.0,
        )

        content = response.choices[0].message.content or "{}"
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())
        logger.info(f"PSIC re-check raw response: {result}")

        # Normalize to "true"/""
        normalized: dict[str, str] = {}
        for f in activity_fields:
            name = f["name"]
            val = str(result.get(name, "")).lower().strip()
            normalized[name] = "true" if val in (
                "yes", "true", "checked", "1", "x", "✓", "✔",
            ) else ""

        checked = sum(1 for v in normalized.values() if v)
        logger.info(f"PSIC re-check: {checked}/{len(activity_fields)} activities checked")
        logger.info(f"PSIC re-check normalized: {normalized}")
        return normalized

    except Exception as e:
        logger.error(f"PSIC re-check failed: {e}")
        return None


def _detect_checkboxes_with_vision(
    client: Any,
    model: str,
    checkbox_fields: list[dict[str, Any]],
    image_content: dict[str, Any],
    ocr_lines_formatted: str = "",
    disagreement_hint: str = "",
) -> dict[str, Any] | None:
    """
    Use AI Vision to detect which checkboxes/radio buttons are checked
    in the form image. This is a focused, dedicated call that gives the
    model's full attention to visual checkbox states.

    Returns dict of {field_name: "true"/"" for checkboxes, option value for radio}.
    """
    # Build a concise field description
    fields_desc_parts = []
    for f in checkbox_fields:
        ftype = f.get("type", "checkbox")
        label = f.get("label", f["name"])
        name = f["name"]
        hint = f.get("hint", "")
        section = f.get("section", "")
        location = ""
        if hint:
            location = f" (Location: {hint})"
        elif section:
            location = f" (Section: {section})"

        if ftype == "checkbox":
            fields_desc_parts.append(
                f'  "{name}": Single checkbox labeled "{label}".{location}'
            )
        elif ftype == "checkbox-group":
            options = f.get("options", [])
            opt_str = ", ".join(f'"{o}"' for o in options)
            fields_desc_parts.append(
                f'  "{name}": Checkbox group "{label}" with options: {opt_str}.{location}'
            )
        elif ftype == "radio":
            options = f.get("options", [])
            opt_str = ", ".join(f'"{o}"' for o in options)
            fields_desc_parts.append(
                f'  "{name}": Radio select "{label}" — options: {opt_str}.{location}'
            )

    fields_desc = "\n".join(fields_desc_parts)

    # Include OCR text hints for radio fields to help disambiguate
    ocr_hint = ""
    if ocr_lines_formatted:
        ocr_hint = (
            "\nOCR TEXT CONTEXT (use as secondary signal to verify your visual reading):\n"
            f"{ocr_lines_formatted}\n"
        )

    prompt = (
        "You are an expert at reading scanned Philippine government forms.\n\n"
        "TASK: Examine EVERY checkbox and radio button in this form image INDIVIDUALLY. "
        "For each one, look directly at the small square box and determine if it contains "
        "any dark mark (checked) or is empty (unchecked).\n\n"
        "VISUAL GUIDE:\n"
        "- CHECKED: filled/darkened square ■, checkmark ✓, X mark, or ANY dark mark inside the box\n"
        "- UNCHECKED: empty/white/light square □ with nothing inside\n\n"
        "CRITICAL RULES:\n"
        "- Do NOT guess or assume — look at EACH box individually\n"
        "- Do NOT default to the first option if unsure — examine all options in a group\n"
        "- For radio groups: EXACTLY ONE option should be checked. Compare ALL options visually\n"
        "- For the PSIC activity section: MULTIPLE checkboxes can be checked simultaneously\n"
        "- Cross-reference with the OCR text below if available — OCR may have captured "
        "handwritten text near checked boxes\n\n"
        "DETAILED FORM LAYOUT:\n"
        "- Section A (top): Registration Type — two boxes side by side: □ NEW  □ RENEWAL\n"
        "- Section B: TIN Status — two boxes: □ With TIN  □ Without TIN\n"
        "- Section C (Box 8): Civil Status — FOUR boxes in a row, left to right:\n"
        "  □ Legally Separated  □ Single  □ Married  □ Widowed\n"
        "  Look carefully at EACH of these 4 boxes — only ONE should have a mark\n"
        "- Section C (Box 9): Gender — □ Male  □ Female\n"
        "- Section C (Box 10): Refugee — □ Yes  □ No  |  Stateless — □ Yes  □ No\n"
        "- Section D (Box 12): Territorial Scope — 4 options:\n"
        "  □ Barangay  □ City/Municipality  □ Regional  □ National\n"
        "- Section G (Box 24): PSIC Business Activity — 6 boxes in a 2×3 GRID:\n"
        "  ┌──────────────────────────┬──────────────┬──────────────┐\n"
        "  │ □ Manufacturer/Producer  │ □ Service    │ □ Retailer   │  ← TOP ROW\n"
        "  ├──────────────────────────┼──────────────┼──────────────┤\n"
        "  │ □ Wholesaler             │ □ Importer   │ □ Exporter   │  ← BOTTOM ROW\n"
        "  └──────────────────────────┴──────────────┴──────────────┘\n"
        "  CRITICAL: The LEFTMOST box in the top row is Manufacturer/Producer, NOT Service.\n"
        "  Service is the MIDDLE box in the top row. Do NOT confuse their positions.\n"
        "  Multiple activities CAN be checked! Examine each of the 6 boxes individually.\n"
        "  A filled/darkened/solid square ■ = checked. Empty/clear square □ = unchecked.\n"
        "- Section H: □ Same as Business Details\n"
        "- Section I: Partner Agencies — □ PhilHealth  □ SSS  □ Pag-IBIG\n"
        f"{ocr_hint}\n"
        f"{disagreement_hint}"
        f"FIELDS TO DETECT ({len(checkbox_fields)} total):\n"
        f"{fields_desc}\n\n"
        "RESPONSE FORMAT:\n"
        "- For single checkboxes: \"yes\" if checked, \"no\" if unchecked\n"
        "- For radio buttons: return EXACTLY one option value from the list that is checked\n"
        "- For checkbox groups: comma-separated checked option values\n\n"
        "Return ONLY a JSON object. No explanation, no markdown:\n"
        "{\n"
        '  "field_name": "yes" or "no" or "option_value",\n'
        "  ...\n"
        "}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content,
                ],
            }],
            max_tokens=2000,
            temperature=0.0,
        )

        content = response.choices[0].message.content or "{}"

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            repaired = content
            last_comma = repaired.rfind(",")
            if last_comma > 0:
                repaired = repaired[:last_comma]
            if not repaired.rstrip().endswith("}"):
                repaired = repaired.rstrip() + "\n}"
            try:
                result = json.loads(repaired)
            except json.JSONDecodeError as e2:
                logger.error(f"Checkbox detection JSON parse failed: {e2}")
                return None

        # Log raw AI response for debugging
        logger.info(f"Checkbox AI raw response: {result}")

        # Normalize values
        normalized: dict[str, str] = {}
        for f in checkbox_fields:
            name = f["name"]
            if name in result:
                val = str(result[name]).strip()
                val_lower = val.lower()
                ftype = f.get("type", "checkbox")

                if ftype == "checkbox":
                    # Normalize → "true" for component compatibility
                    normalized[name] = "true" if val_lower in (
                        "yes", "true", "checked", "1", "x", "✓", "✔",
                        "on", "selected", "filled",
                    ) else ""
                elif ftype == "radio":
                    options = f.get("options", [])
                    matched = _match_radio_option(val_lower, options)
                    normalized[name] = matched
                else:
                    # checkbox-group — keep as-is
                    normalized[name] = val
            else:
                normalized[name] = ""

        checked_count = sum(1 for v in normalized.values() if v and v not in ("", "no"))
        logger.info(f"Checkbox detection: {checked_count}/{len(checkbox_fields)} fields have selections")
        logger.info(f"Checkbox normalized values: {normalized}")
        return normalized

    except Exception as e:
        logger.error(f"Checkbox detection failed: {e}")
        return None


def _run_ai_batch(
    client: Any,
    model: str,
    batch_fields: list[dict[str, Any]],
    ocr_lines_formatted: str,
    image_content: dict[str, Any] | None,
    batch_idx: int,
    total_batches: int,
    disagreement_hint: str = "",
) -> dict[str, Any] | None:
    """
    Run a single AI extraction batch for a subset of fields.
    Handles text, checkbox, and radio field types.
    Returns dict of {field_name: value} or None on failure.
    """
    # Build detailed field descriptions including options for checkbox/radio
    field_desc_lines = []
    for f in batch_fields:
        ftype = f.get("type", "text")
        label = f.get("label", f["name"])
        name = f["name"]
        options = f.get("options", [])

        if ftype == "checkbox":
            field_desc_lines.append(
                f'  - "{name}": Checkbox "{label}". '
                f'Return "yes" if checked/filled/marked, "no" if unchecked.'
            )
        elif ftype == "radio":
            opt_str = ", ".join(f'"{o}"' for o in options)
            field_desc_lines.append(
                f'  - "{name}": Radio "{label}" with options: {opt_str}. '
                f'Return EXACTLY one option value.'
            )
        elif ftype == "checkbox-group":
            opt_str = ", ".join(f'"{o}"' for o in options)
            field_desc_lines.append(
                f'  - "{name}": Checkbox group "{label}" — options: {opt_str}. '
                f'Return comma-separated checked values.'
            )
        else:
            field_desc_lines.append(
                f'  - "{name}": {label} (type: {ftype})'
            )

    fields_desc = "\n".join(field_desc_lines)

    prompt_text = (
        "You are an expert OCR data extraction specialist for Philippine government forms.\n\n"
        "I have a scanned form where OCR has extracted the following text lines:\n\n"
        f"{ocr_lines_formatted}\n\n"
        f"{disagreement_hint}"
        f"Extract ONLY these {len(batch_fields)} fields from the text and image:\n"
        f"{fields_desc}\n\n"
        "RULES:\n"
        "- Match field labels to their corresponding values in the OCR text\n"
        "- Values may appear on the same line as labels (after colon) or on adjacent lines\n"
        "- If a value spans multiple lines, combine them\n"
        "- If a field is not found, use empty string\n"
        "- For checkbox fields, return \"yes\" if checked or \"no\" if unchecked\n"
        "- For radio fields, return EXACTLY one of the listed option values\n"
        "- Return ONLY valid JSON, no markdown, no other text\n\n"
        "Return a JSON object mapping field names to extracted values:\n"
        "{\n"
        '  "field_name": "extracted value",\n'
        "  ...\n"
        "}\n"
        "Use EXACTLY the field names listed above. Every field must be present."
    )

    try:
        messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        if image_content:
            messages_content.append(image_content)

        # Scale max_tokens to batch size (~100 tokens per field is generous)
        max_tokens = max(1500, len(batch_fields) * 120)

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": messages_content}],
            max_tokens=max_tokens,
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"

        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        # Parse JSON with repair fallback
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Batch {batch_idx}/{total_batches}: JSON malformed, attempting repair")
            repaired = content
            last_comma = repaired.rfind(",")
            if last_comma > 0:
                repaired = repaired[:last_comma]
            if not repaired.rstrip().endswith("}"):
                repaired = repaired.rstrip() + "\n}"
            try:
                result = json.loads(repaired)
                logger.info(f"Batch {batch_idx}/{total_batches}: JSON repair recovered {len(result)} fields")
            except json.JSONDecodeError as e2:
                logger.error(f"Batch {batch_idx}/{total_batches}: JSON repair failed: {e2}")
                return None

        batch_label = f"Batch {batch_idx}/{total_batches}" if total_batches > 1 else "AI"
        filled = sum(1 for v in result.values() if v)
        logger.info(f"{batch_label}: extracted {filled}/{len(batch_fields)} fields")
        return result

    except Exception as e:
        logger.error(f"Batch {batch_idx}/{total_batches} failed: {e}")
        return None


def _map_fields_naive(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Naive label-based field mapping fallback.
    Searches for lines matching field labels and extracts adjacent values.
    """
    fields_spec = field_schema.get("fields", [])
    raw_lines = ocr_result.get("raw_lines", [])

    if not raw_lines or not fields_spec:
        return [
            {"field_name": f["name"], "ocr_value": "", "confidence": 0.0}
            for f in fields_spec
        ]

    mapped_fields = []

    for field_spec in fields_spec:
        field_name = field_spec["name"]
        field_label = field_spec.get("label", field_name).lower()

        best_value = ""
        best_confidence = 0.0

        for i, line in enumerate(raw_lines):
            line_text = line["text"].lower().strip()

            if _fuzzy_label_match(field_label, line_text):
                value = _extract_value_from_line(line["text"], field_spec.get("label", field_name))
                if value:
                    best_value = value
                    best_confidence = line["confidence"]
                elif i + 1 < len(raw_lines):
                    best_value = raw_lines[i + 1]["text"]
                    best_confidence = raw_lines[i + 1]["confidence"]
                break

        mapped_fields.append({
            "field_name": field_name,
            "ocr_value": best_value,
            "confidence": best_confidence,
        })

    return mapped_fields


def _fuzzy_label_match(label: str, line_text: str) -> bool:
    """Check if a line contains a field label (fuzzy match)."""
    label_words = label.lower().split()
    matches = sum(1 for word in label_words if word in line_text)
    threshold = max(1, len(label_words) * 0.6)
    return matches >= threshold


def _extract_value_from_line(line: str, label: str) -> str:
    """Try to extract value from a line like 'Label: Value'."""
    if ":" in line:
        parts = line.split(":", 1)
        return parts[1].strip()

    pattern = re.escape(label) + r"[\s_\-:.]+"
    cleaned = re.sub(pattern, "", line, flags=re.IGNORECASE).strip()
    if cleaned and cleaned != line.strip():
        return cleaned
    return ""


def enhance_with_vision(
    image_bytes: bytes,
    field_schema: dict[str, Any],
    low_confidence_fields: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Use Groq Vision API to re-extract specific low-confidence fields.
    This is a targeted enhancement — called only for fields that the
    primary mapping couldn't extract confidently.

    Returns dict of {field_name: {"value": str, "confidence": float}}
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.AI_API_KEY:
        logger.warning("AI_API_KEY not set, skipping vision enhancement")
        return {}

    try:
        import base64
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
        )

        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        fields_to_extract = [
            f for f in field_schema.get("fields", [])
            if f["name"] in low_confidence_fields
        ]
        fields_desc = "\n".join(
            f"- {f['label']} (field_name: {f['name']})" for f in fields_to_extract
        )

        response = client.chat.completions.create(
            model=settings.AI_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are an OCR specialist for Philippine government forms. "
                                "Extract ONLY the following field values from the form image. "
                                "Return a JSON object with field_name as key and extracted value as string.\n\n"
                                f"Fields to extract:\n{fields_desc}\n\n"
                                'Return format: {{"field_name": "extracted_value", ...}}\n'
                                "If a field is unreadable, use empty string. Return ONLY valid JSON."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        enhanced = json.loads(content.strip())

        return {
            k: {"value": str(v), "confidence": 0.85}
            for k, v in enhanced.items()
            if k in low_confidence_fields
        }

    except Exception as e:
        logger.error(f"Vision enhancement failed: {e}")
        return {}
