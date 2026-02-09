"""
System Logs API endpoints.

提供系統日誌查詢、統計、清理功能（ROOT 專用）。
也提供前端錯誤回報端點（所有登入用戶可用）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import get_current_user, require_root
from app.db.base import get_async_session
from app.db.models import SystemLog
from app.services.system_log import write_log

router = APIRouter(prefix="/system-logs", tags=["System Logs"])


# ── Request Models ──────────────────────────────────────────


class FrontendErrorRequest(BaseModel):
    """前端錯誤回報請求。"""

    summary: str
    detail: str | None = None
    module: str | None = None


# ── 前端錯誤回報（登入用戶可用） ──────────────────────────────


@router.post("/frontend-error")
async def report_frontend_error(
    data: FrontendErrorRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, str]:
    """
    接收前端 JS 錯誤回報。

    前端透過 errorReporter 呼叫此端點回報錯誤。
    """
    await write_log(
        level="ERROR",
        source="frontend",
        summary=data.summary,
        detail=data.detail,
        module=data.module,
        user_id=user.get("user_id"),
        username=user.get("username"),
        maintenance_id=user.get("maintenance_id"),
    )
    return {"status": "ok"}


# ── 管理員日誌查詢（ROOT 專用） ──────────────────────────────


@router.get("")
async def get_system_logs(
    user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: str | None = Query(None),
    source: str | None = Query(None),
    search: str | None = Query(None),
    maintenance_id: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
) -> dict[str, Any]:
    """
    查詢系統日誌（分頁、過濾、搜尋）。
    """
    stmt = select(SystemLog)

    # 過濾條件
    if level:
        stmt = stmt.where(SystemLog.level == level.upper())
    if source:
        stmt = stmt.where(SystemLog.source == source)
    if maintenance_id:
        stmt = stmt.where(SystemLog.maintenance_id == maintenance_id)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                SystemLog.summary.like(pattern),
                SystemLog.detail.like(pattern),
                SystemLog.module.like(pattern),
            )
        )
    if start_date:
        stmt = stmt.where(SystemLog.created_at >= start_date)
    if end_date:
        stmt = stmt.where(SystemLog.created_at <= end_date)

    # 計算總數
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # 排序 + 分頁
    stmt = stmt.order_by(SystemLog.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    logs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        "items": [
            {
                "id": log.id,
                "level": log.level,
                "source": log.source,
                "module": log.module,
                "summary": log.summary,
                "detail": log.detail,
                "user_id": log.user_id,
                "username": log.username,
                "maintenance_id": log.maintenance_id,
                "request_path": log.request_path,
                "request_method": log.request_method,
                "status_code": log.status_code,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@router.get("/stats")
async def get_system_log_stats(
    user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    統計摘要：各等級日誌數量。
    """
    stmt = (
        select(SystemLog.level, func.count().label("count"))
        .group_by(SystemLog.level)
    )
    result = await session.execute(stmt)
    level_counts = {row.level: row.count for row in result.all()}

    return {
        "error": level_counts.get("ERROR", 0),
        "warning": level_counts.get("WARNING", 0),
        "info": level_counts.get("INFO", 0),
        "total": sum(level_counts.values()),
    }


@router.delete("/cleanup")
async def cleanup_system_logs(
    user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
    retain_days: int = Query(30, ge=0, le=365),
) -> dict[str, Any]:
    """
    清理舊日誌（保留最近 N 天）。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retain_days)

    stmt = delete(SystemLog).where(SystemLog.created_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()

    deleted_count = result.rowcount

    # 記錄清理操作
    await write_log(
        level="INFO",
        source="service",
        summary=f"日誌清理: 刪除了 {deleted_count} 筆超過 {retain_days} 天的舊日誌",
        module="system_logs",
        user_id=user.get("user_id"),
        username=user.get("username"),
    )

    return {
        "deleted_count": deleted_count,
        "retain_days": retain_days,
    }
