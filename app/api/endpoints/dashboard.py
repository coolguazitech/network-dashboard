"""
Dashboard API endpoints.

提供 Dashboard 所需的數據和前端配置。
"""
from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_async_session
from app.services.indicator_service import IndicatorService
from app.api.endpoints.auth import get_current_user, check_maintenance_access

router = APIRouter()  # 不要在這裡設置 prefix


@router.get("/config/frontend")
async def get_frontend_config() -> dict[str, Any]:
    """
    獲取前端配置參數。

    Returns:
        dict: 前端所需的配置參數
            - polling_interval_seconds: 前端 polling 間隔（秒）
            - checkpoint_interval_minutes: Checkpoint 快照週期（分鐘）
            - collection_interval_seconds: 後端資料採集間隔（秒）
            - mock_converge_time_seconds: Mock 收斂時間 T（秒）
    """
    return {
        "polling_interval_seconds": settings.frontend_polling_interval_seconds,
        "checkpoint_interval_minutes": settings.checkpoint_interval_minutes,
        "collection_interval_seconds": settings.collection_interval_seconds,
        "mock_converge_time_seconds": settings.mock_ping_converge_time,
        "use_mock_api": settings.use_mock_api,
    }


@router.get("/maintenance/{maintenance_id}/summary")
async def get_maintenance_summary(
    maintenance_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取維護作業的指標摘要。

    用於 Dashboard 上方的快速概覽。

    Args:
        maintenance_id: 維護作業 ID
        session: 資料庫 session

    Returns:
        dict: 包含各指標通過率和整體統計
    """
    check_maintenance_access(user, maintenance_id)
    service = IndicatorService()
    summary = await service.get_dashboard_summary(maintenance_id, session)
    return summary


@router.get("/maintenance/{maintenance_id}/indicator/{indicator_type}/details")
async def get_indicator_details(
    maintenance_id: str,
    indicator_type: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取特定指標的詳細結果。

    包含失敗清單和詳細信息。

    Args:
        maintenance_id: 維護作業 ID
        indicator_type: 指標類型 (transceiver/version/uplink)
        session: 資料庫 session

    Returns:
        dict: 指標評估結果和失敗清單
    """
    check_maintenance_access(user, maintenance_id)
    service = IndicatorService()
    results = await service.evaluate_all(maintenance_id, session)

    if indicator_type not in results:
        return {"error": f"Unknown indicator type: {indicator_type}"}

    result = results[indicator_type]

    return {
        "indicator_type": result.indicator_type,
        "phase": result.phase.value,
        "maintenance_id": result.maintenance_id,
        "total_count": result.total_count,
        "pass_count": result.pass_count,
        "fail_count": result.fail_count,
        "pass_rate": result.pass_rate_percent,
        "pass_rates": result.pass_rates,
        "summary": result.summary,
        "failures": result.failures or [],
    }


@router.get("/maintenance/{maintenance_id}/comparison")
async def get_maintenance_comparison(
    maintenance_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取維護作業的 PRE/POST 對比。
    """
    check_maintenance_access(user, maintenance_id)
    from app.services.comparison_service import ComparisonService

    service = ComparisonService()
    comparison = await service.compare_maintenance(maintenance_id, session)
    return comparison.model_dump()
