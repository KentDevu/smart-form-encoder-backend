"""
Multi-AI Consensus Validation Service.

Architecture: 3 Generators + 1 Adversary Checker

Phase 1 (Generator): 3 independent AI instances extract the same fields in
    parallel using different API keys (same model). Each sees the same image +
    OCR text but operates with no knowledge of other validators' answers.

Phase 2 (Consensus): Compare all generator outputs per-field.
    - Unanimous agreement → high confidence (0.99)
    - Majority agreement → use majority value, confidence = agreement ratio
    - No majority → flag for adversary review

Phase 3 (Adversary): A 4th AI instance reviews the consensus results.
    It receives the original image + the merged extraction + any disagreements
    and acts as a discriminator — pinpointing likely errors and suggesting
    corrections.

Phase 4 (Refinement): If agreement < target threshold, re-extract only the
    disagreed/flagged fields with focused prompts. Iterate up to max_rounds.
"""

import json
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)


def run_consensus_extraction(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None,
    extract_fn: Any,
    api_keys: list[str],
    settings: Any,
) -> list[dict[str, Any]] | None:
    """
    Run the full multi-AI consensus extraction pipeline.

    Args:
        ocr_result: PaddleOCR raw results
        field_schema: Template field schema
        image_bytes: Original form image bytes
        extract_fn: The single-pass extraction function (from ocr_service)
        api_keys: List of AI API keys (first 3 = generators, 4th = checker)
        settings: App settings

    Returns:
        List of field dicts with consensus-boosted confidence, or None on failure.
    """
    if len(api_keys) < 4:
        logger.warning(
            f"Consensus requires 4 API keys (3 generators + 1 checker), "
            f"got {len(api_keys)}. Falling back to single extraction."
        )
        return None

    generator_keys = api_keys[:3]
    checker_key = api_keys[3]
    max_rounds = settings.AI_CONSENSUS_MAX_ROUNDS
    target_agreement = settings.AI_CONSENSUS_TARGET_AGREEMENT

    fields_spec = field_schema.get("fields", [])
    all_field_names = [f["name"] for f in fields_spec]

    # Track fields that still need consensus
    fields_to_extract = all_field_names.copy()
    final_results: dict[str, dict[str, Any]] = {}
    # Track disagreement history for context in later rounds
    disagreement_history: dict[str, dict[str, Any]] = {}

    for round_num in range(1, max_rounds + 1):
        logger.info(
            f"Consensus round {round_num}/{max_rounds}: "
            f"{len(fields_to_extract)} fields to process"
        )

        # ── Phase 1: Generator extractions (parallel) ──
        # In rounds 2+, pass disagreement context so generators look more carefully
        round_context = disagreement_history if round_num > 1 else None
        round_schema = _build_subset_schema(field_schema, fields_to_extract)
        generator_outputs = _run_generators_parallel(
            ocr_result=ocr_result,
            field_schema=round_schema,
            image_bytes=image_bytes,
            extract_fn=extract_fn,
            api_keys=generator_keys,
            settings=settings,
            disagreement_context=round_context,
        )

        if not generator_outputs:
            logger.error(f"Round {round_num}: all generators failed")
            break

        # ── Phase 2: Build consensus ──
        consensus, disagreements = _build_consensus(
            generator_outputs, fields_to_extract
        )

        # Merge into final results
        for field_name, field_data in consensus.items():
            final_results[field_name] = field_data

        agreed_count = sum(
            1 for f in consensus.values() if f["agreement"] >= target_agreement
        )
        total = len(fields_to_extract)
        agreement_ratio = agreed_count / total if total else 1.0

        logger.info(
            f"Round {round_num} consensus: {agreed_count}/{total} fields "
            f"meet {target_agreement:.0%} threshold "
            f"(overall: {agreement_ratio:.1%})"
        )

        # Check if we've hit the target
        if agreement_ratio >= target_agreement:
            logger.info(
                f"Target agreement {target_agreement:.0%} reached in round {round_num}"
            )
            # Still run adversary on the full result for quality assurance
            break

        # Fields that didn't reach consensus go to next round
        fields_to_extract = [
            name for name, data in consensus.items()
            if data["agreement"] < target_agreement
        ]

        # Update disagreement history for next round's context
        for field_name in fields_to_extract:
            data = consensus[field_name]
            disagreement_history[field_name] = {
                "previous_votes": data.get("raw_values", []),
                "current_winner": data["value"],
                "agreement": data["agreement"],
                "round": round_num,
            }

        if not fields_to_extract:
            break

    # ── Phase 3: Adversary checker ──
    adversary_corrections = _run_adversary_checker(
        ocr_result=ocr_result,
        field_schema=field_schema,
        image_bytes=image_bytes,
        consensus_results=final_results,
        checker_key=checker_key,
        settings=settings,
    )

    if adversary_corrections:
        corrections_applied = 0
        skipped_unanimous = 0
        for field_name, correction in adversary_corrections.items():
            if field_name in final_results:
                current = final_results[field_name]

                # For most fields, NEVER override unanimous consensus.
                # Exception: always-audit fields (PSIC, refugee/stateless)
                # where all generators can make the same positional error.
                ALWAYS_AUDIT_FIELDS = {
                    "activity_manufacturer", "activity_service",
                    "activity_retailer", "activity_wholesaler",
                    "activity_importer", "activity_exporter",
                }
                if current["agreement"] >= 1.0 and field_name not in ALWAYS_AUDIT_FIELDS:
                    skipped_unanimous += 1
                    logger.debug(
                        f"Adversary wanted to change unanimous '{field_name}' "
                        f"'{current['value']}' → '{correction.get('corrected_value')}' "
                        f"— BLOCKED (unanimous consensus)"
                    )
                    continue

                # For disputed/audit fields, apply adversary correction
                if correction.get("is_error") and correction.get("corrected_value"):
                    corrected_val = correction["corrected_value"]
                    # Skip if adversary "corrects" to the same value (no-op)
                    if _normalize_for_comparison(str(corrected_val)) == _normalize_for_comparison(str(current["value"])):
                        logger.debug(
                            f"Adversary confirmed '{field_name}' = '{current['value']}' "
                            f"(same value, no change needed)"
                        )
                        continue

                    logger.info(
                        f"Adversary correction: '{field_name}' "
                        f"'{current['value']}' → '{corrected_val}' "
                        f"(agreement was {current['agreement']:.0%}, "
                        f"reason: {correction.get('reason', 'N/A')})"
                    )
                    current["value"] = corrected_val
                    current["confidence"] = 0.95
                    current["adversary_corrected"] = True
                    corrections_applied += 1

        logger.info(
            f"Adversary: {corrections_applied} corrections applied, "
            f"{skipped_unanimous} blocked (unanimous consensus)"
        )

    # ── Build final mapped fields ──
    mapped_fields = []
    for field_spec in fields_spec:
        name = field_spec["name"]
        if name in final_results:
            result = final_results[name]
            mapped_fields.append({
                "field_name": name,
                "ocr_value": result["value"],
                "confidence": result["confidence"],
            })
        else:
            mapped_fields.append({
                "field_name": name,
                "ocr_value": "",
                "confidence": 0.0,
            })

    filled = sum(1 for f in mapped_fields if f["ocr_value"])
    logger.info(
        f"Consensus extraction complete: {filled}/{len(mapped_fields)} fields filled"
    )
    return mapped_fields


