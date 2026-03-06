"""ML training data service — queries verified entries for model training."""

import logging
from uuid import UUID

from sqlalchemy import Select, func, select, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.form_entry import FormEntry, FormEntryStatus
from app.models.form_field import FormField
from app.models.form_template import FormTemplate
from app.services.storage_service import get_presigned_url

logger = logging.getLogger(__name__)


async def get_training_data(
    db: AsyncSession,
    template_id: UUID | None = None,
    limit: int = 1000,
    offset: int = 0,
    corrected_only: bool = False,
) -> tuple[list[dict], int]:
    """
    Export verified form entries with their OCR vs verified field data.

    Returns:
        Tuple of (entries_list, total_count)
    """
    # Base query: only verified/archived entries (they have human-verified data)
    base_filter = FormEntry.status.in_([
        FormEntryStatus.VERIFIED,
        FormEntryStatus.ARCHIVED,
    ])

    if template_id:
        base_filter = and_(base_filter, FormEntry.template_id == template_id)

    # Count total
    count_q = select(func.count()).select_from(FormEntry).where(base_filter)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch entries with fields and template
    q = (
        select(FormEntry)
        .options(
            selectinload(FormEntry.fields),
            selectinload(FormEntry.template),
        )
        .where(base_filter)
        .order_by(FormEntry.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    entries = result.scalars().all()

    entries_data = []
    for entry in entries:
        fields_data = []
        for field in entry.fields:
            # If corrected_only, skip fields that weren't corrected
            if corrected_only and not field.was_corrected:
                continue

            fields_data.append({
                "field_name": field.field_name,
                "ocr_value": field.ocr_value or "",
                "verified_value": field.verified_value or "",
                "was_corrected": field.was_corrected,
                "confidence": field.confidence,
            })

        # Skip entries with no matching fields (when corrected_only filters everything)
        if corrected_only and not fields_data:
            continue

        # Generate a presigned URL for the image
        try:
            image_url = get_presigned_url(entry.image_url)
        except Exception:
            image_url = entry.image_url

        entries_data.append({
            "entry_id": entry.id,
            "template_id": entry.template_id,
            "template_name": entry.template.name if entry.template else "Unknown",
            "image_url": image_url,
            "confidence_score": entry.confidence_score,
            "processing_time": entry.processing_time,
            "fields": fields_data,
        })

    return entries_data, total


async def get_training_stats(db: AsyncSession) -> dict:
    """
    Get summary statistics about available training data.

    Returns counts of verified entries, fields, correction rates, etc.
    """
    # Total verified entries
    verified_count_q = (
        select(func.count())
        .select_from(FormEntry)
        .where(FormEntry.status.in_([
            FormEntryStatus.VERIFIED,
            FormEntryStatus.ARCHIVED,
        ]))
    )
    total_verified = (await db.execute(verified_count_q)).scalar() or 0

    # Field-level stats from verified entries
    field_stats_q = (
        select(
            func.count(FormField.id).label("total_fields"),
            func.sum(case((FormField.was_corrected == True, 1), else_=0)).label("corrected_fields"),  # noqa: E712
            func.avg(FormField.confidence).label("avg_confidence"),
        )
        .join(FormEntry, FormField.entry_id == FormEntry.id)
        .where(FormEntry.status.in_([
            FormEntryStatus.VERIFIED,
            FormEntryStatus.ARCHIVED,
        ]))
    )
    field_stats = (await db.execute(field_stats_q)).one()
    total_fields = field_stats.total_fields or 0
    corrected_fields = int(field_stats.corrected_fields or 0)
    avg_confidence = float(field_stats.avg_confidence or 0.0)

    correction_rate = (corrected_fields / total_fields * 100) if total_fields > 0 else 0.0

    # Per-template breakdown
    template_stats_q = (
        select(
            FormTemplate.name,
            FormTemplate.id,
            func.count(FormEntry.id).label("entry_count"),
        )
        .join(FormEntry, FormTemplate.id == FormEntry.template_id)
        .where(FormEntry.status.in_([
            FormEntryStatus.VERIFIED,
            FormEntryStatus.ARCHIVED,
        ]))
        .group_by(FormTemplate.id, FormTemplate.name)
        .order_by(func.count(FormEntry.id).desc())
    )
    template_rows = (await db.execute(template_stats_q)).all()
    templates = [
        {
            "template_id": str(row.id),
            "template_name": row.name,
            "verified_entries": row.entry_count,
        }
        for row in template_rows
    ]

    return {
        "total_verified_entries": total_verified,
        "total_fields": total_fields,
        "total_corrected_fields": corrected_fields,
        "correction_rate": round(correction_rate, 2),
        "avg_confidence": round(avg_confidence, 4),
        "templates": templates,
    }


async def get_evaluation_metrics(db: AsyncSession) -> dict:
    """
    Calculate accuracy metrics for the current OCR pipeline based on verified data.

    Compares ocr_value vs verified_value for all verified form entries.
    """
    # Only evaluate fields from verified entries that have both values
    base_filter = and_(
        FormEntry.status.in_([FormEntryStatus.VERIFIED, FormEntryStatus.ARCHIVED]),
        FormField.verified_value.isnot(None),
        FormField.verified_value != "",
    )

    # Overall metrics
    overall_q = (
        select(
            func.count(FormField.id).label("total"),
            func.sum(case(
                (FormField.ocr_value == FormField.verified_value, 1),
                else_=0,
            )).label("exact_matches"),
            func.sum(case(
                (FormField.was_corrected == True, 1),  # noqa: E712
                else_=0,
            )).label("corrected"),
            func.avg(FormField.confidence).label("avg_confidence"),
        )
        .join(FormEntry, FormField.entry_id == FormEntry.id)
        .where(base_filter)
    )
    overall = (await db.execute(overall_q)).one()
    total = overall.total or 0
    exact_matches = int(overall.exact_matches or 0)
    corrected = int(overall.corrected or 0)

    # Count distinct entries evaluated
    entry_count_q = (
        select(func.count(func.distinct(FormEntry.id)))
        .join(FormField, FormField.entry_id == FormEntry.id)
        .where(base_filter)
    )
    entries_evaluated = (await db.execute(entry_count_q)).scalar() or 0

    field_accuracy = (exact_matches / total * 100) if total > 0 else 0.0
    correction_rate = (corrected / total * 100) if total > 0 else 0.0

    # Per-template breakdown
    per_template_q = (
        select(
            FormTemplate.name.label("template_name"),
            func.count(FormField.id).label("field_count"),
            func.sum(case(
                (FormField.ocr_value == FormField.verified_value, 1),
                else_=0,
            )).label("exact_matches"),
            func.avg(FormField.confidence).label("avg_confidence"),
        )
        .join(FormEntry, FormField.entry_id == FormEntry.id)
        .join(FormTemplate, FormEntry.template_id == FormTemplate.id)
        .where(base_filter)
        .group_by(FormTemplate.name)
    )
    template_rows = (await db.execute(per_template_q)).all()
    per_template = [
        {
            "template_name": row.template_name,
            "field_count": row.field_count,
            "exact_matches": int(row.exact_matches or 0),
            "field_accuracy": round(
                (int(row.exact_matches or 0) / row.field_count * 100)
                if row.field_count > 0 else 0.0,
                2,
            ),
            "avg_confidence": round(float(row.avg_confidence or 0), 4),
        }
        for row in template_rows
    ]

    # Per-field-name breakdown (which fields are most problematic?)
    per_field_q = (
        select(
            FormField.field_name,
            func.count(FormField.id).label("total"),
            func.sum(case(
                (FormField.ocr_value == FormField.verified_value, 1),
                else_=0,
            )).label("exact_matches"),
            func.sum(case(
                (FormField.was_corrected == True, 1),  # noqa: E712
                else_=0,
            )).label("corrected"),
            func.avg(FormField.confidence).label("avg_confidence"),
        )
        .join(FormEntry, FormField.entry_id == FormEntry.id)
        .where(base_filter)
        .group_by(FormField.field_name)
        .order_by(func.sum(case(
            (FormField.was_corrected == True, 1),  # noqa: E712
            else_=0,
        )).desc())
    )
    field_rows = (await db.execute(per_field_q)).all()
    per_field = [
        {
            "field_name": row.field_name,
            "total": row.total,
            "exact_matches": int(row.exact_matches or 0),
            "corrected": int(row.corrected or 0),
            "field_accuracy": round(
                (int(row.exact_matches or 0) / row.total * 100)
                if row.total > 0 else 0.0,
                2,
            ),
            "avg_confidence": round(float(row.avg_confidence or 0), 4),
        }
        for row in field_rows
    ]

    return {
        "total_entries_evaluated": entries_evaluated,
        "total_fields_evaluated": total,
        "field_accuracy": round(field_accuracy, 2),
        "avg_confidence": round(float(overall.avg_confidence or 0), 4),
        "correction_rate": round(correction_rate, 2),
        "per_template": per_template,
        "per_field": per_field,
    }
