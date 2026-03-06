"""ML training data export endpoints for OCR accuracy improvement pipeline."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.ml import (
    EvaluationMetrics,
    TrainingDataExport,
    TrainingDataStats,
)
from app.services.ml_service import (
    get_evaluation_metrics,
    get_training_data,
    get_training_stats,
)

router = APIRouter(prefix="/ml", tags=["ML Training"])


@router.get(
    "/export-training-data",
    response_model=ApiResponse[TrainingDataExport],
    summary="Export verified form data for ML training",
    description=(
        "Export verified form entries with OCR vs human-verified field data. "
        "Used by Colab notebooks to download training datasets. Admin only."
    ),
)
async def export_training_data(
    template_id: UUID | None = Query(None, description="Filter by template ID"),
    limit: int = Query(1000, ge=1, le=10000, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    corrected_only: bool = Query(
        False, description="Only include fields that were corrected by humans"
    ),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ApiResponse[TrainingDataExport]:
    """Export verified entries as labeled training data for ML pipeline."""
    entries, total = await get_training_data(
        db=db,
        template_id=template_id,
        limit=limit,
        offset=offset,
        corrected_only=corrected_only,
    )

    export = TrainingDataExport(
        entries=entries,
        total=total,
    )

    return ApiResponse(
        success=True,
        data=export,
        message=f"Exported {len(entries)} entries ({total} total available)",
    )


@router.get(
    "/training-stats",
    response_model=ApiResponse[TrainingDataStats],
    summary="Get training data statistics",
    description=(
        "Summary statistics about available training data: "
        "total verified entries, correction rates, per-template breakdown."
    ),
)
async def training_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ApiResponse[TrainingDataStats]:
    """Get summary stats about available training data."""
    stats = await get_training_stats(db)

    return ApiResponse(
        success=True,
        data=TrainingDataStats(**stats),
        message="Training data statistics",
    )


@router.get(
    "/evaluation",
    response_model=ApiResponse[EvaluationMetrics],
    summary="Evaluate current OCR pipeline accuracy",
    description=(
        "Calculate accuracy metrics by comparing OCR values to human-verified values. "
        "Shows field accuracy, correction rate, per-template and per-field breakdowns."
    ),
)
async def evaluation_metrics(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ApiResponse[EvaluationMetrics]:
    """Evaluate current OCR accuracy against human-verified ground truth."""
    metrics = await get_evaluation_metrics(db)

    return ApiResponse(
        success=True,
        data=EvaluationMetrics(**metrics),
        message="OCR pipeline evaluation metrics",
    )