def _build_subset_schema(
    full_schema: dict[str, Any],
    field_names: list[str],
) -> dict[str, Any]:
    """Build a field_schema containing only the specified field names."""
    subset_fields = [
        f for f in full_schema.get("fields", [])
        if f["name"] in field_names
    ]
    return {**full_schema, "fields": subset_fields}


def _run_generators_parallel(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None,
    extract_fn: Any,
    api_keys: list[str],
    settings: Any,
    disagreement_context: dict[str, dict[str, Any]] | None = None,
) -> list[list[dict[str, Any]]]:
    """
    Run 3 generator extractions in parallel, each with a different API key.
    Returns list of extraction results (one per generator).
    """
    results: list[list[dict[str, Any]] | None] = [None] * len(api_keys)

    def _run_single(idx: int, api_key: str) -> tuple[int, list[dict[str, Any]] | None]:
        logger.info(f"Generator {idx + 1} starting extraction")
        start = time.time()
        try:
            result = extract_fn(
                ocr_result=ocr_result,
                field_schema=field_schema,
                image_bytes=image_bytes,
                api_key_override=api_key,
                disagreement_context=disagreement_context,
            )
            elapsed = time.time() - start
            logger.info(
                f"Generator {idx + 1} completed in {elapsed:.1f}s "
                f"({len(result) if result else 0} fields)"
            )
            return idx, result
        except Exception as e:
            logger.error(f"Generator {idx + 1} failed: {e}")
            return idx, None

    with ThreadPoolExecutor(max_workers=len(api_keys)) as executor:
        futures = [
            executor.submit(_run_single, i, key)
            for i, key in enumerate(api_keys)
        ]
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    # Filter out failed generators
    valid_results = [r for r in results if r is not None]
    logger.info(f"{len(valid_results)}/{len(api_keys)} generators succeeded")
    return valid_results


