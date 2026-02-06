"""
Sanity Check Report API endpoints.

Sanity Check 報告匯出功能的 API 端點。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.services.indicator_service import IndicatorService
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/maintenance/{maintenance_id}/preview")
async def preview_report(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    預覽 Sanity Check 報告內容。

    返回 JSON 格式的完整報告數據，供前端預覽或自行處理。
    """
    service = IndicatorService()
    summary = await service.get_dashboard_summary(maintenance_id, session)

    # 獲取所有指標的詳細失敗清單
    results = await service.evaluate_all(maintenance_id, session)

    indicator_details = {}
    for indicator_type, result in results.items():
        indicator_details[indicator_type] = {
            "indicator_type": result.indicator_type,
            "total_count": result.total_count,
            "pass_count": result.pass_count,
            "fail_count": result.fail_count,
            "pass_rate": result.pass_rate_percent,
            "failures": result.failures or [],
        }

    # 使用台灣時區 (UTC+8)
    tw_tz = timezone(timedelta(hours=8))

    return {
        "maintenance_id": maintenance_id,
        "generated_at": datetime.now(tw_tz).isoformat(),
        "summary": summary,
        "indicators": indicator_details,
    }


@router.get("/maintenance/{maintenance_id}/export", response_class=HTMLResponse)
async def export_report_html(
    maintenance_id: str,
    include_details: bool = True,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    """
    匯出 Sanity Check 報告為 HTML 格式。

    返回可下載的完整 HTML 報告文件。
    """
    report_service = ReportService()
    html_content = await report_service.generate_html_report(
        maintenance_id=maintenance_id,
        include_details=include_details,
        session=session,
    )

    # 使用台灣時區 (UTC+8)
    tw_tz = timezone(timedelta(hours=8))
    filename = (
        f"sanity_report_{maintenance_id}_"
        f"{datetime.now(tw_tz).strftime('%Y%m%d_%H%M%S')}.html"
    )

    return HTMLResponse(
        content=html_content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/html; charset=utf-8",
        },
    )
