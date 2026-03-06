import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FormEntryStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    VERIFIED = "verified"
    ARCHIVED = "archived"


class FormEntry(Base):
    __tablename__ = "form_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_templates.id"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[FormEntryStatus] = mapped_column(
        Enum(FormEntryStatus), nullable=False, default=FormEntryStatus.UPLOADED, index=True
    )
    raw_ocr_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Raw OCR extraction output"
    )
    verified_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Human-verified final data"
    )
    confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Overall confidence 0.0-1.0"
    )
    processing_time: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="OCR processing time in seconds"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    template: Mapped["FormTemplate"] = relationship(
        "FormTemplate", back_populates="entries"
    )
    uploader: Mapped["User"] = relationship(
        "User", foreign_keys=[uploaded_by], back_populates="uploaded_entries"
    )
    verifier: Mapped["User | None"] = relationship(
        "User", foreign_keys=[verified_by], back_populates="verified_entries"
    )
    fields: Mapped[list["FormField"]] = relationship(
        "FormField", back_populates="entry", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FormEntry {self.id} ({self.status.value})>"
