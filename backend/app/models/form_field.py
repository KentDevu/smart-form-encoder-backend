import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FormField(Base):
    __tablename__ = "form_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_entries.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Field label from template schema"
    )
    ocr_value: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Raw OCR-extracted value"
    )
    verified_value: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Human-verified final value"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="Confidence score 0.0-1.0"
    )
    was_corrected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True if encoder modified the OCR value"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    entry: Mapped["FormEntry"] = relationship(
        "FormEntry", back_populates="fields"
    )

    def __repr__(self) -> str:
        return f"<FormField {self.field_name} (conf: {self.confidence})>"
