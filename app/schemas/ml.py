"""Pydantic schemas for ML training data export endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrainingFieldData(BaseModel):
    """A single field's training data (OCR vs verified)."""
    field_name: str
    ocr_value: str | None = None
    verified_value: str | None = None
    was_corrected: bool = False
    confidence: float = 0.0


class TrainingEntryData(BaseModel):
    """A form entry with its image URL and field-level training data."""
    entry_id: UUID
    template_id: UUID
    template_name: str
    image_url: str = Field(description="Pre-signed download URL for the form image")
    confidence_score: float | None = None
    processing_time: float | None = None
    fields: list[TrainingFieldData]


class TrainingDataExport(BaseModel):
    """Response shape for training data export endpoint."""
    entries: list[TrainingEntryData]
    total: int
    export_date: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d")
    )


class TrainingDataStats(BaseModel):
    """Summary statistics for available training data."""
    total_verified_entries: int = 0
    total_fields: int = 0
    total_corrected_fields: int = 0
    correction_rate: float = Field(
        default=0.0,
        description="Percentage of fields that were corrected by humans"
    )
    avg_confidence: float = 0.0
    templates: list[dict] = Field(
        default_factory=list,
        description="Per-template breakdown of verified entry counts"
    )


class EvaluationMetrics(BaseModel):
    """Accuracy evaluation metrics for the current OCR pipeline."""
    total_entries_evaluated: int = 0
    total_fields_evaluated: int = 0
    field_accuracy: float = Field(
        default=0.0,
        description="% of fields where OCR value exactly matches verified value"
    )
    avg_confidence: float = 0.0
    correction_rate: float = Field(
        default=0.0,
        description="% of fields requiring human correction"
    )
    per_template: list[dict] = Field(
        default_factory=list,
        description="Per-template accuracy breakdown"
    )
    per_field: list[dict] = Field(
        default_factory=list,
        description="Per-field-name accuracy breakdown"
    )
