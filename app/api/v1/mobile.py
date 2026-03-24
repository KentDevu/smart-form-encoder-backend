"""Mobile API endpoints - specifically for the mobile app."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.storage_service import get_presigned_url, upload_file_to_r2
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/mobile", tags=["Mobile"])


class UploadMetadataRequest(BaseModel):
    """Request for mobile upload metadata."""
    template_id: str
    device_id: str
    metadata: dict  # Contains: form_type, capture_timestamp, notes


class PresignedUrlResponse(BaseModel):
    """Response containing presigned URL for direct R2 upload."""
    upload_url: str
    form_entry_id: str
    object_key: str


class FormEntryCreateMobile(BaseModel):
    """Request to create form entry from mobile upload."""
    template_id: str
    image_url: str
    device_id: str
    form_entry_id: str  # From presigned URL response
    metadata: dict  # Contains: form_type, capture_timestamp, notes


@router.post("/upload-url", response_model=ApiResponse[PresignedUrlResponse])
async def get_mobile_upload_url(
    request: UploadMetadataRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PresignedUrlResponse]:
    """
    Generate Cloudflare R2 presigned URL for mobile app upload.

    Mobile apps use this endpoint to get a presigned URL, then upload directly to R2,
    then call the form-entries endpoint to create the database record.

    Args:
        request: Device ID, template ID, and metadata
        db: Database session

    Returns:
        Pre-signed URL for direct R2 upload + form_entry_id for tracking
    """
    try:
        form_entry_id = str(uuid.uuid4())
        now = datetime.utcnow()
        object_key = f"forms/{now.year}/{now.month:02d}/{form_entry_id}/image.jpg"

        # Generate presigned URL (15 min expiry)
        presigned_url = generate_presigned_url(object_key, method='put', expiration=900)

        # Store metadata temporarily for verification
        # In production, this would use Redis or similar
        from app.core.redis_client import redis_client

        await redis_client.set(
            f"upload_metadata:{form_entry_id}",
            {
                "template_id": request.template_id,
                "device_id": request.device_id,
                "metadata": request.metadata,
            },
            ex=900,  # 15 minutes
        )

        return ApiResponse(
            success=True,
            data=PresignedUrlResponse(
                upload_url=presigned_url,
                form_entry_id=form_entry_id,
                object_key=object_key,
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/form-entries", response_model=ApiResponse[dict])
async def create_mobile_form_entry(
    form_data: FormEntryCreateMobile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    Create form entry after mobile app uploads to R2 via presigned URL.

    This endpoint expects the mobile app to have already uploaded the image
    to R2 using the presigned URL from /upload-url.

    Args:
        form_data: Template ID, image URL (object key), device ID, form entry ID
        current_user: Authenticated user (from JWT)
        db: Database session

    Returns:
        Confirmation of form entry creation
    """
    try:
        from app.models.form_entry import FormEntry, FormEntryStatus
        from app.schemas.form import FormEntryResponse

        # Verify upload metadata exists (optional, for extra security)
        from app.core.redis_client import redis_client

        cached_metadata = await redis_client.get(f"upload_metadata:{form_data.form_entry_id}")

        # Create form entry
        form_entry = FormEntry(
            id=form_data.form_entry_id,
            template_id=form_data.template_id,
            image_url=form_data.image_url,  # This is the object key in R2
            uploaded_by=current_user.id,
            uploaded_by_device_id=form_data.device_id,
            raw_ocr_data=form_data.metadata,  # Store metadata from mobile
            status=FormEntryStatus.UPLOADED,
        )
        db.add(form_entry)
        await db.commit()
        await db.refresh(form_entry)

        # Trigger OCR processing asynchronously
        from app.services.ocr_task import process_ocr_task
        process_ocr_task.delay(str(form_entry.id))

        # Clean up cached metadata
        if cached_metadata:
            await redis_client.delete(f"upload_metadata:{form_data.form_entry_id}")

        return ApiResponse(
            success=True,
            data={"form_entry_id": str(form_entry.id)},
            message="Form entry created successfully. OCR processing started.",
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/submissions", response_model=ApiResponse[dict])
async def list_mobile_submissions(
    device_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    List form submissions for mobile app.

    Args:
        device_id: Filter by device ID (optional)
        status: Filter by status (optional)
        limit: Maximum number of results (default 50)
        offset: Offset for pagination (default 0)
        current_user: Authenticated user
        db: Database session

    Returns:
        Paginated list of form entries
    """
    try:
        from sqlalchemy import select, func, desc
        from app.models.form_entry import FormEntry

        # Base query
        query = select(FormEntry).where(FormEntry.uploaded_by == current_user.id)

        # Apply filters
        if status:
            query = query.where(FormEntry.status == status)
        if device_id:
            query = query.where(FormEntry.uploaded_by_device_id == device_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and sorting
        query = (
            query.order_by(desc(FormEntry.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(query)
        entries = result.scalars().all()

        return ApiResponse(
            success=True,
            data={
                "items": [
                    {
                        "id": str(entry.id),
                        "template_id": str(entry.template_id),
                        "template_name": None,  # Could be joined if needed
                        "image_url": entry.image_url,
                        "status": entry.status.value,
                        "confidence_score": entry.confidence_score,
                        "created_at": entry.created_at.isoformat(),
                    }
                    for entry in entries
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
