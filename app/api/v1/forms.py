from uuid import UUID
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse

logger = logging.getLogger(__name__)

from app.schemas.form import (
    FormEntryListResponse,
    FormEntryResponse,
    FormTemplateResponse,
    FormVerifyRequest,
)
from app.services.form_service import FormService
from app.services.storage_service import upload_file_to_r2

router = APIRouter(prefix="/forms", tags=["Forms"])


@router.get("/templates", response_model=ApiResponse[list[FormTemplateResponse]])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[FormTemplateResponse]]:
    """List all active form templates."""
    service = FormService(db)
    templates = await service.list_templates()

    return ApiResponse(
        success=True,
        data=[FormTemplateResponse.model_validate(t) for t in templates],
    )


@router.post("/templates/generate", response_model=ApiResponse[dict])
async def generate_template(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
) -> ApiResponse[dict]:
    """
    Upload a sample form image and have AI analyze it to generate
    a FormLayoutSchema JSON. Returns the schema for preview/editing
    before the admin saves it as a template.
    """
    from app.services.template_generator import generate_template_from_image

    allowed = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
    if file.content_type not in allowed:
        return ApiResponse(
            success=False,
            data=None,
            message="File must be PNG, JPEG, or PDF",
        )

    image_bytes = await file.read()
    schema = generate_template_from_image(image_bytes)

    return ApiResponse(success=True, data=schema)


