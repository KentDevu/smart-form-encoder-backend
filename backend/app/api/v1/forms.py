from uuid import UUID
import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse
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
    WebSocket endpoint for real-time OCR progress updates.
    
    Connects to ws://host/api/v1/forms/ws/ocr/{form_id}
    
    Sends JSON messages with OCR status:
    {
        "status": "uploaded" | "processing" | "extracted" | "verified" | "archived",
        "confidence_score": float | null,
        "message": str | null
    }
    """
    await websocket.accept()
    
    try:
        from sqlalchemy import select
        from app.models.form_entry import FormEntry
        from app.database import AsyncSessionLocal
        
        # Get initial form state
        async with AsyncSessionLocal() as db:
            stmt = select(FormEntry).where(FormEntry.id == form_id)
            result = await db.execute(stmt)
            entry = result.scalar_one_or_none()
            
            if not entry:
                await websocket.send_json({
                    "error": "Form not found"
                })
                await websocket.close()
                return
        
        # Send initial status
        await websocket.send_json({
            "status": entry.status,
            "confidence_score": float(entry.confidence_score) if entry.confidence_score else None,
            "message": "Connected to OCR progress stream"
        })
        
        last_status = entry.status
        last_confidence = entry.confidence_score
        
        # Poll for updates every 2 seconds
        while True:
            await asyncio.sleep(2)
            
            async with AsyncSessionLocal() as db:
                stmt = select(FormEntry).where(FormEntry.id == form_id)
                result = await db.execute(stmt)
                entry = result.scalar_one_or_none()
                
                if not entry:
                    # Form might have been deleted
                    await websocket.send_json({
                        "status": "archived",
                        "confidence_score": None,
                        "message": "Form archived or deleted"
                    })
                    break
                
                # Only send if status changed
                if entry.status != last_status or entry.confidence_score != last_confidence:
                    await websocket.send_json({
                        "status": entry.status,
                        "confidence_score": float(entry.confidence_score) if entry.confidence_score else None,
                        "message": f"Status updated to {entry.status}"
                    })
                    last_status = entry.status
                    last_confidence = entry.confidence_score
                    
                    # Close connection when processing is complete
                    if entry.status in ["extracted", "verified", "archived"]:
                        break

        # Always close the WebSocket after the loop ends
        await websocket.close()

    except WebSocketDisconnect:
        print(f"[OCR WebSocket] Client disconnected for form {form_id}")
    except Exception as e:
        print(f"[OCR WebSocket] Error for form {form_id}: {e}")
        try:
            await websocket.send_json({
                "error": f"Server error: {str(e)}"
            })
        except:
            pass
        finally:
            try:
                await websocket.close()
            except:
                pass