def _build_consensus(
    generator_outputs: list[list[dict[str, Any]]],
    field_names: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """
    Build field-by-field consensus from multiple generator outputs.

    For each field:
    - Count how many generators agree on the same value
    - Pick the majority value
    - Calculate agreement ratio

    Returns:
        (consensus_dict, disagreement_field_names)
        consensus_dict: {field_name: {"value": str, "confidence": float,
                                       "agreement": float, "votes": dict}}
    """
    # Index generator outputs by field_name for easy lookup
    gen_field_maps: list[dict[str, dict[str, Any]]] = []
    for output in generator_outputs:
        field_map = {f["field_name"]: f for f in output}
        gen_field_maps.append(field_map)

    num_generators = len(generator_outputs)
    consensus: dict[str, dict[str, Any]] = {}
    disagreements: list[str] = []

    for field_name in field_names:
        # Collect values from all generators
        values: list[str] = []
        confidences: list[float] = []

        for gen_map in gen_field_maps:
            field_data = gen_map.get(field_name)
            if field_data:
                val = str(field_data.get("ocr_value", "")).strip()
                conf = float(field_data.get("confidence", 0.0))
                values.append(val)
                confidences.append(conf)
            else:
                values.append("")
                confidences.append(0.0)

        # Normalize for comparison (lowercase, strip whitespace)
        normalized = [_normalize_for_comparison(v) for v in values]

        # Count votes
        vote_counter = Counter(normalized)
        most_common_normalized, top_count = vote_counter.most_common(1)[0]

        agreement = top_count / num_generators

        # Find the original (non-normalized) value for the winner
        winner_value = ""
        winner_confidence = 0.0
        for i, norm_val in enumerate(normalized):
            if norm_val == most_common_normalized:
                # Prefer the version with highest confidence
                if confidences[i] > winner_confidence or not winner_value:
                    winner_value = values[i]
                    winner_confidence = confidences[i]

        # Boost confidence based on agreement level
        if agreement >= 1.0:
            # Unanimous — very high confidence
            boosted_confidence = min(0.99, max(winner_confidence, 0.95))
        elif agreement >= 0.67:
            # Majority — moderate boost
            boosted_confidence = min(0.95, winner_confidence * (0.8 + agreement * 0.2))
        else:
            # No clear majority — lower confidence
            boosted_confidence = winner_confidence * 0.6
            disagreements.append(field_name)

        consensus[field_name] = {
            "value": winner_value,
            "confidence": round(boosted_confidence, 4),
            "agreement": round(agreement, 4),
            "votes": dict(vote_counter),
            "raw_values": values,
        }

        if agreement < 1.0:
            logger.debug(
                f"Field '{field_name}': agreement={agreement:.0%}, "
                f"votes={dict(vote_counter)}, winner='{winner_value}'"
            )

    agreed = sum(1 for c in consensus.values() if c["agreement"] >= 1.0)
    logger.info(
        f"Consensus built: {agreed}/{len(field_names)} unanimous, "
        f"{len(disagreements)} disagreements"
    )

    return consensus, disagreements


def _normalize_for_comparison(value: str) -> str:
    """Normalize a value for consensus comparison."""
    if not value:
        return ""
    # Lowercase, strip, collapse whitespace, remove trailing punctuation
    normalized = value.lower().strip()
    normalized = " ".join(normalized.split())
    # Remove trailing periods and commas
    normalized = normalized.rstrip(".,;:")
    return normalized


def _run_adversary_checker(
    ocr_result: dict[str, Any],
    field_schema: dict[str, Any],
    image_bytes: bytes | None,
    consensus_results: dict[str, dict[str, Any]],
    checker_key: str,
    settings: Any,
) -> dict[str, dict[str, Any]] | None:
    """
    Run the adversary AI checker to validate consensus results.

    The adversary receives:
    - The original form image
    - The OCR text
    - The consensus-extracted values (with agreement scores)
    - Specific instructions to find errors

    Returns dict of corrections: {field_name: {"is_error": bool,
        "corrected_value": str, "reason": str}}
    """
    from openai import OpenAI
    import base64

    if not checker_key:
        logger.warning("No checker API key, skipping adversary validation")
        return None

    try:
        client = OpenAI(
            api_key=checker_key,
            base_url=settings.AI_BASE_URL,
        )

        # Build image content
        image_content = None
        if image_bytes:
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

        # Build OCR text
        raw_lines = ocr_result.get("raw_lines", [])
        ocr_text = "\n".join(
            f"  Line {i+1}: \"{line['text']}\" (conf: {line['confidence']:.2f})"
            for i, line in enumerate(raw_lines)
        )

        # Build consensus summary
        # Disputed fields are always shown to adversary.
        # Known-tricky fields (PSIC checkboxes, refugee/stateless) are ALWAYS
        # audited even when unanimous, because all generators can make the
        # same positional confusion error on these.
        ALWAYS_AUDIT_FIELDS = {
            "activity_manufacturer", "activity_service", "activity_retailer",
            "activity_wholesaler", "activity_importer", "activity_exporter",
        }

        fields_spec = field_schema.get("fields", [])
        fields_by_name = {f["name"]: f for f in fields_spec}

        disputed_parts = []
        audit_parts = []
        unanimous_count = 0
        for field_name, data in consensus_results.items():
            spec = fields_by_name.get(field_name, {})
            label = spec.get("label", field_name)
            value = data["value"]
            agreement = data["agreement"]
            raw_values = data.get("raw_values", [])

            ftype = spec.get("type", "text")
            options = spec.get("options", [])
            type_hint = ""
            if ftype == "checkbox":
                type_hint = " [CHECKBOX: return 'true' if checked, '' if unchecked]"
            elif ftype == "radio" and options:
                type_hint = f" [RADIO: must be one of: {', '.join(options)}]"

            if agreement >= 1.0 and field_name not in ALWAYS_AUDIT_FIELDS:
                unanimous_count += 1
                continue  # Don't show unanimous non-audit fields

            if agreement >= 1.0 and field_name in ALWAYS_AUDIT_FIELDS:
                # Unanimous but always-audit — show separately
                audit_parts.append(
                    f'  "{field_name}" ({label}): '
                    f"Unanimous: \"{value}\"{type_hint}"
                )
            else:
                disputed_parts.append(
                    f'  "{field_name}" ({label}): '
                    f"Votes: {raw_values} → Current: \"{value}\"{type_hint}"
                )

        if not disputed_parts and not audit_parts:
            # All unanimous and nothing to audit
            logger.info(
                f"All {unanimous_count} fields are unanimous — skipping adversary"
            )
            return None

        disputed_summary = "\n".join(disputed_parts)
        audit_summary = "\n".join(audit_parts)

        # Build the focus section
        focus_section = ""
        if disputed_parts:
            focus_section += (
                f"{len(disputed_parts)} field(s) had DISAGREEMENTS between extractors.\n"
                "DISPUTED FIELDS:\n"
                f"{disputed_summary}\n\n"
            )
        if audit_parts:
            focus_section += (
                f"{len(audit_parts)} field(s) are MANDATORY AUDIT targets "
                "(known-tricky checkbox positions — generators can confuse adjacent boxes).\n"
                "AUDIT FIELDS (verify even though generators agreed):\n"
                f"{audit_summary}\n\n"
            )

        prompt = (
            "You are an ADVERSARY VALIDATION AI for a Philippine government form OCR system.\n\n"
            "Three independent AI extractors have processed this form. They AGREED unanimously "
            f"on {unanimous_count} other fields (those are LOCKED).\n\n"
            f"{focus_section}"
            "PHYSICAL LAYOUT GUIDE (crucial for checkboxes):\n"
            "- Section G, Box 24 — PSIC Main Business Activity is a 2×3 GRID:\n"
            "  TOP ROW (left to right):    □ Manufacturer/Producer  □ Service      □ Retailer\n"
            "  BOTTOM ROW (left to right): □ Wholesaler             □ Importer     □ Exporter\n"
            "  MULTIPLE boxes CAN be checked. A filled/dark square ■ means checked.\n"
            "  COMMON ERROR: confusing Service (top-middle) with Manufacturer (top-left).\n"
            "  Look at EACH box position individually.\n"
            "- Section C, Box 10 — Refugee/Stateless has FOUR boxes in TWO pairs:\n"
            "  Refugee? □ Yes □ No  |  Stateless person? □ Yes □ No\n"
            "  Check each pair independently.\n\n"
            "OCR TEXT (from PaddleOCR):\n"
            f"{ocr_text}\n\n"
            "INSTRUCTIONS:\n"
            "1. Look at the ORIGINAL form image carefully\n"
            "2. For each field listed above (disputed AND audit), determine the correct value\n"
            "3. Return corrections for ANY field where the current value is WRONG\n"
            "4. For checkbox fields: return 'true' if checked, empty string '' if unchecked\n"
            "5. For radio fields: return EXACTLY one of the listed option values\n"
            "6. For text fields: return the exact text as it appears in the form\n"
            "7. If a field's current value is already correct, don't include it\n\n"
            "Return ONLY a JSON object. No markdown, no explanation:\n"
            "{\n"
            '  "field_name": {\n'
            '    "is_error": true,\n'
            '    "corrected_value": "correct value from image",\n'
            '    "reason": "brief explanation"\n'
            "  },\n"
            "  ...\n"
            "}\n"
            "Only include fields that need correction. Empty {} means current values are correct."
        )

        messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image_content:
            messages_content.append(image_content)

        response = client.chat.completions.create(
            model=settings.AI_VISION_MODEL,
            messages=[{"role": "user", "content": messages_content}],
            max_tokens=3000,
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
            # Attempt repair
            repaired = content
            last_comma = repaired.rfind(",")
            if last_comma > 0:
                repaired = repaired[:last_comma]
            if not repaired.rstrip().endswith("}"):
                repaired = repaired.rstrip() + "\n}"
            try:
                result = json.loads(repaired)
            except json.JSONDecodeError as e:
                logger.error(f"Adversary JSON parse failed: {e}")
                return None

        error_count = sum(1 for v in result.values() if v.get("is_error"))
        logger.info(
            f"Adversary checker found {error_count} errors out of "
            f"{len(consensus_results)} fields"
        )

        return result

    except Exception as e:
        logger.error(f"Adversary checker failed: {e}")
        return None
