"""Template-first deterministic field extraction from OCR lines."""

from __future__ import annotations

from typing import Any


def _line_center(line: dict[str, Any]) -> tuple[float, float]:
    bbox = line.get("bbox") or []
    if len(bbox) < 4:
        return (0.0, 0.0)
    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _line_in_region(line: dict[str, Any], region: dict[str, float], page_size: tuple[float, float]) -> bool:
    page_w, page_h = page_size
    if page_w <= 0 or page_h <= 0:
        return True
    center_x, center_y = _line_center(line)
    rel_x = center_x / page_w
    rel_y = center_y / page_h
    return (
        region.get("x_min", 0.0) <= rel_x <= region.get("x_max", 1.0)
        and region.get("y_min", 0.0) <= rel_y <= region.get("y_max", 1.0)
    )


def _estimate_page_size(raw_lines: list[dict[str, Any]]) -> tuple[float, float]:
    max_x = 0.0
    max_y = 0.0
    for line in raw_lines:
        bbox = line.get("bbox") or []
        if len(bbox) < 4:
            continue
        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]
        max_x = max(max_x, max(xs))
        max_y = max(max_y, max(ys))
    return (max_x, max_y)


def _find_best_label_match(label_candidates: list[str], eligible_lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    for candidate in label_candidates:
        needle = candidate.lower().strip()
        if not needle:
            continue
        for line in eligible_lines:
            haystack = str(line.get("text", "")).lower()
            if needle in haystack:
                return line
    return None


def extract_fields_with_template_map(
    *,
    raw_lines: list[dict[str, Any]],
    field_schema: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Deterministically extract values using template extraction metadata."""
    page_size = _estimate_page_size(raw_lines)
    extracted: dict[str, dict[str, Any]] = {}

    for field in field_schema.get("fields", []):
        name = field.get("name", "")
        field_type = field.get("type", "text")
        extraction = field.get("extraction", {})
        anchors = extraction.get("anchor_labels") or [field.get("label", name)]
        region = extraction.get("search_region") or {}

        eligible_lines = [
            line
            for line in raw_lines
            if _line_in_region(line, region, page_size)
        ]
        anchor_line = _find_best_label_match(anchors, eligible_lines)

        value = ""
        confidence = 0.0
        context_lines: list[str] = []
        unresolved = True

        if anchor_line:
            context_lines.append(str(anchor_line.get("text", "")))
            anchor_text = str(anchor_line.get("text", ""))
            label = str(field.get("label", name))

            if field_type in {"checkbox", "radio"}:
                lower = anchor_text.lower()
                if any(token in lower for token in ["✓", "✔", " x ", "[x]", "(x)", "checked", "yes"]):
                    value = "true" if field_type == "checkbox" else (field.get("options") or [""])[0]
                    confidence = float(anchor_line.get("confidence", 0.6))
                    unresolved = False
            else:
                if ":" in anchor_text:
                    candidate = anchor_text.split(":", 1)[1].strip()
                    if candidate:
                        value = candidate
                        confidence = float(anchor_line.get("confidence", 0.6))
                        unresolved = False

                if unresolved:
                    # fallback to nearest line on the right/below anchor
                    ax, ay = _line_center(anchor_line)
                    nearest_line = None
                    nearest_distance = float("inf")
                    for line in eligible_lines:
                        if line is anchor_line:
                            continue
                        text = str(line.get("text", "")).strip()
                        if not text or text.lower() == label.lower():
                            continue
                        lx, ly = _line_center(line)
                        if lx < ax:
                            continue
                        distance = abs(lx - ax) + abs(ly - ay)
                        if distance < nearest_distance:
                            nearest_distance = distance
                            nearest_line = line
                    if nearest_line is not None:
                        value = str(nearest_line.get("text", "")).strip()
                        confidence = float(nearest_line.get("confidence", 0.55))
                        context_lines.append(str(nearest_line.get("text", "")))
                        unresolved = not bool(value)

        extracted[name] = {
            "value": value,
            "confidence": max(0.0, min(1.0, confidence)),
            "source": "deterministic",
            "unresolved": unresolved,
            "context_lines": context_lines[:5],
            "ai_prompt_hint": extraction.get("ai_prompt_hint"),
        }

    return extracted
