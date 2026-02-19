"""
Dashboard API endpoints.

提供 Dashboard 所需的數據和前端配置。
"""
from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_async_session
from app.db.models import CollectionError
from app.services.indicator_service import IndicatorService
from app.api.endpoints.auth import get_current_user, check_maintenance_access

router = APIRouter()  # 不要在這裡設置 prefix


@router.get("/config/frontend")
async def get_frontend_config(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """
    獲取前端配置參數。

    Returns:
        dict: 前端所需的配置參數
            - polling_interval_seconds: 前端 polling 間隔（秒）
            - checkpoint_interval_minutes: Checkpoint 快照週期（分鐘）
            - collection_interval_seconds: 後端資料採集間隔（秒）
    """
    return {
        "polling_interval_seconds": settings.frontend_polling_interval_seconds,
        "checkpoint_interval_minutes": settings.checkpoint_interval_minutes,
        "collection_interval_seconds": settings.collection_interval_seconds,
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

    # 查詢採集錯誤
    err_stmt = select(CollectionError).where(
        CollectionError.maintenance_id == maintenance_id,
        CollectionError.collection_type == indicator_type,
    )
    err_result = await session.execute(err_stmt)
    error_map: dict[str, str] = {
        err.switch_hostname: err.error_message
        for err in err_result.scalars().all()
    }

    # 合併失敗清單：有 CollectionError 的設備只顯示一行（系統異常）
    seen_error_devices: set[str] = set()
    merged_failures: list[dict] = []

    for f in (result.failures or []):
        device = f.get("device", "")
        if device in error_map:
            # 該設備有系統異常 → 合併為一行，標記為系統異常
            if device not in seen_error_devices:
                seen_error_devices.add(device)
                merged_failures.append({
                    **f,
                    "reason": f"系統異常: {error_map[device]}",
                    "is_system_error": True,
                })
        else:
            merged_failures.append(f)

    # 補上只有 CollectionError 但 indicator 未報告的設備
    for hostname, msg in error_map.items():
        if hostname not in seen_error_devices:
            merged_failures.append({
                "device": hostname,
                "interface": "N/A",
                "reason": f"系統異常: {msg}",
                "data": None,
                "is_system_error": True,
            })

    all_failures = merged_failures

    # CE 算進分母，但只補上 indicator 自己尚未計入的設備
    # （expectations-based indicator 已把無資料設備當失敗，不需重複加）
    ce_count = len(error_map)
    supplement_count = ce_count - len(seen_error_devices)
    adjusted_total = result.total_count + supplement_count
    adjusted_fail = result.fail_count + supplement_count
    adjusted_rate = (
        (result.pass_count / adjusted_total * 100)
        if adjusted_total > 0 else 0.0
    )

    return {
        "indicator_type": result.indicator_type,
        "maintenance_id": result.maintenance_id,
        "total_count": adjusted_total,
        "pass_count": result.pass_count,
        "fail_count": adjusted_fail,
        "pass_rate": adjusted_rate,
        "pass_rates": result.pass_rates,
        "summary": result.summary,
        "failures": all_failures,
        "passes": result.passes,
        "collection_errors": ce_count,
    }


