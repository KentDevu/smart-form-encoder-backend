"""Cloudflare R2 storage service — handles file uploads and pre-signed URLs."""

import uuid
from datetime import datetime

import boto3
from botocore.config import Config

from app.config import get_settings

settings = get_settings()


def _get_r2_client():
    """Create a boto3 S3 client configured for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_file_to_r2(
    file_content: bytes,
    filename: str,
    content_type: str,
    form_entry_id: str | None = None,
) -> str:
    """
    Upload a file to Cloudflare R2 and return the object key.

    Path format: forms/{year}/{month}/{entry_id}/{filename}
    """
    now = datetime.utcnow()
    entry_id = form_entry_id or str(uuid.uuid4())

    # Sanitize filename
    safe_name = filename.replace(" ", "_").replace("/", "_")
    object_key = f"forms/{now.year}/{now.month:02d}/{entry_id}/{safe_name}"

    client = _get_r2_client()
    client.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=object_key,
        Body=file_content,
        ContentType=content_type,
    )

    return object_key


def get_presigned_url(object_key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed URL for reading an object from R2."""
    client = _get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": object_key,
        },
        ExpiresIn=expires_in,
    )


def generate_presigned_url(object_key: str, method: str = "put", expiration: int = 900) -> str:
    """Generate a pre-signed URL for uploading or reading an object from R2."""
    client = _get_r2_client()
    action = "put_object" if method.lower() == "put" else "get_object"
    return client.generate_presigned_url(
        action,
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": object_key,
        },
        ExpiresIn=expiration,
    )


def delete_file_from_r2(object_key: str) -> None:
    """Delete a file from R2."""
    client = _get_r2_client()
    client.delete_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=object_key,
    )
