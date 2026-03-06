import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Action type: create, update, delete, verify, login, etc."
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Entity type: form_entry, user, form_template, etc."
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="ID of the affected entity"
    )
    changes: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="JSON diff of changes made"
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True, comment="Client IP address"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Human-readable description"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} on {self.entity_type} by {self.user_id}>"