@router.post("/templates", response_model=ApiResponse[FormTemplateResponse])
async def create_template(
    name: str = Form(...),
    description: str = Form(""),
    field_schema: str = Form(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FormTemplateResponse]:
    """Create a new form template. field_schema should be a JSON string."""
    import json
    try:
        schema_dict = json.loads(field_schema)
    except json.JSONDecodeError:
        return ApiResponse(
            success=False,
            data=None,
            message="field_schema must be valid JSON",
        )

    service = FormService(db)
    template = await service.create_template(
        name=name,
        description=description or None,
        field_schema=schema_dict,
    )

    return ApiResponse(
        success=True,
        data=FormTemplateResponse.model_validate(template),
        message=f"Template '{name}' created successfully",
    )


@router.get("/templates/{template_id}", response_model=ApiResponse[FormTemplateResponse])
async def get_template(
    template_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FormTemplateResponse]:
    """Get a form template by ID."""
    service = FormService(db)
    template = await service.get_template(template_id)

    return ApiResponse(
        success=True,
        data=FormTemplateResponse.model_validate(template),
    )


@router.get("", response_model=ApiResponse[PaginatedResponse[FormEntryListResponse]])
async def list_forms(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    template_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PaginatedResponse[FormEntryListResponse]]:
    """List form entries with pagination and filtering."""
    service = FormService(db)
    result = await service.list_entries(
        current_user=current_user,
        page=page,
        per_page=per_page,
        status=status,
        template_id=template_id,
    )

    return ApiResponse(
        success=True,
        data=PaginatedResponse(
            items=[FormEntryListResponse.model_validate(e) for e in result["items"]],
            total=result["total"],
            page=result["page"],
            per_page=result["per_page"],
            total_pages=result["total_pages"],
        ),
    )


@router.post("/upload", response_model=ApiResponse[FormEntryResponse])
async def upload_form(
    template_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FormEntryResponse]:
    """Upload a scanned form image, store in R2, create entry, and trigger OCR."""
    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/tiff", "application/pdf"}
    if file.content_type not in allowed_types:
        from app.core.exceptions import BadRequestException
        raise BadRequestException(f"File type '{file.content_type}' not allowed. Use JPEG, PNG, WebP, TIFF, or PDF.")

    # Read file content
    file_content = await file.read()

    # Upload to R2
    object_key = upload_file_to_r2(
        file_content=file_content,
        filename=file.filename or "form.jpg",
        content_type=file.content_type or "image/jpeg",
    )

    # Create form entry
    service = FormService(db)
    entry = await service.create_entry(
        template_id=template_id,
        image_url=object_key,
        uploaded_by=current_user.id,
    )

    # Trigger OCR processing asynchronously
    from app.services.ocr_task import process_ocr_task
    process_ocr_task.delay(str(entry.id))

    return ApiResponse(
        success=True,
        data=FormEntryResponse.model_validate(entry),
        message="Form uploaded successfully. OCR processing started.",
    )


@router.get("/{form_id}", response_model=ApiResponse[FormEntryResponse])
async def get_form(
    form_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FormEntryResponse]:
    """Get a form entry by ID with its OCR results."""
    service = FormService(db)
    entry = await service.get_entry(form_id, current_user)

    return ApiResponse(
        success=True,
        data=FormEntryResponse.model_validate(entry),
    )


@router.get("/{form_id}/image-url")
async def get_form_image_url(
    form_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Get a presigned URL for viewing the form image."""
    from app.services.storage_service import get_presigned_url

    service = FormService(db)
    entry = await service.get_entry(form_id, current_user)

    presigned_url = get_presigned_url(entry.image_url, expires_in=3600)

    return ApiResponse(
        success=True,
        data={"image_url": presigned_url},
    )


@router.put("/{form_id}/verify", response_model=ApiResponse[FormEntryResponse])
async def verify_form(
    form_id: UUID,
    body: FormVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FormEntryResponse]:
    """Submit verified/corrected field data for a form entry."""
    service = FormService(db)
    entry = await service.verify_entry(form_id, body.fields, current_user)

    return ApiResponse(
        success=True,
        data=FormEntryResponse.model_validate(entry),
        message="Form verified successfully",
    )


@router.post("/{form_id}/retry", response_model=ApiResponse[FormEntryResponse])
async def retry_ocr(
    form_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FormEntryResponse]:
    """Retry OCR processing for a form that is stuck in processing state."""
    from app.models.form_entry import FormEntry, FormEntryStatus
    from app.models.form_field import FormField
    from sqlalchemy import update, delete, select

    # Load entry WITHOUT eager loading fields to avoid memory spike
    # (fields can number in the hundreds after OCR)
    result = await db.execute(
        select(FormEntry).where(FormEntry.id == form_id).with_only_columns(FormEntry)
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("Form entry not found")

    # Access control: encoders can only retry their own entries
    if current_user.role.value == "encoder" and entry.uploaded_by != current_user.id:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException("You can only retry your own form entries")

    # Only allow retry for uploaded or processing status
    if entry.status not in [FormEntryStatus.UPLOADED, FormEntryStatus.PROCESSING]:
        return ApiResponse(
            success=False,
            data=None,
            message=f"Cannot retry form in '{entry.status}' status. Form must be in 'uploaded' or 'processing' state.",
        )

    # Save entry data BEFORE commit (avoids lazy-loading after commit)
    entry_id = entry.id
    template_id = entry.template_id
    uploaded_by = entry.uploaded_by
    uploaded_by_device_id = entry.uploaded_by_device_id
    verified_by = entry.verified_by
    image_url = entry.image_url
    created_at = entry.created_at

    # Clear existing data and reset status in single transaction
    # Delete existing fields (batch delete is efficient)
    await db.execute(
        delete(FormField).where(FormField.entry_id == form_id)
    )

    # Reset entry status with direct update (no refresh needed)
    await db.execute(
        update(FormEntry).where(FormEntry.id == form_id).values(
            status=FormEntryStatus.UPLOADED,
            raw_ocr_data=None,
            verified_data=None,
            confidence_score=None,
            processing_time=None,
        )
    )
    await db.commit()

    # Build response using saved values (no lazy-loading from entry object)
    response_data = FormEntryResponse.model_construct(
        id=entry_id,
        template_id=template_id,
        uploaded_by=uploaded_by,
        uploaded_by_device_id=uploaded_by_device_id,
        verified_by=verified_by,
        image_url=image_url,
        status="uploaded",  # Reset value
        raw_ocr_data=None,  # Reset value
        verified_data=None,  # Reset value
        confidence_score=None,  # Reset value
        processing_time=None,  # Reset value
        created_at=created_at,
        updated_at=None,  # Will be set on DB, but we reflect the reset
        fields=[],  # Empty since we just deleted them
    )

    # Trigger OCR processing asynchronously
    from app.services.ocr_task import process_ocr_task
    process_ocr_task.delay(str(form_id))

    return ApiResponse(
        success=True,
        data=response_data,
        message="OCR processing restarted.",
    )


@router.delete("/{form_id}", response_model=ApiResponse[None])
async def delete_form(
    form_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """Delete a form entry (admin only)."""
    service = FormService(db)
    await service.delete_entry(form_id)

    return ApiResponse(
        success=True,
        message="Form entry deleted successfully",
    )


@router.websocket("/ws/ocr/{form_id}")
async def websocket_ocr_progress(
    websocket: WebSocket,
    form_id: UUID,
):
    """
    WebSocket endpoint for real-time OCR progress updates using Redis pub/sub.

    Connects to ws://host/api/v1/forms/ws/ocr/{form_id}

    Sends JSON messages with OCR status:
    {
        "status": "uploaded" | "processing" | "extracted" | "verified" | "archived",
        "confidence_score": float | null,
        "message": str | null
    }

    Memory-efficient: Uses Redis pub/sub instead of database polling.
    """
    from app.services.websocket_manager import manager
    from sqlalchemy import select
    from app.models.form_entry import FormEntry
    from app.database import async_session_factory

    form_id_str = str(form_id)

    try:
        try:
            # Connect using the WebSocket manager
            await manager.connect(websocket, form_id_str)

            # Get and send initial form state
            async with async_session_factory() as db:
                stmt = select(FormEntry).where(FormEntry.id == form_id)
                result = await db.execute(stmt)
                entry = result.scalar_one_or_none()

                if not entry:
                    await websocket.send_json({
                        "status": "archived",
                        "error": "Form not found"
                    })
                    return

                # Send initial status
                await websocket.send_json({
                    "status": entry.status,
                    "confidence_score": float(entry.confidence_score) if entry.confidence_score else None,
                    "message": f"OCR status: {entry.status}"
                })

                # Connection stays open even if already "extracted" - manager will deliver any subsequent
                # Redis pub/sub messages or status updates (e.g., verification, archival)

        except Exception as e:
            logger.error(f"[OCR WebSocket] Error setting up connection for {form_id}: {e}")
            try:
                await websocket.close()
            except Exception:
                pass
            return

        try:
            # Keep connection alive and send/receive messages
            # WebSocket manager handles actual message delivery via Redis pub/sub
            while True:
                try:
                    # Wait for client messages with timeout (30 seconds)
                    # This allows us to send heartbeats to detect dead connections
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                    # Client can send "ping" to keep connection alive
                    if data == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive and detect network issues
                    await websocket.send_json({"type": "heartbeat"})
                    continue

        except WebSocketDisconnect:
            logger.info(f"[OCR WebSocket] Client disconnected for form {form_id}")
        except Exception as e:
            logger.error(f"[OCR WebSocket] Error for form {form_id}: {e}")

    finally:
        await manager.disconnect(websocket, form_id_str)
