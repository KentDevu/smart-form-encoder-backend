import math
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.form_entry import FormEntry, FormEntryStatus
from app.models.form_field import FormField
from app.models.form_template import FormTemplate
from app.models.user import User, UserRole


class FormService:
    """Handles form entry business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_entry(
        self, template_id: UUID, image_url: str, uploaded_by: UUID
    ) -> FormEntry:
        """Create a new form entry after image upload."""
        # Validate template exists
        result = await self.db.execute(
            select(FormTemplate).where(FormTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise NotFoundException("Form template not found")

        entry = FormEntry(
            template_id=template_id,
            uploaded_by=uploaded_by,
            image_url=image_url,
            status=FormEntryStatus.UPLOADED,
        )
        self.db.add(entry)
        await self.db.flush()

        # Re-fetch with eager-loaded relationships to avoid async lazy-load issues
        result = await self.db.execute(
            select(FormEntry)
            .options(selectinload(FormEntry.fields))
            .where(FormEntry.id == entry.id)
        )
        entry = result.scalar_one()
        return entry

    async def list_templates(self) -> list[FormTemplate]:
        """List all active form templates."""
        result = await self.db.execute(
            select(FormTemplate)
            .where(FormTemplate.is_active == True)  # noqa: E712
            .order_by(FormTemplate.name)
        )
        return list(result.scalars().all())

    async def get_template(self, template_id: UUID) -> FormTemplate:
        """Get a form template by ID."""
        result = await self.db.execute(
            select(FormTemplate).where(FormTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise NotFoundException("Form template not found")
        return template

    async def create_template(
        self, name: str, description: str | None, field_schema: dict
    ) -> FormTemplate:
        """Create a new form template."""
        template = FormTemplate(
            name=name,
            description=description,
            field_schema=field_schema,
        )
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def get_entry(self, entry_id: UUID, current_user: User) -> FormEntry:
        """Get a form entry by ID with access control."""
        result = await self.db.execute(
            select(FormEntry)
            .options(selectinload(FormEntry.fields))
            .where(FormEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if entry is None:
            raise NotFoundException("Form entry not found")

        # Encoders can only view their own entries
        if current_user.role == UserRole.ENCODER and entry.uploaded_by != current_user.id:
            raise ForbiddenException("You can only view your own form entries")

        return entry

    async def list_entries(
        self,
        current_user: User,
        page: int = 1,
        per_page: int = 20,
        status: str | None = None,
        template_id: UUID | None = None,
    ) -> dict:
        """List form entries with pagination and filtering."""
        query = select(FormEntry)

        # Encoders can only see their own entries
        if current_user.role == UserRole.ENCODER:
            query = query.where(FormEntry.uploaded_by == current_user.id)

        # Apply filters
        if status:
            query = query.where(FormEntry.status == FormEntryStatus(status))
        if template_id:
            query = query.where(FormEntry.template_id == template_id)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Apply pagination
        query = (
            query.order_by(FormEntry.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )

        result = await self.db.execute(query)
        entries = result.scalars().all()

        return {
            "items": entries,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": math.ceil(total / per_page) if total > 0 else 0,
        }

    async def verify_entry(
        self, entry_id: UUID, verified_fields: dict[str, str], verifier: User
    ) -> FormEntry:
        """Submit human-verified data for a form entry."""
        result = await self.db.execute(
            select(FormEntry)
            .options(selectinload(FormEntry.fields))
            .where(FormEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if entry is None:
            raise NotFoundException("Form entry not found")

        # Encoders can only verify their own entries
        if verifier.role == UserRole.ENCODER and entry.uploaded_by != verifier.id:
            raise ForbiddenException("You can only verify your own form entries")

        if entry.status not in (FormEntryStatus.EXTRACTED, FormEntryStatus.VERIFIED):
            raise NotFoundException(
                "Form entry must be in 'extracted' status to be verified"
            )

        # Update each field with verified values
        for field in entry.fields:
            if field.field_name in verified_fields:
                new_value = verified_fields[field.field_name]
                field.was_corrected = field.ocr_value != new_value
                field.verified_value = new_value

        # Update entry
        entry.verified_by = verifier.id
        entry.verified_data = verified_fields
        entry.status = FormEntryStatus.VERIFIED

        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def delete_entry(self, entry_id: UUID) -> None:
        """Delete a form entry (admin only)."""
        result = await self.db.execute(
            select(FormEntry).where(FormEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if entry is None:
            raise NotFoundException("Form entry not found")

        await self.db.delete(entry)
        await self.db.flush()
