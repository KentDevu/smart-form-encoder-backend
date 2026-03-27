"""Template extraction schema validation and normalization."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class SearchRegion(BaseModel):
    """Relative search region (0.0-1.0) within a page."""

    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 1.0
    y_max: float = 1.0

    @field_validator("x_min", "y_min", "x_max", "y_max")
    @classmethod
    def _validate_bounds(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("region bounds must be between 0.0 and 1.0")
        return value


class FieldExtractionConfig(BaseModel):
    """Extraction directives for one field."""

    strategy: str = Field(default="label_nearby")
    anchor_labels: list[str] = Field(default_factory=list)
    search_region: SearchRegion = Field(default_factory=SearchRegion)
    ai_prompt_hint: str | None = None
    value_postprocess: str | None = None

    @field_validator("strategy")
    @classmethod
    def _validate_strategy(cls, value: str) -> str:
        allowed = {"label_nearby", "line_match", "checkbox_mark"}
        if value not in allowed:
            raise ValueError(f"unsupported strategy: {value}")
        return value


class TemplateField(BaseModel):
    """Single form field metadata."""

    name: str
    label: str | None = None
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    extraction: FieldExtractionConfig = Field(default_factory=FieldExtractionConfig)


def normalize_template_schema(field_schema: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure every field has a valid extraction config.
    Raises ValueError for invalid schema.
    """
    fields = field_schema.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("template field_schema.fields must be a non-empty list")

    normalized_fields: list[dict[str, Any]] = []
    for raw_field in fields:
        candidate = dict(raw_field or {})
        if "label" not in candidate and "name" in candidate:
            candidate["label"] = str(candidate["name"]).replace("_", " ").title()
        try:
            validated = TemplateField.model_validate(candidate)
        except ValidationError as exc:
            raise ValueError(f"invalid template field schema: {exc}") from exc
        normalized_fields.append(validated.model_dump())

    normalized_schema = dict(field_schema)
    normalized_schema["fields"] = normalized_fields
    return normalized_schema
