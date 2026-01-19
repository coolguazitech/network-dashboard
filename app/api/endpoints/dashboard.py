"""
Dashboard API endpoints.

提供 Dashboard 所需的數據。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.services.indicator_service import IndicatorService

router = APIRouter()  # 不要在這裡設置 prefix


@router.get("/maintenance/{maintenance_id}/summary")
async def get_maintenance_summary(
    maintenance_id: str,
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
    service = IndicatorService()
    summary = await service.get_dashboard_summary(maintenance_id, session)
    return summary


@router.get("/maintenance/{maintenance_id}/indicator/{indicator_type}/details")
async def get_indicator_details(
    maintenance_id: str,
    indicator_type: str,
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
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取維護作業的 PRE/POST 對比。
    """
    from app.services.comparison_service import ComparisonService
    
    service = ComparisonService()
    comparison = await service.compare_maintenance(maintenance_id, session)
    return comparison.model_dump()
