"""
Object storage service (MinIO / S3-compatible).

提供檔案上傳、取得公開 URL 等操作。
使用 miniopy-async 做非同步 I/O。
"""
from __future__ import annotations

import io
import json
import logging

from miniopy_async import Minio

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


def _get_client() -> Minio:
    """Get or create MinIO async client (singleton)."""
    global _client
    if _client is None:
        cfg = settings.minio
        _client = Minio(
            endpoint=cfg.endpoint,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            secure=cfg.secure,
            region=cfg.region or None,
        )
    return _client


async def ensure_bucket() -> None:
    """Ensure the upload bucket exists; create if missing with public-read policy."""
    client = _get_client()
    bucket = settings.minio.bucket
    if not await client.bucket_exists(bucket):
        await client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)

        # Set public-read policy so images can be viewed by browsers
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                },
            ],
        }
        await client.set_bucket_policy(bucket, json.dumps(policy))
        logger.info("Set public-read policy on bucket: %s", bucket)


async def upload_file(
    object_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Upload bytes to MinIO.

    Args:
        object_name: Object key (e.g., "cases/mid123/abc.jpg")
        data: File content bytes
        content_type: MIME type

    Returns:
        Public URL string for the uploaded object.
    """
    client = _get_client()
    bucket = settings.minio.bucket

    await client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )

    logger.debug("Uploaded %s (%d bytes)", object_name, len(data))
    return get_public_url(object_name)



async def get_object(object_name: str) -> tuple[bytes, str]:
    """
    Download an object from MinIO.

    Returns:
        (data_bytes, content_type)
    """
    client = _get_client()
    bucket = settings.minio.bucket
    response = await client.get_object(bucket, object_name)
    try:
        data = await response.read()
    finally:
        response.close()
        await response.release()
    ct = response.headers.get("Content-Type", "application/octet-stream")
    return data, ct


def get_public_url(object_name: str) -> str:
    """
    Build the proxy URL that goes through the app (port 8000).

    Returns a relative path so it works regardless of host/port.
    """
    return f"/api/v1/uploads/files/{object_name}"
