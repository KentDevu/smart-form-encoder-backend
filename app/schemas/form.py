from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FormEntryCreate(BaseModel):
    template_id: UUID
    image_url: str = Field(..., max_length=500)


class FormFieldResponse(BaseModel):
    id: UUID
    field_name: str
    ocr_value: str | None = None
    verified_value: str | None = None
    confidence: float
    was_corrected: bool

    model_config = {"from_attributes": True}


class FormEntryResponse(BaseModel):
    id: UUID
    template_id: UUID
    uploaded_by: UUID
    verified_by: UUID | None = None
    image_url: str
    status: str
    raw_ocr_data: dict | None = None
    verified_data: dict | None = None
    confidence_score: float | None = None
    processing_time: float | None = None
    fields: list[FormFieldResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FormEntryListResponse(BaseModel):
    id: UUID
    template_id: UUID
    uploaded_by: UUID
    image_url: str
    status: str
    confidence_score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FormVerifyRequest(BaseModel):
    """Request to submit verified/corrected field data."""
    fields: dict[str, str] = Field(
        ...,
        description="Mapping of field_name to verified_value",
        examples=[{"business_name": "Juan's Store", "owner_name": "Juan Dela Cruz"}],
    )


class FormTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    field_schema: dict
    sample_image_url: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateSearchRegion(BaseModel):
    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 1.0
    y_max: float = 1.0


class TemplateExtractionConfig(BaseModel):
    strategy: str = "label_nearby"
    anchor_labels: list[str] = Field(default_factory=list)
    search_region: TemplateSearchRegion = Field(default_factory=TemplateSearchRegion)
    ai_prompt_hint: str | None = None
    value_postprocess: str | None = None


class TemplateFieldSchema(BaseModel):
    name: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    extraction: TemplateExtractionConfig = Field(default_factory=TemplateExtractionConfig)
