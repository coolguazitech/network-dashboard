"""
Image upload endpoint for case notes.

案件筆記圖片上傳 API — 使用 MinIO (S3-compatible) 儲存。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.endpoints.auth import get_current_user
from app.services.storage import upload_file
from app.services.system_log import write_log

router = APIRouter(prefix="/uploads", tags=["Uploads"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.post("/case-image/{maintenance_id}")
async def upload_case_image(
    maintenance_id: str,
    file: UploadFile,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, str]:
    """上傳案件筆記圖片至 MinIO。"""
    # 驗證檔案類型
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案類型: {file.content_type}",
        )

    # 讀取並驗證大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="檔案大小超過 5MB 限制")

    # 產生唯一檔名
    ext = Path(file.filename or "img").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    object_name = f"cases/{maintenance_id}/{filename}"

    # 上傳至 MinIO
    url = await upload_file(
        object_name=object_name,
        data=content,
        content_type=file.content_type or "image/jpeg",
    )

    await write_log(
        level="INFO",
        source=user.get("username", "unknown"),
        summary=f"上傳案件圖片: {filename}",
        module="uploads",
        maintenance_id=maintenance_id,
    )

    return {"url": url, "filename": filename}
